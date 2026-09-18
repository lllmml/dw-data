"""D4.2 read-only global identity observations; never a Canonical resolver."""
from collections import Counter, defaultdict
from hashlib import sha256
from decimal import Decimal

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.models.proposals import voltage_compatible

VERSION = '1.0.0'
SCOPE = 'ANALYSIS_ONLY_CROSS_CASE_COUNTERFACTUAL'


def identifier(kind, value):
    return 'd4.2-analysis:' + kind + ':' + sha256(canonical_json_bytes(value)).hexdigest()


def voltage_relation(left, right):
    if len(left) != 1 or len(right) != 1:
        return 'UNKNOWN'
    try:
        return 'COMPATIBLE' if voltage_compatible(left[0], right[0]) else 'CONFLICT'
    except ValueError:
        return 'UNKNOWN'


def station_relation(left, right):
    if len(left) != 1 or len(right) != 1:
        return 'UNKNOWN'
    return 'SAME_STATION' if left == right else 'CROSS_STATION'


class GlobalSourceReferenceIndex:
    """A multimap of raw definitions, preserving duplicate source rows."""

    def __init__(self, cases):
        self.by_identity = defaultdict(list)
        self.by_raw = defaultdict(list)
        self.entries = []
        for case in sorted(cases, key=lambda c: c['case_id']):
            for entity in sorted(case['entities'], key=lambda e: (e['source_entity_type'],
                                  e['raw_source_id'], e['source_record_ref'])):
                entry = {k: v for k, v in entity.items() if k != 'fields'}
                entry.update({k: case[k] for k in ('case_id', 'source_case_key', 'station_ids',
                    'station_witnesses', 'feeder_ids', 'feeder_names', 'feeder_refs')})
                entry['index_id'] = identifier('identity', [case['case_id'],
                    entity['source_entity_type'], entity['raw_source_id'], entity['source_record_ref']])
                self.entries.append(entry)
                self.by_identity[(entity['source_entity_type'], entity['raw_source_id'])].append(entry)
                self.by_raw[entity['raw_source_id']].append(entry)


def components(nodes, adjacency):
    """Iterative deterministic connected groups; also works on symmetric adjacency."""
    remaining = set(nodes); result = []
    for start in sorted(nodes):
        if start not in remaining:
            continue
        remaining.remove(start); stack = [start]; group = []
        while stack:
            current = stack.pop(); group.append(current)
            for other in sorted(adjacency.get(current, ())):
                if other in remaining:
                    remaining.remove(other); stack.append(other)
        result.append(sorted(group))
    return result


def strongly_connected(nodes, adjacency):
    visited = set(); finish = []; reverse = defaultdict(set)
    for a, neighbours in adjacency.items():
        for b in neighbours:
            reverse[b].add(a)
    for start in sorted(nodes):
        if start in visited:
            continue
        visited.add(start); stack = [(start, iter(sorted(adjacency.get(start, ())))) ]
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                finish.append(node); stack.pop()
            elif child not in visited:
                visited.add(child); stack.append((child, iter(sorted(adjacency.get(child, ())))))
    visited = set(); result = []
    for start in reversed(finish):
        if start in visited:
            continue
        visited.add(start); stack = [start]; group = []
        while stack:
            node = stack.pop(); group.append(node)
            for child in sorted(reverse[node]):
                if child not in visited:
                    visited.add(child); stack.append(child)
        result.append(sorted(group))
    return sorted(result)


def ratio(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'ratio': str(Decimal(numerator) / Decimal(denominator)) if denominator else None}


def audit(cases):
    cases = sorted(cases, key=lambda c: c['case_id'])
    by_case = {c['case_id']: c for c in cases}
    index = GlobalSourceReferenceIndex(cases)
    records = []; edges = defaultdict(list); exact = 0
    for case in cases:
        for ref in sorted(case['references'], key=lambda r: (r['source_record_ref'], r['raw_field'])):
            if ref['local_resolution_status'] == 'EXACT':
                exact += 1; continue
            raw = ref['raw_reference_value']
            if not raw:
                continue
            matches = index.by_raw.get(raw, [])
            local = [e for e in matches if e['case_id'] == case['case_id']]
            foreign = [e for e in matches if e['case_id'] != case['case_id']]
            classification = ('MULTIPLE_EXTERNAL_MATCH' if len(foreign) > 1 else
                'UNIQUE_EXTERNAL_MATCH' if foreign else
                'LOCAL_UNRESOLVED_ONLY' if local else 'UNDEFINED_GLOBAL')
            row = dict(ref, case_id=case['case_id'], source_case_key=case['source_case_key'],
                       feeder_ids=case['feeder_ids'], feeder_refs=case['feeder_refs'],
                       reference_id=identifier('reference', [case['case_id'], ref['source_record_ref'], ref['raw_field']]),
                       classification=classification, local_candidate_count=len(local),
                       local_candidate_ids=[e['index_id'] for e in local],
                       external_candidate_count=len(foreign), candidates=[], labels=[classification],
                       ownership_status='OWNERSHIP_UNCONFIRMED' if foreign else 'NOT_APPLICABLE')
            kinds = {e['source_entity_type'] for e in foreign}
            if len(kinds) > 1:
                row['labels'].append('CROSS_TYPE_EXTERNAL_MATCH')
            for entity in foreign:
                target_case = by_case[entity['case_id']]
                station = station_relation(case['station_ids'], target_case['station_ids'])
                voltage = voltage_relation(ref['voltage_values'], entity['voltage_values'])
                same_id = bool(set(case['feeder_ids']) & set(entity['feeder_ids']))
                same_name = bool(set(case['feeder_names']) & set(entity['feeder_names']))
                family = 'EXACT_FEEDER_ID' if same_id else 'EXACT_FEEDER_NAME_OBSERVATION' if same_name else 'UNCONFIRMED'
                candidate = {'index_id': entity['index_id'], 'case_id': entity['case_id'],
                    'source_record_ref': entity['source_record_ref'], 'source_entity_type': entity['source_entity_type'],
                    'canonical_ref': entity['canonical_ref'], 'identity_status': entity['identity_status'],
                    'type_compatible': entity['source_entity_type'] in ref['allowed_types'],
                    'station_relationship': station, 'voltage_relationship': voltage,
                    'voltage_basis': entity.get('voltage_basis', 'DIRECT_SOURCE_FIELD'),
                    'explicit_voltage_conflict': voltage == 'CONFLICT' and ref.get('voltage_basis', 'DIRECT_SOURCE_FIELD') == 'DIRECT_SOURCE_FIELD' and entity.get('voltage_basis', 'DIRECT_SOURCE_FIELD') == 'DIRECT_SOURCE_FIELD',
                    'voltage_values': entity['voltage_values'], 'voltage_witnesses': entity['voltage_witnesses'],
                    'station_ids': entity['station_ids'], 'station_witnesses': entity['station_witnesses'],
                    'feeder_relationship': family, 'feeder_ids': entity['feeder_ids'],
                    'feeder_names': entity['feeder_names']}
                row['candidates'].append(candidate)
            for field, value, dest in (('station_relationship', 'SAME_STATION', 'same_station_match_count'),
                                      ('station_relationship', 'CROSS_STATION', 'cross_station_match_count'),
                                      ('voltage_relationship', 'COMPATIBLE', 'voltage_compatible_count'),
                                      ('voltage_relationship', 'CONFLICT', 'voltage_conflict_count')):
                row[dest] = sum(c[field] == value for c in row['candidates'])
            row['explicit_voltage_conflict_count'] = sum(c['explicit_voltage_conflict'] for c in row['candidates'])
            for count, label in (('same_station_match_count', 'SAME_STATION_EXTERNAL_MATCH'),
                                 ('voltage_compatible_count', 'VOLTAGE_COMPATIBLE_EXTERNAL_MATCH'),
                                 ('voltage_conflict_count', 'VOLTAGE_CONFLICT_EXTERNAL_MATCH')):
                if row[count]: row['labels'].append(label)
            if any(c['feeder_relationship'] != 'UNCONFIRMED' for c in row['candidates']):
                row['labels'].append('SAME_FEEDER_FAMILY_EXTERNAL_MATCH')
            sole = row['candidates'][0] if len(foreign) == 1 else None
            row['safe_looking_candidate'] = bool(sole and not local and sole['type_compatible']
                and sole['identity_status'] == 'UNIQUE' and sole['canonical_ref']
                and sole['voltage_relationship'] == 'COMPATIBLE'
                and sole['station_relationship'] != 'CROSS_STATION'
                and not case.get('hard_blockers') and not by_case[sole['case_id']].get('hard_blockers'))
            row['strict_candidate'] = bool(row['safe_looking_candidate'] and row['same_station_match_count'])
            for destination in sorted({e['case_id'] for e in foreign}):
                edges[(case['case_id'], destination)].append(row)
            records.append(row)
    for row in records:
        destinations = {c['case_id'] for c in row['candidates']}
        reciprocal = sorted(d for d in destinations if (d, row['case_id']) in edges)
        row['reciprocal_case_ids'] = reciprocal
        if destinations:
            row['labels'].append('RECIPROCAL_REFERENCE' if reciprocal else 'ONE_WAY_EXTERNAL_REFERENCE')
        row['labels'].sort()
    edge_rows = []; adjacency = defaultdict(set); undirected = defaultdict(set)
    for (a, b), witnesses in sorted(edges.items()):
        candidates = [c for r in witnesses for c in r['candidates'] if c['case_id'] == b]
        adjacency[a].add(b); undirected[a].add(b); undirected[b].add(a)
        edge_rows.append({'source_case_id': a, 'target_case_id': b,
            'reference_count': len(witnesses),
            'distinct_raw_ids': sorted({r['raw_reference_value'] for r in witnesses}),
            'entity_types': sorted({c['source_entity_type'] for c in candidates}),
            'reciprocal': (b, a) in edges,
            'station_relationship': dict(sorted(Counter(c['station_relationship'] for c in candidates).items())),
            'voltage_compatibility': dict(sorted(Counter(c['voltage_relationship'] for c in candidates).items())),
            'feeder_relationship': dict(sorted(Counter(c['feeder_relationship'] for c in candidates).items())),
            'ambiguous_reference_count': sum(r['external_candidate_count'] > 1 for r in witnesses),
            'reference_ids': sorted(r['reference_id'] for r in witnesses),
            'example_witnesses': [{'source_record_ref': r['source_record_ref'], 'raw_field': r['raw_field'],
                                  'raw_reference_value': r['raw_reference_value']} for r in witnesses[:5]]})
    weak = components(by_case, undirected); strong = strongly_connected(by_case, adjacency)
    partition_pairs = {(r['case_id'], r['candidates'][0]['case_id']) for r in records if r['strict_candidate']}
    partition_adj = defaultdict(set)
    for a, b in sorted(partition_pairs):
        if (b, a) in partition_pairs:
            partition_adj[a].add(b); partition_adj[b].add(a)
    partitions = components(partition_adj, partition_adj)
    component_rows = []
    edge_by_case = defaultdict(list)
    for edge in edge_rows: edge_by_case[edge['source_case_id']].append(edge)
    for kind, members in [('WEAK', m) for m in weak] + [('PARTITION_CANDIDATE', m) for m in partitions]:
        member_set = set(members)
        internal = [e for c in members for e in edge_by_case[c] if e['target_case_id'] in member_set]
        reciprocal = [e for e in internal if e['reciprocal'] and e['source_case_id'] < e['target_case_id']]
        likely = kind == 'PARTITION_CANDIDATE'
        component_rows.append({'component_id': identifier(kind.lower(), members), 'kind': kind,
            'member_cases': members, 'member_source_case_keys': [by_case[c]['source_case_key'] for c in members],
            'size': len(members), 'classification': 'POSSIBLE_EXPORT_PARTITION_CLUSTER' if likely else 'DIRECTORY_REFERENCE_COMPONENT',
            'station_ids': sorted({s for c in members for s in by_case[c]['station_ids']}),
            'feeder_ids': sorted({s for c in members for s in by_case[c]['feeder_ids']}),
            'voltage_domains': sorted({by_case[c]['voltage_kv'] for c in members if by_case[c]['voltage_kv']}),
            'cross_reference_directions': [[e['source_case_id'], e['target_case_id']] for e in internal],
            'reciprocal_pairs': [[e['source_case_id'], e['target_case_id']] for e in reciprocal],
            'entity_type_composition': dict(sorted(Counter(t for e in internal for t in e['entity_types']).items())),
            'candidate_ownership_conflicts': {'distinct_feeder_ids': len({s for c in members for s in by_case[c]['feeder_ids']}),
                                            'ambiguous_reference_edge_occurrences': sum(e['ambiguous_reference_count'] for e in internal)},
            'ownership_status': 'OWNERSHIP_UNCONFIRMED' if internal else 'NOT_APPLICABLE'})
    component_rows += [{'component_id': identifier('scc', m), 'kind': 'STRONG', 'member_cases': m, 'size': len(m)} for m in strong]
    external = [r for r in records if r['external_candidate_count']]
    affected = {r['case_id'] for r in external}
    involved = affected | {c['case_id'] for r in external for c in r['candidates']}
    reciprocal_count = sum(bool(r['reciprocal_case_ids']) for r in external)
    label_counts = Counter(label for r in records for label in r['labels'])
    incoming = Counter(e['target_case_id'] for e in edge_rows)
    external_by_case = Counter(r['case_id'] for r in external)
    inventory = [{k: v for k, v in c.items() if k not in ('entities', 'references')} | {
        'in_degree': incoming[c['case_id']], 'out_degree': len(adjacency[c['case_id']]),
        'cross_case_reference_count': external_by_case[c['case_id']]}
        for c in cases]
    summary = {'scope': SCOPE, 'version': VERSION, 'case_count': len(cases),
        'global_index_rows': len(index.entries), 'case_local_exact_excluded': exact,
        'empty_references_excluded': sum(c['empty_reference_count'] for c in cases),
        'audited_unresolved_reference_count': len(records), 'cross_case_reference_count': len(external),
        'affected_case_count': len(affected),
        'affected_feeder_count': len({f for r in external for f in r['feeder_refs']}),
        'involved_current_gridcases': len(involved),
        'classification_counts': dict(sorted(Counter(r['classification'] for r in records).items())),
        'label_counts': dict(sorted(label_counts.items())),
        'same_station_external_references': sum(bool(r['same_station_match_count']) for r in external),
        'cross_station_external_references': sum(bool(r['cross_station_match_count']) for r in external),
        'explicit_voltage_conflict_references': sum(bool(r['explicit_voltage_conflict_count']) for r in external),
        'voltage_conflict_references': sum(bool(r['voltage_conflict_count']) for r in external),
        'same_station_candidate_matches': sum(r['same_station_match_count'] for r in records),
        'cross_station_candidate_matches': sum(r['cross_station_match_count'] for r in records),
        'reciprocal_reference_count': reciprocal_count,
        'reciprocal_reference_ratio': ratio(reciprocal_count, len(external)),
        'reciprocal_edge_ratio': ratio(sum(e['reciprocal'] for e in edge_rows), len(edge_rows)),
        'same_station_ratio': ratio(sum(bool(r['same_station_match_count']) for r in external), len(external)),
        'cross_station_ratio': ratio(sum(bool(r['cross_station_match_count']) for r in external), len(external)),
        'voltage_compatible_ratio': ratio(sum(bool(r['voltage_compatible_count']) for r in external), len(external)),
        'ambiguous_external_ratio': ratio(sum(r['external_candidate_count'] > 1 for r in external), len(external)),
        'connected_components': len(weak), 'weakly_connected_components': len(weak),
        'strongly_connected_components': len(strong), 'directed_edges': len(edge_rows),
        'largest_component_size': max(map(len, weak), default=0),
        'possible_export_partition_clusters': sum(c.get('classification') == 'POSSIBLE_EXPORT_PARTITION_CLUSTER' for c in component_rows),
        'safe_looking_candidates': sum(r['safe_looking_candidate'] for r in records),
        'strict_candidates': sum(r['strict_candidate'] for r in records),
        'approved': False, 'applied': False, 'case_boundary_changed': False,
        'recommendation': 'REQUIRES_BUSINESS_CONFIRMATION' if external else 'INSUFFICIENT_EVIDENCE'}
    return {'case_inventory': inventory, 'global_reference_index': index.entries,
            'cross_case_references': records, 'case_reference_edges': edge_rows,
            'case_reference_components': component_rows,
            'external_match_classification': [{'reference_id': r['reference_id'], 'classification': r['classification'],
                'labels': r['labels'], 'candidate_ids': [c['index_id'] for c in r['candidates']]} for r in records],
            'summary': summary}
