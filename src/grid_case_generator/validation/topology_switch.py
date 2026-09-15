"""Read-only risk measurements on temporary, edge-identified multigraphs."""
from collections import Counter, defaultdict, deque


def reachable(adjacency, start, blocked=None):
    seen = set() if start is None else {start}
    pending = list(seen)
    while pending:
        for other, edge_id in adjacency[pending.pop()]:
            if edge_id != blocked and other not in seen:
                seen.add(other)
                pending.append(other)
    return seen


def graph_risks(nodes, edges, head, regions, case_id):
    """Edges supplied by caller are either structural or conducting, never collapsed."""
    adjacency = defaultdict(list)
    degree = Counter({n: 0 for n in nodes})
    for edge in edges:
        a, b = edge['a'], edge['b']
        if a not in nodes or b not in nodes:
            raise ValueError('dangling analysis edge')
        adjacency[a].append((b, edge['id'])); adjacency[b].append((a, edge['id']))
        degree[a] += 1; degree[b] += 1
    seen = reachable(adjacency, head)
    # A baseline-first deterministic forest preserves the baseline cycle basis.
    parent = {n: n for n in nodes}
    def root(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]; node = parent[node]
        return node
    tree = defaultdict(list)
    cycles = []; sizes = Counter(); new_sizes = Counter()
    for edge in sorted(edges, key=lambda e: (e['added'], e['id'])):
        a, b = edge['a'], edge['b']; ra, rb = root(a), root(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
            tree[a].append((b, edge['id'])); tree[b].append((a, edge['id']))
            continue
        previous = {a: None}; pending = deque([a])
        while b not in previous:
            vertex = pending.popleft()
            for other, edge_id in sorted(tree[vertex]):
                if other not in previous:
                    previous[other] = (vertex, edge_id); pending.append(other)
        path = []; vertex = b
        while vertex != a:
            vertex, edge_id = previous[vertex]; path.append(edge_id)
        path.append(edge['id']); size = len(path)
        sizes[str(size)] += 1
        if edge['added']: new_sizes[str(size)] += 1
        cycles.append({'closing_edge': edge['id'], 'edge_ids': sorted(path), 'size': size,
                       'new': edge['added'], 'isolated_from_head': a not in seen})
    by_role = defaultdict(Counter); abnormal = Counter(); abnormal_examples = []
    for node_id, node in sorted(nodes.items()):
        role = node['role']; value = degree[node_id]
        by_role[role][str(value)] += 1
        limit = 2 if role.startswith('switch-port/') else 1 if role == 'transformer-mv/mv' else 4
        if value > limit:
            abnormal[role] += 1
            abnormal_examples.append({'node_id': node_id, 'role': role, 'degree': value, 'review_threshold': limit})
    supported = {'feeder-head/mv', 'junction/bus', 'switch-port/in', 'switch-port/out', 'transformer-mv/mv'}
    unsupported = [e['id'] for e in edges if any(nodes[n]['role'] not in supported for n in (e['a'], e['b']))]
    region_nodes = {n: set(regions.get(node.get('raw_bus_id'), ())) for n, node in nodes.items()}
    mapped_regions = set().union(*region_nodes.values()) if region_nodes else set()
    reachable_regions = set().union(*(region_nodes[n] for n in seen)) if seen else set()
    foreign = {r for r in reachable_regions if r.split('|', 1)[0] != case_id}
    crossings = []
    # Equal raw Bus IDs shared by feeders are ambiguous, not distinct regions.
    for edge in sorted(edges, key=lambda e: e['id']):
        if not edge['added'] or edge['kind'] != 'switch' or len(mapped_regions) < 2:
            continue
        sides = []
        for endpoint in (edge['a'], edge['b']):
            component = reachable(adjacency, endpoint, edge['id'])
            sides.append({nodes[n].get('raw_bus_id'): region_nodes[n] for n in component if region_nodes[n]})
        pairs = sorted({(a, b) for a, left in sides[0].items() for b, right in sides[1].items()
                        if a != b and any(x != y for x in left for y in right)})
        if pairs:
            crossings.append({'switch_edge': edge['id'], 'source_bus_pairs': pairs,
                              'already_alternate_path': edge['b'] in reachable(adjacency, edge['a'], edge['id'])})
    return {
        'node_count': len(nodes), 'edge_count': len(edges),
        'cycles_count': len(cycles), 'cycle_size_distribution': dict(sorted(sizes.items())),
        'new_cycles_count': sum(new_sizes.values()), 'new_cycle_size_distribution': dict(sorted(new_sizes.items())),
        'isolated_new_cycles_count': sum(c['new'] and c['isolated_from_head'] for c in cycles),
        'cycle_examples': cycles[:3], 'new_cycle_examples': [c for c in cycles if c['new']][:3],
        'node_degree_distribution': dict(sorted(Counter(str(d) for d in degree.values()).items())),
        'degree_by_role': {k: dict(sorted(v.items())) for k, v in sorted(by_role.items())},
        'degree_above_review_threshold_count': sum(abnormal.values()),
        'degree_above_review_threshold_by_role': dict(sorted(abnormal.items())),
        'degree_examples': abnormal_examples[:3],
        'unsupported_path_count': len(unsupported), 'unsupported_edge_examples': sorted(unsupported)[:3],
        'cross_feeder_projection_count': len(crossings), 'cross_feeder_examples': crossings[:3],
        'region_assessed_cases': int(bool(mapped_regions)),
        'region_unmapped_cases': int(not mapped_regions),
        'shared_region_bus_count': sum(len(r) > 1 for r in region_nodes.values()),
        'reachable_foreign_region_count': len(foreign), 'reachable_foreign_regions': sorted(foreign),
    }
