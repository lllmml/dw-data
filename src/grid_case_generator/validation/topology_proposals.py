"""Independent proposal validation and physical/conducting counterfactual metrics."""
from hashlib import sha256

from grid_case_generator.analysis.completion_profiles import graph_profile
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.models.proposals import positive_voltage, voltage_compatible


def base_hash(c):
    return sha256(canonical_json_bytes({'nodes':sorted(c['base_nodes'],key=lambda n:n['node_id']),
        'edges':sorted(c['base_edges'],key=lambda e:e['edge_id']),
        'states':sorted(c['state_constraints'],key=lambda s:s['source_record_ref'])})).hexdigest()


def measure_graph(c,nodes=None,edges=None,devices=(),*,physical=False):
    ns=c['base_nodes'] if nodes is None else nodes;es=c['base_edges'] if edges is None else edges
    ids={n['node_id'] for n in ns}
    triples=[(e['a'],e['b'],physical or e['conducting']) for e in es]
    g=graph_profile(ids,triples,c['head_id'],set())
    seen=set(g['reachable_node_ids']);reached={n['transformer_key'] for n in ns if n.get('transformer_key') and n['node_id'] in seen}
    targets={t['target_key'] for t in c['targets']};model_targets=targets|{d['target_key'] for d in devices}
    n=len(reached & targets)
    status='NO_SOURCE_TARGET' if not targets else 'FULL' if n==len(targets) else 'PARTIAL' if n else 'FAILED'
    return {'components':g['conducting_components'],'cycle_rank':g['conducting_cycle_rank'],
        'node_count':len(ns),'edge_count':len(es),'reachable_lines':sum(e['kind']=='LINE' and (physical or e['conducting']) and e['a'] in seen and e['b'] in seen for e in es),
        'reachable_transformers':n,'target_count':len(targets),'target_coverage':status,
        'reachable_model_transformers':len(reached & model_targets),'model_target_count':len(model_targets),
        'maximum_degree':g['maximum_conducting_degree'],
        'disconnected_synthetic_nodes':sum(n.get('evidence_class')=='RULE_GENERATED' and n['node_id'] not in seen for n in ns)}


def validate_bundle(c,b):
    errors=set();assumptions=set(b.get('assumptions',[]))
    required={'bundle_id','case_id','feeder_id','kind','source_target_key','nodes','edges','devices',
        'assumptions','source_refs','business_refs','evidence_refs','rule_id','rule_version','config_hash',
        'base_graph_sha256','evidence_class','stage','lifecycle'}
    if set(b)!=required:errors.add('BUNDLE_SCHEMA_MISMATCH')
    if b.get('stage') not in ('PROPOSED','VALIDATED'):errors.add('LIFECYCLE_NOT_ALLOWED')
    if b.get('case_id')!=c['case_id'] or b.get('feeder_id') not in {f['feeder_id'] for f in c['feeders']}:errors.add('CROSS_CASE_CONNECTION')
    if b.get('base_graph_sha256')!=base_hash(c):errors.add('BASE_OR_SOURCE_STATE_CHANGED')
    nodes={n['node_id']:n for n in c['base_nodes']};base_ids=set(nodes)
    new_ids=[n['node_id'] for n in b['nodes']]
    if len(set(new_ids))!=len(new_ids) or base_ids & set(new_ids):errors.add('DUPLICATE_GENERATED_NODE')
    nodes.update({n['node_id']:n for n in b['nodes']})
    for obj in [*b['nodes'],*b['edges'],*b['devices']]:
        if obj['case_id']!=c['case_id'] or obj.get('feeder_id')!=b['feeder_id']:errors.add('CROSS_CASE_CONNECTION')
        if obj.get('evidence_class')!='RULE_GENERATED':errors.add('FALSE_SOURCE_PROVENANCE')
    source_targets={t['target_key']:t for t in c['targets']}
    devices=[d['device_id'] for d in b['devices']]
    if len(set(devices))!=len(devices):errors.add('DUPLICATE_SYNTHETIC_DEVICE')
    if any(d['target_key'] in source_targets or d.get('source_entity_id') for d in b['devices']):errors.add('DUPLICATE_SOURCE_TRANSFORMER')
    if b['source_target_key'] is not None:
        target=source_targets.get(b['source_target_key'])
        if not target or not target['identity_unique']:errors.add('AMBIGUOUS_IDENTITY')
        elif target['reference_composition']!='NO_REFERENCE':errors.add('EXISTING_ENDPOINT_EVIDENCE')
        if any(n.get('transformer_key')==b['source_target_key'] for n in c['base_nodes']):errors.add('DUPLICATE_ATTACHMENT')
    pairs={tuple(sorted((e['a'],e['b']))) for e in c['base_edges']};edge_ids={e['edge_id'] for e in c['base_edges']}
    base_contacts=set()
    for e in b['edges']:
        if e['edge_id'] in edge_ids:errors.add('DUPLICATE_SEMANTIC_EDGE')
        edge_ids.add(e['edge_id']);pair=tuple(sorted((e['a'],e['b'])))
        if pair in pairs:errors.add('DUPLICATE_SEMANTIC_EDGE')
        pairs.add(pair)
        if e['a']==e['b']:errors.add('INVALID_SELF_LOOP')
        if e['a'] not in nodes or e['b'] not in nodes:
            errors.add('DANGLING_GENERATED_REFERENCE');continue
        base_contacts.update({e['a'],e['b']} & base_ids)
        try:
            a,bv=nodes[e['a']]['voltage_kv'],nodes[e['b']]['voltage_kv']
            if e['kind']=='TRANSFORMER_TRANSFER':
                if positive_voltage(a)<=positive_voltage(bv) or not e.get('transformer_key'):errors.add('UNKNOWN_TRANSFORMER_DIRECTION')
            elif not voltage_compatible(a,bv):errors.add('INCOMPATIBLE_VOLTAGE')
        except ValueError:errors.add('INVALID_VOLTAGE')
    if len(base_contacts)>1:errors.add('UNSAFE_COMPONENT_BRIDGE_OR_OPEN_BYPASS')
    for state in c['state_constraints']:
        if state['kind']=='EARTHING_SWITCH' and state['state']=='CLOSED' and set(state['node_ids']) & base_contacts:
            errors.add('CLOSED_EARTHING_AT_ATTACHMENT')
    for n in b['nodes']:
        try:positive_voltage(n['voltage_kv'])
        except ValueError:errors.add('INVALID_VOLTAGE')
        target=source_targets.get(n.get('transformer_key'))
        if target and target['hv_kv']:
            try:
                if not voltage_compatible(target['hv_kv'],n['voltage_kv']):errors.add('INCOMPATIBLE_VOLTAGE')
            except ValueError:errors.add('INVALID_SOURCE_VOLTAGE')
    if not errors:
        before=measure_graph(c,physical=True)
        after=measure_graph(c,list(nodes.values()),c['base_edges']+b['edges'],b['devices'],physical=True)
        if after['cycle_rank']!=before['cycle_rank']:errors.add('NEW_CYCLE')
        if after['disconnected_synthetic_nodes']:errors.add('DISCONNECTED_PHYSICAL_SYNTHETIC_NODE')
    return {'bundle_id':b['bundle_id'],'case_id':c['case_id'],'structural_status':'REJECTED' if errors else 'PASS',
        'electrical_sanity':'REJECTED' if errors else 'ASSUMPTION' if assumptions else 'PASS',
        'reasons':sorted(errors),'assumptions':sorted(assumptions),
        'stage':'PROPOSED' if errors or assumptions else 'VALIDATED',
        'scope':'STRUCTURE_AND_DECLARED_VOLTAGE_ONLY','approved':False,'applied':False,
        'e3_ready':False,'opendss_ready':False,'source_state_preserved':'BASE_OR_SOURCE_STATE_CHANGED' not in errors}
