from dataclasses import replace
from decimal import Decimal

import pytest
from source_fixture import mapped
from test_switch_semantics import fixture
from grid_case_generator.generation.topology import interpret_topology
from grid_case_generator.models.topology import TopologyConfig
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.analysis.feeder_coverage import analyze_feeder_case, FeederSummary


def analyze(rows):
    details = mapped(rows)
    baseline = interpret_topology(details, TopologyConfig(Decimal('10.5')))
    return analyze_feeder_case(details, baseline)


def test_full_feeder_and_per_feeder_switch_count():
    result = analyze(fixture())
    feeder, = result['feeders']
    assert feeder['switch_count'] == feeder['case_scope_switch_count'] == 1
    assert feeder['source_feeder_id'] == 'f'
    assert result['policies']['S2']['strict_topology_status'] == 'FULL'
    assert result['policies']['S2']['transformer_goal_status'] == 'FULL'
    assert result['policies']['S0']['strict_topology_status'] == 'PARTIAL'


def test_whole_source_denominator_and_partial_transformers():
    rows = fixture()
    rows['TRANSFORMER'].append({'Transformer_ID': 'orphan'})
    result = analyze(rows)
    s2 = result['policies']['S2']
    assert s2['strict_topology_status'] == s2['transformer_goal_status'] == 'PARTIAL'
    assert s2['totals']['TRANSFORMER'] == 2
    assert s2['reachable']['TRANSFORMER'] == 1
    assert 'transformer_unreachable' in s2['blocker_tags']


def test_orphan_switch_prevents_strict_full_but_not_transformer_goal():
    rows = fixture(); rows['SWITCH'].append({'Switch_ID': 'orphan'})
    result = analyze(rows)
    assert result['feeders'][0]['switch_count'] == 2
    assert result['policies']['S2']['strict_topology_status'] == 'PARTIAL'
    assert result['policies']['S2']['transformer_goal_status'] == 'FULL'


def test_no_source_is_not_invented_feeder():
    rows = fixture(); rows['FEEDER'] = []
    result = analyze(rows)
    assert result['feeders'] == []
    assert result['policies']['S2']['strict_topology_status'] == 'FAILED'
    assert result['policies']['S2']['primary_failure_reason'] == 'missing_source'
    summary = FeederSummary(); summary.add(result)
    report = summary.finish()['feeder_coverage']
    assert report['population']['raw_feeder_rows'] == 0
    assert report['population']['cases_without_feeder'] == 1
    assert report['policies']['S2']['strict_topology_status']['FAILED'] == 0
    assert report['case_cohort']['S2']['strict_topology_status']['FAILED'] == 1


def test_multiple_feeders_do_not_claim_unique_equipment_ownership():
    rows = fixture(); rows['FEEDER'].append({'Feeder_ID': 'other', 'Feeder_SourceBus': 'up'})
    result = analyze(rows)
    assert len(result['feeders']) == 2
    assert all(f['switch_count'] is None and f['case_scope_switch_count'] == 1 for f in result['feeders'])
    assert result['policies']['S2']['strict_topology_status'] == 'FAILED'


def test_empty_target_is_not_vacuous_success():
    rows = fixture(); rows['TRANSFORMER'] = []; rows['LINE'] = []
    result = analyze(rows)
    assert result['policies']['S2']['strict_topology_status'] == 'FAILED'
    assert result['policies']['S2']['transformer_goal_status'] == 'FAILED'
    assert result['policies']['S2']['no_transformer_targets']


def test_unknown_conduction_recovers_real_feeder():
    rows = fixture(state='UNKNOWN')
    # Put the switch directly after the source; there is no other usable source Line.
    rows['LINE'] = rows['LINE'][1:]
    rows['LINE'][0]['Line_FromBus'] = 'st'
    result = analyze(rows)
    assert result['policies']['S2']['strict_topology_status'] == 'FAILED'
    assert result['policies']['S2']['primary_failure_reason'] == 'switch_unknown'
    assert result['policies']['S2_UNKNOWN_NONCONDUCTING']['strict_topology_status'] == 'PARTIAL'
    assert result['policies']['S2_UNKNOWN_CONDUCTING']['strict_topology_status'] == 'FULL'
    summary = FeederSummary(); summary.add(result)
    recovery = summary.finish()['policy_recovery']['from_S2']['S2_UNKNOWN_CONDUCTING']
    assert recovery['failed_to_full'] == 1
    assert recovery['by_primary_failure_reason']['switch_unknown']['failed_to_full'] == 1


@pytest.mark.parametrize('state', ['Open', 'Closed'])
def test_known_states_never_overridden(state):
    result = analyze(fixture(state=state))
    assert result['policies']['S2']['graph_sha256'] == result['policies']['S2_UNKNOWN_CONDUCTING']['graph_sha256']
    assert result['policies']['S2_UNKNOWN_CONDUCTING']['assumed_conducting_switch_ids'] == []


def test_baseline_unknown_is_overridden_only_in_counterfactual():
    result = analyze(fixture(state='UNKNOWN', x='', y=''))
    assert result['policies']['S2']['transformer_goal_status'] == 'FAILED'
    assert result['policies']['S2_UNKNOWN_CONDUCTING']['transformer_goal_status'] == 'FULL'


def test_state_unknown_not_a_license_to_repair_structure():
    rows = fixture(state='UNKNOWN')
    rows['LINE'].append({'Line_ID': 'extra', 'Line_FromBus': 's', 'Line_ToBus': 'b'})
    result = analyze(rows)
    assert result['policies']['S2_UNKNOWN_CONDUCTING']['transformer_goal_status'] == 'FAILED'
    assert result['policies']['S2_UNKNOWN_CONDUCTING']['assumed_conducting_switch_ids'] == []


def test_endpoint_unknown_is_already_allowed_by_s2():
    result = analyze(fixture(x='missing', y='unresolved'))
    assert result['policies']['SEMANTIC_CONSERVATIVE']['transformer_goal_status'] == 'FAILED'
    assert result['policies']['S2']['transformer_goal_status'] == 'FULL'
    assert result['policies']['S2']['graph_sha256'] == result['policies']['S2_UNKNOWN_CONDUCTING']['graph_sha256']


def test_rejected_identity_stays_in_denominator():
    rows = fixture(); rows['SWITCH'].append(dict(rows['SWITCH'][0]))
    result = analyze(rows)
    assert result['switch_inventory']['raw_rows'] == 2
    assert result['switch_inventory']['identity_groups'] == 1
    assert result['policies']['S2']['totals']['SWITCH'] == 1
    assert result['policies']['S2']['reachable']['SWITCH'] == 0


def test_tie_blocker_and_overlap():
    rows = fixture(state='Open'); rows['SWITCH'][0]['Switch_IsTie'] = 'True'
    result = analyze(rows)
    assert set(result['policies']['S2']['blocker_tags']) >= {'tie_unresolved', 'topology_disconnected', 'transformer_unreachable'}
    assert result['policies']['S2']['primary_failure_reason'] == 'tie_unresolved'


def test_order_and_source_immutability():
    details = mapped(fixture(state='UNKNOWN'))
    baseline = interpret_topology(details, TopologyConfig(Decimal('10.5')))
    before = canonical_json_bytes((details.records, details.accounting, baseline))
    first = analyze_feeder_case(details, baseline)
    second = analyze_feeder_case(replace(details, records=tuple(reversed(details.records)), accounting=tuple(reversed(details.accounting))), baseline)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert canonical_json_bytes((details.records, details.accounting, baseline)) == before


def test_semantic_conservative_keeps_structure_but_blocks_unknown():
    result = analyze(fixture(x='unknown_x', y='unknown_y'))
    conservative = result['policies']['SEMANTIC_CONSERVATIVE']
    optimistic = result['policies']['SEMANTIC_OPTIMISTIC']
    assert conservative['coverage']['switch_projected_count'] == optimistic['coverage']['switch_projected_count'] == 1
    assert conservative['coverage']['switch_conducting_count'] == 0
    assert optimistic['coverage']['switch_conducting_count'] == 1
    assert conservative['transformer_goal_status'] == 'FAILED'
    assert optimistic['transformer_goal_status'] == 'FULL'
    summary = FeederSummary(); summary.add(result)
    recovery = summary.finish()['policy_recovery']['semantic_relaxation']
    assert recovery['failed_to_full'] == recovery['by_primary_failure_reason']['switch_unknown']['failed_to_full'] == 1
    assert recovery['strict_newly_full'] == 1


def test_primary_coverage_and_strict_quality_gap():
    rows = fixture(); rows['SWITCH'].append({'Switch_ID': 'unused'})
    summary = FeederSummary(); summary.add(analyze(rows))
    report = summary.finish()['feeder_coverage']['policies']['S2']
    assert report['transformer_goal_status']['FULL'] == 1
    assert report['strict_topology_status']['PARTIAL'] == 1
    assert report['target_full_but_strict_incomplete'] == 1


def test_artifact_hashseed_and_same_input(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys
    code = '''from test_feeder_coverage import analyze, fixture
from grid_case_generator.io.feeder_coverage_artifacts import write_feeder_analysis
from grid_case_generator.analysis.feeder_coverage_cli import render_report
import sys
rows=fixture(state='UNKNOWN',x='unresolved',y='unknown')
write_feeder_analysis(sys.argv[1], {'source':sys.argv[1]+'e1','baseline':sys.argv[1]+'e2','projection':sys.argv[1]+'e22'}, {'source':'a'*64,'baseline':'b'*64,'projection':'c'*64}, [analyze(rows)], render_report)
'''
    for seed in ('1', '999', '1_repeat'):
        env = dict(os.environ, PYTHONHASHSEED=seed.split('_')[0], PYTHONPATH=str(Path(__file__).parent.resolve()))
        subprocess.run([sys.executable, '-c', code, str(tmp_path / seed)], env=env, check=True)
    def snapshot(root): return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert snapshot(tmp_path / '1') == snapshot(tmp_path / '999') == snapshot(tmp_path / '1_repeat')


def test_artifact_isolation_and_csv_counts(tmp_path):
    import csv
    from grid_case_generator.io.feeder_coverage_artifacts import write_feeder_analysis, verify_feeder_analysis
    from grid_case_generator.analysis.feeder_coverage_cli import render_report
    roots = {k: tmp_path / k for k in ('source', 'baseline', 'projection')}
    for output in (*roots.values(), roots['projection'] / 'nested', tmp_path):
        with pytest.raises(ValueError): write_feeder_analysis(output, roots, {}, [], render_report)
    rows = fixture(); rows['FEEDER'][0]['Feeder_Name'] = 'quoted,\nname'
    output = tmp_path / 'output'
    write_feeder_analysis(output, roots, {}, [analyze(rows)], render_report)
    manifest = verify_feeder_analysis(output)
    assert manifest['files']['feeder_switch_counts.csv']['record_count'] == 2
    with (output / 'feeder_switch_counts.csv').open(newline='') as stream:
        row, = list(csv.DictReader(stream))
        assert row['source_feeder_id'] == 'f' and row['switch_count'] == '1'
    with pytest.raises(FileExistsError): write_feeder_analysis(output, roots, {}, [], render_report)
    (output / 'failure_analysis.json').write_text('{}\n')
    with pytest.raises(ValueError): verify_feeder_analysis(output)


def test_end_to_end_verified_inputs_unchanged(tmp_path, monkeypatch):
    import csv
    import io
    from zipfile import ZipFile
    from source_fixture import SCHEMA
    from grid_case_generator.io.nanjing_source.import_pipeline import import_archive
    from grid_case_generator.io.topology_artifacts import audit_source_artifact
    from grid_case_generator.io.switch_projection_artifacts import run_projection_analysis
    from grid_case_generator.analysis.switch_projection_proposal import render_proposal
    from grid_case_generator.io.feeder_coverage_artifacts import run_feeder_analysis, verify_feeder_analysis
    from grid_case_generator.analysis.feeder_coverage_cli import render_report
    archive = tmp_path / 'fixture.zip'
    with ZipFile(archive, 'w') as z:
        for case, rows in [('ordinary', fixture(x='unresolved', y='unknown')), ('empty', {})]:
            for schema in SCHEMA.files:
                stream = io.StringIO(newline=''); writer = csv.writer(stream); writer.writerow(schema.header)
                for row in rows.get(schema.file_type.value, []): writer.writerow([row.get(k, '') for k in schema.header])
                z.writestr(case + '/' + schema.filename, stream.getvalue())
    e1, e2, e22 = (tmp_path / p for p in ('e1', 'e2', 'e22'))
    import_archive(archive, e1, imported_at='2026-09-15T00:00:00Z'); archive.unlink()
    def fail(*args, **kwargs): raise AssertionError('opened raw ZIP')
    monkeypatch.setattr(ZipFile, '__init__', fail)
    audit_source_artifact(e1, e2, TopologyConfig(Decimal('10.5')))
    run_projection_analysis(e1, e2, e22, render_proposal)
    def snapshot(root): return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    before = [snapshot(p) for p in (e1, e2, e22)]
    reports = run_feeder_analysis(e1, e2, e22, tmp_path / 'out', render_report)
    assert reports['feeder_coverage']['population']['feeder_identity_groups'] == 1
    assert reports['feeder_coverage']['policies']['S2']['transformer_goal_status']['FULL'] == 1
    assert reports['policy_recovery']['semantic_relaxation']['failed_to_full'] == 1
    verify_feeder_analysis(tmp_path / 'out')
    assert before == [snapshot(p) for p in (e1, e2, e22)]


def test_shared_case_targets_are_not_multiplied_in_population_totals():
    rows = fixture(); rows['FEEDER'].append({'Feeder_ID': 'other', 'Feeder_SourceBus': 'up'})
    summary = FeederSummary(); summary.add(analyze(rows))
    report = summary.finish()['feeder_coverage']
    assert report['population']['feeder_identity_groups'] == 2
    assert report['policies']['S2']['source_transformer_groups'] == 1


def test_semantic_optimistic_does_not_close_known_open():
    result = analyze(fixture(state='Open', x='unknown_x', y='unknown_y'))
    assert result['policies']['SEMANTIC_OPTIMISTIC']['coverage']['switch_conducting_count'] == 0
    assert result['policies']['SEMANTIC_CONSERVATIVE']['graph_sha256'] == result['policies']['SEMANTIC_OPTIMISTIC']['graph_sha256']


def test_assumed_conducting_unknown_is_not_reported_as_policy_blocker():
    rows = fixture(state='UNKNOWN')
    rows['LINE'][0]['Line_ToBus'] = 'unresolved_source_path'
    result = analyze(rows)
    assert 'switch_unknown' in result['policies']['S2']['blocker_tags']
    optimistic = result['policies']['S2_UNKNOWN_CONDUCTING']
    assert optimistic['transformer_goal_status'] == 'FAILED'
    assert 'switch_unknown' not in optimistic['blocker_tags']
    assert 'topology_disconnected' in optimistic['blocker_tags']
