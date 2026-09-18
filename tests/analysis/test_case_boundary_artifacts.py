from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.case_boundary_audit import write_artifact, verify_artifact, load_cases


def put(root, name, rows):
    p = root / name; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in rows))


def manifest(root):
    put(root, 'manifest.json', [{'files': {str(p.relative_to(root)): {'sha256': sha256(p.read_bytes()).hexdigest()}
        for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'manifest.json'}}])


def roots_at(tmp_path):
    roots = {k: tmp_path/k for k in ('source','accepted','d3','d4','placement')}
    for root in roots.values(): root.mkdir()
    cases=[]; accepted=[]; d3=[]
    for cid, bus in [('A','HA'), ('B','XB')]:
        cases.append({'source_case_key':'data/'+cid})
        rows=[('BUS', {'Bus_ID':bus,'Bus_BaseKV':'10','Bus_Station_ID':'S'}),
              ('FEEDER', {'Feeder_ID':'F'+cid,'Feeder_Name':'name'+cid,'Feeder_SourceBus':bus}),
              ('STATION', {'Station_ID':'S'})]
        if cid=='A': rows.append(('LINE', {'Line_ID':'L','Line_FromBus':'HA','Line_ToBus':'XB'}))
        accounts=[]; resolutions=[]
        for kind, fields in rows:
            record=cid+':'+kind
            accounts.append({'raw_record': {'source_record_ref':record, 'source_file_type':kind,
                'fields':list(fields.items())}, 'identity_status':'UNIQUE',
                'canonical_ref': {'entity_id':record,'entity_type':kind}})
            for field, value in fields.items():
                if field not in ('Bus_Station_ID','Feeder_SourceBus','Line_FromBus','Line_ToBus'):continue
                path = ('terminal[2].raw_connected_ref' if field=='Line_ToBus' else
                        'terminal[1].raw_connected_ref' if field=='Line_FromBus' else field)
                resolutions.append({'request':{'owner_source_record_ref':record,'raw_reference_value':value,
                    'reference_field_path':path},'resolution_status':'UNRESOLVED' if field=='Line_ToBus' else 'EXACT'})
        prefix='cases/'+cid+'/'
        put(roots['source'],prefix+'records/GridCase.jsonl',[{'case_id':cid,'source_case_key':'data/'+cid}])
        put(roots['source'],prefix+'row_accountability.jsonl',accounts)
        put(roots['source'],prefix+'resolutions.jsonl',resolutions)
        accepted.append({'case_id':cid,'hard_blockers':[], 'base_nodes':[
            {'node_id':'j'+cid,'case_id':cid,'kind':'JUNCTION','transformer_key':None},
            {'node_id':'h'+cid,'case_id':cid,'kind':'HEAD','transformer_key':None}],
            'base_edges':[],'head_id':'h'+cid,'region_source_refs':{'j'+cid:[cid+':BUS']},'targets':[]})
        d3.append({'base':{'case_id':cid},'projections':[], 'terminals':[]})
    put(roots['source'],'inventory.json',[{'cases':cases}])
    put(roots['accepted'],'case_topologies.jsonl',accepted)
    put(roots['d3'],'case_inputs.jsonl',d3)
    put(roots['d4'],'feeder_gap_taxonomy.jsonl',[])
    put(roots['placement'],'target_feeders.jsonl',[])
    for root in roots.values():manifest(root)
    return roots


def test_source_bound_artifact_rebuild_and_no_mutation(tmp_path):
    roots=roots_at(tmp_path)
    before={str(p):p.read_bytes() for root in roots.values() for p in root.rglob('*') if p.is_file()}
    output=tmp_path/'audit'
    summary=write_artifact(roots,output)
    assert summary['cross_case_reference_count']==1
    assert verify_artifact(roots,output)['input_bound']
    assert before=={str(p):p.read_bytes() for root in roots.values() for p in root.rglob('*') if p.is_file()}
    impact=json.loads((output/'counterfactual_impact.json').read_text())
    assert impact['line_endpoint_identity_resolution_count']==1
    assert impact['line_representation_count']==1
    assert impact['topology_written'] is False and impact['proposal_created'] is False
    with pytest.raises(FileExistsError):write_artifact(roots,output)


def test_manifest_tamper_fails(tmp_path):
    roots=roots_at(tmp_path); output=tmp_path/'audit';write_artifact(roots,output)
    m=json.loads((output/'manifest.json').read_text());m['files']['summary.json']['sha256']='0'*64
    put(output,'manifest.json',[m])
    with pytest.raises(ValueError,match='manifest checksum'):verify_artifact(roots,output)


def test_source_binding_tamper_fails(tmp_path):
    roots=roots_at(tmp_path);output=tmp_path/'audit';write_artifact(roots,output)
    path=roots['source']/'cases/A/row_accountability.jsonl'
    path.write_bytes(path.read_bytes().replace(b'"XB"',b'"MISSING"'))
    with pytest.raises(ValueError,match='binding checksum'):verify_artifact(roots,output)
    manifest(roots['source'])
    with pytest.raises(ValueError,match='source binding'):verify_artifact(roots,output)


def test_detail_rehash_still_fails_source_replay(tmp_path):
    roots=roots_at(tmp_path);output=tmp_path/'audit';write_artifact(roots,output)
    p=output/'summary.json';s=json.loads(p.read_text());s['case_count']=99;put(output,'summary.json',[s])
    m=json.loads((output/'manifest.json').read_text());m['files']['summary.json']['sha256']=sha256(p.read_bytes()).hexdigest()
    put(output,'manifest.json',[m])
    with pytest.raises(ValueError,match='replay'):verify_artifact(roots,output)


def test_hash_seed_independence(tmp_path):
    roots=roots_at(tmp_path)
    code='from pathlib import Path;from grid_case_generator.io.case_boundary_audit import write_artifact;import json,sys;write_artifact({k:Path(v) for k,v in json.loads(sys.argv[1]).items()},Path(sys.argv[2]))'
    for seed in ('1','999'):
        subprocess.run([sys.executable,'-c',code,json.dumps({k:str(v) for k,v in roots.items()}),str(tmp_path/seed)],
            env=dict(os.environ,PYTHONHASHSEED=seed),check=True)
    assert {p.name:p.read_bytes() for p in (tmp_path/'1').iterdir()}=={p.name:p.read_bytes() for p in (tmp_path/'999').iterdir()}


def test_local_resolver_not_called_or_modified(tmp_path):
    import grid_case_generator.validation.reference_resolution as resolver
    path=Path(resolver.__file__);before=path.read_bytes()
    roots=roots_at(tmp_path);write_artifact(roots,tmp_path/'audit')
    assert path.read_bytes()==before
    for name in ('case_boundary_audit.py','case_boundary_impact.py'):
        source=(Path('src/grid_case_generator/analysis')/name).read_text()
        assert 'resolve_source_reference(' not in source


def test_invalid_explicit_bus_voltage_is_not_replaced_by_head_voltage(tmp_path):
    roots=roots_at(tmp_path)
    p=roots['source']/'cases/B/row_accountability.jsonl'
    rows=[json.loads(line) for line in p.read_text().splitlines()]
    rows.append({'raw_record': {'source_record_ref':'B:badbus','source_file_type':'BUS',
        'fields':[['Bus_ID','BAD'],['Bus_BaseKV','invalid']]}, 'identity_status':'UNIQUE',
        'canonical_ref': {'entity_id':'B:badbus','entity_type':'BUS'}})
    put(roots['source'],'cases/B/row_accountability.jsonl',rows)
    loaded=load_cases(roots['source'],roots['accepted'])
    bad=[e for c in loaded for e in c['entities'] if e['raw_source_id']=='BAD']
    assert bad[0]['voltage_values']==[]
