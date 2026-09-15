from dataclasses import replace
from decimal import Decimal
import os
from pathlib import Path
import subprocess
import sys

import pytest
from source_fixture import mapped
from test_switch_semantics import fixture
from grid_case_generator.generation.topology import interpret_topology
from grid_case_generator.models.topology import TopologyConfig
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.analysis.switch_projection_analysis import analyze_projection_case, ProjectionSummary
from grid_case_generator.validation.topology_switch import graph_risks


def analyze(rows):
    details = mapped(rows)
    baseline = interpret_topology(details, TopologyConfig(Decimal('10.5')))
    return analyze_projection_case(details, baseline)


@pytest.mark.parametrize('state,projected,conducting', [('Closed', 1, 1), ('Open', 1, 0), ('UNKNOWN', 0, 0)])
def test_state_strategies(state, projected, conducting):
    result = analyze(fixture(state=state, x='unresolved', y='other'))
    for strategy in ('S1', 'S2', 'S3_B'):
        metrics = result['strategies'][strategy]['coverage']
        assert metrics['switch_projected_count'] == projected
        assert metrics['switch_conducting_count'] == conducting
        assert metrics['reachable_transformers'] == conducting
    assert result['strategies']['S3_A']['coverage']['switch_projected_count'] == 1
    assert result['strategies']['S0']['coverage']['reachable_transformers'] == 0


def test_voltage_conflict_is_not_text_mismatch():
    rows = fixture(x='hv')
    rows['BUS'].append({'Bus_ID': 'hv', 'Bus_BaseKV': '110'})
    result = analyze(rows)
    assert result['candidates'][0]['safety']['assessment'] == 'CONFLICTING'
    assert result['strategies']['S1']['coverage']['reachable_transformers'] == 1
    assert result['strategies']['S2']['coverage']['reachable_transformers'] == 0
    rows['BUS'][-1]['Bus_BaseKV'] = '10.5'
    result = analyze(rows)
    assert result['candidates'][0]['safety']['assessment'] == 'UNKNOWN'
    assert result['strategies']['S2']['coverage']['reachable_transformers'] == 1


@pytest.mark.parametrize('x,y', [('a', 'b'), ('b', 'a')])
def test_exact_compatible(x, y):
    assert analyze(fixture(x=x, y=y))['candidates'][0]['safety']['assessment'] == 'COMPATIBLE'


@pytest.mark.parametrize('blocked', ['voltage', 'transformer', 'degree', 'duplicate', 'unsupported'])
def test_preserve_other_exclusions(blocked):
    rows = fixture()
    if blocked == 'voltage': rows['BUS'][1]['Bus_BaseKV'] = '110'
    elif blocked == 'transformer': rows['TRANSFORMER'][0]['Transformer_FromBus'] = 'a'
    elif blocked == 'degree': rows['LINE'].append({'Line_ID': 'extra', 'Line_FromBus': 's', 'Line_ToBus': 'b'})
    elif blocked == 'duplicate': rows['LINE'].append(dict(rows['LINE'][1]))
    else:
        rows['LINE'][2]['Line_ToBus'] = 'ap'
        rows['ACCESS_POINT'] = [{'AccessPoint_ID': 'ap', 'AccessPoint_ToBus': 't'}]
    result = analyze(rows)
    assert result['strategies']['S1']['coverage']['reachable_transformers'] == 0
    if blocked == 'unsupported':
        assert result['strategies']['S1']['risk']['blocked_unsupported_path_count'] == 1
        assert result['strategies']['S1']['risk']['conducting']['unsupported_path_count'] == 0


def test_tie_impact_and_unknown_type():
    for flag, group in [('True', 'tie'), ('False', 'normal'), ('', 'unknown_type')]:
        rows = fixture(); rows['SWITCH'][0]['Switch_IsTie'] = flag
        result = analyze(rows)
        entry = result['tie_analysis']['S1'][group]
        assert entry['candidate_count'] == entry['projected_count'] == 1
        assert entry['only_group_delta']['reachable_transformers'] == 1
        assert entry['remove_group_loss']['reachable_transformers'] == 1


def test_source_and_graph_order_stability():
    details = mapped(fixture())
    baseline = interpret_topology(details, TopologyConfig(Decimal('10.5')))
    before = canonical_json_bytes((details.records, details.accounting, baseline))
    one = analyze_projection_case(details, baseline)
    shuffled = replace(details, records=tuple(reversed(details.records)), accounting=tuple(reversed(details.accounting)))
    two = analyze_projection_case(shuffled, baseline)
    assert canonical_json_bytes(one) == canonical_json_bytes(two)
    assert canonical_json_bytes((details.records, details.accounting, baseline)) == before
    first, second = ProjectionSummary(), ProjectionSummary()
    first.add(one); second.add(two)
    assert canonical_json_bytes(first.finish()) == canonical_json_bytes(second.finish())


def test_multigraph_cycle_degree_and_regions():
    nodes = {n: {'role': 'junction/bus', 'owner': n, 'raw_bus_id': n} for n in 'abc'}
    def edge(key, a, b, kind='line', added=True):
        return {'id': key, 'a': a, 'b': b, 'kind': kind, 'owner': key, 'conducting': True, 'added': added}
    edges = [edge('base', 'a', 'b', added=False), edge('parallel', 'a', 'b'), edge('loop', 'c', 'c')]
    risk = graph_risks(nodes, edges, 'a', {}, 'case')
    assert risk['new_cycles_count'] == 2
    assert risk['new_cycle_size_distribution'] == {'1': 1, '2': 1}
    assert risk['isolated_new_cycles_count'] == 1
    assert risk['node_degree_distribution'] == {'2': 3}
    risk = graph_risks(nodes, [edge('switch', 'a', 'b', 'switch')], 'a', {'a': ['case'], 'b': ['foreign']}, 'case')
    assert risk['cross_feeder_projection_count'] == 1
    assert risk['reachable_foreign_region_count'] == 1


def test_artifact_hashseed(tmp_path):
    code = '''from test_switch_projection import analyze,fixture
from grid_case_generator.io.switch_projection_artifacts import write_projection_analysis
import sys
write_projection_analysis(sys.argv[1], {'source': sys.argv[1]+'e1', 'baseline': sys.argv[1]+'e2'}, {'source':'a'*64,'baseline':'b'*64}, [analyze(fixture())], 'PROPOSED / NOT ACCEPTED / NOT IMPLEMENTED\\n')
'''
    for seed in ('1', '999'):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(Path(__file__).parent.resolve()))
        subprocess.run([sys.executable, '-c', code, str(tmp_path / seed)], env=env, check=True)
    def snapshot(root): return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert snapshot(tmp_path / '1') == snapshot(tmp_path / '999')


def test_output_isolation_and_checksums(tmp_path):
    from grid_case_generator.io.switch_projection_artifacts import write_projection_analysis, verify_projection_analysis
    roots = {'source': tmp_path / 'e1', 'baseline': tmp_path / 'e2'}
    checksums = {'source': 'a'*64, 'baseline': 'b'*64}
    for output in [roots['source'], roots['baseline'] / 'child', tmp_path]:
        with pytest.raises(ValueError):
            write_projection_analysis(output, roots, checksums, [], 'proposal')
    out = tmp_path / 'out'
    write_projection_analysis(out, roots, checksums, [analyze(fixture())], 'PROPOSED / NOT ACCEPTED / NOT IMPLEMENTED\n')
    verify_projection_analysis(out)
    with pytest.raises(FileExistsError): write_projection_analysis(out, roots, checksums, [], 'proposal')
    (out / 'risk_analysis.json').write_text('{}\n')
    with pytest.raises(ValueError): verify_projection_analysis(out)


def test_head_carries_exact_feeder_source_region():
    details = mapped(fixture())
    baseline = interpret_topology(details, TopologyConfig(Decimal('10.5')))
    cid = str(baseline.topology.case_id)
    result = analyze_projection_case(details, baseline, {'up': [cid + '|f']})
    risk = result['strategies']['S0']['risk']['conducting']
    assert risk['region_assessed_cases'] == 1
    assert risk['reachable_foreign_region_count'] == 0


def test_end_to_end_projection_read_only(tmp_path, monkeypatch):
    import csv
    import io
    from zipfile import ZipFile
    from source_fixture import SCHEMA
    from grid_case_generator.io.nanjing_source.import_pipeline import import_archive
    from grid_case_generator.io.topology_artifacts import audit_source_artifact
    from grid_case_generator.io.switch_projection_artifacts import run_projection_analysis, verify_projection_analysis
    from grid_case_generator.analysis.switch_projection_proposal import render_proposal
    archive = tmp_path / 'fixture.zip'
    with ZipFile(archive, 'w') as z:
        for case, rows in [('motif', fixture()), ('empty', {})]:
            for schema in SCHEMA.files:
                stream = io.StringIO(newline=''); writer = csv.writer(stream); writer.writerow(schema.header)
                for row in rows.get(schema.file_type.value, []): writer.writerow([row.get(k, '') for k in schema.header])
                z.writestr(case + '/' + schema.filename, stream.getvalue())
    e1, e2 = tmp_path / 'e1', tmp_path / 'e2'
    import_archive(archive, e1, imported_at='2026-09-15T00:00:00Z')
    archive.unlink()
    def fail(*args, **kwargs): raise AssertionError('opened raw ZIP')
    monkeypatch.setattr(ZipFile, '__init__', fail)
    audit_source_artifact(e1, e2, TopologyConfig(Decimal('10.5')))
    def snapshot(root): return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    before = snapshot(e1), snapshot(e2)
    reports = run_projection_analysis(e1, e2, tmp_path / 'analysis', render_proposal)
    assert reports['coverage_by_strategy']['strategies']['S1']['total_cases'] == 2
    assert reports['coverage_by_strategy']['strategies']['S1']['reachable_transformers'] == 1
    verify_projection_analysis(tmp_path / 'analysis')
    assert (snapshot(e1), snapshot(e2)) == before


def test_baseline_projected_switch_is_preserved():
    result = analyze(fixture(x='', y=''))
    for name in ('S0', 'S1', 'S2', 'S3_A', 'S3_B'):
        assert result['strategies'][name]['coverage']['switch_projected_count'] == 1
        assert result['strategies'][name]['coverage']['reachable_transformers'] == 1
    assert result['strategies']['S1']['risk']['structural']['new_cycles_count'] == 0


def test_empty_case_and_duplicate_summary():
    result = analyze({})
    assert result['strategies']['S0']['coverage']['cases_with_feeder_head'] == 0
    summary = ProjectionSummary(); summary.add(result)
    assert summary.finish()['coverage_by_strategy']['strategies']['S0']['reachable_transformer_ratio'] is None
    with pytest.raises(ValueError): summary.add(result)


@pytest.mark.parametrize('voltage', ['', 'not-a-number', '0', '-1', '10'])
def test_missing_invalid_or_compatible_voltage_is_not_safety_conflict(voltage):
    rows = fixture(x='other_bus')
    rows['BUS'].append({'Bus_ID': 'other_bus', 'Bus_BaseKV': voltage})
    result = analyze(rows)
    assert result['candidates'][0]['safety']['assessment'] == 'UNKNOWN'
    assert result['strategies']['S2']['coverage']['reachable_transformers'] == 1


def test_unresolved_and_ambiguous_remain_unknown():
    rows = fixture(x='ambiguous')
    rows['BUS'] += [{'Bus_ID': 'ambiguous', 'Bus_BaseKV': '110'}] * 2
    result = analyze(rows)
    assert result['candidates'][0]['safety']['assessment'] == 'UNKNOWN'
    assert result['strategies']['S2']['coverage']['reachable_transformers'] == 1


def test_actual_unsupported_and_role_degree_are_counted():
    nodes = {'s': {'role': 'switch-port/in', 'owner': 's'},
             'ap': {'role': 'unsupported/access-point', 'owner': 'ap'}}
    edges = [{'id': str(i), 'a': 's', 'b': 'ap', 'kind': 'line', 'owner': str(i),
              'conducting': True, 'added': True} for i in range(3)]
    risk = graph_risks(nodes, edges, 's', {}, 'case')
    assert risk['unsupported_path_count'] == 3
    assert risk['degree_above_review_threshold_by_role'] == {'switch-port/in': 1}
    assert risk['new_cycle_size_distribution'] == {'2': 2}
    with pytest.raises(ValueError): graph_risks({}, edges, None, {}, 'case')


def test_shared_source_bus_is_not_distinct_cross_feeder_region():
    nodes = {n: {'role': 'junction/bus', 'owner': n, 'raw_bus_id': 'shared'} for n in 'ab'}
    edges = [{'id': 's', 'a': 'a', 'b': 'b', 'kind': 'switch', 'owner': 's', 'conducting': True, 'added': True}]
    risk = graph_risks(nodes, edges, 'a', {'shared': ['case|f', 'foreign|f2']}, 'case')
    assert risk['cross_feeder_projection_count'] == 0
    assert risk['shared_region_bus_count'] == 2


def test_cycle_graph_reproducibility_and_open_structural_cycle():
    rows = fixture(state='Open')
    rows['LINE'].append({'Line_ID': 'parallel_path', 'Line_FromBus': 'a', 'Line_ToBus': 'b'})
    result = analyze(rows)
    risk = result['strategies']['S1']['risk']
    assert risk['structural']['new_cycles_count'] == 1
    assert risk['conducting']['new_cycles_count'] == 0
    rows['LINE'].reverse()
    # Source row locators legitimately change, so compare the graph measurement, not evidence locators.
    other = analyze(rows)
    assert other['strategies']['S1']['risk']['structural']['new_cycles_count'] == 1


def test_multi_case_summary_order_and_example_selection():
    from source_fixture import source_files, map_source_case, DATASET
    results = []
    for case in ('second', 'first'):
        inventory, files = source_files(fixture(), case=case)
        details = map_source_case(inventory, files, dataset_id=DATASET)
        baseline = interpret_topology(details, TopologyConfig(Decimal('10.5')))
        results.append(analyze_projection_case(details, baseline))
    one, two = ProjectionSummary(), ProjectionSummary()
    for result in results: one.add(result)
    for result in reversed(results): two.add(result)
    assert canonical_json_bytes(one.finish()) == canonical_json_bytes(two.finish())
    examples = one.finish()['representative_examples']['strategies']['S1']['projected']
    assert [(e['case_id'], e['switch_id']) for e in examples] == sorted((r['case_id'], 's') for r in results)
