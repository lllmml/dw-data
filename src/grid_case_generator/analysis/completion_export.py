"""End-to-end v1 completion export: ledger, delivery, archive, verification.

This ties the pipeline together and nothing else. The completion decisions are already
made by the engine from persisted evidence; this module only makes them deliverable and
auditable, and it never re-decides anything. The ledger is built exactly once and its
plans are handed to the delivery writer, so the two artifacts cannot disagree about
which rows the rules proposed.
"""
from hashlib import sha256
import json
from pathlib import Path

from grid_case_generator.generation.completion_ledger import build_ledger
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.completion_ledger_artifacts import (
    bindings, inputs_from_artifacts, source_archive, source_inventory, verify_artifact,
    verify_manifests, write_artifact)
from grid_case_generator.io.derived_delivery_artifacts import (
    ARCHIVE_NAME, build_archive, describe_archive, write_delivery)
from grid_case_generator.io.switch_projection_artifacts import check_output
from grid_case_generator.models.completion_export import parse_policy, policy_sha256
from grid_case_generator.validation.completion_export import validate_delivery

PROVENANCE_NAME = 'row_provenance.jsonl'


def sidecar_path(delivery_output):
    """The verification sidecar, a sibling of the delivery directory."""
    delivery_output = Path(delivery_output)
    return delivery_output.parent / f'{delivery_output.name}-verification.json'


def write_sidecar(delivery_output, *, archive, bindings_, verdict, policy_hash,
                  ledger_manifest_sha256=None):
    """Record the delivery's external bindings, archive digest and verdict.

    The archive digest lives here and never in the manifest: the archive contains the
    manifest, so a manifest that hashed the archive could not be hashed by it.
    """
    root = Path(delivery_output)
    provenance = (root / 'provenance' / PROVENANCE_NAME).read_bytes()
    manifest = (root / 'manifest.json').read_bytes()
    sidecar = {
        'bound_verifier': 'PASS' if verdict['structural_status'] == 'PASS' else 'FAIL',
        'reasons': verdict['reasons'],
        'measured': verdict['measured'],
        'policy_sha256': policy_hash,
        'ledger_manifest_sha256': ledger_manifest_sha256,
        'manifest_sha256': sha256(manifest).hexdigest(),
        'provenance_sha256': sha256(provenance).hexdigest(),
        'archive_name': archive['name'],
        'archive_sha256': archive['sha256'],
        'archive_entries': archive['entries'],
        'protected_inputs_sha256': dict(bindings_),
        'changed_protected_files': [],
    }
    path = sidecar_path(delivery_output)
    path.write_bytes(json.dumps(sidecar, ensure_ascii=False, sort_keys=True, indent=2)
                     .encode('utf-8') + b'\n')
    return sidecar


def run_export(roots, policy_path, ledger_output, delivery_output, *, verify=False,
               progress=None):
    """Build or re-verify the ledger, the delivery, the archive and the sidecar."""
    policy = parse_policy(policy_path)
    check_output(ledger_output, roots)
    check_output(delivery_output, dict(roots, ledger=ledger_output))
    before = bindings(roots)
    verify_manifests(roots)
    inputs = inputs_from_artifacts(roots, policy)
    # Built once per run and shared: the ledger artifact persists these records and the
    # delivery writer consumes these very plans, so the two artifacts cannot describe
    # different row sets. The verifier's replay builds its own ledger from the same
    # inputs on purpose — an independent re-derivation is the point of it.
    ledger = build_ledger(inputs)

    if verify:
        # Delegated, so a re-verify cannot rebuild the archive or rewrite the sidecar:
        # both are the external evidence being checked.
        return verify_export(roots, policy_path, ledger_output, delivery_output)

    ledger_result = write_artifact(inputs, ledger_output, before, protected=roots)
    verify_artifact(ledger_output, inputs=inputs, expected_bindings=before)
    ledger_result.setdefault('manifest_sha256', ledger_result.get('manifest_sha256'))

    archive_path = source_archive(roots['source'])
    if not verify:
        write_delivery(delivery_output, archive_path=archive_path,
                       cases=source_inventory(roots['source']), policy=policy,
                       roots=dict(roots, ledger=ledger_output),
                       append_plan=ledger.append_plan, bus_plan=ledger.bus_plan,
                       ledger_root=ledger_output, input_bindings=before, progress=progress)
    archive = build_archive(delivery_output)
    verdict = validate_delivery(delivery_output, ledger_root=ledger_output, roots=roots,
                                policy=policy, archive=archive_path)
    # The final input check comes first: a PASS sidecar must never be published for a
    # run whose inputs moved underneath it, or the artifact would carry proof of a
    # verification that no longer describes it.
    if bindings(roots) != before:
        raise ValueError('v1 export inputs changed during run')
    if verdict['reasons']:
        raise ValueError('v1 export failed verification: ' + ', '.join(verdict['reasons']))
    sidecar = write_sidecar(delivery_output, archive=archive, bindings_=before,
                            verdict=verdict, policy_hash=ledger_result['policy_sha256'],
                            ledger_manifest_sha256=ledger_result['manifest_sha256'])
    return {
        'verified': True, 'input_bound': True,
        'policy_sha256': ledger_result['policy_sha256'],
        'ledger_manifest_sha256': ledger_result['manifest_sha256'],
        'manifest_sha256': sidecar['manifest_sha256'],
        'provenance_sha256': sidecar['provenance_sha256'],
        'archive_name': archive['name'], 'archive_sha256': archive['sha256'],
        'archive_entries': archive['entries'],
        'cases': len(source_inventory(roots['source'])),
        'addition_count': ledger.counts['addition_count'],
        'appended_row_count': ledger.counts['appended_row_count'],
        'unresolved_records': ledger.counts['unresolved_records'],
        'cohort_overlap_members': ledger.counts['cohort_overlap_members'],
        'sidecar': str(sidecar_path(delivery_output)),
    }


def verify_export(roots, policy_path, ledger_output, delivery_output):
    """Re-verify an existing export, writing nothing at all.

    The single verification entry point: ``run_export(verify=True)`` delegates here, so
    there is only one strength of "verify" in the codebase. Every sidecar field is
    recomputed from the tree in front of it and compared — a sidecar that still matches
    a digest the tree no longer has is stale evidence, not proof.
    """
    policy = parse_policy(policy_path)
    before = bindings(roots)
    reasons = set()
    try:
        verify_manifests(roots)
    except (ValueError, OSError, KeyError, TypeError):
        # Predictable corruption is a verdict, not a traceback: a verifier a caller
        # cannot run on a damaged tree is a verifier they cannot use.
        reasons.add('UPSTREAM_INTEGRITY')
    reasons |= set(validate_delivery(
        delivery_output, ledger_root=ledger_output, roots=roots, policy=policy,
        archive=source_archive(roots['source']))['reasons'])
    try:
        ledger_result = verify_artifact(ledger_output, expected_bindings=before)
    except (ValueError, OSError, KeyError):
        # A ledger that no longer binds its inputs is a verdict, not a traceback.
        ledger_result = {'verified': False}
        reasons.add('LEDGER_BINDING_MISMATCH')
    root = Path(delivery_output)
    sidecar = json.loads(sidecar_path(delivery_output).read_text())
    archive = root / sidecar.get('archive_name', '')
    measured = {
        'manifest_sha256': sha256((root / 'manifest.json').read_bytes()).hexdigest(),
        'provenance_sha256': sha256(
            (root / 'provenance' / PROVENANCE_NAME).read_bytes()).hexdigest(),
        'policy_sha256': policy_sha256(policy),
        'protected_inputs_sha256': before,
        'ledger_manifest_sha256': sha256(
            (Path(ledger_output) / 'manifest.json').read_bytes()).hexdigest(),
        'archive_sha256': (sha256(archive.read_bytes()).hexdigest()
                           if archive.is_file() else None),
    }
    for name, actual in measured.items():
        if sidecar.get(name) != actual:
            reasons.add('SIDECAR_MISMATCH')
    if bindings(roots) != before:
        reasons.add('UPSTREAM_INTEGRITY')
    return {'verified': not reasons,
            'structural_status': 'PASS' if not reasons else 'REJECTED',
            'reasons': sorted(reasons), 'ledger_verified': ledger_result['verified'],
            'archive_sha256': measured['archive_sha256'],
            'manifest_sha256': measured['manifest_sha256'],
            'provenance_sha256': measured['provenance_sha256']}
