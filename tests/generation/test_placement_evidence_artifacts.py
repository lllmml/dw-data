from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.placement_evidence_artifacts import (
    write_artifact, verify_artifact, collect, replay_cases, FILES,
)
import placement_fixture as fx

BINDINGS = {'fixture': 'a' * 64, 'd4': 'b' * 64}


def cases():
    return [
        fx.build(buses=[fx.bus('B1', 'j1')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1')], case_key='数据/甲变_10kV甲线101'),
        fx.build(buses=[fx.bus('B2', 'j2')], switches=[fx.switch('S2')],
                 lines=[fx.line('L2', 'B2', 'S2')], case_key='数据/乙变_10kV乙线202'),
    ]


def make(tmp_path, name='artifact', bound=BINDINGS):
    factory = lambda: iter(deepcopy(cases()))
    root = tmp_path / name
    write_artifact(factory, root, bound, tmp_path / 'source')
    return root, factory


def test_artifact_is_complete_and_verifies(tmp_path):
    root, factory = make(tmp_path)
    assert {p.name for p in root.iterdir()} == FILES | {'manifest.json'}
    manifest = json.loads((root / 'manifest.json').read_text())
    assert manifest['artifact_kind'] == 'PROPOSAL_ONLY_COUNTERFACTUAL'
    assert all(manifest[k] is False for k in ('approved', 'applied', 'accepted_v2_changed',
                                              'source_changed', 'd4_artifact_changed', 'e3_ready'))
    result = verify_artifact(root, factory=factory, source_root=tmp_path / 'source',
                             expected_bindings=BINDINGS)
    assert result['verified'] and result['input_bound']


def test_inputs_are_never_mutated(tmp_path):
    before = deepcopy(cases())
    factory = lambda: iter(deepcopy(cases()))
    write_artifact(factory, tmp_path / 'artifact', BINDINGS, tmp_path / 'source')
    assert cases() == before


def test_d4_replay_is_bound_to_the_untouched_before_run(tmp_path):
    root, _ = make(tmp_path)
    coverage = json.loads((root / 'counterfactual_coverage.json').read_text())
    summary, edges, _ = collect(iter(cases()))
    assert coverage['before']['physical_backbone'] == \
        summary['d2_eligibility']['after']['counts']['accepted_physical_backbone']
    assert coverage['d4_proposals_before'] == len(edges)
    replay = [json.loads(line) for line in (root / 'd4_replay.jsonl').read_text().splitlines()]
    before = [r for r in replay if r['origin'] == 'BEFORE']
    new = [r for r in replay if r['origin'] == 'NEW']
    assert len(before) == coverage['d4_proposals_before']
    assert len(new) == coverage['d4_proposals_added']
    assert len(replay) == coverage['d4_proposals_after']
    assert all(r['approved'] is False and r['applied'] is False for r in replay)
    assert all(r['replay_status'] in ('STILL_VALID', 'SUPERSEDED_BY_BETTER_PLACEMENT',
                                      'NOW_AMBIGUOUS', 'INVALID') for r in before)
    assert all(r['replay_status'] == 'NEW_ON_PLACEMENT_COUNTERFACTUAL' for r in new)


def test_placement_enables_new_d4_backbone_proposals(tmp_path):
    # These Fixtures have no D4 backbone proposal before placement and one each after,
    # because the represented Line component now has a unique accepted Bus junction.
    root, _ = make(tmp_path)
    coverage = json.loads((root / 'counterfactual_coverage.json').read_text())
    assert coverage['d4_proposals_before'] == 0
    assert coverage['d4_proposals_after'] == 2
    assert coverage['after']['physical_backbone'] > coverage['before']['physical_backbone']


def test_no_source_line_feeder_gets_no_layout_proposal(tmp_path):
    blank = fx.build(buses=[fx.bus('B9', 'j9')], case_key='数据/丙变_10kV丙线303')
    factory = lambda: iter([blank] + cases())
    root = tmp_path / 'artifact'
    write_artifact(factory, root, BINDINGS, tmp_path / 'source')
    evidence = [json.loads(line) for line in (root / 'line_endpoint_evidence.jsonl').read_text().splitlines()]
    proposals = [json.loads(line) for line in (root / 'line_component_proposals.jsonl').read_text().splitlines()]
    targets = [json.loads(line) for line in (root / 'target_feeders.jsonl').read_text().splitlines()]
    assert len(targets) == 2
    assert len(proposals) == 2
    assert all(row['case_id'] != blank['accepted']['case_id'] for row in evidence)
    assert all(row['source_line_record_ref'].startswith('zip-member:') for row in proposals)


def _source_root_with(tmp_path, rows):
    """A minimal read-only intake so the cross-Case index has something to scan."""
    case = tmp_path / 'source' / 'cases' / 'case:elsewhere'
    case.mkdir(parents=True, exist_ok=True)
    (case / 'row_accountability.jsonl').write_text(
        ''.join(json.dumps({'raw_record': {'fields': [list(pair)]}}, separators=(',', ':')) + '\n'
                for pair in rows))
    return tmp_path / 'source'


def test_cross_case_reference_is_labelled_but_never_followed(tmp_path):
    source = _source_root_with(tmp_path, [('Switch_ID', 'S1'), ('Bus_ID', 'B1')])
    x = fx.build(buses=[fx.bus('B2', 'j2')], lines=[fx.line('L2', 'B2', 'S1')],
                 case_key='数据/乙变_10kV乙线202')
    root = tmp_path / 'artifact'
    write_artifact(lambda: iter(deepcopy([x])), root, BINDINGS, source)
    rows = [json.loads(line) for line in
            (root / 'line_endpoint_evidence.jsonl').read_text().splitlines()]
    external = [r for r in rows if r['resolver_status'] == 'EXTERNAL_DEFINED']
    assert len(external) == 1
    assert external[0]['ownership_status'] == 'EXTERNAL'
    assert external[0]['resolved_source_id'] is None
    assert external[0]['placement_evidence_class'] == 'NO_ANCHOR_EVIDENCE'
    blocked = [json.loads(line) for line in
               (root / 'rejected_candidates.jsonl').read_text().splitlines()]
    assert {r['outcome'] for r in blocked} == {'LINE_BLOCKED_NO_ANCHOR_EVIDENCE'}
    assert {r['reasons'][0] for r in blocked} == {'CROSS_CASE_REFERENCE_NOT_FOLLOWED'}
    assert not [json.loads(line) for line in
                (root / 'line_component_proposals.jsonl').read_text().splitlines()]


def test_undefined_reference_is_distinguished_from_cross_case(tmp_path):
    source = _source_root_with(tmp_path, [('Switch_ID', 'S1')])
    x = fx.build(buses=[fx.bus('B2', 'j2')], lines=[fx.line('L2', 'B2', 'NOWHERE')],
                 case_key='数据/丙变_10kV丙线303')
    root = tmp_path / 'artifact'
    write_artifact(lambda: iter(deepcopy([x])), root, BINDINGS, source)
    rows = [json.loads(line) for line in
            (root / 'line_endpoint_evidence.jsonl').read_text().splitlines()]
    classes = {r['endpoint_side']: r['resolver_status'] for r in rows}
    assert classes == {1: 'EXACT_CASE_LOCAL', 2: 'UNDEFINED_REFERENCE'}


def test_every_review_is_emitted_exactly_once(tmp_path):
    root, _ = make(tmp_path)
    for name in ('accesspoint_reviews.jsonl', 'remote_switch_reviews.jsonl',
                 'shared_reference_reviews.jsonl'):
        rows = [json.loads(line) for line in (root / name).read_text().splitlines()]
        keys = [(r['case_id'], r['source_id']) for r in rows]
        assert len(keys) == len(set(keys)), name


def test_no_device_is_generated(tmp_path):
    root, _ = make(tmp_path)
    for name in ('placement_anchors.jsonl', 'line_component_proposals.jsonl'):
        for line in (root / name).read_text().splitlines():
            row = json.loads(line)
            assert row.get('evidence_class') == 'RULE_INFERRED'
            assert row.get('device_id') is None and not row.get('devices')
            assert row.get('transformer_key') is None
            assert row['approved'] is False and row['applied'] is False


def test_manifest_binding_tamper_fails(tmp_path):
    root, factory = make(tmp_path)
    manifest = json.loads((root / 'manifest.json').read_text())
    manifest['input_manifest_sha256'] = {'fixture': 'c' * 64}
    (root / 'manifest.json').write_bytes(canonical_json_bytes(manifest) + b'\n')
    with pytest.raises(ValueError, match='binding'):
        verify_artifact(root, expected_bindings=BINDINGS)


def test_stale_accepted_and_d4_binding_fails(tmp_path):
    root, _ = make(tmp_path)
    with pytest.raises(ValueError, match='binding'):
        verify_artifact(root, expected_bindings=dict(BINDINGS, accepted_v2='0' * 64))
    with pytest.raises(ValueError, match='binding'):
        verify_artifact(root, expected_bindings=dict(BINDINGS, d4='1' * 64))


def test_scope_violation_in_manifest_fails(tmp_path):
    root, _ = make(tmp_path)
    manifest = json.loads((root / 'manifest.json').read_text())
    manifest['applied'] = True
    (root / 'manifest.json').write_bytes(canonical_json_bytes(manifest) + b'\n')
    with pytest.raises(ValueError, match='scope violation'):
        verify_artifact(root)


def test_detail_tamper_with_rehashed_manifest_fails(tmp_path):
    root, factory = make(tmp_path)
    path = root / 'line_component_proposals.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]['outcome'] = 'LINE_ALREADY_REPRESENTED'
    path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
    manifest = json.loads((root / 'manifest.json').read_text())
    manifest['files'][path.name]['sha256'] = sha256(path.read_bytes()).hexdigest()
    (root / 'manifest.json').write_bytes(canonical_json_bytes(manifest) + b'\n')
    with pytest.raises(ValueError, match='replay'):
        verify_artifact(root, factory=factory, source_root=tmp_path / 'source')


def test_verifier_recomputes_from_authoritative_inputs(tmp_path):
    root, _ = make(tmp_path)
    changed = cases()
    changed[0]['accepted']['nominal_voltage_kv'] = '20'
    with pytest.raises(ValueError, match='replay|invalid'):
        verify_artifact(root, factory=lambda: iter(changed), source_root=tmp_path / 'source')


def test_no_overwrite(tmp_path):
    root, factory = make(tmp_path)
    with pytest.raises(FileExistsError):
        write_artifact(factory, root, BINDINGS, tmp_path / 'source')


def test_hash_seed_independent(tmp_path):
    source = tmp_path / 'cases.json'
    source.write_text(json.dumps(cases()))
    script = ('from pathlib import Path; import json,sys;'
              'sys.path.insert(0, "tests/generation");'
              'from grid_case_generator.io.placement_evidence_artifacts import write_artifact;'
              'write_artifact(lambda: iter(json.loads(Path(sys.argv[1]).read_text())),'
              ' Path(sys.argv[2]), {"fixture":"a"*64,"d4":"b"*64}, Path(sys.argv[3]))')
    for seed in ('1', '999'):
        subprocess.run([sys.executable, '-c', script, str(source), str(tmp_path / seed),
                        str(tmp_path / 'source')],
                       env=dict(os.environ, PYTHONHASHSEED=seed), check=True)
    for path in (tmp_path / '1').iterdir():
        assert path.read_bytes() == (tmp_path / '999' / path.name).read_bytes()


def test_replay_cases_only_changes_the_overlay():
    original = cases()
    overlay = {original[0]['accepted']['case_id']: {'nodes': [], 'edges': []}}
    assert list(replay_cases(iter(original), overlay, True)) == original
    assert list(replay_cases(iter(original), overlay, False)) == original
