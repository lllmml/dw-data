from grid_case_generator.analysis.case_boundary_impact import Connectivity, graph_diagnostics


def test_cycles_multiple_heads_and_open_bypass_are_diagnosed():
    nodes = ['a', 'b', 'c']
    base = [('a', 'b', False), ('b', 'c', True)]
    additions = [('a', 'c', True)]
    result = graph_diagnostics(nodes, base, additions, ['a', 'b'])
    assert result['open_cut_bypasses'] == 1
    assert result['physical_cycle_rank_delta'] == 1
    assert result['new_multiple_head_components'] == 1


def test_union_is_order_independent():
    a = Connectivity(['a','b','c'], [('a','b',True),('b','c',True)])
    b = Connectivity(['c','b','a'], [('c','b',True),('b','a',True)])
    assert a.connected('a','c') and b.connected('a','c')
