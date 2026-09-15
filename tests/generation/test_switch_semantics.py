from dataclasses import replace
from decimal import Decimal
import pytest
from source_fixture import mapped
from grid_case_generator.generation.topology import interpret_topology
from grid_case_generator.models.topology import TopologyConfig
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.analysis.switch_semantics import (
    literal_motif, id_pattern, investigate_case, aggregate_cases,
)


def fixture(state='Closed', x='a', y='b'):
    return {'STATION':[{'Station_ID':'st'}],
        'BUS':[{'Bus_ID':'up','Bus_BaseKV':'110','Bus_Station_ID':'st'},
               {'Bus_ID':'a','Bus_BaseKV':'10.5'}, {'Bus_ID':'b','Bus_BaseKV':'10.5'}],
        'FEEDER':[{'Feeder_ID':'f','Feeder_SourceBus':'up'}],
        'LINE':[{'Line_ID':'head','Line_FromBus':'st','Line_ToBus':'a'},
                {'Line_ID':'in','Line_FromBus':'a','Line_ToBus':'s'},
                {'Line_ID':'out','Line_FromBus':'s','Line_ToBus':'b'},
                {'Line_ID':'tail','Line_FromBus':'b','Line_ToBus':'t'}],
        'SWITCH':[{'Switch_ID':'s','Switch_FromBus':x,'Switch_ToBus':y,
                   'Switch_NormalState':state,'Switch_IsTie':'False','Switch_HasMeasurement':'True'}],
        'TRANSFORMER':[{'Transformer_ID':'t'}]}


def analyze(rows):
    source=mapped(rows)
    baseline=interpret_topology(source,TopologyConfig(Decimal('10.5')))
    return investigate_case(source,baseline)


@pytest.mark.parametrize('x,y,expected', [
    ('a','b','DIRECT'),('b','a','REVERSE'),('a','z','X_A_ONLY'),('z','b','Y_B_ONLY'),
    ('b','z','X_B_ONLY'),('z','a','Y_A_ONLY'),('z','z','X_EQUALS_Y'),
    ('','','BOTH_MISSING'),('x','','Y_MISSING'),('','y','X_MISSING'),('x','y','BOTH_DIFFERENT')])
def test_motifs(x,y,expected):
    assert literal_motif('a','b',x,y)['motif']==expected


def test_candidate_endpoints_and_counterfactual():
    result=analyze(fixture())
    candidate,=result['candidates']
    assert candidate['endpoints']['A']['source_entity_type']=='BUS'
    assert candidate['endpoints']['X']['diagnostic_entity_type']=='BUS'
    assert candidate['breakdown']=='EXACT_COMPATIBLE'
    assert candidate['relations']['A_X']['distance']=='0'
    assert result['counterfactual']['baseline']['reachable_transformers']==0
    assert result['counterfactual']['A']['reachable_transformers']==1
    assert result['counterfactual']['B']['reachable_transformers']==1


@pytest.mark.parametrize('state', ['Open','UNKNOWN'])
def test_counterfactual_never_closes_open_or_unknown(state):
    result=analyze(fixture(state))
    assert result['counterfactual']['A']['reachable_transformers']==0


def test_unknown_endpoints_are_not_confirmed_conflicts():
    result=analyze(fixture(x='12345',y='12346'))
    c,=result['candidates']
    assert c['breakdown']=='ENDPOINT_UNRESOLVED'
    assert c['semantic_assessment']=='UNRESOLVED_SEMANTICS'
    assert c['relations']['A_X']['distance']=='UNRESOLVED'
    assert result['counterfactual']['A']['reachable_transformers']==1
    assert result['counterfactual']['B']['reachable_transformers']==0


def test_degree_and_baseline_device_count():
    rows=fixture(); rows['LINE'].append({'Line_ID':'extra','Line_FromBus':'s','Line_ToBus':'z'})
    result=analyze(rows)
    assert not result['candidates']
    assert result['degree']['baseline_SWITCH_DEGREE']['3']==1
    assert result['degree']['all_identity_groups']['3']==1


def test_duplicate_lines_are_not_selected():
    rows=fixture(); rows['LINE'].append(dict(rows['LINE'][1]))
    result=analyze(rows)
    assert not result['candidates']
    assert result['degree']['all_identity_groups']['2']==1


def test_case_aggregation_and_order():
    result=analyze(fixture())
    assert result['case_summary']['motif_purity']==Decimal('1.000000')
    report=aggregate_cases([result])
    assert report['dataset_summary']['candidate_switches']==1
    source=mapped(fixture()); baseline=interpret_topology(source,TopologyConfig(Decimal('10.5')))
    before=canonical_json_bytes((source.records,baseline))
    shuffled=replace(source,records=tuple(reversed(source.records)),accounting=tuple(reversed(source.accounting)))
    assert canonical_json_bytes(investigate_case(shuffled,baseline))==canonical_json_bytes(result)
    assert canonical_json_bytes((source.records,baseline))==before


def test_id_diagnostics_do_not_repair():
    assert id_pattern('00123','123')['leading_zero_only']
    assert id_pattern('12345678','12345690')['common_prefix_length']==6
    assert id_pattern('1.23e+18','1230000000000000000')['scientific_notation']
    assert not id_pattern('1.23e+18','1230000000000000000')['exact_same']


def test_diagnostic_lookup_does_not_replace_source_reference():
    rows=fixture(x='f')
    c,=analyze(rows)['candidates']
    assert c['endpoints']['X']['source_reference_status']=='UNRESOLVED'
    assert c['endpoints']['X']['diagnostic_entity_type']=='FEEDER'
    assert c['endpoints']['X']['source_target_ref'] is None


def test_graph_distances_and_membership():
    rows=fixture(x='st'); rows['BUS'][1]['Bus_Station_ID']='st'
    c,=analyze(rows)['candidates']
    assert c['relations']['A_X']['distance']=='1'
    assert c['relations']['A_X']['direct_bus_station_membership']
    assert c['breakdown']=='DIFFERENT_SOURCE_LAYER'
    rows=fixture(x='s')
    c,=analyze(rows)['candidates']
    assert c['relations']['A_X']['distance']=='2'
    assert not c['relations']['A_X']['direct_bus_station_membership']
    rows=fixture(x='b',y='a')
    c,=analyze(rows)['candidates']
    assert c['relations']['A_X']['distance']=='2'


def test_ambiguous_lookup_and_disconnected_graph():
    rows=fixture(x='z'); rows['BUS'] += [{'Bus_ID':'z'}]
    c,=analyze(rows)['candidates']
    # Switch->z itself is an EXACT reference edge; the Line motif gives a longer path.
    assert c['relations']['A_X']['distance']=='GT2'
    rows['BUS'].append({'Bus_ID':'z'})
    c,=analyze(rows)['candidates']
    assert c['endpoints']['X']['diagnostic_status']=='AMBIGUOUS'
    assert c['breakdown']=='ENDPOINT_AMBIGUOUS'


def test_all_degree_directions_and_no_candidates():
    rows=fixture(); rows['LINE'][2].update(Line_FromBus='b',Line_ToBus='s')
    r=analyze(rows)
    assert r['degree_two_directions']['all_identity_groups']['TWO_IN']==1
    assert not r['candidates'] and r['case_summary']['motif_purity'] is None
    rows=fixture(); rows['LINE'][1].update(Line_FromBus='s',Line_ToBus='a')
    assert analyze(rows)['degree_two_directions']['all_identity_groups']['TWO_OUT']==1
    rows=fixture(); rows['LINE']=[]
    assert analyze(rows)['degree']['all_identity_groups']['0']==1
    rows=fixture(); rows['LINE']=rows['LINE'][:2]
    assert analyze(rows)['degree']['all_identity_groups']['1']==1


def test_artifact_determinism_hashseed(tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    code='''from test_switch_semantics import fixture,mapped
from dataclasses import replace
from decimal import Decimal
import sys
from grid_case_generator.generation.topology import interpret_topology
from grid_case_generator.models.topology import TopologyConfig
from grid_case_generator.analysis.switch_semantics import investigate_case
from grid_case_generator.io.switch_semantics_artifacts import write_investigation
source=mapped(fixture()); baseline=interpret_topology(source,TopologyConfig(Decimal('10.5')))
source=replace(source,records=tuple(reversed(source.records)),accounting=tuple(reversed(source.accounting))) if sys.argv[2]=='999' else source
write_investigation(sys.argv[1],sys.argv[1]+'e1',sys.argv[1]+'e2','a'*64,'b'*64,[investigate_case(source,baseline)])
'''
    for seed in ('1','999'):
        env=dict(os.environ,PYTHONHASHSEED=seed,PYTHONPATH=str(Path(__file__).parent.resolve()))
        subprocess.run([sys.executable,'-c',code,str(tmp_path/seed),seed],env=env,check=True)
    def snapshot(root): return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert snapshot(tmp_path/'1')==snapshot(tmp_path/'999')


def test_artifact_verification_and_isolation(tmp_path):
    from grid_case_generator.io.switch_semantics_artifacts import write_investigation,verify_investigation_artifact
    result=analyze(fixture()); output=tmp_path/'diagnostics'
    write_investigation(output,tmp_path/'source',tmp_path/'baseline','a'*64,'b'*64,[result])
    verify_investigation_artifact(output)
    with pytest.raises(FileExistsError): write_investigation(output,tmp_path/'source',tmp_path/'baseline','a'*64,'b'*64,[result])
    with pytest.raises(ValueError): write_investigation(tmp_path/'baseline'/'child',tmp_path/'source',tmp_path/'baseline','a'*64,'b'*64,[result])
    (output/'dataset_summary.json').write_text('{}\n')
    with pytest.raises(ValueError): verify_investigation_artifact(output)


@pytest.mark.parametrize('blocked', ['transformer','voltage'])
def test_counterfactual_preserves_non_switch_exclusions(blocked):
    rows=fixture()
    if blocked=='transformer': rows['TRANSFORMER'][0]['Transformer_FromBus']='a'
    else: rows['BUS'][1]['Bus_BaseKV']='110'
    assert analyze(rows)['counterfactual']['A']['reachable_transformers']==0


def test_multi_case_aggregation_is_order_independent():
    from source_fixture import source_files,map_source_case,DATASET
    results=[]
    for key in ('first','second'):
        inventory,files=source_files(fixture(),case=key)
        source=map_source_case(inventory,files,dataset_id=DATASET)
        baseline=interpret_topology(source,TopologyConfig(Decimal('10.5')))
        results.append(investigate_case(source,baseline))
    assert canonical_json_bytes(aggregate_cases(results))==canonical_json_bytes(aggregate_cases(reversed(results)))
    report=aggregate_cases(results)
    assert report['motif_distribution']['exclusive']['DIRECT']['case_count']==2
    assert report['dataset_summary']['candidate_switches']==2


def test_end_to_end_read_only_inputs(tmp_path,monkeypatch):
    import csv,io
    from zipfile import ZipFile
    from source_fixture import SCHEMA
    from grid_case_generator.io.nanjing_source.import_pipeline import import_archive
    from grid_case_generator.io.topology_artifacts import audit_source_artifact
    from grid_case_generator.io.switch_semantics_artifacts import run_investigation,verify_investigation_artifact
    archive=tmp_path/'fixture.zip'
    with ZipFile(archive,'w') as z:
        for key,rows in [('motif',fixture()),('empty',{})]:
            for schema in SCHEMA.files:
                stream=io.StringIO(newline=''); writer=csv.writer(stream);writer.writerow(schema.header)
                for row in rows.get(schema.file_type.value,[]): writer.writerow([row.get(k,'') for k in schema.header])
                z.writestr(key+'/'+schema.filename,stream.getvalue())
    e1=tmp_path/'e1';e2=tmp_path/'e2'
    import_archive(archive,e1,imported_at='2026-09-15T00:00:00Z')
    archive.unlink()
    def fail(*args,**kwargs): raise AssertionError('diagnostics opened ZIP')
    monkeypatch.setattr(ZipFile,'__init__',fail)
    audit_source_artifact(e1,e2,TopologyConfig(Decimal('10.5')))
    snapshot=lambda root:{str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    before1,before2=snapshot(e1),snapshot(e2)
    report=run_investigation(e1,e2,tmp_path/'analysis')
    assert report['total_cases']==2 and report['candidate_switches']==1
    verify_investigation_artifact(tmp_path/'analysis')
    assert snapshot(e1)==before1 and snapshot(e2)==before2


def test_raw_ids_have_no_reserved_diagnostic_prefix():
    rows=fixture();rows['LINE'][1]['Line_ID']='@row:incoming';rows['LINE'][2]['Line_ID']='@row:outgoing'
    assert len(analyze(rows)['candidates'])==1


def test_extra_out_of_matrix_identity_does_not_override_exact_reference():
    rows=fixture();rows['LINE'].append({'Line_ID':'a','Line_FromBus':'b','Line_ToBus':'missing'})
    c,=analyze(rows)['candidates']
    assert c['endpoints']['A']['source_reference_status']=='EXACT'
    assert c['endpoints']['A']['diagnostic_status']=='AMBIGUOUS'
    assert c['breakdown']=='EXACT_COMPATIBLE'
    assert c['relations']['A_X']['distance']=='0'


def test_disconnected_diagnostic_target_has_no_inserted_lookup_edge():
    rows=fixture(x='f2');rows['FEEDER'].append({'Feeder_ID':'f2'})
    c,=analyze(rows)['candidates']
    assert c['endpoints']['X']['source_reference_status']=='UNRESOLVED'
    assert c['endpoints']['X']['diagnostic_entity_type']=='FEEDER'
    assert c['relations']['A_X']['distance']=='DISCONNECTED'


def test_degree_gt_three_and_grouping():
    rows=fixture()
    rows['LINE'] += [{'Line_ID':'extra1','Line_FromBus':'s','Line_ToBus':'z'},
                    {'Line_ID':'extra2','Line_FromBus':'s','Line_ToBus':'z'}]
    assert analyze(rows)['degree']['all_identity_groups']['GT3']==1
    report=aggregate_cases([analyze(fixture())])
    groups=report['motif_distribution']['stratifications']
    assert groups['normal_state']['CLOSED']['total']==1
    assert groups['is_tie']['FALSE']['total']==1
    assert groups['has_measurement']['TRUE']['total']==1


def test_scenario_c_only_adds_demonstrated_membership():
    rows=fixture(x='st');rows['BUS'][1]['Bus_Station_ID']='st'
    report=aggregate_cases([analyze(rows)])
    counter=report['counterfactual_reachability']
    assert counter['C_data_supported']
    assert counter['B']['reachable_transformers']==0
    assert counter['C']['reachable_transformers']==1
    assert not aggregate_cases([analyze(fixture())])['counterfactual_reachability']['C_data_supported']
