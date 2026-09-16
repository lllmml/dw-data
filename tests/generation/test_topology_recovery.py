from dataclasses import replace
from decimal import Decimal

import pytest
from source_fixture import mapped
from test_switch_semantics import fixture
from grid_case_generator.generation.topology import interpret_topology
from grid_case_generator.models.topology import TopologyConfig
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.analysis.topology_recovery import analyze_recovery_case, LEAF, UNIQUE_T, MULTI_T, RISK_T


def analyze(rows, reverse=False):
    details = mapped(rows)
    baseline = interpret_topology(details, TopologyConfig(Decimal('10.5')))
    if reverse:
        details = replace(details, records=tuple(reversed(details.records)), accounting=tuple(reversed(details.accounting)))
    files = [{'source_file_type': f.source_file_type.value, 'member_path': f.member_path,
              'header': list(f.header), 'row_count': len(f.records)} for f in details.files]
    before = canonical_json_bytes((details.records, details.accounting, baseline))
    result = analyze_recovery_case(details, baseline, files)
    assert canonical_json_bytes((details.records, details.accounting, baseline)) == before
    return result


def feeder(result):
    return result['feeders'][0]


def transformer(result, raw_id):
    return next(t for t in result['transformers'] if t['source_id'] == raw_id)


def test_zero_row_no_vacuous_full():
    rows = fixture(); rows['TRANSFORMER'] = []; rows['LINE'] = []
    r = analyze(rows); f = feeder(r)
    assert f['target_coverage'] == 'NO_SOURCE_TARGET'
    assert f['source_evidence_cohort'] == 'ZERO_TRANSFORMER_ROWS'
    assert f['recovery_readiness'] == 'ROLE_UNDETERMINED'
    assert r['transformer_file_evidence']['row_count'] == 0
    assert f['completion_cohorts'] == ['B']
    assert not f['e3_ready']


def test_missing_file_not_called_zero_row():
    details = mapped({'TRANSFORMER': []})
    b = interpret_topology(details, TopologyConfig(Decimal('10.5')))
    r = analyze_recovery_case(details, b, [])
    assert r['source_evidence_cohort'] == 'SOURCE_FILE_UNDETERMINED'


def test_transformer_reference_composition_and_readiness():
    rows = fixture(y='t')
    rows['TRANSFORMER'] += [{'Transformer_ID': 'orphan'}, {'Transformer_ID': 'only_switch'}]
    rows['SWITCH'].append({'Switch_ID': 'decl', 'Switch_ToBus': 'only_switch'})
    r = analyze(rows)
    assert transformer(r, 'orphan')['reference_composition'] == 'NO_REFERENCE'
    assert transformer(r, 'only_switch')['reference_composition'] == 'SWITCH_ONLY'
    assert transformer(r, 't')['reference_composition'] == 'LINE_AND_SWITCH'
    assert feeder(r)['source_evidence_cohort'] == 'HAS_UNREFERENCED_TRANSFORMER'
    assert 'A' in feeder(r)['completion_cohorts']
    assert transformer(analyze(fixture()), 't')['reference_composition'] == 'LINE_ONLY'


def test_exact_does_not_promote_s2_or_candidates():
    r = analyze(fixture())
    assert feeder(r)['target_coverage'] == 'FULL'
    assert not feeder(r)['e3_ready']
    assert any(c['evidence_class'] == 'UNRESOLVED' for c in r['connections'] if c['policy'] == 'S2')
    assert all(c['evidence_class'] != 'SOURCE_CONFIRMED' for c in r['connections'])
    assert feeder(r)['evidence_composition']['synthetic_connections'] == 0
    assert 'NEEDS_RULE_REVIEW' in feeder(r)['readiness_reasons']


def test_duplicate_transformer_not_selected():
    rows = fixture(); rows['TRANSFORMER'].append({'Transformer_ID': 't'})
    r = analyze(rows); t = transformer(r, 't')
    assert t['identity_ambiguous']
    assert not t['attachment']['S2']['reachable']
    assert 'D' in feeder(r)['completion_cohorts']
    assert t['incoming_references'][0]['diagnostic_status'] == 'AMBIGUOUS'


def test_unresolved_own_reference_is_not_no_evidence():
    rows = fixture(); rows['TRANSFORMER'] = [{'Transformer_ID': 't', 'Transformer_FromBus': 'missing'}]
    r = analyze(rows); t = transformer(r, 't')
    assert t['unresolved_reference']
    assert t['outgoing_references'][0]['raw_value'] == 'missing'


def test_known_open_frontier_and_conflict_cohort():
    r = analyze(fixture(state='Open'))
    f = feeder(r)
    assert 'KNOWN_OPEN' in f['observed_blockers']
    assert 'D' in f['completion_cohorts']
    assert f['recovery_readiness'] == 'BLOCKED_BY_CONFLICT'
    assert all(p['reachable_transformers'] == 0 for p in r['experiments'].values())


def test_voltage_accesspoint_multiple_boundaries():
    rows = fixture()
    rows['BUS'].append({'Bus_ID': 'hv', 'Bus_BaseKV': '110'})
    rows['ACCESS_POINT'] = [{'AccessPoint_ID': 'ap'}]
    rows['LINE'] += [{'Line_ID': 'v', 'Line_FromBus': 'a', 'Line_ToBus': 'hv'},
                     {'Line_ID': 'apline', 'Line_FromBus': 'a', 'Line_ToBus': 'ap'},
                     {'Line_ID': 'missing', 'Line_FromBus': 'a', 'Line_ToBus': 'unknown'}]
    f = feeder(analyze(rows))
    assert {'VOLTAGE_CONFLICT', 'ACCESS_POINT_UNSUPPORTED', 'ENDPOINT_UNRESOLVED'} <= set(f['observed_blockers'])
    assert f['primary_blocker'] == 'VOLTAGE_CONFLICT'
    assert f['recovery_readiness'] == 'BLOCKED_BY_CONFLICT'


def test_leaf_representation_not_applied_and_no_fake_target():
    rows = fixture(); rows['LINE'] = rows['LINE'][:2]; rows['TRANSFORMER'] = []
    rows['SWITCH'][0]['Switch_ToBus'] = ''
    r = analyze(rows)
    w, = [w for w in r['candidates'] if w['rule_id'] == LEAF]
    assert w['evidence_class'] == 'UNRESOLVED' and not w['approved']
    assert w['supporting_source_refs'] and w['source_terminal_refs']
    assert r['experiments'][LEAF]['target_coverage'] == 'NO_SOURCE_TARGET'
    assert r['graphs']['S2']['reachable_lines'] == 1
    assert r['experiments'][LEAF]['reachable_lines'] == 2


def test_unique_switch_attachment_gain_only_counterfactual():
    rows = fixture(y='orphan'); rows['TRANSFORMER'].append({'Transformer_ID': 'orphan'})
    r = analyze(rows)
    assert len([w for w in r['candidates'] if w['rule_id'] == UNIQUE_T]) == 1
    assert r['graphs']['S2']['reachable_transformers'] == 1
    assert r['experiments'][UNIQUE_T]['reachable_transformers'] == 2
    assert not transformer(r, 'orphan')['attachment']['S2']['projected']
    rows['SWITCH'].append({'Switch_ID': 'another', 'Switch_ToBus': 'orphan'})
    assert not any(w['rule_id'] == UNIQUE_T for w in analyze(rows)['candidates'])


def test_multi_incoming_not_mixed_and_duplicate_incidence_excluded():
    rows = fixture(); rows['LINE'].append({'Line_ID': 'tail2', 'Line_FromBus': 'b', 'Line_ToBus': 't'})
    r = analyze(rows)
    assert r['graphs']['S2']['reachable_transformers'] == 0
    assert r['experiments'][MULTI_T]['reachable_transformers'] == 1
    assert {w['rule_id'] for w in r['candidates']} >= {MULTI_T, RISK_T}
    rows['LINE'][-1]['Line_FromBus'] = 't'; rows['LINE'][-1]['Line_ToBus'] = 'b'
    assert not any(w['rule_id'] == MULTI_T for w in analyze(rows)['candidates'])
    rows['LINE'].append(dict(rows['LINE'][-1]))
    assert not any(w['rule_id'] in (MULTI_T, RISK_T) for w in analyze(rows)['candidates'])


def test_order_reversal_byte_identical():
    rows = fixture(y='orphan'); rows['TRANSFORMER'].append({'Transformer_ID': 'orphan'})
    assert canonical_json_bytes(analyze(rows)) == canonical_json_bytes(analyze(rows, reverse=True))


def test_no_feeder_and_multiple_feeders_keep_case_evidence():
    rows = fixture(); rows['FEEDER'] = []
    r = analyze(rows); assert not r['feeders'] and r['transformers']
    rows = fixture(); rows['FEEDER'].append({'Feeder_ID': 'f2', 'Feeder_SourceBus': 'up'})
    r = analyze(rows)
    assert len(r['feeders']) == 2
    assert all(f['recovery_readiness'] == 'ROLE_UNDETERMINED' and 'D' in f['completion_cohorts'] for f in r['feeders'])


def test_candidate_preserves_existing_accepted_switch_ports():
    rows=fixture(x='',y='')
    rows['LINE'][2]['Line_ToBus']='t'
    r=analyze(rows)
    assert r['graphs']['S0']==r['graphs']['S2']
    assert r['experiments'][MULTI_T]['reachable_transformers']==1
    assert all(c['approved'] for c in r['connections'])


def test_missing_header_not_certified_as_zero_row_source():
    rows=fixture();rows['TRANSFORMER']=[];details=mapped(rows)
    b=interpret_topology(details,TopologyConfig(Decimal('10.5')))
    files=[{'source_file_type':'TRANSFORMER','member_path':'case/09_Transformer.csv','row_count':0,'header':None}]
    assert analyze_recovery_case(details,b,files)['source_evidence_cohort']=='SOURCE_FILE_UNDETERMINED'
