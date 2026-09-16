"""E2.3-A: deterministic observations and experiments, never accepted topology."""
from collections import defaultdict
from hashlib import sha256

from grid_case_generator.analysis.feeder_coverage import analyze_feeder_case, unique_owner
from grid_case_generator.analysis.switch_semantics import SourceMotifIndex
from grid_case_generator.analysis.switch_projection_analysis import analyze_projection_case, build_graph, graph_coverage
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.nanjing_source.schema import NANJING_SOURCE_SCHEMA
from grid_case_generator.models.recovery import EvidenceClass, TargetCoverage, RecoveryReadiness
from grid_case_generator.models.types import EntityRef, Identifier, CanonicalId
from grid_case_generator.models.topology import ProjectionStatus
from grid_case_generator.validation.topology_switch import reachable

VERSION = 'topology-recovery-evidence-v1'
RULE_VERSION = '1.0.0'
LEAF = 'LEAF_SWITCH_TERMINAL_REPRESENTATION_V1'
UNIQUE_T = 'UNIQUE_SWITCH_DECLARED_T_ATTACHMENT_V1'
MULTI_T = 'MULTI_INCOMING_T_ATTACHMENT_V1'
RISK_T = 'MULTI_LINE_T_AS_MV_JUNCTION'
RULES = (LEAF, UNIQUE_T, MULTI_T, RISK_T)
EXPERIMENTS = {**{r: (r,) for r in RULES}, 'CUMULATIVE_LEAF_UNIQUE': (LEAF, UNIQUE_T),
               'CUMULATIVE_NARROW': (LEAF, UNIQUE_T, MULTI_T), 'RISK_COMBINED': (LEAF, UNIQUE_T, RISK_T)}
ENDPOINT_FIELDS = {
    'LINE': ('Line_FromBus', 'Line_ToBus'), 'SWITCH': ('Switch_FromBus', 'Switch_ToBus'),
    'DISCONNECTOR': ('Disconnector_FromBus', 'Disconnector_ToBus'),
    'EARTHING_SWITCH': ('EarthingSwitch_Bus',), 'TRANSFORMER': ('Transformer_FromBus', 'Transformer_ToBus'),
    'ACCESS_POINT': ('AccessPoint_Bus',), 'LOAD': ('Load_Bus',), 'DER': ('DER_Bus',),
}
PRIMARY_ORDER = ('MISSING_HEAD', 'NO_LINE', 'NO_HEAD_REACHABLE_LINE', 'REACHABLE_LINE_NO_TRANSFORMER',
                 'IDENTITY_CONFLICT', 'ENDPOINT_AMBIGUOUS', 'VOLTAGE_CONFLICT', 'KNOWN_OPEN',
                 'SWITCH_DEGREE_RULE', 'ACCESS_POINT_UNSUPPORTED', 'ENDPOINT_UNRESOLVED',
                 'TRANSFORMER_MULTI_INCIDENCE', 'OTHER_BOUNDARY')
CONSTRAINTS = {'IDENTITY_CONFLICT', 'ENDPOINT_AMBIGUOUS', 'VOLTAGE_CONFLICT', 'KNOWN_OPEN', 'OWNERSHIP_UNRESOLVED'}


def evidence_id(kind, case_id, key):
    return 'recovery-evidence:' + sha256(canonical_json_bytes([VERSION, kind, case_id, key])).hexdigest()


def ref(kind, owner):
    return EntityRef(entity_type=Identifier(kind), entity_id=CanonicalId(owner))


def seen_nodes(edges, head):
    adjacency = defaultdict(list)
    for e in edges:
        if e['conducting']:
            adjacency[e['a']].append((e['b'], e['id']))
            adjacency[e['b']].append((e['a'], e['id']))
    return reachable(adjacency, head)


def target_status(total, reached):
    if not total: return TargetCoverage.NO_SOURCE_TARGET
    if reached == total: return TargetCoverage.FULL
    return TargetCoverage.PARTIAL if reached else TargetCoverage.FAILED


def cycle_rank(nodes, edges):
    """Multigraph cyclomatic number, retaining parallel edges and self loops."""
    parent = {n: n for n in nodes}
    def root(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]; n = parent[n]
        return n
    rank = 0
    for e in edges:
        a, b = root(e['a']), root(e['b'])
        if a == b: rank += 1
        else: parent[a] = b
    return rank


def measure(nodes, edges, head, transformer_groups):
    seen = seen_nodes(edges, head)
    owners = {n['owner'] for key, n in nodes.items() if n['role'] == 'transformer-mv/mv' and key in seen}
    n = sum(unique_owner(a) in owners for a in transformer_groups)
    return {'target_coverage': target_status(len(transformer_groups), n),
            'reachable_transformers': n,
            'reachable_lines': len({e['owner'] for e in edges if e['kind'] == 'line' and e['conducting'] and e['a'] in seen and e['b'] in seen}),
            'graph_sha256': sha256(canonical_json_bytes({'nodes': nodes, 'edges': edges})).hexdigest(),
            'structural_cycle_rank': cycle_rank(nodes, edges),
            'conducting_cycle_rank': cycle_rank(nodes, [e for e in edges if e['conducting']])}


def sorted_rows(rows):
    return sorted(rows, key=lambda r: r['evidence_id'])


def analyze_recovery_case(details, baseline, files, candidates=None, feeder_analysis=None):
    """Pure case analysis. Inputs are typed, verified evidence; fixtures use the same mapper."""
    index = SourceMotifIndex(details)
    cid = str(index.case.case_id)
    if baseline.topology.case_id != cid: raise ValueError('recovery case mismatch')
    if candidates is None: candidates = analyze_projection_case(details, baseline)['candidates']
    candidates = sorted(candidates, key=lambda c: c['switch_id'])
    if any(c['case_id'] != cid for c in candidates): raise ValueError('candidate case mismatch')
    if feeder_analysis is None: feeder_analysis = analyze_feeder_case(details, baseline, candidates)
    if feeder_analysis['case_id'] != cid: raise ValueError('feeder evidence case mismatch')
    chosen = {c['source_entity_ref'].entity_id: c for c in candidates if c['decisions']['S2']['projected']}
    groups = {k: [a for (kind, _), a in sorted(index.groups.items()) if kind == k]
              for k in ('TRANSFORMER', 'LINE', 'SWITCH', 'FEEDER')}
    head = baseline.topology.feeder_head_id
    topologies = {policy: build_graph(index, baseline, {} if policy == 'S0' else chosen) for policy in ('S0', 'S2')}
    measurements = {p: measure(n, e, head, groups['TRANSFORMER']) for p, (n, e) in topologies.items()}
    for policy, (nodes, edges) in topologies.items():
        expected = feeder_analysis['policies'][policy]
        observed = measurements[policy]
        coverage = graph_coverage(nodes, edges, head, len(groups['SWITCH']), baseline.coverage.counts['published_transformers'])
        if (observed['graph_sha256'] != expected['graph_sha256'] or coverage != expected['coverage']
                or observed['reachable_transformers'] != expected['reachable']['TRANSFORMER']
                or observed['reachable_lines'] != expected['reachable']['LINE']):
            raise ValueError('recovery baseline graph/coverage mismatch: ' + cid + '/' + policy)
    for kind in groups:
        if kind != 'FEEDER' and len(groups[kind]) != feeder_analysis['policies']['S2']['totals'][kind]:
            raise ValueError('source denominator mismatch: ' + kind)
    case_ref = ref('GRID_CASE', cid)
    def provenance(kind, key, owner=None, accounts=(), terminals=(), supporting=(), conflicts=(), rule='SOURCE_EVIDENCE_AUDIT_V1', reason='OBSERVED_SOURCE_EVIDENCE'):
        locators = {str(a.raw_record.source_record_ref) for a in accounts}
        locators.update(supporting)
        locators.update(str(t.source_record_ref) for t in terminals if t.source_record_ref)
        entity = ref('EQUIPMENT', owner) if owner else None
        return {'evidence_id': evidence_id(kind, cid, key), 'case_id': cid, 'source_case_ref': case_ref,
                'source_entity_ref': entity, 'source_terminal_refs': sorted({str(t.terminal_id) for t in terminals}),
                'supporting_source_refs': sorted(locators), 'conflict_refs': sorted(set(conflicts)),
                'rule_id': rule, 'rule_version': RULE_VERSION, 'derived_ids': [],
                'decision_reason': reason, 'evidence_class': EvidenceClass.UNRESOLVED, 'approved': False}
    incoming = defaultdict(list); own = defaultdict(list)
    for a in index.rows:
        row = a.raw_record; fields = dict(row.fields or ()); kind = row.source_file_type.value
        for number, field in enumerate(ENDPOINT_FIELDS.get(kind, ()), 1):
            raw = fields.get(field)
            if not raw: continue
            ep = index.endpoint(raw, row, number)
            declaration = {'source_record_ref': str(row.source_record_ref), 'field': field, 'raw_value': raw,
                           'owner_kind': kind, 'owner_ref': a.canonical_ref,
                           'source_reference_status': ep['source_reference_status'],
                           'resolved_source_ref': ep['source_target_ref'],
                           'diagnostic_status': ep['diagnostic_status'],
                           'diagnostic_entity_type': ep['diagnostic_entity_type'],
                           'supporting_source_refs': list(ep['supporting_source_refs'])}
            incoming[raw].append(declaration)
            own[str(row.source_record_ref)].append(declaration)
    projected = {p.source_terminal_ref.entity_id: p for p in baseline.projections
                 if p.source_terminal_ref is not None and p.projection_status is ProjectionStatus.PROJECTED}
    excluded = {p.source_terminal_ref.entity_id: p for p in baseline.projections
                if p.source_terminal_ref is not None and p.projection_status is not ProjectionStatus.PROJECTED}
    owner_projections = defaultdict(list)
    for p in baseline.projections: owner_projections[p.source_entity_ref.entity_id].append(p)
    seen = {p: seen_nodes(e, head) for p, (n, e) in topologies.items()}
    transformer_rows = []
    for accounts in groups['TRANSFORMER']:
        fields = dict(accounts[0].raw_record.fields or ())
        raw = fields.get('Transformer_ID') or None
        owner = unique_owner(accounts)
        declarations = incoming.get(raw, []) if raw else []
        outgoing = [d for a in accounts for d in own[str(a.raw_record.source_record_ref)]]
        kinds = {d['owner_kind'] for d in declarations}
        composition = ('NO_REFERENCE' if not declarations and not outgoing else
                       'LINE_ONLY' if kinds == {'LINE'} and not outgoing else
                       'SWITCH_ONLY' if kinds == {'SWITCH'} and not outgoing else
                       'LINE_AND_SWITCH' if kinds == {'LINE', 'SWITCH'} and not outgoing else 'OTHER')
        conflicts = [str(a.raw_record.source_record_ref) for a in accounts] if owner is None else []
        row = provenance('transformer', raw or str(accounts[0].raw_record.source_record_ref), owner, accounts,
                         terminals=tuple(t for a in accounts if a.canonical_ref for t in index.terminals[a.canonical_ref.entity_id]),
                         supporting=[v for d in declarations for v in d['supporting_source_refs']], conflicts=conflicts)
        attachment = {}
        for p, (nodes, edges) in topologies.items():
            ids = sorted(n for n, value in nodes.items() if value['role'] == 'transformer-mv/mv' and owner is not None and value['owner'] == owner)
            attachment[p] = {'projected': bool(ids), 'reachable': any(n in seen[p] for n in ids), 'derived_ids': ids}
        row.update(source_id=raw, source_record_refs=sorted(str(a.raw_record.source_record_ref) for a in accounts),
                   raw_row_count=len(accounts), identity_statuses=sorted({a.identity_status.value if a.identity_status else 'UNASSESSED' for a in accounts}),
                   identity_ambiguous=owner is None, reference_composition=composition,
                   incoming_references=declarations, outgoing_references=outgoing,
                   unresolved_reference=any(d['source_reference_status'] in ('UNRESOLVED', 'NOT_PUBLISHED') or d['diagnostic_status']=='UNRESOLVED' for d in declarations+outgoing),
                   ambiguous_reference=any(d['diagnostic_status']=='AMBIGUOUS' or d['source_reference_status']=='AMBIGUOUS' for d in declarations+outgoing),
                   line_incidence_count=len({key for key, number, a in index.incident.get(raw, ())}), attachment=attachment)
        transformer_rows.append(row)
    transformer_rows = sorted_rows(transformer_rows)
    tfiles = sorted((f for f in files if str(f['source_file_type']) == 'TRANSFORMER'), key=lambda f: f['member_path'])
    file_evidence = {'files': tfiles, 'file_count': len(tfiles), 'row_count': sum(f['row_count'] for f in tfiles),
                     'source_identity_groups': len(transformer_rows)}
    unreferenced = [t for t in transformer_rows if t['reference_composition']=='NO_REFERENCE']
    expected_header = next(f.header for f in NANJING_SOURCE_SCHEMA.files if f.file_type.value=='TRANSFORMER')
    recognized_files = bool(tfiles) and all(tuple(f.get('header') or ())==expected_header for f in tfiles)
    file_evidence['recognized_headers'] = recognized_files
    cohort = ('ZERO_TRANSFORMER_ROWS' if recognized_files and file_evidence['row_count']==0 and not transformer_rows
              else 'SOURCE_FILE_UNDETERMINED' if not transformer_rows else
              'HAS_UNREFERENCED_TRANSFORMER' if unreferenced else 'ALL_TARGETS_HAVE_REFERENCE')
    # Terminal mappings are independent per policy; never modify Source Terminal.
    accepted_switch_owners = {e['owner'] for e in topologies['S0'][1] if e['kind']=='switch'}
    def terminal_nodes(policy):
        result = {key: p.derived_target_ids[0] for key, p in projected.items()}
        if policy == 'S2':
            for owner in sorted(index.terminals):
                for t in index.terminals[owner]:
                    target = t.resolved_source_ref
                    if target and t.source_ref_status.value=='EXACT' and target.entity_id in chosen and target.entity_id not in accepted_switch_owners:
                        # Only Line incidence has the E2.2 in/out convention.
                        entity = index.entities.get(owner)
                        if getattr(entity, 'equipment_type', None) == 'LINE':
                            result[t.terminal_id] = 'analysis-only:' + target.entity_id + (':in' if t.terminal_no==2 else ':out')
        return result
    terminal_maps = {p: terminal_nodes(p) for p in topologies}
    blockers = []
    reason_tags = {'SWITCH_DEGREE':'SWITCH_DEGREE_RULE', 'ACCESS_POINT_UNSUPPORTED':'ACCESS_POINT_UNSUPPORTED',
                   'UNRESOLVED_REFERENCE':'ENDPOINT_UNRESOLVED', 'MISSING_REFERENCE':'ENDPOINT_UNRESOLVED',
                   'AMBIGUOUS_REFERENCE':'ENDPOINT_AMBIGUOUS', 'IDENTITY_NOT_UNIQUE':'IDENTITY_CONFLICT',
                   'INCIDENT_IDENTITY_CONFLICT':'IDENTITY_CONFLICT', 'BUS_VOLTAGE_CONFLICT':'VOLTAGE_CONFLICT',
                   'INVALID_VOLTAGE_EVIDENCE':'VOLTAGE_CONFLICT', 'TRANSFORMER_DEGREE':'TRANSFORMER_MULTI_INCIDENCE'}
    for policy, (nodes, edges) in topologies.items():
        mapping = terminal_maps[policy]
        for owner, entity in sorted(index.entities.items()):
            if getattr(entity, 'equipment_type', None) != 'LINE': continue
            terms = index.terminals[owner]
            if [t.terminal_no for t in terms] != [1, 2]: continue
            for i, t in enumerate(terms):
                if mapping.get(terms[1-i].terminal_id) not in seen[policy] or t.terminal_id in mapping: continue
                p = excluded.get(t.terminal_id)
                reason = str(p.exclusion_reason) if p else 'NO_PROJECTION'
                tag = reason_tags.get(reason, 'OTHER_BOUNDARY')
                row = provenance('frontier', [policy, t.terminal_id], owner, terminals=(t, terms[1-i]),
                                 supporting=p.supporting_source_refs if p else (),
                                 conflicts=p.supporting_source_refs if p and tag in CONSTRAINTS else (),
                                 rule='FRONTIER_OBSERVATION_V1', reason=reason)
                row.update(policy=policy, tag=tag, raw_endpoint=t.raw_connected_ref,
                           resolved_source_ref=t.resolved_source_ref, reached_node_id=mapping[terms[1-i].terminal_id])
                blockers.append(row)
        for e in edges:
            device = index.devices.get(e['owner'])
            if e['kind']=='switch' and device and device.normal_state and device.normal_state.value=='OPEN' and ((e['a'] in seen[policy]) != (e['b'] in seen[policy])):
                refs = sorted(index.entity_refs[e['owner']])
                row = provenance('frontier', [policy, e['id']], e['owner'], terminals=index.terminals[e['owner']], supporting=refs,
                                 conflicts=refs, rule='FRONTIER_OBSERVATION_V1', reason='NORMAL_OPEN_NOT_SOURCE_ERROR')
                row.update(policy=policy, tag='KNOWN_OPEN', derived_ids=[e['id']], raw_endpoint=None, resolved_source_ref=None,
                           reached_node_id=e['a'] if e['a'] in seen[policy] else e['b'])
                blockers.append(row)
        structural_tags = []
        m = measurements[policy]
        if head is None: structural_tags.append('MISSING_HEAD')
        if not groups['LINE']: structural_tags.append('NO_LINE')
        elif not m['reachable_lines']: structural_tags.append('NO_HEAD_REACHABLE_LINE')
        elif not m['reachable_transformers']: structural_tags.append('REACHABLE_LINE_NO_TRANSFORMER')
        for tag in structural_tags:
            row = provenance('frontier', [policy, tag], rule='FRONTIER_OBSERVATION_V1', reason=tag,
                             accounts=tuple(a for g in groups['FEEDER'] for a in g))
            row.update(policy=policy, tag=tag, raw_endpoint=None, resolved_source_ref=None, reached_node_id=head)
            blockers.append(row)
    # Case-wide constraints also preserve conflicts beyond the currently reachable frontier.
    constraints = set()
    constraint_refs = set()
    for accounts in index.groups.values():
        if len(accounts)>1 or any(a.identity_status is not None and a.identity_status.value!='UNIQUE' for a in accounts):
            constraints.add('IDENTITY_CONFLICT'); constraint_refs.update(str(a.raw_record.source_record_ref) for a in accounts)
    for p in baseline.projections:
        reason = str(p.exclusion_reason)
        if 'VOLTAGE_CONFLICT' in reason or reason=='INVALID_VOLTAGE_EVIDENCE':
            constraints.add('VOLTAGE_CONFLICT'); constraint_refs.update(p.supporting_source_refs)
    ownership = len(groups['FEEDER'])!=1 or unique_owner(groups['FEEDER'][0]) is None
    if ownership: constraints.add('OWNERSHIP_UNRESOLVED')
    # Connection-level approval and provenance, distinct from counterfactual reachability.
    connections = []
    baseline_ids = {e['id'] for e in topologies['S0'][1]}
    for policy, (nodes, edges) in topologies.items():
        for e in edges:
            ps = owner_projections[e['owner']]
            supporting = {r for p in ps for r in p.supporting_source_refs}
            supporting.update(index.entity_refs[e['owner']])
            candidate = chosen.get(e['owner'])
            if candidate: supporting.update(candidate.get('supporting_source_refs', ()))
            row = provenance('connection', [policy, e['id']], e['owner'], terminals=index.terminals[e['owner']],
                             supporting=supporting, rule='ACCEPTED_V1_BRANCH' if e['id'] in baseline_ids else 'S2_COUNTERFACTUAL',
                             reason='BASELINE_PRESERVED' if e['id'] in baseline_ids else 'S2_NOT_ACCEPTED')
            approved = e['id'] in baseline_ids
            row.update(policy=policy, approved=approved,
                       evidence_class=EvidenceClass.RULE_INFERRED if approved else EvidenceClass.UNRESOLVED,
                       derived_ids=[e['id'], e['a'], e['b']], conducting=e['conducting'],
                       approved_rule_refs=sorted({str(p.rule_id)+'/'+p.rule_version for p in ps if p.projection_status is ProjectionStatus.PROJECTED}) if approved else [])
            connections.append(row)
    # Candidate discovery over full source incidence. No candidate becomes accepted.
    raw_by_locator = {str(a.raw_record.source_record_ref):a.raw_record for a in index.rows}
    witnesses = []; additions = defaultdict(list); overrides = defaultdict(dict); new_nodes = defaultdict(dict)
    nodes, edges = topologies['S2']
    def candidate(rule, owner, accounts, terms, related, assumptions, edits, extra_nodes):
        ps = [p for p in owner_projections[owner] if p.exclusion_reason is not None]
        conflict = [r for p in ps if str(p.exclusion_reason) in ('IDENTITY_NOT_UNIQUE','BUS_VOLTAGE_CONFLICT','INVALID_VOLTAGE_EVIDENCE') for r in p.supporting_source_refs]
        row = provenance('candidate', [rule, owner], owner, accounts, terms, related, conflict, rule, 'UNAPPROVED_SEMANTICS')
        row['source_records'] = [{'source_record_ref':loc,'source_file_type':raw_by_locator[loc].source_file_type,
                                  'fields':raw_by_locator[loc].fields} for loc in row['supporting_source_refs'] if loc in raw_by_locator]
        row.update(assumptions=assumptions, experiment_status='RISK_EXPERIMENT_ONLY' if rule==RISK_T else 'CANDIDATE_ONLY',
                   recommended=False if rule==RISK_T else None,
                   derived_ids=sorted(extra_nodes), source_exclusions=sorted({str(p.exclusion_reason) for p in ps}))
        witnesses.append(row); additions[rule].extend(edits); new_nodes[rule].update(extra_nodes)
    def safe_incidence(raw, owner):
        incident = index.incident.get(raw, ())
        if index.malformed_lines: return None
        result = []
        for key, number, a in incident:
            if unique_owner(index.line_groups[key]) is None: return None
            ts = index.terms_by_row.get((a.raw_record.source_record_ref, number), ())
            if len(ts)!=1 or ts[0].source_ref_status.value!='EXACT' or ts[0].resolved_source_ref.entity_id!=owner: return None
            result.append((a, ts[0]))
        return result
    def node_id(owner): return 'recovery-analysis:' + owner + ':mv'
    for (kind, key), accounts in sorted(index.groups.items()):
        if kind not in ('SWITCH','TRANSFORMER'): continue
        owner = unique_owner(accounts)
        if owner is None or key[0]!='ID': continue
        raw = key[1]; a = accounts[0]; fields = dict(a.raw_record.fields or ())
        incident = safe_incidence(raw, owner)
        if incident is None: continue
        related = {str(a.raw_record.source_record_ref)}
        related.update(str(row.raw_record.source_record_ref) for row, t in incident)
        terms = tuple(index.terminals[owner]) + tuple(t for row, t in incident)
        if kind=='SWITCH':
            device = index.devices.get(owner)
            if not device or not device.normal_state or device.normal_state.value not in ('CLOSED','OPEN'): continue
            x, y = fields.get('Switch_FromBus',''), fields.get('Switch_ToBus','')
            if len(incident)==1 and incident[0][1].terminal_no==2 and not y:
                line, term = incident[0]; outer = dict(line.raw_record.fields or ()).get('Line_FromBus')
                ep = index.endpoint(x, a.raw_record, 1)
                outer_ep = index.endpoint(outer, line.raw_record, 1)
                if x and x==outer and ep['source_reference_status']=='EXACT' and ep['diagnostic_status']=='EXACT' and outer_ep['source_reference_status']=='EXACT':
                    port = 'recovery-analysis:' + owner + ':in'; other = port + ':unbound'
                    related.update(ep['supporting_source_refs'])
                    override = {term.terminal_id:port}; overrides[LEAF].update(override)
                    ns = {port:{'role':'switch-port/in','owner':owner,'raw_bus_id':None}, other:{'role':'switch-port/out','owner':owner,'raw_bus_id':None}}
                    ed = {'id':'recovery-analysis:'+owner, 'a':port,'b':other,'kind':'switch','owner':owner,'conducting':device.normal_state.value=='CLOSED','added':True}
                    candidate(LEAF, owner, accounts, terms, related, ['REMOTE_CONNECTION_UNRESOLVED'], [ed], ns)
            ep = index.endpoint(y, a.raw_record, 2)
            if owner in chosen and ep['source_reference_status']=='EXACT' and ep['diagnostic_status']=='EXACT' and ep['diagnostic_entity_type']=='TRANSFORMER' and not index.incident.get(y):
                declarations = [d for d in incoming[y] if d['owner_kind']=='SWITCH']
                if len({d['source_record_ref'] for d in declarations})!=1: continue
                target = ep['source_target_ref'].entity_id
                target_accounts = index.lookup[y]
                tf = dict(target_accounts[0].raw_record.fields or ())
                if unique_owner(target_accounts)!=target or tf.get('Transformer_FromBus') or tf.get('Transformer_ToBus'): continue
                nid = node_id(target); ns = {nid:{'role':'transformer-mv/mv','owner':target,'raw_bus_id':None}}
                ed = {'id':'recovery-analysis:attachment:'+owner, 'a':'analysis-only:'+owner+':out','b':nid,'kind':'hypothetical-attachment','owner':owner,'conducting':True,'added':True}
                if ed['a'] not in nodes: continue
                related.update(ep['supporting_source_refs'])
                candidate(UNIQUE_T, owner, accounts+target_accounts, terms, related, ['SWITCH_LINE_ENDPOINT_RELATION_UNCONFIRMED','TRANSFORMER_MV_SIDE_UNCONFIRMED'], [ed], ns)
        else:
            if fields.get('Transformer_FromBus') or fields.get('Transformer_ToBus'): continue
            if len({row.raw_record.source_record_ref for row, t in incident})<=1: continue
            nid = node_id(owner); ns = {nid:{'role':'transformer-mv/mv','owner':owner,'raw_bus_id':None}}
            rules = [RISK_T]
            if len(incident)==2 and all(t.terminal_no==2 for row,t in incident): rules.append(MULTI_T)
            for rule in rules:
                overrides[rule].update({t.terminal_id:nid for row,t in incident})
                candidate(rule, owner, accounts, terms, related, ['SAME_MV_WINDING_UNCONFIRMED'], [], ns)
    experiments = {}
    for name, rules in EXPERIMENTS.items():
        nn = dict(nodes); ee = {e['id']:e for e in edges}; override = {}
        for rule in rules:
            nn.update(new_nodes[rule]); ee.update({e['id']:e for e in additions[rule]}); override.update(overrides[rule])
        for owner, entity in sorted(index.entities.items()):
            if getattr(entity,'equipment_type',None)!='LINE' or entity.identity_status.value!='UNIQUE': continue
            ts = index.terminals[owner]
            if [t.terminal_no for t in ts]!=[1,2] or not any(t.terminal_id in override for t in ts): continue
            ends = [override.get(t.terminal_id,terminal_maps['S2'].get(t.terminal_id)) for t in ts]
            if all(ends):
                # Replace this source Line's representation, never add duplicate physical Line edges.
                ee = {key:e for key,e in ee.items() if not(e['kind']=='line' and e['owner']==owner)}
                ed = {'id':'recovery-analysis:line:'+owner,'a':ends[0],'b':ends[1],'kind':'line','owner':owner,'conducting':True,'added':True}
                ee[ed['id']] = ed
        experiments[name] = measure(nn, sorted(ee.values(),key=lambda e:e['id']), head, groups['TRANSFORMER'])
    blockers = sorted_rows(blockers); witnesses = sorted_rows(witnesses); connections = sorted_rows(connections)
    policy_tags = {p: sorted({b['tag'] for b in blockers if b['policy']==p}) for p in topologies}
    composition = {'source_confirmed_connections':0,
                   'rule_inferred_connections':sum(c['approved'] for c in connections if c['policy']=='S2'),
                   'synthetic_connections':0,
                   'unapproved_counterfactual_connections':sum(not c['approved'] for c in connections if c['policy']=='S2'),
                   'unresolved_boundaries':sum(b['policy']=='S2' for b in blockers),
                   'existing_synthetic_head_nodes':int(head is not None)}
    cohort_flags = []
    if unreferenced: cohort_flags.append('A')
    if cohort=='ZERO_TRANSFORMER_ROWS': cohort_flags.append('B')
    if cohort=='ALL_TARGETS_HAVE_REFERENCE' and measurements['S2']['target_coverage']!=TargetCoverage.FULL: cohort_flags.append('C')
    if constraints or set(policy_tags['S2']) & CONSTRAINTS: cohort_flags.append('D')
    readiness = []
    if not transformer_rows or ownership: readiness.append(RecoveryReadiness.ROLE_UNDETERMINED)
    if 'D' in cohort_flags: readiness.append(RecoveryReadiness.BLOCKED_BY_CONFLICT)
    if 'A' in cohort_flags: readiness.append(RecoveryReadiness.NEEDS_SYNTHETIC_COMPLETION)
    if witnesses or measurements['S0']['target_coverage']!=TargetCoverage.FULL or composition['unapproved_counterfactual_connections']:
        readiness.append(RecoveryReadiness.NEEDS_RULE_REVIEW)
    if not readiness: readiness.append(RecoveryReadiness.SOURCE_EVIDENCE_SUFFICIENT)
    fs = []
    for feeder in feeder_analysis['feeders']:
        tags = policy_tags['S2']
        fs.append(dict(feeder, target_coverage=measurements['S2']['target_coverage'], legacy_target_status=feeder_analysis['policies']['S2']['transformer_goal_status'],
                       source_evidence_cohort=cohort, evidence_composition=composition,
                       observed_blockers=tags, primary_blocker=next((t for t in PRIMARY_ORDER if t in tags),'NONE'),
                       recovery_readiness=readiness[0], readiness_reasons=readiness, completion_cohorts=cohort_flags,
                       constraint_tags=sorted(constraints), constraint_refs=sorted(constraint_refs),
                       e3_ready=False, e3_readiness_reason='E3_NOT_AUTHORIZED_AND_CONTRACT_NOT_ASSESSED',
                       experiments=experiments, graphs=measurements))
    return {'case_id':cid, 'source_case_key':index.case.source_case_key, 'feeders':fs,
            'source_evidence_cohort':cohort, 'transformer_file_evidence':file_evidence,
            'transformers':transformer_rows, 'blockers':blockers, 'connections':connections, 'candidates':witnesses,
            'graphs':measurements, 'experiments':experiments,
            'constraint_tags':sorted(constraints), 'constraint_refs':sorted(constraint_refs),
            'case_ownership_unresolved':ownership}
