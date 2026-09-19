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
from grid_case_generator.models.completion_export import parse_policy
from grid_case_generator.validation.completion_export import validate_delivery

PROVENANCE_NAME = 'row_provenance.jsonl'


def sidecar_path(delivery_output):
    """The verification sidecar, a sibling of the delivery directory."""
    delivery_output = Path(delivery_output)
    return delivery_output.parent / f'{delivery_output.name}-verification.json'


def write_sidecar(delivery_output, *, archive, bindings_, verdict, policy_hash):
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
    # Built once: the ledger artifact persists these records and the delivery writer
    # consumes these very plans, so the two can never describe different row sets.
    ledger = build_ledger(inputs)

    if verify:
        ledger_result = verify_artifact(ledger_output, inputs=inputs, expected_bindings=before)
    else:
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
    # Re-verifying must not rebuild: the archive is the delivery's external anchor and
    # rewriting it would replace the very bytes being attested to.
    archive = (describe_archive(delivery_output) if verify
               else build_archive(delivery_output))
    verdict = validate_delivery(delivery_output, ledger_root=ledger_output, roots=roots,
                                policy=policy, archive=archive_path)
    sidecar = write_sidecar(delivery_output, archive=archive, bindings_=before,
                            verdict=verdict, policy_hash=ledger_result['policy_sha256'])
    if bindings(roots) != before:
        raise ValueError('v1 export inputs changed during run')
    if verdict['reasons']:
        raise ValueError('v1 export failed verification: ' + ', '.join(verdict['reasons']))
    return {
        'verified': True, 'input_bound': True,
        'policy_sha256': ledger_result['policy_sha256'],
        'ledger_manifest_sha256': ledger_result['manifest_sha256'],
        'manifest_sha256': sidecar['manifest_sha256'],
        'provenance_sha256': sidecar['provenance_sha256'],
        'archive_name': archive['name'], 'archive_sha256': archive['sha256'],
        'archive_entries': archive['entries'],
        'cases': ledger.counts['completion_records'],
        'addition_count': ledger.counts['addition_count'],
        'appended_row_count': ledger.counts['appended_row_count'],
        'unresolved_records': ledger.counts['unresolved_records'],
        'cohort_overlap_members': ledger.counts['cohort_overlap_members'],
        'sidecar': str(sidecar_path(delivery_output)),
    }


def verify_export(roots, policy_path, ledger_output, delivery_output):
    """Re-verify an existing export without writing anything."""
    policy = parse_policy(policy_path)
    before = bindings(roots)
    verdict = validate_delivery(delivery_output, ledger_root=ledger_output, roots=roots,
                                policy=policy, archive=source_archive(roots['source']))
    ledger_result = verify_artifact(ledger_output, expected_bindings=before)
    sidecar = json.loads(sidecar_path(delivery_output).read_text())
    archive = Path(delivery_output) / sidecar['archive_name']
    if not archive.is_file() or sha256(archive.read_bytes()).hexdigest() != sidecar['archive_sha256']:
        raise ValueError('v1 export archive does not match its sidecar')
    return {'verified': not verdict['reasons'], 'structural_status': verdict['structural_status'],
            'reasons': verdict['reasons'], 'ledger_verified': ledger_result['verified'],
            'archive_sha256': sidecar['archive_sha256'],
            'manifest_sha256': sidecar['manifest_sha256'],
            'provenance_sha256': sidecar['provenance_sha256']}
