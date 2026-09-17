from copy import deepcopy

import pytest
from grid_case_generator.analysis.topology_proposals import propose_case
from grid_case_generator.validation.topology_proposals import validate_bundle, measure_graph
from grid_case_generator.models.proposals import unknown_decision


def case_input():
    return {'case_id':'case:a','source_case_key':'a','feeders':[{'feeder_id':'feeder:a','source_record_refs':['feeder-row'],
        'original_flags':['A'],'d1_primary':'BLOCKED_BY_SOURCE_CONFLICT'}],
        'hard_blockers':[], 'state_constraints':[], 'head_id':'head','nominal_voltage_kv':'10.5',
        's2_usable':True,'source_line_count':1,
        'base_nodes':[{'node_id':n,'case_id':'case:a','voltage_kv':'10.5','kind':k,'transformer_key':None}
            for n,k in [('head','HEAD'),('j','JUNCTION')]],
        'base_edges':[{'edge_id':'line','a':'head','b':'j','conducting':True,'kind':'LINE','case_id':'case:a'}],
        'targets':[{'target_key':'t','source_entity_id':'equipment:t','identity_unique':True,
            'reference_composition':'NO_REFERENCE','hv_kv':None,'lv_kv':None,'source_record_refs':['t-row']}],
        'evidence_refs':['d1:profile'],'region_source_refs':{'j':['bus-row']}}


def run(c=None,d=None):return propose_case(case_input() if c is None else c,{} if d is None else {('case:a','feeder:a'):d},'a'*64)


def test_missing_evidence_generates_explicit_engineering_proposal_not_source_fact():
    c=case_input();before=deepcopy(c);r=run(c)
    assert c==before
    assert r['feeder_eligibility'][0]['primary_class']=='SYNTHETIC_ATTACHMENT_ELIGIBLE'
    assert len(r['proposal_bundles'])==1
    b=r['proposal_bundles'][0]
    assert all(x['evidence_class']=='RULE_GENERATED' for x in b['nodes']+b['edges'])
    assert b['stage']=='PROPOSED' and 'ASSUMED_MV_SIDE' in b['assumptions']
    assert r['coverage']['conducting']['before']['target_coverage']=='FAILED'
    assert r['coverage']['conducting']['after']['target_coverage']=='FULL'
    assert not any(x['kind']=='SYNTHETIC_TRANSFORMER' for x in b['devices'])


def test_open_is_physical_not_whole_case_veto_or_automatic_closure():
    c=case_input();c['base_edges'][0]['conducting']=False;c['base_edges'][0]['kind']='SWITCH'
    c['base_nodes'].append({'node_id':'k','case_id':'case:a','voltage_kv':'10.5','kind':'OTHER','transformer_key':None})
    c['base_edges'].append({'edge_id':'line2','a':'j','b':'k','conducting':True,'kind':'LINE','case_id':'case:a'})
    c['state_constraints']=[{'kind':'SWITCH','state':'OPEN','raw_state':'Open','node_ids':[], 'source_record_ref':'sw-row'}]
    r=run(c)
    assert len(r['proposal_bundles'])==1
    assert r['coverage']['physical']['after']['target_coverage']=='FULL'
    assert r['coverage']['conducting']['after']['target_coverage']=='FAILED'
    assert c['base_edges'][0]['conducting'] is False


@pytest.mark.parametrize('code',['AMBIGUOUS_IDENTITY','INCOMPATIBLE_VOLTAGE','OWNERSHIP_CONFLICT'])
def test_witnessed_hard_conflict_still_forbids(code):
    c=case_input();c['hard_blockers']=[{'code':code,'source_refs':['conflict-row']}]
    r=run(c)
    assert not r['proposal_bundles']
    assert r['feeder_eligibility'][0]['primary_class']=='HARD_SOURCE_CONTRADICTION'
    assert r['rejected_candidates'][0]['reasons']==[code]


def test_explicit_transformer_voltage_conflict_rejected_not_assumed_away():
    c=case_input();c['targets'][0]['hv_kv']='20'
    r=run(c);assert not r['proposal_bundles']
    assert r['feeder_eligibility'][0]['primary_class']=='HARD_SOURCE_CONTRADICTION'
    assert 't-row' in r['feeder_eligibility'][0]['conflicting_source_refs']
    assert any('INCOMPATIBLE_VOLTAGE' in x['reasons'] for x in r['rejected_candidates'])


def test_zero_transformer_requires_business_confirmation_and_no_default_count():
    c=case_input();c['targets']=[]
    assert not run(c)['proposal_bundles']
    d=unknown_decision('case:a','feeder:a');d.update(role='DISTRIBUTION_WITH_TRANSFORMER',transformer_required=True,
        synthetic_transformer_allowed=True,transformer_count=2,demand_basis='business:demand',
        nominal_voltage_kv='10.5',lv_voltage_kv='0.4',confirmation_ref='business:approved')
    r=run(c,d);assert len(r['proposal_bundles'])==2
    assert sum(len(b['devices']) for b in r['proposal_bundles'])==2
    assert r['coverage']['conducting']['after']['target_coverage']=='NO_SOURCE_TARGET'
    assert r['coverage']['conducting']['after']['model_target_count']==2


def test_candidate_local_earthing_and_unlocated_state_distinguished():
    c=case_input();c['state_constraints']=[{'kind':'EARTHING_SWITCH','state':'CLOSED','raw_state':'Closed','node_ids':[], 'source_record_ref':'e-row'}]
    assert run(c)['proposal_bundles']
    c['state_constraints'][0]['node_ids']=['j']
    assert not run(c)['proposal_bundles']


def test_cross_case_self_loop_and_dangling_proposals_rejected():
    c=case_input();b=run(c)['proposal_bundles'][0]
    for mutation in ['case','dangling','loop']:
        bad=deepcopy(b)
        if mutation=='case':bad['nodes'][0]['case_id']='case:other'
        elif mutation=='dangling':bad['edges'][0]['b']='missing'
        else:bad['edges'][0]['b']=bad['edges'][0]['a']
        assert validate_bundle(c,bad)['structural_status']=='REJECTED'


def test_reordering_and_multiple_regions_never_select_first_id():
    c=case_input();c['targets'].append(dict(c['targets'][0],target_key='t2',source_entity_id='equipment:t2'))
    r=run(c);c['targets'].reverse();c['base_nodes'].reverse()
    assert r==run(c)
    c['base_nodes'].append({'node_id':'z','case_id':'case:a','voltage_kv':'10.5','kind':'JUNCTION','transformer_key':None})
    c['base_edges'].append({'edge_id':'line3','a':'j','b':'z','conducting':True,'kind':'LINE','case_id':'case:a'})
    assert not run(c)['proposal_bundles']
