from copy import deepcopy
import pytest
from grid_case_generator.analysis.case_boundary_audit import audit, GlobalSourceReferenceIndex


def case(cid, station='S', voltage='10', entities=(), refs=()):
    return {'case_id': cid, 'source_case_key': 'data/' + cid,
            'station_ids': [station] if station else [], 'station_witnesses': [],
            'feeder_ids': ['F' + cid], 'feeder_names': ['name' + cid],
            'feeder_refs': ['canonical-F' + cid], 'voltage_kv': voltage,
            'voltage_witnesses': [], 'entities': list(entities), 'references': list(refs),
            'empty_reference_count': 0, 'source_type_counts': {}}


def entity(raw, kind='BUS', identity='UNIQUE', voltage='10'):
    return {'raw_source_id': raw, 'source_entity_type': kind, 'source_file_type': kind,
            'source_record_ref': kind + ':' + raw, 'identity_status': identity,
            'canonical_ref': {'entity_id': raw, 'entity_type': kind},
            'voltage_values': [voltage] if voltage else [], 'voltage_witnesses': [],
            'fields': {}}


def ref(raw, status='UNRESOLVED'):
    return {'raw_reference_value': raw, 'source_record_ref': 'line:' + raw,
            'source_entity_type': 'LINE', 'raw_field': 'Line_ToBus',
            'local_resolution_status': status, 'allowed_types': ['BUS', 'SWITCH'],
            'voltage_values': ['10'], 'voltage_witnesses': [], 'owner_source_id': 'L'}


def rows(cases):
    return audit(cases)['cross_case_references']


def test_unique_same_station_voltage_compatible_one_way():
    a, = rows([case('A', refs=[ref('B')]), case('B', entities=[entity('B')])])
    assert a['classification'] == 'UNIQUE_EXTERNAL_MATCH'
    assert a['same_station_match_count'] == 1 and a['voltage_compatible_count'] == 1
    assert 'ONE_WAY_EXTERNAL_REFERENCE' in a['labels']
    assert a['strict_candidate'] and a['ownership_status'] == 'OWNERSHIP_UNCONFIRMED'


def test_multiple_and_cross_type_not_selected():
    a, = rows([case('A', refs=[ref('X')]), case('B', entities=[entity('X')]),
               case('C', entities=[entity('X', 'SWITCH')])])
    assert a['classification'] == 'MULTIPLE_EXTERNAL_MATCH'
    assert 'CROSS_TYPE_EXTERNAL_MATCH' in a['labels']
    assert not a['strict_candidate']


def test_cross_station_and_voltage_conflict():
    a, = rows([case('A', refs=[ref('B')]),
               case('B', station='OTHER', entities=[entity('B', voltage='110')])])
    assert a['cross_station_match_count'] == 1
    assert a['voltage_conflict_count'] == 1 and not a['safe_looking_candidate']


def test_reciprocal_pair_and_partition_cluster():
    result = audit([case('A', entities=[entity('A')], refs=[ref('B')]),
                    case('B', entities=[entity('B')], refs=[ref('A')])])
    assert all('RECIPROCAL_REFERENCE' in r['labels'] for r in result['cross_case_references'])
    assert result['summary']['reciprocal_reference_count'] == 2
    assert result['summary']['possible_export_partition_clusters'] == 1


def test_globally_undefined_and_local_exact_excluded():
    result = audit([case('A', entities=[entity('A')], refs=[ref('A', 'EXACT'), ref('MISSING')])])
    assert len(result['cross_case_references']) == 1
    assert result['cross_case_references'][0]['classification'] == 'UNDEFINED_GLOBAL'


def test_duplicate_rows_in_one_foreign_case_are_ambiguous():
    a, = rows([case('A', refs=[ref('X')]),
               case('B', entities=[entity('X'), dict(entity('X'), source_record_ref='other')])])
    assert a['classification'] == 'MULTIPLE_EXTERNAL_MATCH'


def test_unknown_voltage_never_compatible():
    a, = rows([case('A', refs=[ref('B')]), case('B', voltage=None, entities=[entity('B', voltage=None)])])
    assert not a['strict_candidate'] and a['voltage_compatible_count'] == 0


def test_ambiguous_identity_never_safe():
    a, = rows([case('A', refs=[ref('B')]), case('B', entities=[entity('B', identity='DUPLICATE_CONFLICT')])])
    assert not a['safe_looking_candidate']


def test_inputs_unchanged_and_order_deterministic():
    inputs = [case('A', refs=[ref('B')]), case('B', entities=[entity('B')])]
    saved = deepcopy(inputs)
    first = audit(inputs)
    assert inputs == saved and first == audit(list(reversed(inputs)))
    assert not any('proposal_edges' in k or 'topology' == k for k in first)


def test_index_is_type_and_raw_id_keyed():
    idx = GlobalSourceReferenceIndex([case('A', entities=[entity('X'), entity('X', 'SWITCH')])])
    assert len(idx.by_identity[('BUS', 'X')]) == 1
    assert len(idx.by_identity[('SWITCH', 'X')]) == 1


def test_scc_is_distinct_from_weak_components():
    result = audit([case('A', refs=[ref('B')]), case('B', entities=[entity('B')]), case('C')])
    assert result['summary']['weakly_connected_components'] == 2
    assert result['summary']['strongly_connected_components'] == 3
    assert result['summary']['largest_component_size'] == 2


def test_type_mismatch_does_not_become_safe():
    a, = rows([case('A', refs=[ref('B')]), case('B', entities=[entity('B', 'LOAD')])])
    assert not a['safe_looking_candidate']


def test_local_ambiguity_never_overridden_by_external_unique():
    a, = rows([case('A', entities=[entity('X', identity='DUPLICATE_CONFLICT')], refs=[ref('X', 'AMBIGUOUS')]),
               case('B', entities=[entity('X')])])
    assert a['local_candidate_count'] == 1 and not a['strict_candidate']


def test_explicit_voltage_conflicts_are_distinct_from_context_conflicts():
    r = ref('B'); r['voltage_basis'] = 'SOURCE_HEAD_CONTEXT'
    e = entity('B', voltage='110'); e['voltage_basis'] = 'DIRECT_SOURCE_FIELD'
    row, = rows([case('A', refs=[r]), case('B', entities=[e])])
    assert row['voltage_conflict_count'] == 1
    assert row['explicit_voltage_conflict_count'] == 0


def test_partition_clusters_do_not_absorb_cross_station_neighbours():
    result = audit([case('A', entities=[entity('A')], refs=[ref('B')]),
                    case('B', entities=[entity('B')], refs=[ref('A'), ref('C')]),
                    case('C', station='T', entities=[entity('C')])])
    assert result['summary']['largest_component_size'] == 3
    clusters = [r for r in result['case_reference_components']
                if r.get('classification') == 'POSSIBLE_EXPORT_PARTITION_CLUSTER']
    assert len(clusters) == 1 and clusters[0]['member_cases'] == ['A','B']
