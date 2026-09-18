from copy import deepcopy
import pytest

from grid_case_generator.generation.placement_evidence import (
    CaseEvidence, ANCHOR_RULES, DEFERRED_RULES, DEFERRED_RULE, ACCESS_RULE, LEAF_RULE,
    SERIES_RULE, LINE_RULE, SCOPE, generated_id,
)
from grid_case_generator.validation.placement_evidence import validate_case
import placement_fixture as fx


def analyse(x, foreign=None):
    ev = CaseEvidence(x, foreign)
    return ev, ev.analyse(), ev.reviews()


def evidence(result, side):
    rows = [r for r in result['rows']['line_endpoint_evidence'] if r['endpoint_side'] == side]
    assert len(rows) == 1
    return rows[0]


def only_line(result):
    assert len(result['line_rows']) == 1
    return result['line_rows'][0]


def test_exact_unique_bus_anchor():
    x = fx.build(buses=[fx.bus('B1', 'j1')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1')])
    _, result, _ = analyse(x)
    row = evidence(result, 1)
    assert row['placement_evidence_class'] == 'EXACT_STRUCTURAL_ANCHOR'
    assert row['candidate_anchor_ids'] == ['j1']
    assert row['resolver_status'] == 'EXACT_CASE_LOCAL'
    assert row['voltage_evidence'] == '10.5'


def test_one_sided_line_endpoint_is_recovered():
    x = fx.build(buses=[fx.bus('B1', 'j1')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1')])
    ev, result, _ = analyse(x)
    assert only_line(result)['outcome'] == 'LINE_PLACEMENT_PROPOSED'
    assert evidence(result, 2)['placement_evidence_class'] == 'ENGINEERING_SHARED_REFERENCE_ANCHOR'
    proposal, = result['proposals']
    assert [e['anchor_origin'] for e in proposal['endpoints']] == ['ACCEPTED_NODE', LEAF_RULE]
    assert proposal['evidence_class'] == 'UNRESOLVED'
    assert proposal['approved'] is False and proposal['applied'] is False
    assert proposal['scope'] == SCOPE


def test_multiple_case_local_readings_are_ambiguous():
    x = fx.build(buses=[{'id': 'B1'}], duplicate_id=[('BUS', 'B1')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1')])
    _, result, _ = analyse(x)
    row = evidence(result, 1)
    assert row['placement_evidence_class'] == 'AMBIGUOUS_ANCHOR'
    assert row['resolver_status'] == 'CASE_LOCAL_AMBIGUOUS'
    assert len(row['competing_evidence']) == 2
    line = only_line(result)
    assert line['outcome'] == 'LINE_BLOCKED_NON_UNIQUE_PLACEMENT'
    assert 'AMBIGUOUS_CASE_LOCAL_REFERENCE' in line['reasons']
    assert not result['proposals']


def test_accesspoint_unique_incidence_becomes_engineering_anchor():
    x = fx.build(accesspoints=[fx.accesspoint('A1')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'A1', 'S1')])
    ev, result, review = analyse(x)
    anchor, = [a for a in result['rows']['placement_anchors'] if a['rule_id'] == ACCESS_RULE]
    assert anchor['degree'] == 1 and anchor['port_roles'] == ['JUNCTION']
    assert anchor['evidence_class'] == 'UNRESOLVED'
    assert anchor['internal_edge_id'] is None
    assert anchor['voltage_kv'] == '10.5' and anchor['voltage_source'] == 'DERIVED_MV_DOMAIN'
    assert ev.anchors['A1']['account']['raw_record']['source_file_type'] == 'ACCESS_POINT'
    reviewed, = [r for r in review['accesspoint_reviews'] if r['source_id'] == 'A1']
    assert reviewed['disposition'] == 'ELIGIBLE'
    assert reviewed['rule_id'] == ACCESS_RULE


def test_accesspoint_never_confirmed_as_source_bus():
    x = fx.build(accesspoints=[fx.accesspoint('A1'), fx.accesspoint('A2')],
                 lines=[fx.line('L1', 'A1', 'A2')])
    _, result, _ = analyse(x)
    assert len(result['rows']['placement_anchors']) == 2
    assert {a['evidence_class'] for a in result['rows']['placement_anchors']} == {'UNRESOLVED'}
    assert {a['rule_id'] for a in result['rows']['placement_anchors']} == {ACCESS_RULE}
    assert all(a['internal_edge_id'] is None for a in result['rows']['placement_anchors'])
    assert result['proposals'][0]['assumptions'] == ['DERIVED_PLACEMENT_REPRESENTATION',
                                                     'NOT_A_NEW_LINE_DEVICE',
                                                     'NOT_A_SOURCE_CONNECTION']


def test_accesspoint_competing_entity_type_is_never_anchored():
    x = fx.build(buses=[fx.bus('B1', 'j1')], switches=[fx.switch('X1')], accesspoints=[fx.accesspoint('X1')],
                 lines=[fx.line('L1', 'B1', 'X1')])
    _, result, _ = analyse(x)
    row = evidence(result, 2)
    assert row['placement_evidence_class'] == 'AMBIGUOUS_ANCHOR'
    assert row['resolver_status'] == 'CASE_LOCAL_AMBIGUOUS'
    assert not any(a['source_id'] == 'X1' for a in result['rows']['placement_anchors'])
    assert only_line(result)['outcome'] == 'LINE_BLOCKED_NON_UNIQUE_PLACEMENT'


def test_shared_accesspoint_across_lines_is_one_anchor():
    x = fx.build(buses=[fx.bus('B1', 'j1'), fx.bus('B2', 'j2')], accesspoints=[fx.accesspoint('A1')],
                 lines=[fx.line('L1', 'B1', 'A1'), fx.line('L2', 'B2', 'A1')])
    _, result, review = analyse(x)
    anchor, = [a for a in result['rows']['placement_anchors'] if a['rule_id'] == ACCESS_RULE]
    assert anchor['degree'] == 2
    assert len(anchor['incident_line_refs']) == 2
    assert len(result['proposals']) == 2
    assert review['shared_reference_reviews']
    a1, = [r for r in review['shared_reference_reviews'] if r['source_id'] == 'A1']
    assert a1['rule_id'] == DEFERRED_RULE and a1['outcome'] == 'NARROW_RULE_ENABLED'


def test_remote_switch_unique_downstream_evidence():
    x = fx.build(switches=[fx.switch('S1')], accesspoints=[fx.accesspoint('A1')],
                 lines=[fx.line('L1', 'A1', 'S1')])
    _, result, review = analyse(x)
    anchor, = [a for a in result['rows']['placement_anchors'] if a['rule_id'] == LEAF_RULE]
    assert anchor['port_roles'] == ['ATTACH', 'UNBOUND']
    assert anchor['operating_state'] == 'CLOSED' and anchor['conducting'] is True
    edge, = [e for e in result['edges'] if e['kind'] == 'SWITCH']
    assert edge['conducting'] is True
    row, = [r for r in review['remote_switch_reviews'] if r['source_id'] == 'S1']
    assert row['disposition'] == 'ELIGIBLE' and row['degree'] == 1


def test_remote_switch_multiple_downstream_evidence_is_rejected():
    x = fx.build(buses=[fx.bus('B1', 'j1'), fx.bus('B2', 'j2'), fx.bus('B3', 'j3')],
                 switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1'), fx.line('L2', 'B2', 'S1'), fx.line('L3', 'B3', 'S1')])
    _, result, review = analyse(x)
    assert not [a for a in result['rows']['placement_anchors'] if a['source_id'] == 'S1']
    row, = [r for r in review['remote_switch_reviews'] if r['source_id'] == 'S1']
    assert row['disposition'] == 'REJECTED'
    assert 'SWITCH_DEGREE_NOT_UNIQUE' in row['reason_codes']
    assert {r['outcome'] for r in result['line_rows']} == {'LINE_BLOCKED_NON_UNIQUE_PLACEMENT'}


def test_switch_with_case_local_outer_declaration_is_declined():
    # D3's exact-direct contract owns a Switch whose outer declaration is case-local.
    x = fx.build(buses=[fx.bus('B1', 'j1'), fx.bus('B2', 'j2')],
                 switches=[fx.switch('S1', source='B1')],
                 lines=[fx.line('L1', 'B1', 'S1'), fx.line('L2', 'S1', 'B2')])
    _, result, review = analyse(x)
    assert not result['rows']['placement_anchors']
    assert not result['proposals'] and not result['edges']
    row, = review['remote_switch_reviews']
    assert 'CASE_LOCAL_OUTER_DECLARATION_PRESENT' in row['reason_codes']
    assert row['outer_declaration_status'] == ['EXACT_CASE_LOCAL', 'NO_DECLARATION']
    assert row['disposition'] == 'NEEDS_REVIEW'


def test_switch_without_case_local_declaration_is_eligible():
    x = fx.build(buses=[fx.bus('B1', 'j1'), fx.bus('B2', 'j2')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1'), fx.line('L2', 'S1', 'B2')])
    _, result, review = analyse(x)
    anchor, = result['rows']['placement_anchors']
    assert anchor['rule_id'] == SERIES_RULE and anchor['degree'] == 2
    row, = review['remote_switch_reviews']
    assert row['disposition'] == 'ELIGIBLE' and row['reason_codes'] == []
    assert row['outer_declaration_status'] == ['NO_DECLARATION', 'NO_DECLARATION']


@pytest.mark.parametrize('state,conducting', [('Open', False), ('Closed', True)])
def test_open_switch_remains_nonconducting(state, conducting):
    x = fx.build(buses=[fx.bus('B1', 'j1'), fx.bus('B2', 'j2')], switches=[fx.switch('S1', state=state)],
                 lines=[fx.line('L1', 'B1', 'S1'), fx.line('L2', 'S1', 'B2')])
    _, result, _ = analyse(x)
    anchor, = result['rows']['placement_anchors']
    assert anchor['rule_id'] == SERIES_RULE
    assert anchor['operating_state'] == state.upper()
    assert anchor['conducting'] is conducting
    edge, = result['edges']
    assert edge['conducting'] is conducting


def test_placement_cannot_bypass_open_cut():
    x = fx.build(buses=[fx.bus('B1', 'j1'), fx.bus('B2', 'j2')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1'), fx.line('L2', 'S1', 'B2')])
    ev, result, _ = analyse(x)
    assert result['proposals']
    x['accepted']['base_edges'].append({'edge_id': 'open-cut',
                                        'case_id': x['accepted']['case_id'],
                                        'a': 'j1', 'b': 'j2', 'kind': 'SWITCH', 'conducting': False})
    x['accepted']['state_constraints'].append({'kind': 'SWITCH', 'state': 'OPEN', 'node_ids': [],
                                               'raw_endpoints': {'Switch_ToBus': 'j2'},
                                               'source_record_ref': 'open-row'})
    level = validate_case(x, ev)
    assert 'OPEN_CUT_BYPASSED' in level['reasons']
    assert level['open_cuts_preserved'] is False


def test_generator_withdraws_when_placement_would_bypass_open_cut():
    x = fx.build(buses=[fx.bus('B1', 'j1'), fx.bus('B2', 'j2')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1'), fx.line('L2', 'S1', 'B2')])
    x['accepted']['base_edges'].append({'edge_id': 'open-cut',
                                        'case_id': x['accepted']['case_id'], 'a': 'j1', 'b': 'j2',
                                        'kind': 'SWITCH', 'conducting': False})
    ev, result, _ = analyse(x)
    # A bypass always also raises the physical cycle rank, so either guard may fire first.
    assert ev.withdrawn['reason'] in ('PLACEMENT_WOULD_CREATE_CYCLE',
                                      'PLACEMENT_WOULD_BYPASS_OPEN_CUT')
    assert result['proposals'] == [] and result['nodes'] == [] and result['edges'] == []
    assert {r['outcome'] for r in result['line_rows']} == {'LINE_BLOCKED_NON_UNIQUE_PLACEMENT'}
    assert {r['reasons'][0] for r in result['line_rows']} == {'PLACEMENT_WOULD_CREATE_CYCLE'}
    assert validate_case(x, ev)['reasons'] == []


def test_voltage_conflict_rejects_placement():
    x = fx.build(buses=[fx.bus('B1', 'j1', kv='110')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1')])
    _, result, _ = analyse(x)
    line = only_line(result)
    assert line['outcome'] == 'LINE_BLOCKED_NON_UNIQUE_PLACEMENT'
    assert 'INCOMPATIBLE_VOLTAGE' in line['reasons']
    assert not result['proposals']


def test_identity_ambiguity_rejects_the_line():
    x = fx.build(buses=[fx.bus('B1', 'j1')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1')], duplicate_id=[('LINE', 'L1')])
    ev, result, _ = analyse(x)
    assert result['line_rows'] == [] and result['proposals'] == []
    assert result['rows']['line_endpoint_evidence'] == []
    assert ev.lines == []


def test_cross_case_reference_is_never_followed():
    x = fx.build(buses=[fx.bus('B1', 'j1')], lines=[fx.line('L1', 'B1', 'ELSEWHERE')])
    _, result, _ = analyse(x, {'ELSEWHERE': ['Switch_ID']})
    row = evidence(result, 2)
    assert row['resolver_status'] == 'EXTERNAL_DEFINED'
    assert row['ownership_status'] == 'EXTERNAL'
    assert row['placement_evidence_class'] == 'NO_ANCHOR_EVIDENCE'
    line = only_line(result)
    assert line['outcome'] == 'LINE_BLOCKED_NO_ANCHOR_EVIDENCE'
    assert line['reasons'] == ['CROSS_CASE_REFERENCE_NOT_FOLLOWED']
    assert not result['proposals']


def test_cross_feeder_conflict_rejects_every_line():
    x = fx.build(buses=[fx.bus('B1', 'j1')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1')], feeder_count=2)
    ev, result, _ = analyse(x)
    assert ev.gate == ['NON_UNIQUE_FEEDER']
    line = only_line(result)
    assert line['outcome'] == 'LINE_BLOCKED_NON_UNIQUE_PLACEMENT'
    assert line['reasons'] == ['NON_UNIQUE_FEEDER']
    assert not result['proposals']


def test_shared_reference_rule_stays_disabled():
    x = fx.build(buses=[fx.bus('B1', 'j1'), fx.bus('B2', 'j2')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1'), fx.line('L2', 'B2', 'S1')])
    _, result, review = analyse(x)
    assert DEFERRED_RULE not in ANCHOR_RULES and DEFERRED_RULE in DEFERRED_RULES
    assert not [a for a in result['rows']['placement_anchors'] if a['rule_id'] == DEFERRED_RULE]
    assert all(r['disposition'] == 'NEEDS_REVIEW' and r['rule_id'] == DEFERRED_RULE
               for r in review['shared_reference_reviews'])
    assert all(r['deferred_rules'][DEFERRED_RULE] == 'SHARED_REFERENCE_JUNCTION_SEMANTICS_NOT_PROVEN'
               for r in review['shared_reference_reviews'])


def test_parallel_declarations_are_never_reduced_by_picking_one():
    x = fx.build(buses=[fx.bus('B1', 'j1'), fx.bus('B2', 'j2')], accesspoints=[fx.accesspoint('A1')],
                 lines=[fx.line('L1', 'B1', 'A1'), fx.line('L2', 'B1', 'A1')])
    ev, result, _ = analyse(x)
    assert ev.parallel_withdrawal == [r['source_line_record_ref'] for r in result['line_rows']]
    assert not result['proposals']
    assert {r['reasons'][0] for r in result['line_rows']} == {
        'PARALLEL_DUPLICATE_DECLARATION_NOT_REPRESENTABLE'}
    assert result['nodes'] == [] and result['edges'] == []


def test_anchor_keeps_every_port_when_only_one_side_is_represented():
    # L2's far endpoint is undefined, so only L1 is represented; the series anchor must
    # still keep its OUT port rather than leave the proposal pointing at a pruned node.
    x = fx.build(buses=[fx.bus('B1', 'j1')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1'), fx.line('L2', 'S1', 'NOWHERE')])
    ev, result, _ = analyse(x)
    anchor, = result['rows']['placement_anchors']
    assert anchor['rule_id'] == SERIES_RULE and anchor['degree'] == 2
    assert set(anchor['port_ids']) == {n['node_id'] for n in result['nodes']}
    assert len(result['proposals']) == 1
    assert validate_case(x, ev)['reasons'] == []
    assert {r['outcome'] for r in result['line_rows']} == {'LINE_PLACEMENT_PROPOSED',
                                                           'LINE_BLOCKED_NO_ANCHOR_EVIDENCE'}


def test_no_duplicate_source_line_is_generated():
    x = fx.build(buses=[fx.bus('B1', 'j1')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1')])
    _, result, _ = analyse(x)
    assert [e['kind'] for e in result['edges']] == ['SWITCH']
    assert [e['kind'] for e in result['graph_edges']] == ['SWITCH', 'LINE']
    line_edge, = [e for e in result['graph_edges'] if e['kind'] == 'LINE']
    source_lines = {a['canonical_ref']['entity_id'] for a in x['source']['accounts']
                    if a['raw_record']['source_file_type'] == 'LINE'}
    assert line_edge['source_entity_ref']['entity_id'] in source_lines
    assert line_edge['edge_id'] == generated_id('line', x['accepted']['case_id'],
                                                result['line_rows'][0]['feeder_id'], LINE_RULE,
                                                line_edge['source_entity_ref']['entity_id'])
    assert len({p['source_line_ref']['entity_id'] for p in result['proposals']}) == len(result['proposals'])
    for obj in (*result['nodes'], *result['edges'], *result['proposals']):
        assert obj.get('kind') not in ('TRANSFORMER', 'LOAD', 'DER', 'SYNTHETIC_TRANSFORMER')
        assert 'device_id' not in obj and 'devices' not in obj


def test_source_endpoint_text_is_unchanged():
    x = fx.build(buses=[fx.bus('B1', 'j1')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', '  S1  ')])
    before = deepcopy(x)
    _, result, _ = analyse(x)
    assert x == before
    texts = {r['raw_endpoint_value'] for r in result['rows']['line_endpoint_evidence']}
    assert '  S1  ' in texts
    assert not result['proposals']


def test_deterministic_ids_and_repeatability():
    x = fx.build(buses=[fx.bus('B1', 'j1')], switches=[fx.switch('S1'), fx.switch('S2')],
                 accesspoints=[fx.accesspoint('A1')],
                 lines=[fx.line('L1', 'B1', 'S1'), fx.line('L2', 'A1', 'S1'),
                        fx.line('L3', 'S2', 'A1')])
    first = CaseEvidence(x).analyse()
    second = CaseEvidence(x).analyse()
    assert first == second
    assert all(o['node_id'].startswith('d4.1-generated:port:') for o in first['nodes'])
    assert all(o['edge_id'].startswith('d4.1-generated:') for o in first['edges'])
    assert all(p['proposal_id'].startswith('d4.1-generated:line-proposal:') for p in first['proposals'])


def test_iteration_order_never_selects_placement():
    x = fx.build(buses=[fx.bus('B1', 'j1'), fx.bus('B2', 'j2')], switches=[fx.switch('S1')],
                 accesspoints=[fx.accesspoint('A1')],
                 lines=[fx.line('L1', 'B1', 'S1'), fx.line('L2', 'A1', 'S1')])
    reference = CaseEvidence(x).analyse()
    shuffled = deepcopy(x)
    shuffled['source']['accounts'].reverse()
    shuffled['source']['terminals'].reverse()
    shuffled['source']['projections'].reverse()
    shuffled['accepted']['base_nodes'].reverse()
    assert CaseEvidence(shuffled).analyse() == reference


def test_no_hash_or_random_dependency():
    import ast
    from pathlib import Path
    for name in ('generation/placement_evidence.py', 'validation/placement_evidence.py'):
        tree = ast.parse((Path('src/grid_case_generator') / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(a.name in ('random', 'numpy', 'secrets') for a in node.names)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != 'hash', name


@pytest.mark.parametrize('stream', ['nodes_out', 'edges_out', 'proposals', 'placement_anchors'])
def test_unapproved_rule_inferred_fails_validation(stream):
    x = fx.build(buses=[fx.bus('B1', 'j1')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1')])
    ev, result, _ = analyse(x)
    assert validate_case(x, ev)['reasons'] == []
    objects = ev.rows[stream] if stream == 'placement_anchors' else getattr(ev, stream)
    assert objects and all(o['evidence_class'] == 'UNRESOLVED' for o in objects)
    objects[0]['evidence_class'] = 'RULE_INFERRED'
    assert 'UNAPPROVED_RULE_PROVENANCE' in validate_case(x, ev)['reasons']


def test_unresolved_objects_participate_in_counterfactual():
    x = fx.build(buses=[fx.bus('B1', 'j1')], switches=[fx.switch('S1')],
                 lines=[fx.line('L1', 'B1', 'S1')])
    ev, result, _ = analyse(x)
    assert len(result['graph_edges']) == 2
    assert all(o['evidence_class'] == 'UNRESOLVED' for o in result['graph_edges'])
    assert validate_case(x, ev)['structural_status'] == 'PASS'
