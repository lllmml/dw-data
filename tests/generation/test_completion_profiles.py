from copy import deepcopy
from decimal import Decimal
import json

from source_fixture import mapped
from test_switch_semantics import fixture
from test_topology_recovery import analyze
from grid_case_generator.generation.topology import interpret_topology
from grid_case_generator.models.topology import TopologyConfig
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.analysis.completion_profiles import build_profile, graph_profile
from grid_case_generator.analysis.completion_contract import evaluate
from grid_case_generator.models.completion import CompletionFacts


def profile(rows=None):
    rows = fixture() if rows is None else rows
    d = mapped(rows)
    top = interpret_topology(d, TopologyConfig(Decimal('10.5')))
    r = json.loads(canonical_json_bytes(analyze(rows)))
    raw = json.loads(canonical_json_bytes(d.accounting))
    topology = json.loads(canonical_json_bytes(top.topology))
    return build_profile(r, raw, topology, r['transformers'], r['connections'], r['blockers'])


def test_source_reordered_profiles_equal_and_inputs_immutable():
    d = mapped(fixture()); r = json.loads(canonical_json_bytes(analyze(fixture())))
    raw = json.loads(canonical_json_bytes(d.accounting))
    topology = json.loads(canonical_json_bytes(interpret_topology(d, TopologyConfig(Decimal('10.5'))).topology))
    args = [r, raw, topology, r['transformers'], r['connections'], r['blockers']]
    before = deepcopy(args)
    a = build_profile(*args)
    b = build_profile(r, list(reversed(raw)), topology, list(reversed(r['transformers'])),
                      list(reversed(r['connections'])), list(reversed(r['blockers'])))
    assert a == b and args == before
    assert a['graphs']['S2']['target_coverage'] == 'FULL'
    f = CompletionFacts.from_dict(a['feeders'][0]['facts'])
    assert evaluate(f)['evidence_class'] == 'UNRESOLVED'
    assert not f.ownership_confirmed


def test_multigraph_components_parallel_self_loop_and_hops():
    nodes = {'h', 'a', 'b', 'isolated'}
    edges = [('h','a',True), ('h','a',True), ('a','a',True), ('a','b',False)]
    g = graph_profile(nodes, edges, 'h', {'a'})
    assert g['structural_components'] == 2
    assert g['conducting_components'] == 3
    assert g['conducting_cycle_rank'] == g['structural_cycle_rank'] == 2
    assert g['parallel_excess'] == g['self_loops'] == 1
    assert g['candidate_junctions'] == [{'node_id':'a','hops':1,'degree':4}]


def test_zero_rows_missing_demands_and_simconfig_do_not_grant_role():
    rows = fixture(); rows['TRANSFORMER'] = []; rows['LINE'] = []
    p = profile(rows)
    d = evaluate(CompletionFacts.from_dict(p['feeders'][0]['facts']))
    assert d['role_assessment'] == 'ROLE_UNDETERMINED'
    assert not any(x['eligible'] for x in d['operations'].values())


def test_open_not_at_frontier_still_blocks_conservative_profile():
    rows = fixture()
    rows['SWITCH'].append({'Switch_ID':'isolated-open','Switch_NormalState':'Open'})
    p = profile(rows)
    assert 'KNOWN_OPEN_PRESENT' in p['feeders'][0]['facts']['explicit_prohibitions']
    assert p['source']['state_counts']['SWITCH:OPEN'] >= 1


def test_earthing_state_not_series_open_and_closed_is_conservative_veto():
    rows=fixture();rows['EARTHING_SWITCH']=[{'EarthingSwitch_ID':'earth','EarthingSwitch_State':'Open'}]
    p=profile(rows)
    assert 'EXISTING_NEGATIVE_SOURCE_EVIDENCE' not in p['feeders'][0]['facts']['explicit_prohibitions']
    rows['EARTHING_SWITCH'][0]['EarthingSwitch_State']='Closed'
    p=profile(rows)
    assert 'EXISTING_NEGATIVE_SOURCE_EVIDENCE' in p['feeders'][0]['facts']['explicit_prohibitions']
