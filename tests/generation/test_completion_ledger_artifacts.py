import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from grid_case_generator.generation.completion_ledger import build_ledger
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.completion_ledger_artifacts import (
    FILES, STREAMS, bindings, code_hash, summarize, verify_artifact, write_artifact)
from grid_case_generator.models.completion_export import policy_bytes

import completion_fixture as cf

BINDINGS = {'source': 'a' * 64, 'audit': 'b' * 64}


@pytest.fixture
def inputs():
    return cf.ledger_inputs()


def make(tmp_path, inputs=None, name='ledger', **kwargs):
    inputs = inputs or cf.ledger_inputs(**kwargs)
    return write_artifact(inputs, tmp_path / name, BINDINGS), inputs


def rows(root, name):
    return [json.loads(line) for line in (root / name).read_bytes().splitlines()]


def test_clean_artifact_verifies(tmp_path, inputs):
    result, _ = make(tmp_path)
    root = tmp_path / 'ledger'
    assert result['written'] is True
    verdict = verify_artifact(root, inputs=inputs, expected_bindings=BINDINGS)
    assert verdict['verified'] is True
    assert verdict['input_bound'] is True


def test_every_stream_carries_a_row(tmp_path, inputs):
    """An artifact test must not pass on an empty artifact."""
    make(tmp_path)
    root = tmp_path / 'ledger'
    for name in STREAMS:
        assert rows(root, name + '.jsonl'), name


def test_write_once_and_scope_flags(tmp_path, inputs):
    make(tmp_path)
    with pytest.raises(FileExistsError):
        write_artifact(inputs, tmp_path / 'ledger', BINDINGS)
    manifest = json.loads((tmp_path / 'ledger' / 'manifest.json').read_text())
    for flag in ('approved', 'applied', 'canonical_changed', 'accepted_v2_changed',
                 'source_changed', 'e3_ready', 'opendss_ready'):
        assert manifest[flag] is False
    assert manifest['artifact_kind'] == 'COMPLETION_LEDGER'
    assert manifest['code_sha256'] == code_hash()


def test_inventory_is_exact_and_the_manifest_lists_every_file(tmp_path, inputs):
    make(tmp_path)
    root = tmp_path / 'ledger'
    on_disk = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    assert on_disk == set(FILES) | {'manifest.json'}
    assert set(json.loads((root / 'manifest.json').read_text())['files']) == set(FILES)


# --- determinism ---


def test_same_inputs_are_byte_identical(tmp_path, inputs):
    make(tmp_path, name='a')
    make(tmp_path, name='b')
    for name in (*FILES, 'manifest.json'):
        assert (tmp_path / 'a' / name).read_bytes() == (tmp_path / 'b' / name).read_bytes()


def test_ordering_is_independent_of_input_iteration_order(tmp_path, inputs):
    """Reversing every input stream must not move a single byte of the artifact."""
    reversed_inputs = replace(
        inputs, audit_rows=inputs.audit_rows[::-1],
        placement_feeders=inputs.placement_feeders[::-1],
        backbone_taxonomy=inputs.backbone_taxonomy[::-1],
        audit_cases=inputs.audit_cases[::-1],
        accepted_additions=inputs.accepted_additions[::-1],
        placement_proposals=inputs.placement_proposals[::-1],
        endpoint_evidence=inputs.endpoint_evidence[::-1])
    make(tmp_path, inputs=inputs, name='forward')
    make(tmp_path, inputs=reversed_inputs, name='backward')
    for name in (*FILES, 'manifest.json'):
        assert (tmp_path / 'forward' / name).read_bytes() == \
            (tmp_path / 'backward' / name).read_bytes(), name


def test_records_are_canonical_json(tmp_path, inputs):
    make(tmp_path)
    root = tmp_path / 'ledger'
    for name in STREAMS:
        for line in (root / (name + '.jsonl')).read_bytes().splitlines():
            assert line == canonical_json_bytes(json.loads(line))


# --- the aggregate ---


def test_summary_counts_reconcile_with_the_streams(tmp_path, inputs):
    make(tmp_path)
    root = tmp_path / 'ledger'
    summary = json.loads((root / 'summary.json').read_text())
    completion = rows(root, 'completion_records.jsonl')
    unresolved = rows(root, 'unresolved_records.jsonl')
    assert summary['counts']['completion_records'] == len(completion)
    assert summary['counts']['unresolved_records'] == len(unresolved)
    assert sum(summary['rule_counts'].values()) == len(completion)
    assert sum(summary['reason_counts'].values()) == len(unresolved)
    assert summary['case_count'] == len({r['case_id'] for r in completion + unresolved})


def test_addition_and_row_counts_are_measured_not_hardcoded(tmp_path):
    """A policy with no materializing rule must drive both counts to zero."""
    from grid_case_generator.models.completion_export import CompletionPolicy
    policy = CompletionPolicy(
        policy_version='1.1.0', materialize_tiers=('SAME_STATION',),
        enabled_rules=('ACCEPTED_DETERMINISTIC_RECOVERY_V1',),
        max_reference_closure_depth=2, placement_endpoint_bus=False)
    quiet = replace(cf.ledger_inputs(), policy=policy)
    ledger = build_ledger(quiet)
    assert ledger.counts['addition_count'] == 0
    assert ledger.counts['appended_row_count'] == 0
    assert len(build_ledger(cf.ledger_inputs()).completion_records) > 0


def test_case_summary_reconciles_with_the_record_streams(tmp_path, inputs):
    make(tmp_path)
    root = tmp_path / 'ledger'
    summary = rows(root, 'case_summary.jsonl')
    records = rows(root, 'completion_records.jsonl') + rows(root, 'unresolved_records.jsonl')
    tally = {}
    for r in records:
        key = (r['case_id'], r['completion_status'], r['rule_id'], r['tier'])
        tally[key] = tally.get(key, 0) + 1
    assert {(r['case_id'], r['completion_status'], r['rule_id'], r['tier']): r['record_count']
            for r in summary} == tally
    assert all(r['source_case_key'] for r in summary)
    assert summary == sorted(summary, key=lambda r: (r['case_id'], canonical_json_bytes(r)))


def test_policy_snapshot_reparses_to_the_consumed_policy(tmp_path, inputs):
    make(tmp_path)
    root = tmp_path / 'ledger'
    snapshot = json.loads((root / 'policy_snapshot.json').read_text())
    assert snapshot == json.loads(policy_bytes(inputs.policy))
    manifest = json.loads((root / 'manifest.json').read_text())
    assert manifest['policy_sha256'] == \
        sha256(policy_bytes(inputs.policy)).hexdigest()
    assert snapshot == json.loads(policy_bytes(inputs.policy))


def test_report_states_the_boundary_and_every_limitation(tmp_path, inputs):
    make(tmp_path)
    text = (tmp_path / 'ledger' / 'report.md').read_text()
    for phrase in ('approved: false', 'PROPOSED', 'SOURCE_HEAD_CONTEXT',
                   'declaration completions', 'Q-CASE-001', 'UNRESOLVED taxonomy',
                   'cohort_overlap_members'):
        assert phrase in text, phrase


# --- tamper detection ---


def tamper_manifest(root, mutate):
    path = root / 'manifest.json'
    manifest = json.loads(path.read_text())
    mutate(manifest)
    path.write_bytes(canonical_json_bytes(manifest) + b'\n')


def test_byte_append_fails(tmp_path, inputs):
    make(tmp_path)
    root = tmp_path / 'ledger'
    path = root / 'completion_records.jsonl'
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='checksum|count'):
        verify_artifact(root, inputs=inputs, expected_bindings=BINDINGS)


def test_extra_file_fails_inventory(tmp_path, inputs):
    make(tmp_path)
    root = tmp_path / 'ledger'
    (root / 'extra.jsonl').write_bytes(b'')
    with pytest.raises(ValueError, match='inventory'):
        verify_artifact(root, inputs=inputs, expected_bindings=BINDINGS)


def test_missing_file_fails_inventory(tmp_path, inputs):
    make(tmp_path)
    root = tmp_path / 'ledger'
    (root / 'completion_records.jsonl').unlink()
    with pytest.raises(ValueError, match='inventory'):
        verify_artifact(root, inputs=inputs, expected_bindings=BINDINGS)


def test_flipped_scope_flag_fails(tmp_path, inputs):
    make(tmp_path)
    root = tmp_path / 'ledger'
    tamper_manifest(root, lambda m: m.update(applied=True))
    with pytest.raises(ValueError, match='scope violation'):
        verify_artifact(root, inputs=inputs, expected_bindings=BINDINGS)


def test_stale_policy_hash_fails(tmp_path, inputs):
    make(tmp_path)
    root = tmp_path / 'ledger'
    tamper_manifest(root, lambda m: m.update(policy_sha256='0' * 64))
    with pytest.raises(ValueError, match='replay|policy'):
        verify_artifact(root, inputs=inputs, expected_bindings=BINDINGS)


def test_stale_upstream_binding_fails(tmp_path, inputs):
    make(tmp_path)
    with pytest.raises(ValueError, match='binding'):
        verify_artifact(tmp_path / 'ledger', inputs=inputs,
                        expected_bindings=dict(BINDINGS, audit='0' * 64))


def test_rehashed_semantic_tamper_still_fails_replay(tmp_path, inputs):
    """The replay, not the checksum, is what makes a rewritten record detectable."""
    make(tmp_path)
    root = tmp_path / 'ledger'
    path = root / 'completion_records.jsonl'
    records = [json.loads(line) for line in path.read_bytes().splitlines()]
    records[0]['completion_status'] = 'CONFIRMED'
    path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in records))
    tamper_manifest(root, lambda m: m['files'][path.name].update(
        sha256=sha256(path.read_bytes()).hexdigest()))
    with pytest.raises(ValueError, match='replay'):
        verify_artifact(root, inputs=inputs, expected_bindings=BINDINGS)


def test_rehashed_policy_snapshot_tamper_still_fails_replay(tmp_path, inputs):
    make(tmp_path)
    root = tmp_path / 'ledger'
    path = root / 'policy_snapshot.json'
    snapshot = json.loads(path.read_text())
    snapshot['policy_version'] = '9.9.9'
    path.write_bytes(canonical_json_bytes(snapshot) + b'\n')
    tamper_manifest(root, lambda m: m['files'][path.name].update(
        sha256=sha256(path.read_bytes()).hexdigest()))
    with pytest.raises(ValueError, match='replay|policy'):
        verify_artifact(root, inputs=inputs, expected_bindings=BINDINGS)


def test_nonexistent_artifact_is_rejected(tmp_path, inputs):
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_artifact(tmp_path / 'absent')


# --- the thirteen roots ---


def test_bindings_require_exactly_thirteen_roots():
    with pytest.raises(ValueError, match='thirteen'):
        bindings({'source': 'x'})


def test_summarize_is_pure_over_a_ledger(inputs):
    ledger = build_ledger(inputs)
    assert summarize(ledger) == summarize(build_ledger(inputs))
