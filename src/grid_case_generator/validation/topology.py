"""Electrical reachability over accepted E2 branches; cycles are preserved."""
from collections import defaultdict
from grid_case_generator.models.topology import DerivedRole


def reachable_nodes(head, branches):
    adjacency = defaultdict(set)
    for branch in branches:
        if branch.conducting:
            adjacency[branch.from_node_id].add(branch.to_node_id)
            adjacency[branch.to_node_id].add(branch.from_node_id)
    seen = set() if head is None else {head}
    pending = list(seen)
    while pending:
        for node in adjacency[pending.pop()]:
            if node not in seen:
                seen.add(node)
                pending.append(node)
    return tuple(sorted(seen))


def validate_topology(result):
    graph = result.topology
    ids = [n.node_id for n in graph.nodes] + [b.branch_id for b in graph.branches]
    id_set = set(ids)
    if len(ids) != len(id_set):
        raise ValueError('duplicate derived ID')
    nodes = {n.node_id for n in graph.nodes}
    if graph.feeder_head_id is not None and graph.feeder_head_id not in nodes:
        raise ValueError('missing feeder head')
    for branch in graph.branches:
        if branch.from_node_id not in nodes or branch.to_node_id not in nodes:
            raise ValueError('dangling branch')
    if graph.reachable_node_ids != reachable_nodes(graph.feeder_head_id, graph.branches):
        raise ValueError('incorrect reachability')
    for projection in result.projections:
        if not set(projection.derived_target_ids) <= id_set:
            raise ValueError('dangling projection')
    reachable = set(graph.reachable_node_ids)
    transformers = tuple(sorted(n.source_entity_ref.entity_id for n in graph.nodes
        if n.role is DerivedRole.TRANSFORMER_MV and n.node_id in reachable))
    if graph.reachable_transformer_ids != transformers:
        raise ValueError('incorrect reachable transformer subset')
    usable = graph.feeder_head_id is not None and any(
        b.role is DerivedRole.LINE and b.conducting and b.from_node_id in reachable
        for b in graph.branches)
    report = result.coverage
    if (report.case_id != graph.case_id or report.has_reachable_transformer != bool(transformers)
            or report.usable_subgraph != usable
            or report.counts['reachable_transformers'] != len(transformers)):
        raise ValueError('coverage disagrees with topology')
