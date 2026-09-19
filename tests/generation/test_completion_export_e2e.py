"""End-to-end: a synthetic intake through the whole pipeline, twice, byte for byte."""
import json
from hashlib import sha256
from pathlib import Path

import pytest
from grid_case_generator.analysis.completion_export import run_export, verify_export
from grid_case_generator.io.derived_delivery_artifacts import ARCHIVE_NAME
from grid_case_generator.models.completion_export import CompletionPolicy, policy_bytes

import completion_fixture as cf
from completion_fixture import DeliveryFixture  # noqa: F401  (pytest fixture type)


def run_from_intake(intake, out):
    """Run one export against a pre-built intake; the subprocess determinism entry point.

    The intake is rebuilt rather than passed as an object, which is safe only because
    `cf.build` is byte-deterministic — and that is itself part of what this checks.
    """
    intake, out = Path(intake), Path(out)
    fixture = cf.build(intake)
    fixture.roots = cf.export_roots(fixture)
    policy_path = intake / 'policy.json'
    policy_path.write_bytes(policy_bytes(fixture.policy))
    return run_export(fixture.roots, policy_path, out.with_name(out.name + '-ledger'), out)


@pytest.fixture
def e2e(tmp_path):
    root = cf.build(tmp_path)
    root.roots = cf.export_roots(root)
    root.policy_path = tmp_path / 'policy.json'
    root.policy_path.write_bytes(policy_bytes(root.policy))
    return root


def snapshot(path):
    return {str(p.relative_to(path)): sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(path).rglob('*')) if p.is_file()}


def run(e2e, name, *, verify=False):
    return run_export(e2e.roots, e2e.policy_path, e2e.tmp_path / f'{name}-ledger',
                      e2e.tmp_path / name, verify=verify)


def test_the_whole_pipeline_produces_a_verifiable_delivery(e2e):
    result = run(e2e, 'out')
    assert result['verified'] is True
    root = e2e.tmp_path / 'out'
    for name in ('manifest.json', 'report.md', 'nanjing-derived-v1.zip'):
        assert (root / name).is_file(), name
    for name in ('row_provenance.jsonl', 'completion_records.jsonl',
                 'unresolved_records.jsonl'):
        assert (root / 'provenance' / name).is_file(), name
    assert (e2e.tmp_path / 'out-verification.json').is_file()
    assert (e2e.tmp_path / 'out-ledger' / 'manifest.json').is_file()


def test_the_delivery_carries_appended_rows(e2e):
    run(e2e, 'out')
    rows = [json.loads(line) for line in
            (e2e.tmp_path / 'out' / 'provenance' / 'row_provenance.jsonl')
            .read_bytes().splitlines()]
    appended = [r for r in rows if r['row_kind'] == 'APPENDED']
    assert appended
    assert {r['rule_id'] for r in appended} <= {
        'CROSS_CASE_REFERENCE_COPY_V1', 'PLACEMENT_MISSING_ENDPOINT_BUS_V1'}
    assert all(r['completion_status'] == 'PROPOSED' for r in appended)
    assert all(r['evidence_refs'] for r in appended)


def test_two_runs_are_byte_identical(e2e):
    run(e2e, 'a')
    run(e2e, 'b')
    assert snapshot(e2e.tmp_path / 'a') == snapshot(e2e.tmp_path / 'b')
    sidecar_a = json.loads((e2e.tmp_path / 'a-verification.json').read_text())
    sidecar_b = json.loads((e2e.tmp_path / 'b-verification.json').read_text())
    for key in ('manifest_sha256', 'provenance_sha256', 'archive_sha256'):
        assert sidecar_a[key] == sidecar_b[key], key
    assert sidecar_a['archive_sha256'] == sha256(
        (e2e.tmp_path / 'a' / ARCHIVE_NAME).read_bytes()).hexdigest()


def test_the_run_leaves_every_input_byte_unchanged(e2e):
    before = {key: snapshot(path) for key, path in e2e.roots.items()}
    archive_before = e2e.archive.read_bytes()
    run(e2e, 'out')
    assert {key: snapshot(path) for key, path in e2e.roots.items()} == before
    assert e2e.archive.read_bytes() == archive_before


def test_no_row_is_approved_or_applied(e2e):
    run(e2e, 'out')
    ledger = e2e.tmp_path / 'out-ledger'
    for name in ('completion_records.jsonl', 'unresolved_records.jsonl'):
        for line in (ledger / name).read_bytes().splitlines():
            record = json.loads(line)
            assert 'approved' not in record and 'applied' not in record
    manifest = json.loads((ledger / 'manifest.json').read_text())
    assert manifest['approved'] is False and manifest['applied'] is False
    assert manifest['canonical_changed'] is False
    assert manifest['accepted_v2_changed'] is False
    assert manifest['source_changed'] is False


def test_verify_then_analyze_round_trips(e2e):
    run(e2e, 'out')
    result = verify_export(e2e.roots, e2e.policy_path, e2e.tmp_path / 'out-ledger',
                           e2e.tmp_path / 'out')
    assert result['verified'] is True
    assert result['reasons'] == []
    assert result['structural_status'] == 'PASS'


def test_a_policy_change_moves_the_rows_and_the_hashes(e2e):
    strict = run(e2e, 'strict')
    e2e.policy = CompletionPolicy(
        policy_version='1.1.0', materialize_tiers=('SAME_STATION', 'CROSS_STATION'),
        enabled_rules=e2e.policy.enabled_rules, max_reference_closure_depth=2,
        placement_endpoint_bus=True)
    e2e.policy_path.write_bytes(policy_bytes(e2e.policy))
    loose = run(e2e, 'loose')
    assert strict['policy_sha256'] != loose['policy_sha256']
    assert strict['manifest_sha256'] != loose['manifest_sha256']
    # The source rows are not a policy artefact: only the completion rows may move.
    strict_rows = (e2e.tmp_path / 'strict' / 'data' / e2e.referring_key
                   / '01_Station.csv').read_bytes()
    loose_rows = (e2e.tmp_path / 'loose' / 'data' / e2e.referring_key
                  / '01_Station.csv').read_bytes()
    assert strict_rows == loose_rows


def test_an_export_refuses_to_overwrite_itself(e2e):
    run(e2e, 'out')
    with pytest.raises((FileExistsError, ValueError)):
        run_export(e2e.roots, e2e.policy_path, e2e.tmp_path / 'out-ledger',
                   e2e.tmp_path / 'out')


def test_the_sidecar_records_the_protected_inputs_and_the_archive(e2e):
    run(e2e, 'out')
    sidecar = json.loads((e2e.tmp_path / 'out-verification.json').read_text())
    assert sidecar['bound_verifier'] == 'PASS'
    assert sidecar['changed_protected_files'] == []
    assert sidecar['archive_name'] == ARCHIVE_NAME
    assert sidecar['archive_entries'] > 0
    assert sidecar['measured']['appended_rows'] > 0
    assert set(sidecar['protected_inputs_sha256']) == set(e2e.roots)
    assert sidecar['policy_sha256'] == json.loads(
        (e2e.tmp_path / 'out-ledger' / 'manifest.json').read_text())['policy_sha256']


def test_the_archive_is_byte_identical_across_hash_seeds(tmp_path):
    """An in-process repeat cannot see hash-seed dependence; a separate process can."""
    import os
    import subprocess
    import sys
    intake = tmp_path / 'intake'
    cf.build(intake)                       # one intake, shared by every seed
    script = (
        "import sys; sys.path.insert(0, %r)\n"
        "from pathlib import Path\n"
        "from test_completion_export_e2e import run_from_intake\n"
        "run_from_intake(Path(sys.argv[1]), Path(sys.argv[2]))\n"
    ) % str(Path(__file__).parent)
    digests = {}
    for name, seed in (('s1', '1'), ('s999', '999'), ('s1b', '1')):
        out = tmp_path / name
        env = dict(os.environ, PYTHONHASHSEED=seed)
        subprocess.run([sys.executable, '-c', script, str(intake), str(out)],
                       env=env, check=True, capture_output=True)
        sidecar = json.loads((out.with_name(out.name + '-verification.json')).read_text())
        digests[name] = (sidecar['archive_sha256'], sidecar['manifest_sha256'],
                         sidecar['provenance_sha256'])
    assert digests['s1'] == digests['s999'] == digests['s1b']
    assert (tmp_path / 's1' / ARCHIVE_NAME).read_bytes() == \
        (tmp_path / 's999' / ARCHIVE_NAME).read_bytes()


def test_re_verifying_does_not_rewrite_the_archive(e2e):
    """The archive is the external anchor; a re-verify must not replace it."""
    from grid_case_generator.analysis.completion_export import run_export
    run(e2e, 'out')
    archive = e2e.tmp_path / 'out' / ARCHIVE_NAME
    before = archive.read_bytes()
    sidecar_before = json.loads((e2e.tmp_path / 'out-verification.json').read_text())
    result = run_export(e2e.roots, e2e.policy_path, e2e.tmp_path / 'out-ledger',
                        e2e.tmp_path / 'out', verify=True)
    assert result['verified'] is True
    assert archive.read_bytes() == before, 'the archive must not be rebuilt'
    assert json.loads((e2e.tmp_path / 'out-verification.json').read_text())[
        'archive_sha256'] == sidecar_before['archive_sha256']
    with __import__('zipfile').ZipFile(archive) as z:
        assert not any(n.endswith(ARCHIVE_NAME) for n in z.namelist())


def test_building_the_archive_twice_is_idempotent(e2e):
    from grid_case_generator.io.derived_delivery_artifacts import build_archive
    run(e2e, 'out')
    root = e2e.tmp_path / 'out'
    first = build_archive(root)
    second = build_archive(root)
    assert first == second, 'a second build must not embed the archive inside itself'
