from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile
import csv
import io

import pytest

from grid_case_generator.io.nanjing_source.schema import NANJING_SOURCE_SCHEMA as SCHEMA
from grid_case_generator.io.nanjing_source.models import RawCsvRecord, RawSourceFile, SourceCaseInventory
from grid_case_generator.io.nanjing_source.locator import source_record_ref
from grid_case_generator.models.identifiers import SourceImportIdFactory as IDs
from grid_case_generator.models.records import Equipment, Terminal, Transformer, OperationalValue, SimulationProfile, FieldProvenance
from grid_case_generator.models.types import ImportStatus, SourceReferenceStatus, ConnectivityStatus
from grid_case_generator.io.nanjing_source.import_pipeline import map_source_case, import_archive
from grid_case_generator.io.source_artifacts import read_source_case, verify_source_artifact

DATASET = IDs.dataset_id('a' * 64)


def source_files(rows, case='case'):
    files = []
    for schema in SCHEMA.files:
        member = f'{case}/{schema.filename}'
        records = []
        for n, row in enumerate(rows.get(schema.file_type.value, []), 1):
            values = tuple(row.get(k, '') for k in schema.header)
            records.append(RawCsvRecord(source_case_key=case, source_file_type=schema.file_type,
                header=schema.header, data_row=n, source_record_ref=source_record_ref(member, data_row=n),
                values=values, fields=tuple(zip(schema.header, values))))
        files.append(RawSourceFile(source_case_key=case, source_file_type=schema.file_type,
            member_path=member, header=schema.header, records=tuple(records), diagnostics=()))
    inventory = SourceCaseInventory(source_case_key=case,
        members=tuple((s.file_type, f'{case}/{s.filename}') for s in SCHEMA.files))
    return inventory, tuple(files)


def mapped(rows):
    inventory, files = source_files(rows)
    return map_source_case(inventory, files, dataset_id=DATASET)


def test_complete_equipment_mapping_preserves_values_and_only_resolves_source():
    result = mapped({'BUS': [{'Bus_ID': 'b', 'Bus_BaseKV': '110'}],
        'FEEDER': [{'Feeder_ID': 'f', 'Feeder_SourceBus': 'b'}],
        'LINE': [{'Line_ID': 'l', 'Line_FromBus': 'b', 'Line_ToBus': 't', 'Line_Length_km': '0'}],
        'TRANSFORMER': [{'Transformer_ID': 't', 'Transformer_RatedCapacity_kVA': '630.00'}]})
    assert result.import_status is ImportStatus.COMPLETE
    terminals = [r for r in result.records if isinstance(r, Terminal)]
    assert len(terminals) == 4
    assert all(t.connectivity_status is ConnectivityStatus.NOT_ASSESSED and t.connectivity_node_ref is None for t in terminals)
    assert sum(t.source_ref_status is SourceReferenceStatus.EXACT for t in terminals) == 2
    assert next(r for r in result.records if isinstance(r, Transformer)).rated_capacity_kva == Decimal('630.00')
    assert any(i.code.value == 'SOURCE_VALUE_OUT_OF_RANGE' for i in result.issues)
    assert len(result.accounting) == 4
    assert not result.canonical_valid


def test_duplicate_equipment_conflict_and_identical_never_become_exact():
    result = mapped({'SWITCH': [{'Switch_ID': 's'}, {'Switch_ID': 's'}],
        'TRANSFORMER': [{'Transformer_ID': 't', 'Transformer_RatedCapacity_kVA': '100'},
                        {'Transformer_ID': 't', 'Transformer_RatedCapacity_kVA': '200'}],
        'LINE': [{'Line_ID': 'l', 'Line_FromBus': 's', 'Line_ToBus': 't'}]})
    assert len([r for r in result.records if isinstance(r, Equipment)]) == 2
    line_terms = [r for r in result.records if isinstance(r, Terminal) and r.raw_connected_ref]
    assert all(t.source_ref_status is SourceReferenceStatus.AMBIGUOUS for t in line_terms)
    assert len(result.accounting) == 5
    assert result.import_status is ImportStatus.COMPLETE


def test_operational_and_config_provenance_and_empty_load_der():
    result = mapped({'SWITCH': [{'Switch_ID': 's', 'Switch_Meas_P_kW': '-1.25'}],
        'SIM_CONFIG': [{'Config_Key': 'BaseVoltage_kV', 'Config_Value': '10.5'},
                       {'Config_Key': 'SourceBus', 'Config_Value': 'SUB_10KV'}]})
    value = next(r for r in result.records if isinstance(r, OperationalValue))
    assert value.decimal_value == Decimal('-1.25') and value.timestamp is None
    assert value.quality.value == 'TIME_UNKNOWN'
    profile = next(r for r in result.records if isinstance(r, SimulationProfile))
    assert profile.source_voltage_kv == Decimal('10.5')
    assert profile.source_bus_source_ref.resolution_status is SourceReferenceStatus.UNRESOLVED
    assert len(result.provenance) == 2
    assert all(isinstance(p, FieldProvenance) and p.source_record_ref for p in result.provenance)
    assert not any(isinstance(r, Equipment) and r.equipment_type.value in ('LOAD', 'DER') for r in result.records)


def write_zip(path, rows):
    with ZipFile(path, 'w') as archive:
        for schema in SCHEMA.files:
            stream = io.StringIO(newline='')
            writer = csv.writer(stream)
            writer.writerow(schema.header)
            for row in rows.get(schema.file_type.value, []):
                writer.writerow([row.get(k, '') for k in schema.header])
            archive.writestr(f'case/{schema.filename}', stream.getvalue())


def test_artifact_roundtrip_determinism_and_tamper(tmp_path):
    archive = tmp_path / 'source.zip'
    write_zip(archive, {'BUS': [{'Bus_ID': 'b'}], 'FEEDER': [{'Feeder_ID': 'f', 'Feeder_SourceBus': 'b'}]})
    before = archive.read_bytes()
    outputs = [tmp_path / 'one', tmp_path / 'two']
    for output in outputs:
        result = import_archive(archive, output, imported_at='2026-09-14T00:00:00+00:00')
        assert result['import_status'] == 'COMPLETE'
        verify_source_artifact(output)
    first = {p.relative_to(outputs[0]): p.read_bytes() for p in outputs[0].rglob('*') if p.is_file()}
    second = {p.relative_to(outputs[1]): p.read_bytes() for p in outputs[1].rglob('*') if p.is_file()}
    assert first == second
    case_id = result['cases'][0]['case_id']
    records = read_source_case(outputs[0], case_id)
    assert any(isinstance(r, Equipment) for r in records) is False
    assert archive.read_bytes() == before
    with pytest.raises(FileExistsError):
        import_archive(archive, outputs[0], imported_at='2026-09-14T00:00:00+00:00')
    (outputs[0] / 'dataset.json').write_text('{}')
    with pytest.raises(ValueError, match='checksum'):
        verify_source_artifact(outputs[0])


def test_all_equipment_types_unknown_phase_and_missing_id():
    rows = {}
    for name, prefix in [('SWITCH','Switch'),('DISCONNECTOR','Disconnector'),
                         ('EARTHING_SWITCH','EarthingSwitch'),('ACCESS_POINT','AccessPoint'),
                         ('LINE','Line'),('TRANSFORMER','Transformer'),('LOAD','Load'),('DER','DER')]:
        rows[name] = [{f'{prefix}_ID': name, f'{prefix}_Phase': 'unconfirmed'}, {f'{prefix}_ID': ''}]
    result = mapped(rows)
    assert len([r for r in result.records if isinstance(r, Equipment)]) == 8
    assert len(result.unmapped_records) == 8
    assert len(result.accounting) == 16
    assert all(r.phases is None for r in result.records if isinstance(r, Equipment))


def test_reordered_inputs_have_identical_case_artifacts():
    inventory, files = source_files({'TRANSFORMER': [
        {'Transformer_ID':'t','Transformer_RatedCapacity_kVA':'bad'},
        {'Transformer_ID':'t','Transformer_RatedCapacity_kVA':'bad'}],
        'BUS':[{'Bus_ID':'b','Bus_Phase':'unknown'},{'Bus_ID':'b','Bus_Phase':'unknown'}]})
    first = map_source_case(inventory,files,dataset_id=DATASET)
    reversed_files = tuple(replace(f,records=tuple(reversed(f.records))) for f in reversed(files))
    second = map_source_case(inventory,reversed_files,dataset_id=DATASET)
    assert first.records == second.records
    assert first.issues == second.issues
    assert first.accounting == second.accounting
    assert len([i for i in first.issues if i.code.value=='SOURCE_VALUE_PARSE_FAILED']) == 2


def test_config_conflict_unknown_key_and_missing_key_are_accounted():
    result = mapped({'SIM_CONFIG':[
        {'Config_Key':'BaseVoltage_kV','Config_Value':'10.5'},
        {'Config_Key':'BaseVoltage_kV','Config_Value':'20'},
        {'Config_Key':'new-setting','Config_Value':'literal'},
        {'Config_Key':'','Config_Value':'retain-me'}]})
    profile = next(r for r in result.records if isinstance(r,SimulationProfile))
    assert profile.source_voltage_kv is None
    assert profile.extensions == {'nanjing_csv:new-setting':'literal'}
    assert len(result.accounting)==4 and len(result.unmapped_records)==1
    assert result.import_status is ImportStatus.COMPLETE


def test_unknown_reference_candidate_matrix_is_not_expanded():
    result = mapped({'BUS':[{'Bus_ID':'b'}],
        'TRANSFORMER':[{'Transformer_ID':'t','Transformer_FromBus':'b'}],
        'ACCESS_POINT':[{'AccessPoint_ID':'a','AccessPoint_Bus':'b'}],
        'LINE':[{'Line_ID':'l','Line_FromBus':'1e5','Line_ToBus':'0'}]})
    nonempty = [r for r in result.records if isinstance(r,Terminal) and r.raw_connected_ref]
    assert all(r.source_ref_status is SourceReferenceStatus.UNRESOLVED for r in nonempty)
    assert any(i.code.value=='SOURCE_IDENTIFIER_SUSPICIOUS_FORMAT' for i in result.issues)
    assert any(i.code.value=='SOURCE_REFERENCE_INVALID_LITERAL' for i in result.issues)


def test_parse_interruption_is_incomplete_but_malformed_retained_row_complete(tmp_path):
    archive = tmp_path/'broken.zip'
    with ZipFile(archive,'w') as z:
        schema = SCHEMA.files[0]
        z.writestr('case/'+schema.filename, ','.join(schema.header)+'\n"unfinished')
    report = import_archive(archive,tmp_path/'result',imported_at='2026-09-14T00:00:00+00:00')
    assert report['import_status']=='INCOMPLETE'
    assert report['case_count']==1
    archive2 = tmp_path/'malformed.zip'
    with ZipFile(archive2,'w') as z:
        schema = SCHEMA.files[0]
        z.writestr('case/'+schema.filename, ','.join(schema.header)+'\nonly-one-column\n')
    report = import_archive(archive2,tmp_path/'result2',imported_at='2026-09-14T00:00:00+00:00')
    assert report['import_status']=='COMPLETE'
    assert report['cases'][0]['row_categories']['REJECTED']==1


def test_artifact_restores_every_record_type_and_provenance(tmp_path):
    archive=tmp_path/'all.zip'
    write_zip(archive, {'BUS':[{'Bus_ID':'b','Bus_BaseKV':'110'}],
        'SWITCH':[{'Switch_ID':'s','Switch_Meas_Q_kVAR':'-2'}],
        'TRANSFORMER':[{'Transformer_ID':'t','Transformer_RatedCapacity_kVA':'630.00'}],
        'SIM_CONFIG':[{'Config_Key':'BaseVoltage_kV','Config_Value':'10.5'}]})
    output=tmp_path/'out'
    report=import_archive(archive,output,imported_at='2026-09-14T00:00:00+00:00')
    records=read_source_case(output,report['cases'][0]['case_id'])
    assert next(r for r in records if isinstance(r,Transformer)).rated_capacity_kva==Decimal('630.00')
    assert next(r for r in records if isinstance(r,OperationalValue)).decimal_value==Decimal('-2')
    assert all(t.connectivity_node_ref is None for t in records if isinstance(t,Terminal))


def test_output_guards_and_manifest_traversal(tmp_path):
    archive=tmp_path/'source.zip'
    write_zip(archive,{})
    timestamp='2026-09-14T00:00:00+00:00'
    with pytest.raises(ValueError):
        import_archive(archive,archive,imported_at=timestamp)
    link=tmp_path/'link'
    link.symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(ValueError):
        import_archive(archive,link/'out',imported_at=timestamp)
    with pytest.raises(ValueError):
        import_archive(archive,tmp_path/'out',imported_at='2026-09-14')
    output=tmp_path/'good'
    import_archive(archive,output,imported_at=timestamp)
    import json
    manifest=json.loads((output/'manifest.json').read_text())
    manifest['files']['../source.zip']={'sha256':'bad','record_count':1}
    (output/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='unsafe'):
        verify_source_artifact(output)


def test_program_error_is_reported_without_dropping_following_case(tmp_path,monkeypatch):
    from grid_case_generator.io.nanjing_source import import_pipeline
    archive=tmp_path/'cases.zip'
    with ZipFile(archive,'w') as z:
        for key in ('a','b'):
            for schema in SCHEMA.files:
                z.writestr(key+'/'+schema.filename,','.join(schema.header)+'\n')
    original=import_pipeline.map_source_case
    def injected(inventory,*args,**kwargs):
        if inventory.source_case_key=='a':
            raise RuntimeError('injected failure')
        return original(inventory,*args,**kwargs)
    monkeypatch.setattr(import_pipeline,'map_source_case',injected)
    report=import_archive(archive,tmp_path/'out',imported_at='2026-09-14T00:00:00+00:00')
    assert report['import_status']=='INCOMPLETE'
    assert len(report['cases'])==2
    assert report['cases'][0]['error_type']=='RuntimeError'
    assert report['cases'][1]['import_status']=='COMPLETE'


def test_known_snapshot_timestamp_is_preserved_without_invented_timezone():
    result=mapped({'SWITCH':[{'Switch_ID':'s','Switch_Meas_I_A':'2.5',
        'Switch_Meas_Timestamp':'2026-09-14T01:00:00+08:00'}]})
    point=next(r for r in result.records if isinstance(r,OperationalValue))
    assert point.timestamp=='2026-09-14T01:00:00+08:00'
    assert point.quality.value=='VALID'


def test_hash_seed_does_not_change_persistent_source_artifacts(tmp_path):
    import os
    import subprocess
    import sys
    archive=tmp_path/'source.zip'
    write_zip(archive,{'LINE':[{'Line_ID':'l','Line_FromBus':'s'}],
        'SWITCH':[{'Switch_ID':'s'},{'Switch_ID':'s'}]})
    outputs=[]
    for seed in ('1','98765'):
        output=tmp_path/seed
        completed=subprocess.run([sys.executable,'-m','grid_case_generator.io.nanjing_source',
            'import-source',str(archive),'--output',str(output),'--imported-at','2026-09-14T00:00:00+00:00'],
            env=dict(os.environ,PYTHONHASHSEED=seed),text=True,capture_output=True)
        assert completed.returncode==0,completed.stderr
        outputs.append({str(p.relative_to(output)):p.read_bytes() for p in output.rglob('*') if p.is_file()})
    assert outputs[0]==outputs[1]


def test_persisted_case_details_restore_raw_evidence_and_provenance(tmp_path):
    from grid_case_generator.io.source_artifacts import read_source_case_details
    archive=tmp_path/'source.zip'
    write_zip(archive,{'BUS':[{'Bus_ID':'001'}],
        'LINE':[{'Line_ID':'l','Line_FromBus':'001'}],
        'SIM_CONFIG':[{'Config_Key':'BaseVoltage_kV','Config_Value':'10.5'}]})
    output=tmp_path/'out'
    report=import_archive(archive,output,imported_at='2026-09-14T00:00:00+00:00')
    details=read_source_case_details(output,report['cases'][0]['case_id'])
    assert len(details.accounting)==3
    assert details.accounting[0].raw_record.values[0]=='001'
    assert len(details.provenance)==1
    assert details.provenance[0].source_field=='Config_Value'
    assert any(r.resolution_status is SourceReferenceStatus.EXACT for r in details.resolutions)
    assert details.records==read_source_case(output,report['cases'][0]['case_id'])


def test_aggregate_provenance_is_required_for_canonical_validity():
    from grid_case_generator.validation.source_import import canonical_case_errors
    result=mapped({'SIM_CONFIG':[{'Config_Key':'BaseVoltage_kV','Config_Value':'10.5'}]})
    assert not canonical_case_errors(result.records,result.issues,result.provenance)
    assert canonical_case_errors(result.records,result.issues,())


def test_e1_retains_110kv_feeder_anchor_without_creating_mv_source():
    from grid_case_generator.models.records import Bus, Feeder
    result=mapped({'STATION':[{'Station_ID':'station','Station_Voltage_Level':'110'}],
        'BUS':[{'Bus_ID':'upstream','Bus_BaseKV':'110','Bus_Station_ID':'station'}],
        'FEEDER':[{'Feeder_ID':'f','Feeder_Name':'20kV feeder','Feeder_SourceBus':'upstream'}],
        'LINE':[{'Line_ID':'l','Line_FromBus':'station'}]})
    buses=[r for r in result.records if isinstance(r,Bus)]
    assert len(buses)==1 and buses[0].base_voltage_kv==Decimal('110')
    feeder=next(r for r in result.records if isinstance(r,Feeder))
    assert feeder.source_bus_source_ref.resolved_source_ref.entity_id==buses[0].bus_id
    assert all(r.record_origin.value=='SOURCE' for r in result.records)
    assert not any(isinstance(r,Transformer) for r in result.records)
