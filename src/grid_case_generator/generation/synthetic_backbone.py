"""Source-constrained, proposal-only D4 backbone completion; no mutation of inputs."""
from hashlib import sha256

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.models.proposals import voltage_compatible
from grid_case_generator.analysis.deterministic_recovery import eligibility
from grid_case_generator.validation.topology_proposals import base_hash, measure_graph

VERSION = '1.0.0'
RULE = 'HEAD_TO_UNIQUE_COMPONENT_V1'
SCOPE = 'PROPOSAL_ONLY_COUNTERFACTUAL'
TAGS = ('DISCONNECTED_SOURCE_LINE_COMPONENTS', 'HEAD_TO_SOURCE_COMPONENT_GAP',
        'INTER_COMPONENT_GAP', 'REMOTE_SWITCH_PORT_GAP', 'ACCESS_POINT_GAP',
        'TRANSFORMER_REGION_GAP', 'INSUFFICIENT_STRUCTURE')
STREAMS = ('feeder_gap_taxonomy', 'engineering_anchors', 'candidate_backbone_edges',
           'proposal_bundles', 'proposal_edges', 'proposal_junctions', 'rejected_candidates',
           'proposal_validation', 'case_coverage', 'd2_eligibility_counterfactual')


def generated_id(kind, *parts):
    return 'd4-generated:' + kind + ':' + sha256(canonical_json_bytes([VERSION, *parts])).hexdigest()


def components(c, conducting=False):
    """Component membership is a set; sorting never determines placement."""
    adj = {n['node_id']: set() for n in c['base_nodes']}
    for e in c['base_edges']:
        if not conducting or e['conducting']:
            adj[e['a']].add(e['b']); adj[e['b']].add(e['a'])
    pending = set(adj); groups = []
    while pending:
        seed = pending.pop(); group = {seed}; stack = [seed]
        while stack:
            for node in adj[stack.pop()] - group:
                group.add(node); pending.discard(node); stack.append(node)
        groups.append(frozenset(group))
    return sorted(groups, key=lambda g: sorted(g))


def reached(c, conducting=False):
    return next((g for g in components(c, conducting) if c['head_id'] in g), frozenset())


def source_line_components(x):
    """Reference incidence components are evidence only, never physical connections."""
    lines=[]; parent={}
    def find(n):
        parent.setdefault(n,n)
        while parent[n]!=n:
            parent[n]=parent[parent[n]]; n=parent[n]
        return n
    for a in x['source']['accounts']:
        raw=a['raw_record']; fields=dict(raw['fields'] or [])
        if raw['source_file_type'] not in ('LINE','SWITCH','ACCESS_POINT'): continue
        keys={'LINE':('Line_FromBus','Line_ToBus'),
              'SWITCH':('Switch_FromBus','Switch_ToBus'),
              'ACCESS_POINT':('AccessPoint_ID','AccessPoint_Bus')}[raw['source_file_type']]
        ends=[fields[k] for k in keys if fields.get(k)]
        witness='row:'+raw['source_record_ref']
        for end in ends: parent[find('ref:'+end)]=find(witness)
        if raw['source_file_type']=='LINE': lines.append((witness,raw['source_record_ref']))
    groups={}
    for witness,ref in lines: groups.setdefault(find(witness),[]).append(ref)
    return sorted(sorted(refs) for refs in groups.values())


def selection(x):
    """Unique component and unique Bus boundary, with explicit unresolved-cut veto."""
    c = x['accepted']; ns = {n['node_id']: n for n in c['base_nodes']}
    groups = components(c)
    raw_components=source_line_components(x)
    line_groups = [g for g in groups if any(e['kind']=='LINE' and e['a'] in g for e in c['base_edges'])]
    downstream = [g for g in line_groups if c['head_id'] not in g]
    reasons = set()
    if len(c['feeders']) != 1: reasons.add('NON_UNIQUE_FEEDER')
    if c['hard_blockers'] or any(r['primary_class']=='HARD_SOURCE_CONTRADICTION' for r in eligibility(c)):
        reasons.add('HARD_SOURCE_CONTRADICTION')
    if not c['head_id'] or c['head_id'] not in ns: reasons.add('NO_HEAD')
    if any(n['case_id'] != c['case_id'] for n in c['base_nodes']) or any(e['case_id']!=c['case_id'] for e in c['base_edges']):
        reasons.add('CROSS_CASE_CONNECTION')
    if len(raw_components)>1: reasons.add('COMPETING_SOURCE_REFERENCE_COMPONENTS')
    if not line_groups: reasons.add('INSUFFICIENT_STRUCTURE')
    elif len(line_groups) != 1: reasons.add('NON_UNIQUE_COMPONENT')
    elif not downstream: reasons.add('BACKBONE_ALREADY_REACHABLE')
    anchors = sorted(n['node_id'] for n in c['base_nodes'] if n['kind']=='JUNCTION' and any(n['node_id'] in g for g in downstream))
    if len(anchors) != 1: reasons.add('NON_UNIQUE_ANCHOR' if anchors else 'NO_ENGINEERING_ANCHOR')
    target = anchors[0] if len(anchors)==1 else None
    if target and c['head_id'] in ns:
        try:
            if not (voltage_compatible(ns[target]['voltage_kv'],c['nominal_voltage_kv']) and
                    voltage_compatible(ns[c['head_id']]['voltage_kv'], c['nominal_voltage_kv'])):
                reasons.add('INCOMPATIBLE_VOLTAGE')
        except ValueError: reasons.add('INCOMPATIBLE_VOLTAGE')
    # Source endpoint texts are used only to veto a possible cut, never to invent ports.
    raw_ids = {n.get('source_entity_ref',{}).get('entity_id') for n in x['source']['topology']['nodes'] if n['node_id']==target}
    raw_names = {dict(a['raw_record']['fields'] or []).get('Bus_ID') for a in x['source']['accounts']
                 if a.get('canonical_ref') and a['canonical_ref'].get('entity_id') in raw_ids}
    for s in c['state_constraints']:
        ends = {v for v in s.get('raw_endpoints',{}).values() if v}
        if s['state']=='OPEN' and (target in s['node_ids'] or ends & raw_names or (ends and not s['node_ids'])):
            reasons.add('UNRESOLVED_OPEN_CUT')
        if s['kind']=='EARTHING_SWITCH' and s['state']=='CLOSED' and {target,c['head_id']} & set(s['node_ids']):
            reasons.add('CLOSED_EARTHING_AT_ATTACHMENT')
    return {'reasons':sorted(reasons), 'anchors':anchors, 'target':target,
            'source_reference_components':raw_components,
            'line_components':[sorted(g) for g in line_groups],
            'downstream_components':[sorted(g) for g in downstream]}


def anchor_inventory(x, decision):
    c=x['accepted']; physical=reached(c); conducting=reached(c, True); rows=[]
    originals={n['node_id']:n for n in x['source']['topology']['nodes']}
    line_nodes={e[k] for e in c['base_edges'] if e['kind']=='LINE' for k in ('a','b')}
    for f in sorted(c['feeders'],key=lambda f:f['feeder_id']):
        for n in sorted(c['base_nodes'],key=lambda n:n['node_id']):
            if n['kind'] not in ('HEAD','JUNCTION','SWITCH_PORT') and n['node_id'] not in line_nodes: continue
            nid=n['node_id']; refs=set(n.get('supporting_source_refs',[])) | set(c['region_source_refs'].get(nid,[]))
            original=originals.get(nid,{})
            refs.update(original.get('supporting_source_refs',[]))
            entity=original.get('source_entity_ref',{}).get('entity_id')
            refs.update(a['raw_record']['source_record_ref'] for a in x['source']['accounts']
                        if entity and a.get('canonical_ref',{} ) and a['canonical_ref'].get('entity_id')==entity)
            refs.update(f['source_record_refs'] if n['kind']=='HEAD' else [])
            kind='UNBOUND_SWITCH_PORT' if n.get('port_role')=='UNBOUND' else n['kind'] if n['kind'] in ('HEAD','JUNCTION','SWITCH_PORT') else 'LINE_ENDPOINT'
            exclusions=[]
            if kind not in ('HEAD','JUNCTION'): exclusions.append('PORT_PLACEMENT_NOT_ESTABLISHED')
            if kind=='JUNCTION' and nid not in decision['anchors']: exclusions.append('NOT_IN_DOWNSTREAM_LINE_COMPONENT')
            if nid in decision['anchors'] and len(decision['anchors'])>1: exclusions.append('NON_UNIQUE_ANCHOR')
            rows.append({'case_id':c['case_id'],'feeder_id':f['feeder_id'],'node_id':nid,
                'source_refs':sorted(refs),'voltage_kv':n['voltage_kv'],'anchor_type':kind,
                'physical_reachable':nid in physical,'conducting_reachable':nid in conducting,
                'ambiguity_status':'EXCLUDED' if exclusions else 'UNIQUE' if nid==decision['target'] else 'OBSERVED',
                'exclusion_reasons':exclusions})
        for a in x['source']['accounts']:
            raw=a['raw_record']
            if raw['source_file_type']!='ACCESS_POINT': continue
            rows.append({'case_id':c['case_id'],'feeder_id':f['feeder_id'],'node_id':None,
                'source_refs':[raw['source_record_ref']],'voltage_kv':None,
                'anchor_type':'ENGINEERING_PLACEMENT_ANCHOR','physical_reachable':False,
                'conducting_reachable':False,'ambiguity_status':'NEEDS_REVIEW',
                'exclusion_reasons':['ACCESS_POINT_PLACEMENT_NOT_REVIEWED']})
    return sorted(rows,key=lambda r:(r['feeder_id'],r['node_id'] or '',r['source_refs']))


def propose_case(x):
    from grid_case_generator.validation.synthetic_backbone import validate_bundle
    c=x['accepted']; decision=selection(x); rows={k:[] for k in STREAMS}
    before=eligibility(c); rows['engineering_anchors']=anchor_inventory(x,decision)
    if not decision['reasons']:
        f,=c['feeders']; target=decision['target']; cid=c['case_id']; fid=f['feeder_id']
        refs=set(f['source_record_refs']) | {r for a in rows['engineering_anchors'] if a['node_id']==target for r in a['source_refs']}
        component=set(decision['downstream_components'][0])
        branch_entities={e['source_entity_ref']['entity_id'] for e in x['source']['topology'].get('branches',[])
                         if e['from_node_id'] in component and e['to_node_id'] in component}
        refs.update(a['raw_record']['source_record_ref'] for a in x['source']['accounts']
                    if a.get('canonical_ref') and a['canonical_ref'].get('entity_id') in branch_entities)
        refs.update(ref for e in c['base_edges'] if e['a'] in component and e['b'] in component
                    for ref in e.get('supporting_source_refs',[]))
        refs=sorted(refs)
        bid=generated_id('bundle',cid,fid,RULE,c['head_id'],target)
        edge={'edge_id':generated_id('edge',cid,fid,RULE,c['head_id'],target),
              'case_id':cid,'feeder_id':fid,'a':c['head_id'],'b':target,'kind':'SYNTHETIC_BACKBONE_EDGE',
              'conducting':True,'evidence_class':'RULE_GENERATED','rule_id':RULE,'rule_version':VERSION,
              'source_refs':refs,'bundle_id':bid}
        bundle={'bundle_id':bid,'case_id':cid,'feeder_id':fid,'rule_id':RULE,'rule_version':VERSION,
                'base_graph_sha256':base_hash(c),'evidence_class':'RULE_GENERATED','stage':'PROPOSED',
                'approved':False,'applied':False,'scope':SCOPE,'nodes':[],'edges':[edge],
                'source_refs':refs,'assumptions':['DERIVED_ENGINEERING_COMPLETION','UNIQUE_BUS_DISTRIBUTION_BOUNDARY','NOT_A_SOURCE_CONNECTION'],
                'component_node_ids':decision['downstream_components'][0]}
        rows['candidate_backbone_edges'].append(edge)
        validation=validate_bundle(x,bundle); rows['proposal_validation'].append(validation)
        if validation['reasons']: raise ValueError('D4 internally invalid proposal: '+str(validation))
        rows['proposal_bundles'].append(bundle); rows['proposal_edges'].append(edge)
    after_c=dict(c,base_edges=c['base_edges']+rows['proposal_edges'])
    after=eligibility(after_c)
    for b,a in zip(before,after):
        rows['d2_eligibility_counterfactual'].append({'scope':SCOPE,'before':b,'after':a})
        tags=[]
        if len(decision['line_components'])>1: tags+=['DISCONNECTED_SOURCE_LINE_COMPONENTS','INTER_COMPONENT_GAP']
        if decision['downstream_components']: tags.append('HEAD_TO_SOURCE_COMPONENT_GAP')
        if any(n.get('port_role')=='UNBOUND' for n in c['base_nodes']): tags.append('REMOTE_SWITCH_PORT_GAP')
        if any(a['raw_record']['source_file_type']=='ACCESS_POINT' for a in x['source']['accounts']): tags.append('ACCESS_POINT_GAP')
        if c['targets'] and b['candidate_region_count']!=1: tags.append('TRANSFORMER_REGION_GAP')
        if not decision['line_components']: tags.append('INSUFFICIENT_STRUCTURE')
        reasons=decision['reasons']; hard={'HARD_SOURCE_CONTRADICTION','CROSS_CASE_CONNECTION','INCOMPATIBLE_VOLTAGE','NON_UNIQUE_FEEDER'}
        outcome='AUTOMATIC_PROPOSAL_ELIGIBLE' if rows['proposal_edges'] else 'REJECTED' if hard & set(reasons) else 'NO_BACKBONE_ACTION_REQUIRED' if 'BACKBONE_ALREADY_REACHABLE' in reasons else 'MANUAL_LAYOUT_REQUIRED'
        record={'case_id':c['case_id'],'feeder_id':b['feeder_id'],'source_case_key':c['source_case_key'],
                'd3_primary':b['primary_class'],'taxonomy_primary':next((t for t in TAGS if t in tags),'NO_GAP'),
                'gap_tags':sorted(tags),'outcome':outcome,'reasons':reasons,
                'source_line_count':c['source_line_count'],'represented_line_count':sum(e['kind']=='LINE' for e in c['base_edges']),
                'source_reference_components':decision['source_reference_components'],
                'line_components':decision['line_components'],'candidate_anchor_ids':decision['anchors'],
                'deferred_rules':{'UNIQUE_COMPONENT_BRIDGE_V1':'UNIQUE_PORT_PAIR_NOT_PROVEN',
                                  'UNBOUND_SWITCH_EXTENSION_V1':'DOWNSTREAM_PLACEMENT_NOT_PROVEN',
                                  'ENGINEERING_JUNCTION_V1':'NECESSARY_PLACEMENT_NOT_PROVEN'}}
        rows['feeder_gap_taxonomy'].append(record)
        if reasons: rows['rejected_candidates'].append(dict(record,approved=False,applied=False))
    coverage={'case_id':c['case_id'],'feeder_count':len(c['feeders']),'scope':SCOPE}
    for mode in ('physical','conducting'):
        metrics={}
        for label,model in (('before',c),('after',after_c)):
            m=measure_graph(model,physical=mode=='physical'); seen=reached(model,mode=='conducting')
            m['reachable_switch_groups']=sum(e['kind']=='SWITCH' and e['a'] in seen and e['b'] in seen for e in model['base_edges'])
            m['reachable_source_line_components']=sum(bool(set(g)&seen) for g in decision['line_components'])
            metrics[label]=m
        coverage[mode]=metrics
    rows['case_coverage']=[coverage]; rows['coverage']=coverage
    return rows
