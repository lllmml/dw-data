import pytest
from grid_case_generator.generation.completion_ledger import (
    COUNTS_KEYS, RECORD_KEYS, CompletionInputs, Ledger, build_ledger, closure_key,
    order_records, order_unresolved, record, walk_closure,
)
from grid_case_generator.models.completion_export import parse_policy

EXPECTED_KEYS = {
    'record_id', 'completion_status', 'confidence_class', 'tier', 'rule_id',
    'rule_version', 'case_id', 'source_case_key', 'source_entity_type',
    'donor_source_entity_type', 'source_record_ref', 'donor_source_record_ref',
    'raw_field', 'raw_reference_value', 'evidence_refs', 'closure_depth',
    'policy_version', 'policy_sha256', 'reason'}


def chain(*pairs):
    edges = {}
    for a, b in pairs:
        edges.setdefault(closure_key('case:a', 'SWITCH', a), []).append(
            ('case:a', 'SWITCH', b))
    return edges


def walk(seed, edges, max_depth):
    return list(walk_closure(seed, lambda k: edges.get(k, ()), max_depth=max_depth))


def test_record_key_set_is_exact():
    assert set(RECORD_KEYS) == EXPECTED_KEYS


def test_record_fills_every_key_and_is_identity_stable():
    r = record(rule_id='SOURCE_PASSTHROUGH_V1', case_id='case:a', reason='FIRST')
    assert set(r) == set(RECORD_KEYS)
    assert r['tier'] is None and r['donor_source_record_ref'] is None
    assert r['completion_status'] is None
    renamed = record(rule_id='SOURCE_PASSTHROUGH_V1', case_id='case:a', reason='SECOND')
    assert r['record_id'] == renamed['record_id']
    assert r['record_id'].startswith('v1-completion:ledger:')
    assert len(r['record_id']) == len('v1-completion:ledger:') + 64


def test_record_reason_is_not_part_of_identity():
    a = record(rule_id='R', case_id='case:a', source_record_ref='x', reason='WHY_ONE')
    b = record(rule_id='R', case_id='case:a', source_record_ref='x', reason='WHY_TWO')
    assert a['record_id'] == b['record_id']
    assert a['reason'] != b['reason']


def test_record_identity_changes_with_any_other_field():
    base = record(rule_id='R', case_id='case:a', source_record_ref='x')
    moved = record(rule_id='R', case_id='case:a', source_record_ref='y')
    assert base['record_id'] != moved['record_id']


@pytest.mark.parametrize('bad', ['record_id', 'reason_', 'Rule_id', 'records'])
def test_record_rejects_unknown_or_reserved_field(bad):
    kwargs = {'rule_id': 'R', 'case_id': 'case:a'}
    if bad == 'record_id':
        kwargs['record_id'] = 'caller-supplied'
    else:
        kwargs[bad] = 'x'
    with pytest.raises(ValueError, match=bad if bad in kwargs else 'record_id'):
        record(**kwargs)


def test_record_identity_ignores_dict_input_order():
    a = record(rule_id='R', case_id='case:a', raw_field='Switch_ToBus')
    b = record(case_id='case:a', rule_id='R', raw_field='Switch_ToBus')
    assert a == b


def test_closure_key_orders_case_locally():
    assert closure_key('case:a', 'SWITCH', '1') < closure_key('case:a', 'SWITCH', '2')
    assert closure_key('case:a', 'BUS', '1') < closure_key('case:a', 'SWITCH', '1')
    assert closure_key('case:a', 'SWITCH', '1') < closure_key('case:b', 'SWITCH', '1')
    assert closure_key('case:a', 'SWITCH', '1') == ('case:a', 'SWITCH', '1')


def test_closure_is_bounded_and_reports_the_overflow():
    edges = chain(('a', 'b'), ('b', 'c'), ('c', 'd'))
    seed = closure_key('case:a', 'SWITCH', 'a')

    full = walk(seed, edges, 2)
    assert [m['depth'] for _, m in full] == [1, 2, 3]
    assert [m['depth_exceeded'] for _, m in full] == [False, False, True]

    shallow = walk(seed, edges, 1)
    assert [m['depth'] for _, m in shallow] == [1, 2]
    assert [m['depth_exceeded'] for _, m in shallow] == [False, True]

    zero = walk(seed, edges, 0)
    assert len(zero) == 1
    assert zero[0][1]['depth_exceeded'] is True


def test_an_over_deep_node_is_reported_but_never_expanded():
    # b is at depth 1; with max_depth=0 even b is over-deep, so c must never appear.
    edges = chain(('a', 'b'), ('b', 'c'), ('c', 'd'))
    seed = closure_key('case:a', 'SWITCH', 'a')
    keys = [k for k, _ in walk(seed, edges, 0)]
    assert keys == [closure_key('case:a', 'SWITCH', 'b')]


def test_negative_depth_bound_is_rejected():
    seed = closure_key('case:a', 'SWITCH', 'a')
    with pytest.raises(ValueError, match='closure depth bound'):
        list(walk_closure(seed, lambda k: (), max_depth=-1))


def test_closure_terminates_on_a_cycle_and_a_self_reference():
    seed = closure_key('case:a', 'SWITCH', 'a')
    cycle = walk(seed, chain(('a', 'b'), ('b', 'a')), 8)
    assert [k[2] for k, _ in cycle] == ['b']
    # The seed is marked visited and never yielded, so a self-reference reaches an
    # already-visited node and yields nothing, exactly as the 2-cycle does not
    # re-yield 'a'.
    self_ref = walk(seed, chain(('a', 'a')), 8)
    assert [k[2] for k, _ in self_ref] == []


def test_closure_is_independent_of_frontier_order():
    forward = {'case:a': [('case:a', 'SWITCH', 'b'), ('case:a', 'SWITCH', 'c')]}
    backward = {'case:a': [('case:a', 'SWITCH', 'c'), ('case:a', 'SWITCH', 'b')]}
    lookup = lambda table: (lambda k: table.get(k[0], ()) if k[1:] == ('SWITCH', 'a') else ())
    seed = closure_key('case:a', 'SWITCH', 'a')
    a = [k for k, _ in walk_closure(seed, lookup(forward), max_depth=2)]
    b = [k for k, _ in walk_closure(seed, lookup(backward), max_depth=2)]
    assert a == b


def test_closure_does_not_repeat_a_shared_child():
    seed = closure_key('case:a', 'SWITCH', 'a')
    edges = {seed: [('case:a', 'SWITCH', 'b'), ('case:a', 'SWITCH', 'c')],
             closure_key('case:a', 'SWITCH', 'b'): [('case:a', 'SWITCH', 'x')],
             closure_key('case:a', 'SWITCH', 'c'): [('case:a', 'SWITCH', 'x')]}
    got = [k[2] for k, _ in walk(seed, edges, 4)]
    assert sorted(got) == ['b', 'c', 'x']


def test_walk_closure_is_lazy():
    import types
    seed = closure_key('case:a', 'SWITCH', 'a')
    assert isinstance(walk_closure(seed, lambda k: (), max_depth=1), types.GeneratorType)


def test_record_ordering_is_total_when_only_the_reason_differs():
    a = record(rule_id='A', case_id='case:a', source_record_ref='x', reason='ONE')
    b = record(rule_id='A', case_id='case:a', source_record_ref='x', reason='TWO')
    assert a['record_id'] == b['record_id']
    assert order_records([a, b]) == order_records([b, a])
    assert [r['reason'] for r in order_records([b, a])] == ['ONE', 'TWO']


def test_ordering_tolerates_absent_fields():
    # record() defaults every key to None, so the sort must never compare None to str.
    a = record(rule_id='A', case_id='case:a')
    b = record(reason='X')
    assert order_records([a, b]) == order_records([b, a])
    assert order_unresolved([a, b]) == order_unresolved([b, a])
    assert order_records([a]) == (a,)
    assert order_unresolved([b]) == (b,)


def test_ordering_is_stable_for_records_differing_only_outside_the_key():
    a = record(rule_id='A', case_id='case:a', reason='R', raw_field='F1')
    b = record(rule_id='A', case_id='case:a', reason='R', raw_field='F2')
    assert a['record_id'] != b['record_id']
    assert order_records([a, b]) == order_records([b, a])


def test_ordering_is_explicit_and_deterministic():
    a = record(rule_id='B', case_id='case:a', reason='X')
    b = record(rule_id='A', case_id='case:z', reason='X')
    c = record(rule_id='A', case_id='case:a', reason='Y')
    assert [r['rule_id'] for r in order_records([a, b, c])] == ['A', 'A', 'B']
    assert order_records([a, b, c]) == order_records([c, b, a])
    assert order_records((c, a, b)) == order_records([b, a, c])


def test_unresolved_ordering_is_by_reason_then_case():
    a = record(reason='BETA', case_id='case:a')
    b = record(reason='ALPHA', case_id='case:z')
    c = record(reason='ALPHA', case_id='case:a')
    assert [r['reason'] for r in order_unresolved([a, b, c])] == ['ALPHA', 'ALPHA', 'BETA']
    assert order_unresolved([a, b, c]) == order_unresolved([c, b, a])


def test_build_ledger_scaffold_is_empty_and_zeroed():
    inputs = CompletionInputs(
        policy=parse_policy('configs/nanjing_completion_policy_v1.json'),
        source_case_key_by_case={}, audit_rows=(), accepted_additions=(),
        placement_proposals=(), endpoint_evidence=(), placement_feeders=(),
        backbone_taxonomy=(), audit_classification=())
    ledger = build_ledger(inputs)
    assert isinstance(ledger, Ledger)
    assert ledger.completion_records == ()
    assert ledger.unresolved_records == ()
    assert ledger.case_summary == ()
    assert set(ledger.counts) == set(COUNTS_KEYS)
    assert all(v == 0 for v in ledger.counts.values())


def test_inputs_and_ledger_are_immutable():
    from dataclasses import FrozenInstanceError
    inputs = CompletionInputs(
        policy=parse_policy('configs/nanjing_completion_policy_v1.json'),
        source_case_key_by_case={}, audit_rows=(), accepted_additions=(),
        placement_proposals=(), endpoint_evidence=(), placement_feeders=(),
        backbone_taxonomy=(), audit_classification=())
    with pytest.raises(FrozenInstanceError):
        inputs.audit_rows = ()
    ledger = build_ledger(inputs)
    with pytest.raises(FrozenInstanceError):
        ledger.counts = {}


def test_no_io_or_randomness_in_the_module():
    import ast
    from pathlib import Path as _Path
    source = (_Path(__file__).parents[2]
              / 'src' / 'grid_case_generator' / 'generation'
              / 'completion_ledger.py').read_text()
    tree = ast.parse(source)
    forbidden = {'random', 'secrets', 'time', 'datetime', 'os', 'pathlib', 'zipfile'}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split('.')[0])
    assert not (imported & forbidden), imported & forbidden
    assert 'hash(' not in source
