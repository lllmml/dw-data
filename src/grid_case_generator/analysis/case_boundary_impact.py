"""Transient connectivity diagnostics, with no topology or proposal serialization."""
from collections import Counter, defaultdict
from pathlib import Path

from grid_case_generator.analysis.case_boundary_audit import SCOPE


class Connectivity:
    def __init__(self, nodes, edges=(), conducting=False):
        self.parent = {n: n for n in nodes}; self.size = {n: 1 for n in nodes}
        self.cycles = 0
        for a, b, closed in edges:
            if conducting and not closed: continue
            self.join(a, b)

    def root(self, node):
        while self.parent[node] != node:
            self.parent[node] = self.parent[self.parent[node]]; node = self.parent[node]
        return node

    def connected(self, a, b):
        return a in self.parent and b in self.parent and self.root(a) == self.root(b)

    def join(self, a, b):
        a, b = self.root(a), self.root(b)
        if a == b:
            self.cycles += 1; return
        if self.size[a] < self.size[b]: a, b = b, a
        self.parent[b] = a; self.size[a] += self.size[b]


def graph_diagnostics(nodes, base, additions, heads):
    before = Connectivity(nodes, base); after = Connectivity(nodes, [*base, *additions])
    cb = Connectivity(nodes, base, True); ca = Connectivity(nodes, [*base, *additions], True)
    old_heads = Counter(cb.root(h) for h in heads if h in cb.parent)
    new_heads = Counter(ca.root(h) for h in heads if h in ca.parent)
    return {'physical_cycle_rank_delta': after.cycles - before.cycles,
            'conducting_cycle_rank_delta': ca.cycles - cb.cycles,
            'open_cut_bypasses': sum(not closed and not cb.connected(a,b) and ca.connected(a,b) for a,b,closed in base),
            'new_multiple_head_components': sum(n > 1 for n in new_heads.values()) - sum(n > 1 for n in old_heads.values()),
            'physical_components_before': len({before.root(n) for n in nodes}),
            'physical_components_after': len({after.root(n) for n in nodes}),
            'largest_component_before': max(before.size[before.root(n)] for n in nodes) if nodes else 0,
            'largest_component_after': max(after.size[after.root(n)] for n in nodes) if nodes else 0}


def impact(cases, analysis, roots):
    from grid_case_generator.io.case_boundary_audit import read_lines
    by_case = {c['case_id']: c for c in cases}
    accepted = {c['case_id']: c for c in read_lines(Path(roots['accepted']) / 'case_topologies.jsonl')}
    refs = analysis['cross_case_references']; refs_by_case = defaultdict(list)
    lookup = {}
    for r in refs:
        refs_by_case[r['case_id']].append(r)
        lookup[(r['case_id'], r['source_record_ref'], r['raw_field'])] = r
    index = {e['index_id']: e for e in analysis['global_reference_index']}
    source_entities = {(c['case_id'], e['source_record_ref']): e for c in cases for e in c['entities']}
    bus_anchors = defaultdict(set); nodes = {}; base = []; heads = []
    for cid, c in accepted.items():
        for n in c['base_nodes']: nodes[n['node_id']] = n
        base.extend((e['a'], e['b'], e['conducting']) for e in c['base_edges'])
        if c['head_id']: heads.append(c['head_id'])
        for node, records in c['region_source_refs'].items():
            for record in records:
                entity = source_entities.get((cid, record))
                if entity and entity['source_entity_type'] == 'BUS' and node in nodes:
                    bus_anchors[(cid, record)].add(node)
    # Frozen projections supply only existing accepted targets, never a new junction.
    projected = {}; represented_lines = set()
    for x in read_lines(Path(roots['d3']) / 'case_inputs.jsonl'):
        cid = x['base']['case_id']; terminal = {t['terminal_id']: t for t in x['terminals']}
        accepted_nodes = {n['node_id'] for n in accepted[cid]['base_nodes']}
        for p in x['projections']:
            if p['projection_status'] != 'PROJECTED': continue
            target = p['derived_target_ids']
            if p.get('source_terminal_ref'):
                t = terminal[p['source_terminal_ref']['entity_id']]
                existing = [n for n in target if n in accepted_nodes]
                if len(existing) == 1:
                    projected[(cid, t['source_record_ref'], t['terminal_no'])] = existing[0]
            if p.get('source_entity_ref') and any(t == e['edge_id'] for t in target for e in accepted[cid]['base_edges'] if e['kind'] == 'LINE'):
                represented_lines.add((cid, p['source_entity_ref']['entity_id']))
    for cid, c in accepted.items():
        for e in c['base_edges']:
            if e['kind'] == 'LINE' and e.get('source_entity_ref'):
                represented_lines.add((cid, e['source_entity_ref']['entity_id']))
    local_entities = defaultdict(list)
    for c in cases:
        for e in c['entities']: local_entities[(c['case_id'], e['raw_source_id'])].append(e)
    additions = []; candidate_lines = []; complete_identity = defaultdict(list)
    strict_endpoint = []; resolutions = []
    for r in refs:
        anchor = None
        if r['strict_candidate']:
            candidate = r['candidates'][0]
            e = index[candidate['index_id']]
            anchors = bus_anchors[(e['case_id'], e['source_record_ref'])] if e['source_entity_type'] == 'BUS' else set()
            if len(anchors) == 1: anchor = next(iter(anchors))
            if r['source_entity_type'] == 'LINE': strict_endpoint.append(r['reference_id'])
        resolutions.append({'scope': SCOPE, 'reference_id': r['reference_id'], 'case_id': r['case_id'],
            'source_record_ref': r['source_record_ref'], 'raw_field': r['raw_field'],
            'classification': r['classification'], 'safe_looking_candidate': r['safe_looking_candidate'],
            'unique_same_station_voltage_compatible': r['strict_candidate'],
            'ownership_status': r['ownership_status'], 'existing_accepted_anchor_id': anchor,
            'placement_status': 'EXISTING_BUS_ANCHOR' if anchor else 'NO_UNIQUE_ACCEPTED_ANCHOR',
            'structural_conflicts': (['STATION_CONFLICT'] if r['cross_station_match_count'] else [])
                + (['VOLTAGE_CONFLICT'] if r['voltage_conflict_count'] else [])
                + (['CROSS_FEEDER_OWNERSHIP_UNCONFIRMED'] if r['external_candidate_count'] else []),
            'approved': False, 'applied': False})
    resolution_lookup = {r['reference_id']: r for r in resolutions}
    for case in cases:
        cid = case['case_id']; c = accepted[cid]
        for entity in case['entities']:
            if entity['source_entity_type'] != 'LINE' or entity['identity_status'] != 'UNIQUE' or not entity['canonical_ref']:
                continue
            record = entity['source_record_ref']; fields = entity['fields']; endpoints = []; identity_ok = []; cross = []
            for side, field in enumerate(('Line_FromBus', 'Line_ToBus'), 1):
                raw = fields.get(field, ''); r = lookup.get((cid, record, field))
                local = local_entities.get((cid, raw), [])
                identity_ok.append(bool((len(local) == 1 and local[0]['identity_status'] == 'UNIQUE'
                    and local[0]['source_entity_type'] in ('BUS','SWITCH','STATION','TRANSFORMER','ACCESS_POINT'))
                    or (r and r['strict_candidate'])))
                anchor = projected.get((cid, record, side))
                if not anchor and len(local) == 1 and local[0]['source_entity_type'] == 'BUS':
                    choices = bus_anchors[(cid, local[0]['source_record_ref'])]
                    if len(choices) == 1: anchor = next(iter(choices))
                if r and r['strict_candidate']:
                    cross.append(r['reference_id'])
                    anchor = resolution_lookup[r['reference_id']]['existing_accepted_anchor_id']
                endpoints.append(anchor)
            if not cross: continue
            if all(identity_ok): complete_identity[cid].append(record)
            if all(endpoints) and endpoints[0] != endpoints[1] and (cid, entity['canonical_ref']['entity_id']) not in represented_lines:
                additions.append((endpoints[0], endpoints[1], True))
                candidate_lines.append({'case_id': cid, 'source_record_ref': record,
                    'reference_ids': cross, 'endpoints': endpoints})
    # Counts are over source-Line representations, not invented cross-case connector edges.
    diagnostics = graph_diagnostics(list(nodes), base, additions, heads)
    reachability = {}
    for conducting in (False, True):
        before = Connectivity(nodes, base, conducting); after = Connectivity(nodes, [*base, *additions], conducting)
        line_before = line_after = transformer_before = transformer_after = 0
        for cid, c in accepted.items():
            h = c['head_id']
            for e in c['base_edges']:
                if e['kind'] != 'LINE': continue
                line_before += before.connected(h, e['a']) and before.connected(h, e['b'])
                line_after += after.connected(h, e['a']) and after.connected(h, e['b'])
            for n in c['base_nodes']:
                if n.get('transformer_key'):
                    transformer_before += before.connected(h, n['node_id'])
                    transformer_after += after.connected(h, n['node_id'])
        for line in candidate_lines:
            h = accepted[line['case_id']]['head_id']; a,b = line['endpoints']
            line_after += after.connected(h,a) and after.connected(h,b)
        reachability['conducting' if conducting else 'physical'] = {
            'reachable_lines_before': line_before, 'reachable_lines_after': line_after,
            'reachable_line_delta': line_after-line_before,
            'reachable_transformers_before': transformer_before, 'reachable_transformers_after': transformer_after,
            'reachable_transformer_delta': transformer_after-transformer_before}
    # A backbone eligibility observation must have one local Bus anchor in the new Line component.
    combined = Connectivity(nodes, [*base,*additions])
    eligible = set(); lines_by_case = defaultdict(list)
    for line in candidate_lines: lines_by_case[line['case_id']].append(line)
    for cid, lines in lines_by_case.items():
        roots_now = {combined.root(n) for l in lines for n in l['endpoints']}
        local_bus_nodes = {n for (c, _), ns in bus_anchors.items() if c == cid for n in ns}
        anchors = {n for n in local_bus_nodes if combined.root(n) in roots_now}
        if len(roots_now) == 1 and len(anchors) == 1 and not accepted[cid]['hard_blockers']:
            if not any(e['kind'] == 'LINE' for e in accepted[cid]['base_edges']): eligible.add(cid)
    target = []; old_targets = list(read_lines(Path(roots['placement']) / 'target_feeders.jsonl'))
    for old in old_targets:
        if old['primary_status'] != 'INSUFFICIENT_PLACEMENT_EVIDENCE': continue
        cid = old['case_id']; rr = [r for r in refs_by_case[cid] if r['source_entity_type'] == 'LINE']
        counts = Counter(r['classification'] for r in rr)
        if any(r['cross_station_match_count'] or r['voltage_conflict_count'] for r in rr): category = 'CROSS_STATION_OR_VOLTAGE_CONFLICT'
        elif counts['MULTIPLE_EXTERNAL_MATCH'] or any(r['local_candidate_count'] for r in rr): category = 'AMBIGUOUS_EXTERNAL_REFERENCE'
        elif counts['UNDEFINED_GLOBAL']: category = 'TRULY_MISSING_GLOBAL_REFERENCE'
        elif any(r['strict_candidate'] and r['reciprocal_case_ids'] for r in rr): category = 'LIKELY_EXPORT_PARTITION'
        else: category = 'UNIQUE_EXTERNAL_BUT_OWNERSHIP_UNCONFIRMED'
        data_labels = []
        if counts['UNDEFINED_GLOBAL']: data_labels.append('MISSING_DATA')
        if counts['MULTIPLE_EXTERNAL_MATCH']: data_labels.append('AMBIGUOUS_EXTERNAL_DATA')
        if any(r['external_candidate_count'] for r in rr):
            data_labels += ['EXTERNAL_PARTITIONED_DATA', 'OWNERSHIP_UNCONFIRMED']
        target.append({'scope': SCOPE, 'case_id': cid, 'source_case_key': by_case[cid]['source_case_key'],
            'feeder_id': old['feeder_id'], 'classification': category, 'data_labels': data_labels,
            'missing_endpoint_count': len(rr), 'unique_external_match_count': counts['UNIQUE_EXTERNAL_MATCH'],
            'multiple_match_count': counts['MULTIPLE_EXTERNAL_MATCH'], 'globally_undefined_count': counts['UNDEFINED_GLOBAL'],
            'same_station_match_count': sum(bool(r['same_station_match_count']) for r in rr),
            'reciprocal_reference_count': sum(bool(r['reciprocal_case_ids']) for r in rr),
            'voltage_compatible_count': sum(bool(r['voltage_compatible_count']) for r in rr),
            'if_followed_line_identity_complete_count': len(complete_identity[cid]),
            'if_followed_line_representation_count': len(lines_by_case[cid]),
            'if_followed_backbone_eligibility_impact': int(cid in eligible),
            'unassessed_placement_line_count': len(complete_identity[cid]) - len(lines_by_case[cid]),
            'reference_ids': [r['reference_id'] for r in rr],
            'line_identity_witnesses': complete_identity[cid],
            'representation_witnesses': [l['source_record_ref'] for l in lines_by_case[cid]]})
    no_lines = [r for r in read_lines(Path(roots['d4']) / 'feeder_gap_taxonomy.jsonl')
                if r['d3_primary'] == 'SYNTHETIC_BACKBONE_REQUIRED' and r['source_line_count'] == 0]
    no_line_counts = {'cohort_feeders': len(no_lines),
        'with_external_references': sum(any(r['external_candidate_count'] for r in refs_by_case[f['case_id']]) for f in no_lines),
        'external_reference_count': sum(sum(bool(r['external_candidate_count']) for r in refs_by_case[f['case_id']]) for f in no_lines)}
    outcome = {'scope': SCOPE, 'analysis_kind': 'GLOBAL_REFERENCE_RESOLUTION_COUNTERFACTUAL', 'selection': 'UNIQUE_EXTERNAL + SAME_STATION + VOLTAGE_COMPATIBLE + TYPE_AND_IDENTITY_COMPATIBLE',
        'line_endpoint_identity_resolution_count': len(strict_endpoint),
        'all_reference_identity_resolution_count': sum(r['strict_candidate'] for r in refs),
        'line_identity_complete_upper_bound': sum(map(len, complete_identity.values())),
        'line_representation_count': len(candidate_lines), 'new_backbone_eligible_feeders_existing_anchor_bound': len(eligible),
        'broader_placement_impact': {'backbone_eligible_feeders': None, 'reachable_line_delta': None,
            'reachable_transformer_delta': None,
            'reason': 'Foreign multi-port or unrepresented entities have no approved attachment policy'},
        'reachable_line_delta': reachability['physical']['reachable_line_delta'],
        'reachable_transformer_delta': reachability['physical']['reachable_transformer_delta'],
        'reachability': reachability, 'structural_diagnostics': diagnostics,
        'cross_feeder_bridge_candidates': sum(nodes[l['endpoints'][0]]['case_id'] != nodes[l['endpoints'][1]]['case_id'] for l in candidate_lines),
        'unassessed_line_placement_upper_bound': sum(map(len, complete_identity.values())) - len(candidate_lines),
        'limitation': 'Existing accepted anchors only; identity-complete Lines with unrepresented or multi-port targets need placement policy. No synthetic head link is assumed.',
        'no_source_line_feeders': no_line_counts, 'ownership_confirmed': False,
        'topology_written': False, 'proposal_created': False,
        'line_representation_witnesses': [{k:v for k,v in l.items() if k != 'endpoints'} for l in candidate_lines],
        'backbone_eligibility_case_ids': sorted(eligible)}
    return {'counterfactual_resolution': resolutions, 'target_78_feeders': target,
            'counterfactual_impact': outcome}
