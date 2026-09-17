from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from test_deterministic_recovery import prepare
from test_switch_semantics import fixture
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.deterministic_recovery_artifacts import (
    INPUTS, write_artifacts, verify_artifacts, check_paths,
)


def bindings():
    return {k:'a'*64 for k in INPUTS}


def setup_artifact(tmp_path):
    _, _, c = prepare(fixture())
    a, v = tmp_path/'analysis', tmp_path/'accepted'
    write_artifacts([c], a, v, bindings())
    return a, v


def rehash(a, name):
    mp = a/'manifest.json'; m = json.loads(mp.read_text()); data = (a/name).read_bytes()
    m['files'][name] = {'sha256':sha256(data).hexdigest(), 'record_count':len(data.splitlines())}
    mp.write_bytes(canonical_json_bytes(m)+b'\n')


def rebind(a,v):
    m = json.loads((v/'manifest.json').read_text())
    m['analysis_manifest_sha256'] = sha256((a/'manifest.json').read_bytes()).hexdigest()
    (v/'manifest.json').write_bytes(canonical_json_bytes(m)+b'\n')


def test_replay_summary_and_graph(tmp_path):
    a,v = setup_artifact(tmp_path)
    assert verify_artifacts(a,v)['verified']
    summary = json.loads((a/'summary.json').read_text())
    assert summary['new_accepted_deterministic_edges'] == 3
    assert summary['new_rule_generated_objects'] == 0
    with pytest.raises(FileExistsError): write_artifacts([],a,v,bindings())


@pytest.mark.parametrize('name', ['candidate_connections.jsonl','case_coverage.jsonl','summary.json','d2_eligibility.jsonl'])
def test_rehashed_detail_tamper_fails(tmp_path, name):
    a,v = setup_artifact(tmp_path)
    lines = (a/name).read_text().splitlines(); r = json.loads(lines[0]); r['tampered'] = True
    lines[0] = canonical_json_bytes(r).decode()
    (a/name).write_text('\n'.join(lines)+'\n'); rehash(a,name); rebind(a,v)
    with pytest.raises(ValueError,match='replay'): verify_artifacts(a,v)


def test_accepted_graph_cannot_import_synthetic(tmp_path):
    a,v = setup_artifact(tmp_path)
    p = v/'additions.jsonl'; rows = list(map(json.loads,p.read_text().splitlines()))
    rows[0]['evidence_class'] = 'RULE_GENERATED'
    p.write_bytes(b''.join(canonical_json_bytes(r)+b'\n' for r in rows)); rehash(v,p.name)
    with pytest.raises(ValueError,match='replay'): verify_artifacts(a,v)


def test_manifest_binding_tamper(tmp_path):
    a,v = setup_artifact(tmp_path)
    m = json.loads((v/'manifest.json').read_text()); m['input_manifest_sha256']['source'] = 'b'*64
    (v/'manifest.json').write_bytes(canonical_json_bytes(m)+b'\n')
    with pytest.raises(ValueError,match='binding'): verify_artifacts(a,v)


def test_authoritative_evidence_tamper(tmp_path,monkeypatch):
    import grid_case_generator.io.deterministic_recovery_artifacts as io
    a,v = setup_artifact(tmp_path)
    c = json.loads((a/'case_inputs.jsonl').read_text()); c['base']['source_line_count'] += 1
    monkeypatch.setattr(io,'verify_inputs',lambda roots:bindings())
    monkeypatch.setattr(io,'iter_inputs',lambda roots:iter([c]))
    monkeypatch.setattr(io,'policy_map',lambda roots:{})
    with pytest.raises(ValueError,match='authoritative'): verify_artifacts(a,v,{'fixture':tmp_path})


def test_output_isolation(tmp_path):
    for output in (tmp_path/'source',tmp_path/'source'/'nested',tmp_path):
        with pytest.raises(ValueError): check_paths({'source':tmp_path/'source'},output,tmp_path/'v2')
    with pytest.raises(ValueError): check_paths({},tmp_path/'data'/'raw'/'d3',tmp_path/'v2')
    with pytest.raises(ValueError): check_paths({},tmp_path/'a',tmp_path/'a'/'v2')


def test_hash_seed_byte_identical(tmp_path):
    _, _, c = prepare(fixture())
    path=tmp_path/'input.json'; path.write_bytes(canonical_json_bytes(c))
    script='''
import json,sys
from pathlib import Path
from grid_case_generator.io.deterministic_recovery_artifacts import INPUTS,write_artifacts,verify_artifacts
c=json.loads(Path(sys.argv[1]).read_text()); root=Path(sys.argv[2])
write_artifacts([c],root/'analysis',root/'accepted',{k:'a'*64 for k in INPUTS})
verify_artifacts(root/'analysis',root/'accepted')
'''
    for seed in ('1','999'):
        subprocess.run([sys.executable,'-c',script,str(path),str(tmp_path/seed)],env=dict(os.environ,PYTHONHASHSEED=seed),check=True)
    snapshot=lambda root:{str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert snapshot(tmp_path/'1')==snapshot(tmp_path/'999')


def test_no_device_generation_and_d2_equivalence():
    from grid_case_generator.analysis.deterministic_recovery import eligibility
    from grid_case_generator.analysis.topology_proposals import propose_case
    rows=fixture(); rows['TRANSFORMER'].append({'Transformer_ID':'orphan'})
    _,_,c=prepare(rows); base=c['base']
    one=eligibility(base)[0]; original=propose_case(base,{},'fixture')
    assert one['primary_class']==original['feeder_eligibility'][0]['primary_class']
    assert one['synthetic_candidate_count']==len(original['proposal_bundles'])
    base['base_edges']=[]
    one=eligibility(base)[0]; original=propose_case(base,{},'fixture')
    assert one['primary_class']==original['feeder_eligibility'][0]['primary_class']
    assert one['missing_backbone_or_region_count']==1


def test_bound_full_pipeline_with_empty_case(tmp_path):
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
    from grid_case_generator.io.topology_recovery_artifacts import run_recovery_analysis
    from grid_case_generator.io.completion_artifacts import run_completion_analysis
    from grid_case_generator.io.proposal_artifacts import run_proposal_analysis, verify_proposal_inputs
    from grid_case_generator.models.proposals import DECISION_SCHEMA, decision_bytes
    from grid_case_generator.models.topology import TopologyConfig
    from grid_case_generator.io.deterministic_recovery_artifacts import run_recovery
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
    run_completion_analysis(roots,tmp_path/'d1');roots['d1']=tmp_path/'d1'
    checks=verify_proposal_inputs(roots)
    policy={'schema_version':DECISION_SCHEMA,'decision_version':'1.0.0',
        'input_manifest_sha256':{k:checks[k] for k in ('source','d1')},'decisions':[]}
    decision=tmp_path/'decisions.json';decision.write_bytes(decision_bytes(policy))
    run_proposal_analysis(roots,decision,tmp_path/'d2')
    roots.update(d2=tmp_path/'d2',frozen=roots['baseline'])
    snapshot=lambda root:{str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    before={k:snapshot(p) for k,p in roots.items()}; raw_before=archive.read_bytes()
    a,v=tmp_path/'d3',tmp_path/'v2'
    result=run_recovery(roots,a,v)
    assert result['case_count']==2 and result['feeder_count']==1
    assert verify_artifacts(a,v,roots)['input_bound']
    assert before=={k:snapshot(p) for k,p in roots.items()}
    assert raw_before==archive.read_bytes()
