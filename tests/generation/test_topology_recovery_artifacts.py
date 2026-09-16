import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from test_topology_recovery import analyze, fixture
from grid_case_generator.io.topology_recovery_artifacts import write_recovery_artifact, verify_recovery_artifact


def write(path):
    roots = {k: str(path)+'_'+k for k in ('source','baseline','projection','feeder')}
    return write_recovery_artifact(path, roots, {k:'a'*64 for k in roots}, [analyze(fixture())])


def test_artifact_verification_and_detail_reaggregation(tmp_path):
    out = tmp_path/'out'; summary = write(out)
    manifest = verify_recovery_artifact(out)
    assert manifest['accepted_topology_changed'] is False
    assert summary['feeder_count'] == 1
    assert summary['target_coverage']['FULL'] == 1
    assert summary['synthetic_connections'] == 0
    assert summary['transformer_reference_composition']['LINE_ONLY'] == 1
    assert manifest['files']['transformer_evidence.jsonl']['record_count'] == 1
    assert manifest['files']['feeder_details.jsonl']['record_count'] == 1
    assert json.loads((out/'summary.json').read_text()) == summary


def test_checksum_tamper_and_extra_file(tmp_path):
    out = tmp_path/'out'; write(out)
    p = out/'transformer_evidence.jsonl'; p.write_bytes(p.read_bytes()+b'\n')
    with pytest.raises(ValueError, match='checksum|count|canonical'): verify_recovery_artifact(out)
    other = tmp_path/'other'; write(other); (other/'extra').write_text('x')
    with pytest.raises(ValueError, match='inventory'): verify_recovery_artifact(other)


def test_reaggregation_rejects_rehashed_false_summary(tmp_path):
    from hashlib import sha256
    from grid_case_generator.io.canonical_json import canonical_json_bytes
    out = tmp_path/'out'; write(out)
    p = out/'summary.json'; summary=json.loads(p.read_text()); summary['feeder_count']+=1
    p.write_bytes(canonical_json_bytes(summary)+b'\n')
    mp=out/'manifest.json'; m=json.loads(mp.read_text());m['files']['summary.json']['sha256']=sha256(p.read_bytes()).hexdigest()
    mp.write_bytes(canonical_json_bytes(m)+b'\n')
    with pytest.raises(ValueError, match='summary'): verify_recovery_artifact(out)


def test_output_isolation_existing_and_symlink(tmp_path):
    out=tmp_path/'out'; write(out)
    with pytest.raises(FileExistsError): write(out)
    for destination in (tmp_path/'source', tmp_path/'source'/'nested', tmp_path):
        with pytest.raises(ValueError):
            write_recovery_artifact(destination, {'source':tmp_path/'source'}, {}, [])
    link=tmp_path/'link';link.symlink_to(tmp_path/'source',target_is_directory=True)
    with pytest.raises(ValueError):write_recovery_artifact(link/'out', {'source':tmp_path/'source'}, {}, [])


def test_cross_process_hashseed_reproduction(tmp_path):
    code = '''from test_topology_recovery_artifacts import write
from pathlib import Path
import sys
write(Path(sys.argv[1]))
'''
    # Input paths do not appear in artifacts; same checksums bind all three runs.
    for name,seed in [('a','1'),('b','999'),('c','1')]:
        env=dict(os.environ,PYTHONHASHSEED=seed,PYTHONPATH=str(Path(__file__).parent.resolve()))
        subprocess.run([sys.executable,'-c',code,str(tmp_path/name)],env=env,check=True)
    snapshot=lambda p:{f.name:f.read_bytes() for f in p.iterdir()}
    assert snapshot(tmp_path/'a')==snapshot(tmp_path/'b')==snapshot(tmp_path/'c')


def test_no_feeder_not_counted_as_fake_feeder(tmp_path):
    rows=fixture();rows['FEEDER']=[]
    out=tmp_path/'out'
    s=write_recovery_artifact(out,{'source':tmp_path/'source'}, {'source':'a'*64}, [analyze(rows)])
    assert s['case_count']==s['cases_without_feeder']==1 and s['feeder_count']==0
    assert s['transformer_reference_composition']=={}
    assert s['all_case_transformer_reference_composition']['LINE_ONLY']==1
    verify_recovery_artifact(out)


def test_full_pipeline_verified_inputs_immutable_and_reproduction(tmp_path, monkeypatch):
    import csv
    import io
    from decimal import Decimal
    from zipfile import ZipFile
    from source_fixture import SCHEMA
    from grid_case_generator.io.nanjing_source.import_pipeline import import_archive
    from grid_case_generator.io.topology_artifacts import audit_source_artifact
    from grid_case_generator.io.switch_projection_artifacts import run_projection_analysis
    from grid_case_generator.analysis.switch_projection_proposal import render_proposal
    from grid_case_generator.io.feeder_coverage_artifacts import run_feeder_analysis
    from grid_case_generator.analysis.feeder_coverage_cli import render_report
    from grid_case_generator.io.topology_recovery_artifacts import run_recovery_analysis, verify_inputs
    from grid_case_generator.models.topology import TopologyConfig
    archive=tmp_path/'fixture.zip'
    rows=fixture(y='orphan');rows['TRANSFORMER'].append({'Transformer_ID':'orphan'})
    with ZipFile(archive,'w') as z:
        for case,data in [('ordinary',rows),('empty',{})]:
            for schema in SCHEMA.files:
                stream=io.StringIO(newline='');writer=csv.writer(stream);writer.writerow(schema.header)
                for row in data.get(schema.file_type.value,[]):writer.writerow([row.get(k,'') for k in schema.header])
                z.writestr(case+'/'+schema.filename,stream.getvalue())
    e1,e2,e22,fc=(tmp_path/name for name in ('e1','e2','e22','fc'))
    import_archive(archive,e1,imported_at='2026-09-16T00:00:00Z');archive.unlink()
    def fail(*args,**kwargs):raise AssertionError('raw source must not be reopened')
    monkeypatch.setattr(ZipFile,'__init__',fail)
    audit_source_artifact(e1,e2,TopologyConfig(Decimal('10.5')))
    run_projection_analysis(e1,e2,e22,render_proposal)
    run_feeder_analysis(e1,e2,e22,fc,render_report)
    snapshot=lambda root:{str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    before=[snapshot(p) for p in (e1,e2,e22,fc)]
    for name in ('out','repeat'):
        s=run_recovery_analysis(e1,e2,e22,fc,tmp_path/name)
        assert s['case_count']==2 and s['feeder_count']==1
        assert s['candidate_rules']['UNIQUE_SWITCH_DECLARED_T_ATTACHMENT_V1']['eligible_feeders']==1
        verify_recovery_artifact(tmp_path/name)
    assert snapshot(tmp_path/'out')==snapshot(tmp_path/'repeat')
    assert before==[snapshot(p) for p in (e1,e2,e22,fc)]
    # Rehashed cross-artifact binding must still fail, independently of file checksums.
    mp=fc/'manifest.json';m=json.loads(mp.read_text());m['input_manifest_sha256']['source']='b'*64;mp.write_text(json.dumps(m))
    with pytest.raises(ValueError,match='binding'):
        verify_inputs({'source':e1,'baseline':e2,'projection':e22,'feeder':fc})
