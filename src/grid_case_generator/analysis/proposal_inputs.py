"""Explicit source/state snapshots; D1 whole-case state prohibitions are not reused."""
from collections import defaultdict

from grid_case_generator.analysis.completion_contract import evaluate
from grid_case_generator.models.completion import CompletionFacts


def build_case_input(profile,accounts,topology,transformers,exclusions):
    cid=profile['case_id']
    if topology['case_id']!=cid or any(t['case_id']!=cid for t in transformers):raise ValueError('D2 case binding mismatch')
    feeders=[]
    for f in profile['feeders']:
        fact=CompletionFacts.from_dict(f['facts'])
        feeders.append({'feeder_id':fact.feeder_id,'source_record_refs':f['source_record_refs'],
            'original_flags':list(fact.flags),'d1_primary':evaluate(fact)['primary_action']})
    raw_by_locator={a['raw_record']['source_record_ref']:a for a in accounts}
    node_by_source=defaultdict(list)
    for n in topology['nodes']:node_by_source[n['source_entity_ref']['entity_id']].append(n['node_id'])
    raw_bus_nodes={}
    for a in accounts:
        raw=a['raw_record'];f=dict(raw['fields'] or [])
        if a['identity_status']=='UNIQUE' and a['canonical_ref'] and raw['source_file_type']=='BUS':
            raw_bus_nodes[f.get('Bus_ID')]=node_by_source.get(a['canonical_ref']['entity_id'],[])
    hard=[]
    if len(feeders)!=1 or profile['case_ownership_unresolved']:
        hard.append({'code':'OWNERSHIP_CONFLICT','source_refs':sorted({r for f in feeders for r in f['source_record_refs']}),'scope':'CASE'})
    identity_refs=sorted(a['raw_record']['source_record_ref'] for a in accounts if a['identity_status'] not in (None,'UNIQUE'))
    if identity_refs:hard.append({'code':'AMBIGUOUS_IDENTITY','source_refs':identity_refs,'scope':'CASE'})
    voltage_refs=set()
    for e in exclusions:
        reason=e['exclusion_reason'] or ''
        if 'VOLTAGE_CONFLICT' in reason or reason=='INVALID_VOLTAGE_EVIDENCE':voltage_refs.update(e['supporting_source_refs'])
    if voltage_refs:hard.append({'code':'INCOMPATIBLE_VOLTAGE','source_refs':sorted(voltage_refs),'scope':'CASE'})
    states=[]
    for a in accounts:
        raw=a['raw_record'];kind=raw['source_file_type'];f=dict(raw['fields'] or [])
        state_field={'SWITCH':'Switch_NormalState','DISCONNECTOR':'Disconnector_NormalState','EARTHING_SWITCH':'EarthingSwitch_State'}.get(kind)
        if not state_field:continue
        raw_state=f.get(state_field);state=(raw_state or '').upper()
        endpoint_fields={'SWITCH':('Switch_FromBus','Switch_ToBus'),'DISCONNECTOR':('Disconnector_FromBus','Disconnector_ToBus'),
                         'EARTHING_SWITCH':('EarthingSwitch_Bus',)}[kind]
        endpoints={k:f.get(k) for k in endpoint_fields}
        states.append({'kind':kind,'raw_state':raw_state,'state':state if state in ('OPEN','CLOSED') else 'UNKNOWN',
            'raw_endpoints':endpoints,'node_ids':sorted({n for value in endpoints.values() for n in raw_bus_nodes.get(value,[])}),
            'source_record_ref':raw['source_record_ref']})
    ts=[];target_by_owner={}
    for t in transformers:
        source=t['source_entity_ref']['entity_id'] if t['source_entity_ref'] else None
        if source:target_by_owner[source]=t['evidence_id']
        fields=[dict(raw_by_locator[r]['raw_record']['fields'] or []) for r in t['source_record_refs']]
        unique=t['identity_ambiguous'] is False and source is not None
        f=fields[0] if len(fields)==1 else {}
        ts.append({'target_key':t['evidence_id'],'source_entity_id':source,'identity_unique':unique,
            'reference_composition':t['reference_composition'],'hv_kv':f.get('Transformer_HighVoltage_kV') or None,
            'lv_kv':f.get('Transformer_LowVoltage_kV') or None,'source_record_refs':sorted(t['source_record_refs'])})
    kind_map={'junction/bus':'JUNCTION','feeder-head/mv':'HEAD','transformer-mv/mv':'TRANSFORMER_MV'}
    nodes=[{'node_id':n['node_id'],'case_id':cid,'voltage_kv':n['nominal_voltage_kv'],
            'kind':kind_map.get(n['role'],'OTHER'),'transformer_key':target_by_owner.get(n['source_entity_ref']['entity_id'])
                if n['role']=='transformer-mv/mv' else None} for n in topology['nodes']]
    edges=[{'edge_id':e['branch_id'],'case_id':cid,'a':e['from_node_id'],'b':e['to_node_id'],'conducting':e['conducting'],
            'kind':'LINE' if e['role']=='line/connection' else 'SWITCH'} for e in topology['branches']]
    region_refs={n['node_id']:sorted(a['raw_record']['source_record_ref'] for a in accounts if a['canonical_ref'] and
                 a['canonical_ref']['entity_id']==n['source_entity_ref']['entity_id']) for n in topology['nodes'] if n['role']=='junction/bus'}
    return {'case_id':cid,'source_case_key':profile['source_case_key'],'feeders':sorted(feeders,key=lambda f:f['feeder_id']),
        'hard_blockers':sorted(hard,key=lambda h:h['code']),'state_constraints':sorted(states,key=lambda s:s['source_record_ref']),
        'head_id':topology['feeder_head_id'],'nominal_voltage_kv':profile['head']['nominal_voltage_kv'] if profile['head'] else None,
        's2_usable':profile['graphs']['S2']['usable_backbone'],'source_line_count':profile['source']['row_counts']['LINE'],
        'base_nodes':sorted(nodes,key=lambda n:n['node_id']),'base_edges':sorted(edges,key=lambda e:e['edge_id']),
        'targets':sorted(ts,key=lambda t:t['target_key']),'evidence_refs':[profile['profile_id']], 'region_source_refs':region_refs}
