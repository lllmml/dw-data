from decimal import Decimal
import random
from dataclasses import replace
import pytest
from grid_case_generator.generation.topology import interpret_topology, load_topology_config
from grid_case_generator.models.topology import TopologyConfig, DerivedIdFactory, DerivedRole
from grid_case_generator.io.canonical_json import canonical_json_bytes
from source_fixture import mapped


def fixture(state='CLOSED'):
    return {'STATION':[{'Station_ID':'st'}],
        'BUS':[{'Bus_ID':'up','Bus_BaseKV':'110','Bus_Station_ID':'st'}],
        'FEEDER':[{'Feeder_ID':'f','Feeder_SourceBus':'up'}],
        'LINE':[{'Line_ID':'a','Line_FromBus':'st','Line_ToBus':'s'},
                {'Line_ID':'b','Line_FromBus':'s','Line_ToBus':'t'}],
        'SWITCH':[{'Switch_ID':'s','Switch_NormalState':state.title()}],
        'TRANSFORMER':[{'Transformer_ID':'t'}]}


def run(rows):
    return interpret_topology(mapped(rows), TopologyConfig(Decimal('10.5')))


@pytest.mark.parametrize('state,count', [('CLOSED',1),('OPEN',0),('UNKNOWN',0)])
def test_reachability(state,count):
    result=run(fixture(state))
    assert result.coverage.counts['reachable_transformers']==count
    assert result.coverage.usable_subgraph
    assert len(result.topology.branches)==3


@pytest.mark.parametrize('value', ['0','-1','nan','inf','true','"10.5"'])
def test_bad_config(tmp_path,value):
    p=tmp_path/'c.toml'; p.write_text('fallback_nominal_voltage_kv = '+value)
    with pytest.raises((ValueError,TypeError)): load_topology_config(p)


def test_unknown_config(tmp_path):
    p=tmp_path/'c.toml'; p.write_text('fallback_nominal_voltage_kv = 10.5\nseed = 1')
    with pytest.raises(ValueError): load_topology_config(p)


def test_deterministic_input_and_random():
    source=mapped(fixture()); before=canonical_json_bytes(source.records)
    expected=canonical_json_bytes(interpret_topology(source,TopologyConfig(Decimal('10.5'))))
    for seed in (1,999):
        random.seed(seed)
        shuffled=list(source.records); random.shuffle(shuffled)
        changed=replace(source,records=tuple(shuffled),accounting=tuple(reversed(source.accounting)))
        assert canonical_json_bytes(interpret_topology(changed,TopologyConfig(Decimal('10.5'))))==expected
    assert canonical_json_bytes(source.records)==before


def test_id_closed_roles():
    assert DerivedIdFactory.make(DerivedRole.FEEDER_HEAD,'case','owner').startswith('feeder-head:')
    with pytest.raises(TypeError): DerivedIdFactory.make('arbitrary','case','owner')


@pytest.mark.parametrize('mode,reason', [
    ('missing','MISSING_FEEDER'), ('ambiguous','AMBIGUOUS_FEEDER'),
    ('missing_bus','INVALID_FEEDER_BUS'), ('conflict','NAME_VOLTAGE_CONFLICT')])
def test_anchor_exclusions(mode,reason):
    rows=fixture()
    if mode=='missing': rows['FEEDER']=[]
    elif mode=='ambiguous': rows['FEEDER']*=2
    elif mode=='missing_bus': rows['BUS']=[]
    else: rows['FEEDER'][0]['Feeder_Name']='10kV 20kV'
    result=run(rows)
    assert result.topology.feeder_head_id is None
    assert result.coverage.feeder_anchor_status==reason
    assert not result.coverage.usable_subgraph
    assert not result.coverage.has_reachable_transformer


@pytest.mark.parametrize('name,voltage,origin', [('20kV某线','20.0','NAME_INFERENCE'),
    ('10KV某线','10.5','NAME_INFERENCE'), ('120kV某线','13','DEFAULT'), ('某线','13','DEFAULT')])
def test_voltage_name_and_config(name,voltage,origin):
    rows=fixture(); rows['FEEDER'][0]['Feeder_Name']=name
    result=interpret_topology(mapped(rows),TopologyConfig(Decimal('13')))
    assert result.coverage.nominal_voltage_kv==Decimal(voltage)
    assert result.coverage.voltage_source.value==origin


@pytest.mark.parametrize('value,reason', [('10',None),('10.5',None),('110','BUS_VOLTAGE_CONFLICT'),
    ('oops','INVALID_VOLTAGE_EVIDENCE'), ('0','INVALID_VOLTAGE_EVIDENCE')])
def test_bus_voltage(value,reason):
    rows=fixture(); rows['BUS'].append({'Bus_ID':'j','Bus_BaseKV':value})
    rows['LINE'][0]['Line_FromBus']='j'
    result=run(rows)
    ps=[p for p in result.projections if p.rule_id.value=='BUS_JUNCTION_V1']
    assert len(ps)==1
    assert (ps[0].exclusion_reason.value if ps[0].exclusion_reason else None)==reason
    assert ps[0].source_terminal_ref is not None
    assert len(ps[0].supporting_source_refs)==4


@pytest.mark.parametrize('mode,reason', [('duplicate','AMBIGUOUS_REFERENCE'),('absent','UNRESOLVED_REFERENCE')])
def test_nonexact_bus(mode,reason):
    rows=fixture(); rows['LINE'][0]['Line_FromBus']='j'
    if mode=='duplicate': rows['BUS'] += [{'Bus_ID':'j'},{'Bus_ID':'j'}]
    result=run(rows)
    assert result.coverage.exclusion_reasons[reason]
    assert not result.coverage.usable_subgraph


@pytest.mark.parametrize('mode,reason', [('mismatch','STATION_CHAIN_MISMATCH'),('to','STATION_DIRECTION')])
def test_station_exclusions(mode,reason):
    rows=fixture()
    if mode=='mismatch':
        rows['STATION'].append({'Station_ID':'other'})
        rows['BUS'][0]['Bus_Station_ID']='other'
    else: rows['LINE'][0]['Line_FromBus'],rows['LINE'][0]['Line_ToBus']='s','st'
    result=run(rows)
    assert result.coverage.exclusion_reasons[reason]
    assert not result.coverage.usable_subgraph


def test_station_chain_evidence():
    result=run(fixture())
    projection=next(p for p in result.projections if p.rule_id.value=='STATION_FEEDER_HEAD_V1')
    assert len(projection.supporting_source_refs)==4
    assert projection.source_terminal_ref is not None


@pytest.mark.parametrize('mode,reason', [('one','SWITCH_DEGREE'), ('three','SWITCH_DEGREE'),
    ('from','SWITCH_DIRECTION'), ('to','SWITCH_DIRECTION'),('duplicate','IDENTITY_NOT_UNIQUE'),
    ('conflict','IDENTITY_NOT_UNIQUE'), ('explicit','EXPLICIT_ENDPOINT_EVIDENCE'),
    ('duplicate_line','INCIDENT_IDENTITY_CONFLICT')])
def test_switch_exclusions(mode,reason):
    rows=fixture()
    if mode=='one': rows['LINE'].pop()
    elif mode=='three': rows['LINE'].append({'Line_ID':'c','Line_FromBus':'s','Line_ToBus':'missing'})
    elif mode=='from': rows['LINE'][0].update(Line_FromBus='s',Line_ToBus='st')
    elif mode=='to': rows['LINE'][1].update(Line_FromBus='t',Line_ToBus='s')
    elif mode=='duplicate': rows['SWITCH']*=2
    elif mode=='conflict': rows['SWITCH'].append({'Switch_ID':'s','Switch_NormalState':'Open'})
    elif mode=='explicit': rows['SWITCH'][0]['Switch_FromBus']='st'
    else: rows['LINE'].append(dict(rows['LINE'][1]))
    result=run(rows)
    assert result.coverage.exclusion_reasons[reason]
    assert result.coverage.counts['switch_projected']==0
    assert not result.coverage.has_reachable_transformer


@pytest.mark.parametrize('mode,reason', [('from','TRANSFORMER_DIRECTION'), ('two','TRANSFORMER_DEGREE'),
    ('duplicate','IDENTITY_NOT_UNIQUE'), ('conflict','IDENTITY_NOT_UNIQUE'),('explicit','EXPLICIT_ENDPOINT_EVIDENCE')])
def test_transformer_exclusions(mode,reason):
    rows=fixture()
    if mode=='from': rows['LINE'][1].update(Line_FromBus='t',Line_ToBus='s')
    elif mode=='two': rows['LINE'].append({'Line_ID':'c','Line_FromBus':'missing','Line_ToBus':'t'})
    elif mode=='duplicate': rows['TRANSFORMER']*=2
    elif mode=='conflict': rows['TRANSFORMER'].append({'Transformer_ID':'t','Transformer_RatedCapacity_kVA':'99'})
    else: rows['TRANSFORMER'][0]['Transformer_ToBus']='lv'
    result=run(rows)
    assert result.coverage.exclusion_reasons[reason]
    assert result.coverage.counts['transformer_projected']==0


def test_unresolved_blocks_projected_transformer():
    rows=fixture(); rows['LINE'][0]['Line_FromBus']='missing'
    result=run(rows)
    assert result.coverage.counts['transformer_projected']==1
    assert not result.coverage.has_reachable_transformer
    assert not result.coverage.usable_subgraph


def test_cycles_and_access_point():
    rows=fixture(); rows['BUS'] += [{'Bus_ID':'j'},{'Bus_ID':'k'}]
    rows['LINE'] += [{'Line_ID':'c','Line_FromBus':'st','Line_ToBus':'j'},
        {'Line_ID':'d','Line_FromBus':'j','Line_ToBus':'k'},
        {'Line_ID':'e','Line_FromBus':'k','Line_ToBus':'j'},
        {'Line_ID':'x','Line_FromBus':'k','Line_ToBus':'ap'}]
    rows['ACCESS_POINT']=[{'AccessPoint_ID':'ap'}]
    result=run(rows)
    assert result.coverage.counts['projected_lines']==5
    assert result.coverage.has_reachable_transformer
    assert result.coverage.counts['access_point_excluded']==1
    assert len(result.topology.branches)==6


def test_no_line_and_simconfig_conflict():
    rows=fixture(); rows['LINE']=[]
    rows['SIM_CONFIG']=[{'Config_Key':'BaseVoltage_kV','Config_Value':'110'}]
    result=run(rows)
    assert result.topology.feeder_head_id
    assert not result.coverage.usable_subgraph
    assert result.coverage.exclusion_reasons['SIM_CONFIG_VOLTAGE_CONFLICT']==1


def test_persistence_roundtrip_and_no_overwrite(tmp_path):
    from grid_case_generator.io.topology_artifacts import write_topology_artifact, read_topology_case, verify_topology_artifact
    result=run(fixture()); output=tmp_path/'e2'
    config=TopologyConfig(Decimal('10.5'))
    write_topology_artifact(output, tmp_path/'e1', 'a'*64, config, [result])
    verified=verify_topology_artifact(output)
    assert read_topology_case(output,result.topology.case_id,verified_artifact=verified)==result
    with pytest.raises(FileExistsError):
        write_topology_artifact(output,tmp_path/'e1','a'*64,config,[result])
    p=output/'cases'/result.topology.case_id/'topology.json'
    p.write_text('{}\n')
    with pytest.raises(ValueError): verify_topology_artifact(output)


def test_artifact_hashseed_and_order(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    code='''from test_topology import fixture, mapped
from dataclasses import replace
import random, sys
from decimal import Decimal
from grid_case_generator.generation.topology import interpret_topology
from grid_case_generator.models.topology import TopologyConfig
from grid_case_generator.io.topology_artifacts import write_topology_artifact
source=mapped(fixture()); random.seed(int(sys.argv[2]))
records=list(source.records); random.shuffle(records)
source=replace(source,records=tuple(records),accounting=tuple(reversed(source.accounting)))
config=TopologyConfig(Decimal('10.5'))
write_topology_artifact(sys.argv[1],sys.argv[1]+'input','a'*64,config,[interpret_topology(source,config)])
'''
    for seed in ('1','999'):
        env=dict(os.environ,PYTHONHASHSEED=seed,PYTHONPATH=str(Path(__file__).parent.resolve()))
        subprocess.run([sys.executable,'-c',code,str(tmp_path/seed),seed],env=env,check=True)
    def snapshot(root): return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert snapshot(tmp_path/'1')==snapshot(tmp_path/'999')


def test_unpublished_evidence_and_row_counts():
    rows=fixture()
    rows['SWITCH'].append({'Switch_ID':'s','Switch_NormalState':'Open'})
    result=run(rows)
    assert result.coverage.counts['source_switch_rows']==2
    assert result.coverage.counts['published_switches']==0
    assert result.coverage.counts['switch_candidates']==1
    assert result.coverage.counts['switch_excluded']==1
    p=next(p for p in result.projections if p.rule_id.value=='SERIES_SWITCH_V1' and p.source_terminal_ref is None)
    assert p.source_entity_ref==p.source_case_ref
    assert len(p.supporting_source_refs)==2


def test_full_audit_uses_only_verified_e1(tmp_path,monkeypatch):
    import csv, io
    from zipfile import ZipFile
    from source_fixture import SCHEMA
    from grid_case_generator.io.nanjing_source.import_pipeline import import_archive
    from grid_case_generator.io.topology_artifacts import audit_source_artifact, verify_topology_artifact, read_topology_case
    archive=tmp_path/'raw.zip'
    with ZipFile(archive,'w') as z:
        for name,rows in [('connected',fixture()),('empty',{}),('invalid',{'LINE':[{'Line_ID':'x','Line_Length_km':'0'}]})]:
            for schema in SCHEMA.files:
                stream=io.StringIO(newline=''); writer=csv.writer(stream); writer.writerow(schema.header)
                for row in rows.get(schema.file_type.value,[]): writer.writerow([row.get(k,'') for k in schema.header])
                z.writestr(name+'/'+schema.filename,stream.getvalue())
    e1=tmp_path/'e1'
    import_archive(archive,e1,imported_at="2026-09-15T00:00:00Z")
    before={str(p.relative_to(e1)):p.read_bytes() for p in e1.rglob('*') if p.is_file()}
    archive.unlink()
    def fail(*args,**kwargs): raise AssertionError('E2 opened a ZIP')
    monkeypatch.setattr(ZipFile,'__init__',fail)
    report=audit_source_artifact(e1,tmp_path/'e2',TopologyConfig(Decimal('10.5')))
    assert report['counts']['total_cases']==3
    assert report['counts']['cases_with_reachable_transformer']==1
    assert report['counts']['canonical_invalid_source_cases']>=1
    verified=verify_topology_artifact(tmp_path/'e2')
    cid=verified.manifest['case_ids'][0]
    read_topology_case(tmp_path/'e2',cid,verified_artifact=verified)
    assert before=={str(p.relative_to(e1)):p.read_bytes() for p in e1.rglob('*') if p.is_file()}
    audit_source_artifact(e1,tmp_path/'single',TopologyConfig(Decimal('10.5')),case_id=cid)
    assert read_topology_case(tmp_path/'single',cid)==read_topology_case(tmp_path/'e2',cid,verified_artifact=verified)


def test_unpublished_line_accountability():
    rows=fixture(); rows['LINE'].append(dict(rows['LINE'][0], Line_ToBus='other'))
    result=run(rows)
    assert result.coverage.counts['source_line_rows']==3
    assert result.coverage.counts['published_lines']==1
    assert result.coverage.counts['unpublished_line_rows']==2
    assert result.coverage.counts['unpublished_line_groups']==1
    assert not result.coverage.has_reachable_transformer


def test_id_exact_contract():
    import hashlib,json
    for role in DerivedRole:
        kind,port=role.value.split('/')
        expected=hashlib.sha256(json.dumps(['nanjing-derived-topology-id-v1',kind,'case','甲',port],
            ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        assert DerivedIdFactory.make(role,'case','甲')==kind+':'+expected


def test_all_rule_mappings_have_consistent_exclusions():
    from grid_case_generator.models.topology import ProjectionStatus
    rows=fixture(); rows['LINE'][0]['Line_FromBus']='unknown'
    for p in run(rows).projections:
        if p.projection_status is ProjectionStatus.PROJECTED:
            assert p.derived_target_ids and p.exclusion_reason is None
        else:
            assert p.derived_target_ids==() and p.exclusion_reason
        assert p.supporting_source_refs==tuple(sorted(set(p.supporting_source_refs)))


@pytest.mark.parametrize('mode', ['missing','unresolved','duplicate'])
def test_station_chain_requires_exact_unique_bus_station(mode):
    rows=fixture()
    if mode=='missing': rows['BUS'][0]['Bus_Station_ID']=''
    elif mode=='unresolved': rows['BUS'][0]['Bus_Station_ID']='absent'
    else: rows['STATION']*=2
    result=run(rows)
    assert result.topology.feeder_head_id
    assert not result.coverage.usable_subgraph
    assert not result.coverage.has_reachable_transformer


def test_malformed_line_evidence_prevents_degree_certification():
    source=mapped(fixture())
    accounts=list(source.accounting)
    index=next(i for i,a in enumerate(accounts) if a.raw_record.source_file_type.value=='LINE')
    accounts[index]=replace(accounts[index],raw_record=replace(accounts[index].raw_record,fields=None))
    result=interpret_topology(replace(source,accounting=tuple(accounts)),TopologyConfig(Decimal('10.5')))
    assert result.coverage.counts['switch_projected']==0
    assert result.coverage.counts['transformer_projected']==0
    assert result.coverage.exclusion_reasons['INCOMPLETE_LINE_EVIDENCE']


def test_output_must_be_separate_from_input(tmp_path):
    from grid_case_generator.io.topology_artifacts import write_topology_artifact
    config=TopologyConfig(Decimal('10.5'))
    for source,output in [(tmp_path/'e1',tmp_path/'e1'),(tmp_path/'e1',tmp_path/'e1'/'e2'),(tmp_path/'e1'/'input',tmp_path/'e1')]:
        with pytest.raises(ValueError): write_topology_artifact(output,source,'a'*64,config,[])
    assert not (tmp_path/'e1').exists()


def test_projection_validation():
    projection=run(fixture()).projections[0]
    with pytest.raises(ValueError): replace(projection,derived_target_ids=())
    with pytest.raises(ValueError): replace(projection,supporting_source_refs=('z','a','a'))
    with pytest.raises(ValueError): replace(projection,nominal_voltage_kv=Decimal('NaN'))


def test_validation_rejects_inconsistent_reachability_and_reports():
    from grid_case_generator.validation.topology import validate_topology
    result=run(fixture('OPEN'))
    transformer=next(n.source_entity_ref.entity_id for n in result.topology.nodes if n.role is DerivedRole.TRANSFORMER_MV)
    with pytest.raises(ValueError):
        validate_topology(replace(result,topology=replace(result.topology,reachable_transformer_ids=(transformer,))))
    with pytest.raises(ValueError):
        validate_topology(replace(result,coverage=replace(result.coverage,has_reachable_transformer=True)))


@pytest.mark.parametrize('case,owner', [(123,'owner'),('case',123),(None,'owner'),('case',None)])
def test_id_requires_string_identity(case,owner):
    with pytest.raises(TypeError): DerivedIdFactory.make(DerivedRole.FEEDER_HEAD,case,owner)
