from copy import deepcopy
import pytest
from grid_case_generator.generation.synthetic_backbone import propose_case
from grid_case_generator.validation.synthetic_backbone import validate_bundle


def case():
    c = {'case_id':'c','source_case_key':'c','feeders':[{'feeder_id':'f','source_record_refs':['f-row'],'original_flags':[],'d1_primary':'FIXTURE'}],
         'head_id':'h','nominal_voltage_kv':'10.5','hard_blockers':[], 'state_constraints':[],
         'targets':[], 'evidence_refs':[], 's2_usable':False, 'source_line_count':1, 'region_source_refs':{'j':['bus-row']},
         'base_nodes':[{'node_id':x,'case_id':'c','kind':k,'voltage_kv':'10.5','transformer_key':None}
                       for x,k in [('h','HEAD'),('j','JUNCTION'),('t','TRANSFORMER_MV')]],
         'base_edges':[{'edge_id':'line','case_id':'c','a':'j','b':'t','kind':'LINE','conducting':True}]}
    return {'accepted':c,'source':{'accounts':[], 'topology':{'nodes':[]}}}


def test_unique_candidate_and_immutable():
    x=case(); before=deepcopy(x); r=propose_case(x)
    assert len(r['proposal_bundles'])==1
    assert r['proposal_validation'][0]['reasons']==[]
    assert x==before
    assert r['coverage']['physical']['after']['target_coverage']=='NO_SOURCE_TARGET'
    assert r['proposal_junctions']==[]
    assert r['proposal_edges'][0]['evidence_class']=='RULE_GENERATED'


@pytest.mark.parametrize('mutation,reason', [
    ('tie','NON_UNIQUE_ANCHOR'),('components','NON_UNIQUE_COMPONENT'),
    ('hard','HARD_SOURCE_CONTRADICTION'),('voltage','INCOMPATIBLE_VOLTAGE'),
    ('open','UNRESOLVED_OPEN_CUT'),('ownership','NON_UNIQUE_FEEDER')])
def test_gates(mutation,reason):
    x=case(); c=x['accepted']
    if mutation=='tie': c['base_nodes'][2]['kind']='JUNCTION'
    if mutation=='components':
        c['base_nodes'] += [dict(c['base_nodes'][1],node_id='j2'),dict(c['base_nodes'][2],node_id='t2')]
        c['base_edges'].append(dict(c['base_edges'][0],edge_id='line2',a='j2',b='t2'))
    if mutation=='hard': c['hard_blockers']=[{'code':'AMBIGUOUS_IDENTITY','source_refs':['bad']}]
    if mutation=='voltage': c['base_nodes'][1]['voltage_kv']='110'
    if mutation=='ownership': c['feeders'].append({'feeder_id':'f2','source_record_refs':[]})
    if mutation=='open': c['state_constraints']=[{'kind':'SWITCH','state':'OPEN','node_ids':[], 'raw_endpoints':{'Switch_FromBus':'unknown'}}]
    r=propose_case(x)
    assert not r['proposal_edges']
    assert reason in r['rejected_candidates'][0]['reasons']


def test_order_never_selects_anchor():
    x=case(); x['accepted']['base_nodes'][2]['kind']='JUNCTION'
    r=propose_case(x)
    x['accepted']['base_nodes'].reverse(); x['accepted']['base_edges'].reverse()
    assert propose_case(x)==r


@pytest.mark.parametrize('closed',[False,True])
def test_switch_cut_preserved(closed):
    x=case(); c=x['accepted']
    c['base_nodes'].append(dict(c['base_nodes'][2],node_id='out',kind='SWITCH_PORT'))
    c['base_edges'].append({'edge_id':'sw','case_id':'c','a':'t','b':'out','kind':'SWITCH','conducting':closed})
    c['base_nodes'][-1]['transformer_key']='target'
    c['targets']=[{'target_key':'target','identity_unique':True,'source_entity_id':'t','reference_composition':'LINE_ONLY','hv_kv':None,'lv_kv':None,'source_record_refs':['t-row']}]
    r=propose_case(x)
    assert r['coverage']['physical']['after']['reachable_transformers']==1
    assert r['coverage']['conducting']['after']['reachable_transformers']==int(closed)
    assert c['base_edges'][-1]['conducting']==closed


@pytest.mark.parametrize('bad',['case','id','cycle','node','state','voltage'])
def test_validator_rejects_mutation(bad):
    x=case(); b=deepcopy(propose_case(x)['proposal_bundles'][0])
    if bad=='case': b['edges'][0]['case_id']='foreign'
    if bad=='id': b['edges'][0]['edge_id']='line'
    if bad=='cycle': b['edges'][0].update(a='j',b='t')
    if bad=='node': b['nodes']=[{'node_id':'d4-generated:junction:bad','case_id':'c','kind':'SYNTHETIC_JUNCTION'}]
    if bad=='state': b['base_graph_sha256']='stale'
    if bad=='voltage': x['accepted']['base_nodes'][1]['voltage_kv']='110'
    assert validate_bundle(x,b)['reasons']


def test_competing_raw_structure_not_hidden_by_accepted_graph():
    x=case()
    x['source']['accounts']=[{'raw_record':{'source_file_type':'LINE','source_record_ref':str(i),
        'fields':[['Line_FromBus',a],['Line_ToBus',b]]}} for i,(a,b) in enumerate([('a','b'),('c','d')])]
    r=propose_case(x)
    assert not r['proposal_edges']
    assert 'COMPETING_SOURCE_REFERENCE_COMPONENTS' in r['rejected_candidates'][0]['reasons']


def test_source_endpoint_bytes_unchanged():
    x=case(); x['source']['accounts']=[{'raw_record':{'source_file_type':'LINE','source_record_ref':'l',
        'fields':[['Line_FromBus','0001'],['Line_ToBus',' 02 ']]}}]
    before=deepcopy(x);propose_case(x);assert x==before


def test_open_bypass_detected_by_cycle_and_placement():
    x=case();c=x['accepted'];b=deepcopy(propose_case(x)['proposal_bundles'][0])
    c['base_edges'].append({'edge_id':'open','case_id':'c','a':'h','b':'j','kind':'SWITCH','conducting':False})
    from grid_case_generator.validation.topology_proposals import base_hash
    b['base_graph_sha256']=base_hash(c)
    assert validate_bundle(x,b)['reasons']


def test_generated_junction_namespace_is_separate_but_unreviewed():
    from grid_case_generator.generation.synthetic_backbone import generated_id
    x=case();b=deepcopy(propose_case(x)['proposal_bundles'][0])
    nid=generated_id('junction','c','f','placement')
    assert nid.startswith('d4-generated:junction:')
    b['nodes']=[{'node_id':nid,'kind':'SYNTHETIC_JUNCTION','case_id':'c'}]
    assert 'UNREVIEWED_JUNCTION_OR_DEVICE' in validate_bundle(x,b)['reasons']


def test_no_random_topology_dependencies():
    import ast
    from pathlib import Path
    module=Path('src/grid_case_generator/generation/synthetic_backbone.py')
    tree=ast.parse(module.read_text())
    assert not any(isinstance(n,ast.Import) and any(a.name in ('random','numpy') for a in n.names) for n in ast.walk(tree))


def test_eligibility_independently_recomputed():
    from grid_case_generator.analysis.deterministic_recovery import eligibility
    x=case();r=propose_case(x);c=deepcopy(x['accepted']);c['base_edges']+=r['proposal_edges']
    assert [row['after'] for row in r['d2_eligibility_counterfactual']]==eligibility(c)


def test_cross_case_base_rejected():
    x=case();x['accepted']['base_nodes'][1]['case_id']='foreign'
    assert not propose_case(x)['proposal_edges']


@pytest.mark.parametrize('gate',['raw_components','bundle_provenance','earthing','nominal','raw_open'])
def test_independent_validator_checks_source_and_rule_gates(gate):
    x=case();b=deepcopy(propose_case(x)['proposal_bundles'][0]);c=x['accepted']
    if gate=='bundle_provenance':b['evidence_class']='SOURCE_CONFIRMED'
    if gate=='raw_components':
        x['source']['accounts']=[{'raw_record':{'source_file_type':'LINE','source_record_ref':str(i),
            'fields':[['Line_FromBus',str(i)],['Line_ToBus',str(i+10)]]}} for i in range(2)]
    if gate=='earthing':c['state_constraints']=[{'kind':'EARTHING_SWITCH','state':'CLOSED','node_ids':['j'],'source_record_ref':'earth'}]
    if gate=='nominal':c['nominal_voltage_kv']='110'
    if gate=='raw_open':
        x['source']['topology']['nodes']=[{'node_id':'j','source_entity_ref':{'entity_id':'bus'}}]
        x['source']['accounts']=[{'canonical_ref':{'entity_id':'bus'},'raw_record':{'source_file_type':'BUS','fields':[['Bus_ID','raw-bus']]}}]
        c['state_constraints']=[{'kind':'SWITCH','state':'OPEN','node_ids':['t'],'raw_endpoints':{'Switch_ToBus':'raw-bus'},'source_record_ref':'s'}]
    from grid_case_generator.validation.topology_proposals import base_hash
    b['base_graph_sha256']=base_hash(c)
    assert validate_bundle(x,b)['reasons']


def test_existing_complete_backbone_is_not_manual_layout():
    x=case();x['accepted']['base_edges'].append({'edge_id':'head-line','case_id':'c',
        'a':'h','b':'j','kind':'LINE','conducting':True})
    r=propose_case(x)
    assert not r['proposal_edges']
    assert r['feeder_gap_taxonomy'][0]['outcome']=='NO_BACKBONE_ACTION_REQUIRED'
