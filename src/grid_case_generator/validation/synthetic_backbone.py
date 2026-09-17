"""D4 structural validator, separate from object generation."""
from grid_case_generator.validation.topology_proposals import base_hash, measure_graph
from grid_case_generator.models.proposals import voltage_compatible


def validate_bundle(x, bundle):
    from grid_case_generator.generation.synthetic_backbone import source_line_components, RULE, VERSION, generated_id
    from grid_case_generator.analysis.deterministic_recovery import eligibility
    c=x['accepted']; errors=set(); nodes={n['node_id']:n for n in c['base_nodes']}
    if bundle.get('base_graph_sha256')!=base_hash(c): errors.add('STALE_ACCEPTED_BASE')
    if bundle.get('case_id')!=c['case_id']: errors.add('CROSS_CASE_CONNECTION')
    if len(c['feeders'])!=1 or bundle.get('feeder_id') not in {f['feeder_id'] for f in c['feeders']}:
        errors.add('NON_UNIQUE_FEEDER')
    if c['hard_blockers'] or any(r['primary_class']=='HARD_SOURCE_CONTRADICTION' for r in eligibility(c)): errors.add('HARD_SOURCE_CONTRADICTION')
    if len(source_line_components(x))>1: errors.add('COMPETING_SOURCE_REFERENCE_COMPONENTS')
    if any(n['case_id']!=c['case_id'] for n in c['base_nodes']) or any(e['case_id']!=c['case_id'] for e in c['base_edges']): errors.add('CROSS_CASE_CONNECTION')
    if bundle.get('evidence_class')!='RULE_GENERATED': errors.add('FALSE_SOURCE_PROVENANCE')
    if bundle.get('rule_id')!=RULE or bundle.get('rule_version')!=VERSION: errors.add('RULE_VERSION_MISMATCH')
    if bundle.get('scope')!='PROPOSAL_ONLY_COUNTERFACTUAL': errors.add('INVALID_LIFECYCLE')
    if bundle.get('approved') is not False or bundle.get('applied') is not False or bundle.get('stage')!='PROPOSED':
        errors.add('INVALID_LIFECYCLE')
    if bundle.get('nodes'): errors.add('UNREVIEWED_JUNCTION_OR_DEVICE')
    if len(bundle.get('edges',[]))!=1: errors.add('NONMINIMAL_BUNDLE')
    # Recheck uniqueness from graph membership, independently of persisted selection.
    adj={n:set() for n in nodes}
    for e in c['base_edges']:
        adj[e['a']].add(e['b']); adj[e['b']].add(e['a'])
    remaining=set(nodes); groups=[]
    while remaining:
        seed=remaining.pop(); group={seed}; todo=[seed]
        while todo:
            for n in adj[todo.pop()]-group:
                group.add(n); remaining.discard(n); todo.append(n)
        if any(e['kind']=='LINE' and e['a'] in group for e in c['base_edges']): groups.append(group)
    valid_targets={n for g in groups for n in g if nodes[n]['kind']=='JUNCTION'}
    if len(groups)!=1 or c['head_id'] in set().union(*groups): errors.add('NON_UNIQUE_DISCONNECTED_COMPONENT')
    if len(valid_targets)!=1: errors.add('NON_UNIQUE_ANCHOR')
    for e in bundle.get('edges',[]):
        if e.get('case_id')!=c['case_id'] or e.get('feeder_id')!=bundle.get('feeder_id'): errors.add('CROSS_CASE_CONNECTION')
        if not e.get('edge_id','').startswith('d4-generated:edge:') or e.get('edge_id') in {b['edge_id'] for b in c['base_edges']}:
            errors.add('SOURCE_NAMESPACE_COLLISION')
        if e.get('evidence_class')!='RULE_GENERATED' or e.get('kind')!='SYNTHETIC_BACKBONE_EDGE': errors.add('FALSE_SOURCE_PROVENANCE')
        if e.get('a')!=c['head_id'] or e.get('b') not in valid_targets: errors.add('UNSUPPORTED_PLACEMENT')
        if e.get('edge_id')!=generated_id('edge',c['case_id'],bundle['feeder_id'],RULE,e.get('a'),e.get('b')): errors.add('NONDETERMINISTIC_ID')
        if e.get('conducting') is not True: errors.add('UNREVIEWED_STATE')
        if e.get('a') not in nodes or e.get('b') not in nodes:
            errors.add('DANGLING_ENDPOINT'); continue
        try:
            if not (voltage_compatible(nodes[e['a']]['voltage_kv'],nodes[e['b']]['voltage_kv']) and
                    voltage_compatible(nodes[e['a']]['voltage_kv'],c['nominal_voltage_kv'])): errors.add('INCOMPATIBLE_VOLTAGE')
        except ValueError: errors.add('INCOMPATIBLE_VOLTAGE')
        if e['a']==e['b']: errors.add('NEW_CYCLE')
    # Independent cut veto plus replay of exact rule metadata/evidence in artifact verifier.
    target_ids={e.get('b') for e in bundle.get('edges',[])}
    source_entities={n.get('source_entity_ref',{}).get('entity_id') for n in x['source']['topology']['nodes'] if n['node_id'] in target_ids}
    source_names={dict(a['raw_record']['fields'] or []).get('Bus_ID') for a in x['source']['accounts']
                  if a.get('canonical_ref') and a['canonical_ref'].get('entity_id') in source_entities}
    for s in c['state_constraints']:
        if s['kind']=='EARTHING_SWITCH' and s['state']=='CLOSED' and (target_ids|{c['head_id']}) & set(s['node_ids']):
            errors.add('CLOSED_EARTHING_AT_ATTACHMENT')
        if s['state']=='OPEN' and source_names & {v for v in s.get('raw_endpoints',{}).values() if v}:
            errors.add('UNRESOLVED_OPEN_CUT')
        if s['state']=='OPEN' and any(s.get('raw_endpoints',{}).values()) and not s['node_ids']:
            errors.add('UNRESOLVED_OPEN_CUT')
        if s['state']=='OPEN' and any(e.get('b') in s['node_ids'] for e in bundle.get('edges',[])):
            errors.add('UNRESOLVED_OPEN_CUT')
    if not errors:
        for physical in (True,False):
            before=measure_graph(c,physical=physical)
            after=measure_graph(c,edges=c['base_edges']+bundle['edges'],physical=physical)
            if after['cycle_rank']!=before['cycle_rank']: errors.add('NEW_CYCLE')
        # Every original OPEN edge still occurs with the identical conducting flag.
        # Joining distinct physical components cannot join the two sides of an OPEN
        # edge through an alternate conducting path (that would add a physical cycle).
    return {'bundle_id':bundle['bundle_id'],'case_id':c['case_id'],'reasons':sorted(errors),
            'structural_status':'REJECTED' if errors else 'PASS','scope':'PROPOSAL_ONLY_COUNTERFACTUAL',
            'stage':'PROPOSED','approved':False,'applied':False,'open_cuts_preserved':not errors}


def verify_d2_counterfactual(c, edges, expected):
    """Compare read-only D3 evaluator with the original D2 engine on the overlay.

    D2's temporary proposal objects are discarded; only eligibility is compared.
    No attachment proposal/device is published or applied by D4.
    """
    from collections import Counter
    from grid_case_generator.analysis.topology_proposals import propose_case as d2_engine
    overlay=dict(c,base_edges=c['base_edges']+edges)
    result=d2_engine(overlay,{},'d4-independent-eligibility-check')
    actual={r['feeder_id']:r for r in result['feeder_eligibility']}
    bundles=Counter(r['feeder_id'] for r in result['proposal_bundles'])
    missing={key:Counter() for key in ('missing_backbone_count','missing_region_count','missing_backbone_or_region_count')}
    for r in result['rejected_candidates']:
        reasons=set(r['reasons']);fid=r['feeder_id']
        missing['missing_backbone_count'][fid]+='NO_ACCEPTED_PHYSICAL_BACKBONE' in reasons
        missing['missing_region_count'][fid]+='ATTACHMENT_REGION_UNDETERMINED' in reasons
        missing['missing_backbone_or_region_count'][fid]+=bool(reasons & {'NO_ACCEPTED_PHYSICAL_BACKBONE','ATTACHMENT_REGION_UNDETERMINED'})
    if set(actual)!={r['feeder_id'] for r in expected}:raise ValueError('D4 independent D2 feeder mismatch')
    for e in expected:
        a=actual[e['feeder_id']];fid=e['feeder_id']
        if (a['primary_class']!=e['primary_class'] or bundles[fid]!=e['synthetic_candidate_count'] or
            any(a['structure_sufficiency'][k]!=e[k] for k in ('accepted_physical_backbone','candidate_region_count')) or
            any(missing[k][fid]!=e[k] for k in missing)):
            raise ValueError('D4 independent D2 eligibility mismatch: '+fid)
