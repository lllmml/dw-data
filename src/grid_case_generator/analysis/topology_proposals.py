"""Deterministic engineering proposal bundles on immutable accepted S0 inputs."""
from grid_case_generator.analysis.completion_profiles import graph_profile
from grid_case_generator.models.proposals import (ProposalClass as C, proposal_id, positive_voltage,
    voltage_compatible, unknown_decision, RULE_VERSION)
from grid_case_generator.validation.topology_proposals import base_hash, validate_bundle, measure_graph

STREAMS=('feeder_eligibility','blocker_reclassification','proposal_bundles','proposal_edges',
         'proposal_devices','proposal_validation','rejected_candidates')


def _regions(c,decision):
    nodes={n['node_id']:n for n in c['base_nodes']}
    g=graph_profile(set(nodes),[(e['a'],e['b'],True) for e in c['base_edges']],c['head_id'],
                    {n['node_id'] for n in c['base_nodes'] if n['kind']=='JUNCTION'})
    seen=set(g['reachable_node_ids'])
    usable=bool(c['head_id'] and any(e['kind']=='LINE' and e['a'] in seen and e['b'] in seen for e in c['base_edges']))
    candidates=[r['node_id'] for r in g['candidate_junctions']]
    if decision['attachment_node_id']:
        candidates=[n for n in candidates if n==decision['attachment_node_id']]
    return usable,candidates


def _bundle(c,f,target,region,d,config_hash,*,slot=None):
    new=slot is not None;fid=f['feeder_id'];cid=c['case_id']
    key=['new-transformer',slot] if new else ['existing-transformer',target['target_key']]
    ident=lambda kind,semantic:proposal_id(cid,fid,kind,semantic,config_hash)
    bid=ident('bundle',key);mv=ident('mv-port',key)
    source_refs=sorted(set(f['source_record_refs']+([] if new else target['source_record_refs'])+c['region_source_refs'].get(region,[])))
    business_refs=[d['confirmation_ref']] if d['confirmation_ref'] else []
    voltage=c['nominal_voltage_kv']
    target_key=ident('new-target',key) if new else target['target_key']
    assumptions={'ENGINEERING_PLACEMENT','ENGINEERING_LIMITS_NOT_ASSESSED'}
    if not new:assumptions.add('ENGINEERING_CASE_OWNERSHIP')
    if not new and not target['hv_kv']:assumptions.add('ASSUMED_MV_SIDE')
    if c['state_constraints']:assumptions.add('SOURCE_STATE_CONNECTIVITY_PARTIALLY_UNRESOLVED')
    common={'case_id':cid,'feeder_id':fid,'bundle_id':bid,'evidence_class':'RULE_GENERATED',
        'source_refs':source_refs,'business_refs':business_refs,'rule_id':'CASE_LOCAL_EXISTING_T_LEAF_V1' if not new else 'BUSINESS_CONFIRMED_T_PLAN_V1',
        'rule_version':RULE_VERSION,'config_hash':config_hash}
    nodes=[dict(common,node_id=mv,kind='SYNTHETIC_MV_ATTACHMENT',voltage_kv=voltage,transformer_key=target_key)]
    edges=[dict(common,edge_id=ident('attachment',[region,mv]),a=region,b=mv,conducting=True,kind='SYNTHETIC_ATTACHMENT_EDGE')]
    devices=[]
    lv_voltage=d['lv_voltage_kv'] if new else target['lv_kv'] or d['lv_voltage_kv']
    if lv_voltage:
        lv=ident('lv-bus',key)
        nodes.append(dict(common,node_id=lv,kind='SYNTHETIC_LV_BUS',voltage_kv=lv_voltage,transformer_key=None))
        edges.append(dict(common,edge_id=ident('transformer-transfer',[mv,lv]),a=mv,b=lv,conducting=True,
                          kind='TRANSFORMER_TRANSFER',transformer_key=target_key))
    if new:
        devices.append(dict(common,device_id=ident('transformer',key),kind='SYNTHETIC_TRANSFORMER',
            target_key=target_key,source_entity_id=None,mv_node_id=mv,lv_node_id=lv))
    return {'bundle_id':bid,'case_id':cid,'feeder_id':fid,'kind':'SYNTHETIC_TRANSFORMER' if new else 'SYNTHETIC_ATTACHMENT_EDGE',
        'source_target_key':None if new else target['target_key'],'nodes':nodes,'edges':edges,'devices':devices,
        'assumptions':sorted(assumptions),'source_refs':source_refs,'business_refs':business_refs,
        'evidence_refs':c['evidence_refs'],'rule_id':common['rule_id'],'rule_version':RULE_VERSION,
        'config_hash':config_hash,'base_graph_sha256':base_hash(c),'evidence_class':'RULE_GENERATED','stage':'PROPOSED',
        'lifecycle':[{'stage':s,'reason':reason,'source_refs':source_refs,'business_refs':business_refs} for s,reason in
            [('OBSERVED','SOURCE_INVENTORY'),('ELIGIBLE','CASE_LOCAL_ENGINEERING_RULE'),('PROPOSED','ENGINEERING_PLACEMENT')]]}


def propose_case(c,decisions,config_hash):
    out={name:[] for name in STREAMS};all_nodes=list(c['base_nodes']);all_edges=list(c['base_edges']);all_devices=[]
    for f in sorted(c['feeders'],key=lambda f:f['feeder_id']):
        fid=f['feeder_id'];d=decisions.get((c['case_id'],fid),unknown_decision(c['case_id'],fid))
        usable,regions=_regions(c,d)
        hard_records=list(c['hard_blockers'])
        hard=sorted({b['code'] for b in hard_records})
        gaps=[];accepted_bundles=[];rejected=[]
        def reject(key,reasons,refs=()):
            rejected.append({'case_id':c['case_id'],'feeder_id':fid,'candidate_key':key,'reasons':sorted(set(reasons)),
                'source_refs':sorted(set(refs)),'business_refs':[d['confirmation_ref']] if d['confirmation_ref'] else [],
                'stage':'OBSERVED','applied':False})
        if d['nominal_voltage_kv'] and c['nominal_voltage_kv'] and not voltage_compatible(d['nominal_voltage_kv'],c['nominal_voltage_kv']):
            hard.append('BUSINESS_SOURCE_VOLTAGE_CONTRADICTION')
        if d['role']=='NO_TRANSFORMER_REQUIRED' and c['targets']:
            hard.append('BUSINESS_SOURCE_DEVICE_CONTRADICTION')
        if not c['nominal_voltage_kv']:gaps.append('MV_VOLTAGE_UNDETERMINED')
        if not usable:gaps.append('NO_ACCEPTED_PHYSICAL_BACKBONE')
        if len(regions)!=1:gaps.append('ATTACHMENT_REGION_UNDETERMINED')
        for code in hard:
            if not any(b['code']==code for b in hard_records):
                hard_records.append({'code':code,'scope':'FEEDER','source_refs':sorted(set(f['source_record_refs']+[r for t in c['targets'] for r in t['source_record_refs']])), 'business_refs':[d['confirmation_ref']]})
        if hard:
            reject('feeder',hard,[r for b in hard_records for r in b['source_refs']]);primary=C.HARD_SOURCE_CONTRADICTION
        elif not c['targets'] and d['role']=='UNKNOWN':
            gaps.append('BUSINESS_ROLE_UNCONFIRMED');primary=C.ROLE_CONFIRMATION_REQUIRED
            reject('new-transformer',['BUSINESS_ROLE_UNCONFIRMED'],f['source_record_refs'])
        else:
            unreferenced=[t for t in c['targets'] if t['reference_composition']=='NO_REFERENCE']
            new_allowed=not c['targets'] and d['synthetic_transformer_allowed'] and d['role']=='DISTRIBUTION_WITH_TRANSFORMER'
            # Defense in depth: the public engine still checks required policy fields.
            if new_allowed and not all(d[k] for k in ('transformer_required','transformer_count','demand_basis','nominal_voltage_kv','lv_voltage_kv','confirmation_ref')):
                new_allowed=False;gaps.append('INCOMPLETE_BUSINESS_DEVICE_PLAN')
            work=[(t,None) for t in sorted(unreferenced,key=lambda t:t['target_key'])]
            if new_allowed:work=[(None,slot) for slot in range(d['transformer_count'])]
            for t,slot in work:
                key=t['target_key'] if t else 'business-slot:'+str(slot)
                refs=t['source_record_refs'] if t else f['source_record_refs']
                reasons=list(gaps)
                if t and not t['identity_unique']:reasons.append('AMBIGUOUS_IDENTITY')
                if t and t['source_entity_id'] is None:reasons.append('UNPUBLISHED_TARGET_IDENTITY')
                hv=t['hv_kv'] if t else d['nominal_voltage_kv']
                lv=(t['lv_kv'] or d['lv_voltage_kv']) if t else d['lv_voltage_kv']
                try:
                    if hv and c['nominal_voltage_kv'] and not voltage_compatible(hv,c['nominal_voltage_kv']):reasons.append('INCOMPATIBLE_VOLTAGE')
                    if lv and c['nominal_voltage_kv'] and positive_voltage(lv)>=positive_voltage(c['nominal_voltage_kv']):reasons.append('INCOMPATIBLE_LV_VOLTAGE')
                    if t and t['lv_kv'] and d['lv_voltage_kv'] and not voltage_compatible(t['lv_kv'],d['lv_voltage_kv']):reasons.append('BUSINESS_SOURCE_VOLTAGE_CONTRADICTION')
                except ValueError:reasons.append('INVALID_SOURCE_VOLTAGE')
                candidate_hard=set(reasons)&{'AMBIGUOUS_IDENTITY','INCOMPATIBLE_VOLTAGE','INCOMPATIBLE_LV_VOLTAGE','INVALID_SOURCE_VOLTAGE','BUSINESS_SOURCE_VOLTAGE_CONTRADICTION'}
                for code in sorted(candidate_hard):
                    hard_records.append({'code':code,'scope':'CANDIDATE','candidate_key':key,'source_refs':sorted(refs)})
                if reasons:reject(key,reasons,refs);continue
                b=_bundle(c,f,t,regions[0],d,config_hash,slot=slot)
                validation=validate_bundle(c,b);out['proposal_validation'].append(validation)
                if validation['structural_status']=='REJECTED':reject(key,validation['reasons'],refs);continue
                b['stage']=validation['stage']
                if b['stage']=='VALIDATED':b['lifecycle'].append({'stage':'VALIDATED','reason':'DECLARED_VALIDATION_SCOPE_PASS','source_refs':b['source_refs'],'business_refs':b['business_refs']})
                accepted_bundles.append(b)
                if not lv:reject(key+':lv-bus',['LV_VOLTAGE_POLICY_REQUIRED'],refs)
            if accepted_bundles:primary=C.SYNTHETIC_DEVICE_ELIGIBLE if new_allowed else C.SYNTHETIC_ATTACHMENT_ELIGIBLE
            elif hard_records:primary=C.HARD_SOURCE_CONTRADICTION
            elif measure_graph(c)['target_coverage']=='FULL':primary=C.ALREADY_COMPLETE
            elif c['s2_usable'] and (not usable or not unreferenced):primary=C.DETERMINISTIC_RECOVERY
            elif not usable:primary=C.SYNTHETIC_BACKBONE_REQUIRED
            else:primary=C.INSUFFICIENT_FOR_AUTOMATIC_PROPOSAL
            if not work:reject('feeder',['DETERMINISTIC_REFERENCE_REVIEW' if c['targets'] else 'DEVICE_OR_ROLE_SCOPE_UNRESOLVED'],f['source_record_refs'])
            if not usable:reject('backbone',['BACKBONE_LAYOUT_RULE_REQUIRED'],f['source_record_refs'])
        out['proposal_bundles'].extend(accepted_bundles);out['rejected_candidates'].extend(rejected)
        for b in accepted_bundles:
            out['proposal_edges'].extend(b['edges']);out['proposal_devices'].extend(b['nodes']+b['devices'])
            all_nodes.extend(b['nodes']);all_edges.extend(b['edges']);all_devices.extend(b['devices'])
        hard=sorted({b['code'] for b in hard_records})
        reasons=sorted(set(hard+gaps+[r for x in rejected for r in x['reasons']]))
        out['feeder_eligibility'].append({'case_id':c['case_id'],'source_case_id':c['case_id'],'feeder_id':fid,
            'current_target_coverage':measure_graph(c)['target_coverage'],'primary_class':primary,
            'original_flags':f['original_flags'],'d1_primary':f['d1_primary'],'role_status':d['role'],
            'structure_sufficiency':{'accepted_physical_backbone':usable,'candidate_region_count':len(regions)},
            'automatic_proposal_eligible':bool(accepted_bundles),'physical_topology_blockers':hard,
            'scenario_state_constraints':c['state_constraints'],'reason_codes':reasons,
            'manual_requirements':sorted(set(gaps+['ENGINEERING_ADEQUACY_REVIEW'])),
            'supporting_source_refs':f['source_record_refs'],'conflicting_source_refs':sorted({r for b in hard_records for r in b['source_refs']}),
            'approved':False,'applied':False})
        out['blocker_reclassification'].append({'case_id':c['case_id'],'feeder_id':fid,'d1_primary':f['d1_primary'],
            'primary_class':primary,'hard_source_contradictions':hard_records,
            'operating_state_constraints':c['state_constraints'],'modeling_gaps':sorted(set(gaps)),
            'source_missing_attachment_count':sum(t['reference_composition']=='NO_REFERENCE' for t in c['targets']),
            'whole_case_state_veto':False})
    coverage={'case_id':c['case_id'],'feeder_count':len(c['feeders']),'label':'PROPOSAL_ONLY_COUNTERFACTUAL'}
    for mode in ('physical','conducting'):
        before=measure_graph(c,physical=mode=='physical');after=measure_graph(c,all_nodes,all_edges,all_devices,physical=mode=='physical')
        coverage[mode]={'before':before,'after':after,'new_cycles':after['cycle_rank']-before['cycle_rank'],
                        'target_delta':after['reachable_transformers']-before['reachable_transformers']}
    out['coverage']=coverage
    for name in STREAMS:
        out[name]=sorted(out[name],key=lambda r:str(r.get('bundle_id',r.get('edge_id',r.get('node_id',r.get('device_id',r.get('candidate_key',r.get('feeder_id',''))))))))
    return out
