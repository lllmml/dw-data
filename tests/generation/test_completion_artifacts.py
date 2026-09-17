import json
import os
from pathlib import Path
import subprocess
import sys
from hashlib import sha256

import pytest
from test_completion_profiles import profile
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.completion_artifacts import write_completion_artifact, verify_completion_artifact


def write(path):
    roots = {k:str(path)+'_'+k for k in ('source','baseline','projection','feeder','recovery')}
    return write_completion_artifact(path, roots, {k:'a'*64 for k in roots}, [profile()])


def test_artifact_verifier_recomputes_all_streams(tmp_path):
    out = tmp_path/'out'; s = write(out)
    m = verify_completion_artifact(out)
    assert m['synthetic_objects_created'] == 0 and m['accepted_topology_changed'] is False
    assert s['feeder_count'] == sum(s['primary_action_cohorts'].values()) == 1
    assert m['files']['operation_eligibility.jsonl']['record_count'] == 6
    assert s['conservative_synthetic_eligible'] == 0


def test_checksum_and_rehashed_decision_tamper(tmp_path):
    out=tmp_path/'out'; write(out)
    p=out/'synthetic_eligibility.jsonl'; old=p.read_bytes();p.write_bytes(old+b'\n')
    with pytest.raises(ValueError):verify_completion_artifact(out)
    value=json.loads(old);value['stage']='APPLIED';p.write_bytes(canonical_json_bytes(value)+b'\n')
    mp=out/'manifest.json';m=json.loads(mp.read_text());m['files'][p.name]['sha256']=sha256(p.read_bytes()).hexdigest()
    mp.write_bytes(canonical_json_bytes(m)+b'\n')
    with pytest.raises(ValueError,match='decision|stream'):verify_completion_artifact(out)


def test_isolation_and_forbidden_topology_inventory(tmp_path):
    out=tmp_path/'out';write(out)
    with pytest.raises(FileExistsError):write(out)
    with pytest.raises(ValueError):write_completion_artifact(tmp_path/'source'/'child',{'source':tmp_path/'source'},{},[])
    (out/'topology.json').write_text('{}')
    with pytest.raises(ValueError,match='inventory'):verify_completion_artifact(out)


def test_hash_seed_independent_artifact(tmp_path):
    code='from pathlib import Path; from test_completion_artifacts import write; import sys; write(Path(sys.argv[1]))'
    for name, seed in [('a','1'),('b','999')]:
        env=dict(os.environ,PYTHONHASHSEED=seed,PYTHONPATH=str(Path(__file__).parent.resolve()))
        subprocess.run([sys.executable,'-c',code,str(tmp_path/name)],env=env,check=True)
    snapshot=lambda p:{f.name:f.read_bytes() for f in p.iterdir()}
    assert snapshot(tmp_path/'a') == snapshot(tmp_path/'b')


def test_no_feeder_case_retained(tmp_path):
    from test_switch_semantics import fixture
    rows=fixture();rows['FEEDER']=[]
    out=tmp_path/'out';s=write_completion_artifact(out,{'source':tmp_path/'source'},{'source':'a'*64},[profile(rows)])
    assert s['case_count']==s['cases_without_feeder']==1 and s['feeder_count']==0
    verify_completion_artifact(out)


def test_full_pipeline_inputs_immutable_and_bound_verification(tmp_path):
    import csv
    import io
    from decimal import Decimal
    from zipfile import ZipFile
    from source_fixture import SCHEMA
    from test_switch_semantics import fixture
    from grid_case_generator.io.nanjing_source.import_pipeline import import_archive
    from grid_case_generator.io.topology_artifacts import audit_source_artifact
    from grid_case_generator.io.switch_projection_artifacts import run_projection_analysis
    from grid_case_generator.analysis.switch_projection_proposal import render_proposal
    from grid_case_generator.io.feeder_coverage_artifacts import run_feeder_analysis
    from grid_case_generator.analysis.feeder_coverage_cli import render_report
    from grid_case_generator.io.topology_recovery_artifacts import run_recovery_analysis
    from grid_case_generator.io.completion_artifacts import run_completion_analysis, verify_completion_inputs
    from grid_case_generator.models.topology import TopologyConfig
    archive=tmp_path/'fixture.zip'; rows=fixture()
    rows['TRANSFORMER'].append({'Transformer_ID':'orphan'})
    with ZipFile(archive,'w') as z:
        for case,data in [('ordinary',rows),('empty',{})]:
            for schema in SCHEMA.files:
                stream=io.StringIO(newline='');writer=csv.writer(stream);writer.writerow(schema.header)
                for row in data.get(schema.file_type.value,[]):writer.writerow([row.get(k,'') for k in schema.header])
                z.writestr(case+'/'+schema.filename,stream.getvalue())
    roots={k:tmp_path/k for k in ('source','baseline','projection','feeder','recovery')}
    import_archive(archive,roots['source'],imported_at='2026-09-17T00:00:00Z')
    audit_source_artifact(roots['source'],roots['baseline'],TopologyConfig(Decimal('10.5')))
    run_projection_analysis(roots['source'],roots['baseline'],roots['projection'],render_proposal)
    run_feeder_analysis(roots['source'],roots['baseline'],roots['projection'],roots['feeder'],render_report)
    run_recovery_analysis(roots['source'],roots['baseline'],roots['projection'],roots['feeder'],roots['recovery'])
    snapshot=lambda root:{str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    before={k:snapshot(p) for k,p in roots.items()}
    for name in ('out','repeat'):
        s=run_completion_analysis(roots,tmp_path/name)
        assert s['case_count']==2 and s['feeder_count']==1
        verify_completion_artifact(tmp_path/name,roots)
    assert snapshot(tmp_path/'out')==snapshot(tmp_path/'repeat')
    assert before=={k:snapshot(p) for k,p in roots.items()}
    # Even a checksum-consistent changed profile cannot masquerade as input evidence.
    p=tmp_path/'out'/'case_profiles.jsonl';values=[json.loads(line) for line in p.read_text().splitlines()]
    values[0]['source']['row_counts']['LOAD']=123
    p.write_bytes(b''.join(canonical_json_bytes(v)+b'\n' for v in values))
    mp=tmp_path/'out'/'manifest.json';m=json.loads(mp.read_text());m['files'][p.name]['sha256']=sha256(p.read_bytes()).hexdigest()
    mp.write_bytes(canonical_json_bytes(m)+b'\n')
    with pytest.raises(ValueError,match='authoritative'):verify_completion_artifact(tmp_path/'out',roots)
    m=json.loads((roots['recovery']/'manifest.json').read_text());m['input_manifest_sha256']['source']='b'*64
    (roots['recovery']/'manifest.json').write_bytes(canonical_json_bytes(m)+b'\n')
    with pytest.raises(ValueError,match='binding'):verify_completion_inputs(roots)


def test_rehashed_profile_cannot_contain_topology_payload(tmp_path):
    out=tmp_path/'out';write(out)
    p=out/'case_profiles.jsonl';r=json.loads(p.read_text());r['applied_topology']={'branches':[]}
    p.write_bytes(canonical_json_bytes(r)+b'\n')
    mp=out/'manifest.json';m=json.loads(mp.read_text());m['files'][p.name]['sha256']=sha256(p.read_bytes()).hexdigest()
    mp.write_bytes(canonical_json_bytes(m)+b'\n')
    with pytest.raises(ValueError,match='profile schema'):verify_completion_artifact(out)
