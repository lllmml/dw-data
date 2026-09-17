"""D3 rule gates precede the implementation; source and v1 remain immutable."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import json

import pytest
from source_fixture import mapped
from test_switch_semantics import fixture
from grid_case_generator.generation.topology import interpret_topology
from grid_case_generator.models.topology import TopologyConfig
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.generation.deterministic_recovery import recover_case
from grid_case_generator.analysis.deterministic_recovery import make_input, eligibility
from grid_case_generator.validation.topology_proposals import measure_graph


def prepare(rows):
    details = mapped(rows)
    base = interpret_topology(details, TopologyConfig(Decimal('10.5')))
    return details, base, make_input(details, base)


@pytest.mark.parametrize('state,conducting', [('Open', False), ('Closed', True)])
def test_state_and_source_invariance(state, conducting):
    details, base, c = prepare(fixture(state=state))
    before = canonical_json_bytes((details, base, c))
    r = recover_case(c)
    switch = [e for e in r['additions'] if e.get('kind') == 'SWITCH']
    assert len(switch) == 1 and switch[0]['conducting'] is conducting
    after = r['topology']
    assert measure_graph(after, physical=True)['reachable_transformers'] == 1
    assert measure_graph(after)['reachable_transformers'] == int(conducting)
    assert canonical_json_bytes((details, base, c)) == before
    assert all(o['evidence_class'] == 'RULE_INFERRED' for o in r['additions'])
    for key in ('base_nodes', 'base_edges'):
        assert all(x in after[key] for x in c['base'][key])


@pytest.mark.parametrize('gate', ['inner', 'outer', 'state', 'tie', 'identity', 'voltage', 'degree', 'direction', 'reverse', 'collapsed'])
def test_required_preconditions(gate):
    rows = fixture()
    if gate == 'inner': rows['LINE'][1]['Line_ToBus'] = 'missing'
    if gate == 'outer': rows['SWITCH'][0]['Switch_ToBus'] = 'missing'
    if gate == 'state': rows['SWITCH'][0]['Switch_NormalState'] = 'UNKNOWN'
    if gate == 'tie': rows['SWITCH'][0]['Switch_IsTie'] = 'True'
    if gate == 'identity': rows['SWITCH'].append(dict(rows['SWITCH'][0]))
    if gate == 'voltage': rows['BUS'][1]['Bus_BaseKV'] = '110'
    if gate == 'degree': rows['LINE'].append({'Line_ID': 'extra', 'Line_FromBus': 's', 'Line_ToBus': 'b'})
    if gate == 'direction': rows['LINE'][2].update(Line_FromBus='b', Line_ToBus='s')
    if gate == 'reverse': rows['SWITCH'][0].update(Switch_FromBus='b', Switch_ToBus='a')
    if gate == 'collapsed': rows['LINE'][2]['Line_ToBus'] = 'a'; rows['SWITCH'][0]['Switch_ToBus'] = 'a'
    _, _, c = prepare(rows)
    assert not recover_case(c)['additions']


def test_cross_case_fails_closed():
    _, _, c = prepare(fixture())
    c['accounts'][0]['raw_record']['source_case_key'] = 'foreign'
    with pytest.raises(ValueError, match='case'):
        recover_case(c)


def test_conflict_never_overridden():
    _, _, c = prepare(fixture())
    c['base']['hard_blockers'] = [{'code': 'AMBIGUOUS_IDENTITY', 'source_refs': ['conflict'], 'scope': 'CASE'}]
    assert not recover_case(c)['additions']


def test_leaf_unbound_not_bridge():
    rows = fixture(); rows['LINE'] = rows['LINE'][:2]; rows['SWITCH'][0]['Switch_ToBus'] = ''
    _, _, c = prepare(rows)
    r = recover_case(c)
    assert len([n for n in r['additions'] if n.get('port_role') == 'UNBOUND']) == 1
    assert measure_graph(r['topology'], physical=True)['reachable_transformers'] == 0


def test_multi_transformer_not_collapsed():
    rows = fixture(); rows['LINE'].append({'Line_ID': 'extra', 'Line_FromBus': 'a', 'Line_ToBus': 't'})
    _, _, c = prepare(rows)
    r = recover_case(c)
    assert not any(n.get('transformer_key') for n in r['additions'])
    assert any(x['family'] == 'MULTI_INCOMING_TRANSFORMER_REVIEW' and x['status'] != 'ACCEPTED' for x in r['candidates'])


def test_no_lexical_or_iteration_selection():
    details, base, c = prepare(fixture())
    shuffled = replace(details, records=tuple(reversed(details.records)), accounting=tuple(reversed(details.accounting)))
    assert canonical_json_bytes(recover_case(c)) == canonical_json_bytes(recover_case(make_input(shuffled, base)))


def test_cycle_reported_and_retained():
    rows = fixture(); rows['LINE'].append({'Line_ID': 'parallel', 'Line_FromBus': 'a', 'Line_ToBus': 'b'})
    _, _, c = prepare(rows)
    r = recover_case(c)
    assert r['coverage']['physical']['after']['cycle_rank'] - r['coverage']['physical']['before']['cycle_rank'] == 1


def test_eligibility_is_read_only():
    _, _, c = prepare(fixture())
    before = deepcopy(c)
    result = eligibility(recover_case(c)['topology'])
    assert result and all('primary_class' in r for r in result)
    assert c == before
    assert 'RULE_GENERATED' not in json.dumps(result)


def test_explicit_transformer_voltage_not_overridden():
    rows = fixture(y='t'); rows['LINE'] = rows['LINE'][:3]
    rows['LINE'][2]['Line_ToBus'] = 't'
    rows['TRANSFORMER'][0]['Transformer_HighVoltage_kV'] = '110'
    _, _, c = prepare(rows)
    assert not recover_case(c)['additions']


def test_no_unknown_region_tie_break():
    from grid_case_generator.generation.deterministic_recovery import recover_case
    rows = fixture(); rows['TRANSFORMER'].append({'Transformer_ID':'orphan'})
    _, _, c = prepare(rows)
    model = recover_case(c)['topology']
    result = eligibility(model)[0]
    assert result['candidate_region_count'] == 2
    assert result['synthetic_candidate_count'] == 0
    assert result['missing_region_count'] == 1
