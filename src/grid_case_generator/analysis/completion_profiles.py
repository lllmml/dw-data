"""Read-only profiles from persisted source rows and existing S0/S2 evidence."""
from collections import Counter, defaultdict, deque
from dataclasses import asdict
from hashlib import sha256

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.models.completion import CompletionFacts, Prohibition as P
from grid_case_generator.analysis.completion_contract import VERSION


def graph_profile(nodes, edges, head, junctions):
    """Multigraph diagnostics; no graph objects or connections are generated."""
    nodes = set(nodes)
    if any(a not in nodes or b not in nodes for a, b, _ in edges):
        raise ValueError('graph endpoint missing')
    def components(active):
        parent = {n: n for n in nodes}
        def root(n):
            while parent[n] != n:
                parent[n] = parent[parent[n]]; n = parent[n]
            return n
        for a, b, _ in active:
            parent[root(a)] = root(b)
        return len({root(n) for n in nodes})
    conducting = [e for e in edges if e[2]]
    adj = defaultdict(list)
    for a, b, _ in conducting:
        adj[a].append(b); adj[b].append(a)
    hops = {head: 0} if head in nodes else {}
    queue = deque(hops)
    while queue:
        a = queue.popleft()
        for b in adj[a]:
            if b not in hops: hops[b] = hops[a] + 1; queue.append(b)
    sc, cc = components(edges), components(conducting)
    pairs = Counter(tuple(sorted((a, b))) for a, b, _ in edges)
    return {'node_count': len(nodes), 'branch_count': len(edges), 'conducting_branch_count': len(conducting),
            'structural_components': sc, 'conducting_components': cc,
            'structural_cycle_rank': len(edges)-len(nodes)+sc,
            'conducting_cycle_rank': len(conducting)-len(nodes)+cc,
            'self_loops': sum(a == b for a, b, _ in edges),
            'parallel_excess': sum(n-1 for n in pairs.values()),
            'maximum_conducting_degree': max((len(v) for v in adj.values()), default=0),
            'reachable_node_ids': sorted(hops),
            'candidate_junctions': [{'node_id': n, 'hops': hops[n], 'degree': len(adj[n])}
                                   for n in sorted(junctions & hops.keys())]}


def build_profile(recovery_case, accounts, topology, transformers, connections, blockers):
    cid = recovery_case['case_id']
    if topology['case_id'] != cid or any(r['case_id'] != cid for r in [*transformers, *connections, *blockers]):
        raise ValueError('profile input case mismatch')
    counts = Counter(); nonempty = defaultdict(Counter); values = defaultdict(Counter)
    state_counts = Counter(); constraint_refs = set(recovery_case['constraint_refs'])
    own_endpoints = 0
    for account in accounts:
        raw = account['raw_record']
        if raw['source_case_key'] != recovery_case['source_case_key']:
            raise ValueError('source row case mismatch')
        kind = raw['source_file_type']; fields = dict(raw['fields'] or [])
        counts[kind] += 1
        nonempty[kind].update(k for k, v in fields.items() if v)
        if kind == 'TRANSFORMER':
            own_endpoints += bool(fields.get('Transformer_FromBus') or fields.get('Transformer_ToBus'))
        tracked = {'STATION': ('Station_Type', 'Station_Voltage_Level'),
                   'BUS': ('Bus_BaseKV',), 'ACCESS_POINT': ('AccessPoint_UserType', 'AccessPoint_ContractCapacity_kVA'),
                   'TRANSFORMER': ('Transformer_HighVoltage_kV', 'Transformer_LowVoltage_kV')}
        for key in tracked.get(kind, ()):
            values[key][fields.get(key) or '<EMPTY>'] += 1
        if kind == 'SIM_CONFIG':
            values['SimConfig:'+str(fields.get('Config_Key'))][fields.get('Config_Value') or '<EMPTY>'] += 1
        state_field = {'SWITCH':'Switch_NormalState', 'DISCONNECTOR':'Disconnector_NormalState',
                       'EARTHING_SWITCH':'EarthingSwitch_State'}.get(kind)
        if state_field:
            state = (fields.get(state_field) or '').upper()
            if state not in ('OPEN', 'CLOSED'): state = 'UNKNOWN'
            state_counts[kind+':'+state] += 1
            if (kind != 'EARTHING_SWITCH' and state == 'OPEN') or (kind == 'EARTHING_SWITCH' and state == 'CLOSED'):
                constraint_refs.add(raw['source_record_ref'])
    counts = {kind: counts[kind] for kind in ('STATION','BUS','SWITCH','DISCONNECTOR','EARTHING_SWITCH',
                                              'FEEDER','ACCESS_POINT','LINE','TRANSFORMER','LOAD','DER','SIM_CONFIG')}
    base_nodes = {n['node_id'] for n in topology['nodes']}
    junctions = {n['node_id'] for n in topology['nodes'] if n['role'] == 'junction/bus'}
    head = topology['feeder_head_id']
    head_node = next((n for n in topology['nodes'] if n['node_id'] == head), None)
    graphs = {}
    for policy in ('S0', 'S2'):
        es = sorted((c for c in connections if c['policy'] == policy), key=lambda c: c['evidence_id'])
        edges = [(e['derived_ids'][1], e['derived_ids'][2], e['conducting']) for e in es]
        nodes = base_nodes | {n for e in edges for n in e[:2]}
        g = graph_profile(nodes, edges, head, junctions)
        if policy == 'S0' and g['reachable_node_ids'] != sorted(topology['reachable_node_ids']):
            raise ValueError('S0 persisted reachability mismatch')
        reached = set(g['reachable_node_ids'])
        rt = sum(any(n in reached for n in t['attachment'][policy]['derived_ids']) for t in transformers)
        expected = recovery_case['graphs'][policy]
        if rt != expected['reachable_transformers']:
            raise ValueError('Transformer evidence reachability mismatch')
        # Source row canonical refs identify physical Line owners, not ID patterns.
        line_owners = {a['canonical_ref']['entity_id'] for a in accounts
                       if a['canonical_ref'] and a['raw_record']['source_file_type'] == 'LINE'}
        reached_lines = {e['source_entity_ref']['entity_id'] for e in es if e['source_entity_ref']
                         and e['source_entity_ref']['entity_id'] in line_owners and e['conducting']
                         and all(n in reached for n in e['derived_ids'][1:])}
        if len(reached_lines) != expected['reachable_lines']:
            raise ValueError('Line evidence reachability mismatch')
        for key in ('structural_cycle_rank', 'conducting_cycle_rank'):
            if g[key] != expected[key]: raise ValueError('graph cycle evidence mismatch')
        g.update(target_coverage=expected['target_coverage'], reachable_transformers=rt,
                 reachable_lines=len(reached_lines), usable_backbone=bool(head and reached_lines),
                 input_graph_sha256=expected['graph_sha256'],
                 frontier_counts=dict(Counter(b['tag'] for b in blockers if b['policy'] == policy)))
        graphs[policy] = g
    explicit = set()
    tag_codes = {'IDENTITY_CONFLICT': P.AMBIGUOUS_IDENTITY, 'ENDPOINT_AMBIGUOUS': P.AMBIGUOUS_IDENTITY,
                 'VOLTAGE_CONFLICT': P.INCOMPATIBLE_VOLTAGE, 'OWNERSHIP_UNRESOLVED': P.OWNERSHIP_UNRESOLVED,
                 'KNOWN_OPEN': P.KNOWN_OPEN_PRESENT}
    for tag in recovery_case['constraint_tags']:
        if tag in tag_codes: explicit.add(tag_codes[tag])
    for b in blockers:
        if b['tag'] in tag_codes:
            explicit.add(tag_codes[b['tag']]); constraint_refs.update(b['conflict_refs'])
    if any(state_counts[k+':OPEN'] for k in ('SWITCH', 'DISCONNECTOR')): explicit.add(P.KNOWN_OPEN_PRESENT)
    if state_counts['EARTHING_SWITCH:CLOSED']: explicit.add(P.EXISTING_NEGATIVE_SOURCE_EVIDENCE)
    unref = [t for t in transformers if t['reference_composition'] == 'NO_REFERENCE']
    feeders = []
    for f in sorted(recovery_case['feeders'], key=lambda f: f['feeder_id']):
        facts = CompletionFacts(case_id=cid, feeder_id=f['feeder_id'], flags=tuple(sorted(f['completion_cohorts'])),
            explicit_prohibitions=tuple(sorted(explicit)), target_count=len(transformers), unreferenced_count=len(unref),
            source_line_count=counts['LINE'], accepted_junction_count=len(graphs['S0']['candidate_junctions']),
            located_transformer_count=graphs['S0']['reachable_transformers'], valid_head=head is not None,
            s0_usable=graphs['S0']['usable_backbone'], s2_usable=graphs['S2']['usable_backbone'],
            s0_full=graphs['S0']['target_coverage']=='FULL', s2_full=graphs['S2']['target_coverage']=='FULL',
            ownership_conflict=recovery_case['case_ownership_unresolved'],
            unknown_switch_state=any(state_counts[k+':UNKNOWN'] for k in ('SWITCH','DISCONNECTOR','EARTHING_SWITCH')))
        feeders.append({'facts': asdict(facts), 'source_feeder_id': f['source_feeder_id'],
                        'name_weak_evidence_only': f['name'], 'source_record_refs': sorted(f['source_record_refs']),
                        'scope': f['scope'], 'source_evidence_cohort': f['source_evidence_cohort']})
    return {'case_id': cid, 'source_case_key': recovery_case['source_case_key'],
            'profile_id': 'completion-evidence:'+sha256(canonical_json_bytes([VERSION,'case-profile',cid])).hexdigest(),
            'case_ownership_unresolved': recovery_case['case_ownership_unresolved'],
            'source': {'row_counts':counts, 'nonempty_fields':dict(nonempty), 'field_values':dict(values),
                       'state_counts':dict(state_counts), 'transformer_own_endpoint_rows':own_endpoints,
                       'source_accounting_member':'cases/'+cid+'/row_accountability.jsonl'},
            'head':head_node, 'graphs':graphs, 'target_count':len(transformers), 'unreferenced_count':len(unref),
            'unreferenced_transformer_evidence_refs':sorted(t['evidence_id'] for t in unref),
            'transformer_file_evidence':recovery_case['transformer_file_evidence'],
            'source_constraint_tags':sorted(recovery_case['constraint_tags']),
            'conflict_refs':sorted(constraint_refs), 'feeders':feeders}


PROFILE_FIELDS = {'case_id','source_case_key','profile_id','case_ownership_unresolved','source',
    'head','graphs','target_count','unreferenced_count','unreferenced_transformer_evidence_refs',
    'transformer_file_evidence','source_constraint_tags','conflict_refs','feeders'}
GRAPH_FIELDS = {'node_count','branch_count','conducting_branch_count','structural_components',
    'conducting_components','structural_cycle_rank','conducting_cycle_rank','self_loops',
    'parallel_excess','maximum_conducting_degree','reachable_node_ids','candidate_junctions',
    'target_coverage','reachable_transformers','reachable_lines','usable_backbone',
    'input_graph_sha256','frontier_counts'}


def validate_profile(p):
    """Closed D1 schema excludes graph payloads; input-bound verification proves facts."""
    if set(p) != PROFILE_FIELDS or set(p['graphs']) != {'S0','S2'}:
        raise ValueError('D1 profile schema mismatch')
    if set(p['source']) != {'row_counts','nonempty_fields','field_values','state_counts',
                           'transformer_own_endpoint_rows','source_accounting_member'}:
        raise ValueError('D1 source profile schema mismatch')
    for graph in p['graphs'].values():
        if set(graph) != GRAPH_FIELDS:raise ValueError('D1 graph profile schema mismatch')
        for region in graph['candidate_junctions']:
            if set(region) != {'node_id','hops','degree'}:raise ValueError('D1 region profile schema mismatch')
    for feeder in p['feeders']:
        if set(feeder) != {'facts','source_feeder_id','name_weak_evidence_only','source_record_refs',
                          'scope','source_evidence_cohort'}:raise ValueError('D1 feeder profile schema mismatch')
        f=CompletionFacts.from_dict(feeder['facts'])
        if (f.case_id!=p['case_id'] or f.target_count!=p['target_count']
            or f.unreferenced_count!=p['unreferenced_count']
            or f.source_line_count!=p['source']['row_counts']['LINE']
            or f.accepted_junction_count!=len(p['graphs']['S0']['candidate_junctions'])):
            raise ValueError('D1 facts/profile mismatch')
