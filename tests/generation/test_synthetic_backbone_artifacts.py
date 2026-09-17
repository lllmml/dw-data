from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from test_synthetic_backbone import case
from grid_case_generator.io.synthetic_backbone_artifacts import write_artifact, verify_artifact


def test_replay_and_rehashed_tamper(tmp_path):
    root=tmp_path/'artifact'; write_artifact([case()],root,{'fixture':'a'*64})
    assert verify_artifact(root)['verified']
    p=root/'summary.json'; data=json.loads(p.read_text());data['proposal_edges']+=1
    from grid_case_generator.io.canonical_json import canonical_json_bytes
    from hashlib import sha256
    p.write_bytes(canonical_json_bytes(data)+b'\n')
    m=json.loads((root/'manifest.json').read_text());m['files']['summary.json']['sha256']=sha256(p.read_bytes()).hexdigest()
    (root/'manifest.json').write_bytes(canonical_json_bytes(m)+b'\n')
    with pytest.raises(ValueError,match='replay'):verify_artifact(root)


def test_no_overwrite(tmp_path):
    root=tmp_path/'artifact';write_artifact([case()],root,{'fixture':'a'*64})
    with pytest.raises(FileExistsError):write_artifact([case()],root,{'fixture':'a'*64})


def test_hash_seed_independent(tmp_path):
    source=tmp_path/'case.json';source.write_text(json.dumps(case()))
    script='from pathlib import Path; import json,sys; from grid_case_generator.io.synthetic_backbone_artifacts import write_artifact; write_artifact([json.loads(Path(sys.argv[1]).read_text())],Path(sys.argv[2]),{"fixture":"a"*64})'
    for seed in ('1','999'):
        subprocess.run([sys.executable,'-c',script,str(source),str(tmp_path/seed)],env=dict(os.environ,PYTHONHASHSEED=seed),check=True)
    for p in (tmp_path/'1').iterdir():assert p.read_bytes()==(tmp_path/'999'/p.name).read_bytes()


def test_authoritative_snapshot_tamper(tmp_path):
    root=tmp_path/'artifact';write_artifact([case()],root,{'fixture':'a'*64})
    changed=deepcopy(case());changed['accepted']['nominal_voltage_kv']='20'
    with pytest.raises(ValueError,match='authoritative'):verify_artifact(root,cases=[changed])


def test_stale_accepted_binding(tmp_path):
    root=tmp_path/'artifact';write_artifact([case()],root,{'accepted_v2':'a'*64})
    with pytest.raises(ValueError,match='binding'):
        verify_artifact(root,expected_bindings={'accepted_v2':'b'*64})


def test_source_tamper_fails_checksum(tmp_path):
    root=tmp_path/'artifact';write_artifact([case()],root,{'source':'a'*64})
    p=root/'case_inputs.jsonl';p.write_text(p.read_text().replace('bus-row','tampered'))
    with pytest.raises(ValueError,match='checksum'):verify_artifact(root)


def test_counterfactual_tamper_rehashed(tmp_path):
    from hashlib import sha256
    from grid_case_generator.io.canonical_json import canonical_json_bytes
    root=tmp_path/'artifact';write_artifact([case()],root,{'fixture':'a'*64})
    p=root/'d2_eligibility_counterfactual.jsonl';r=json.loads(p.read_text());r['after']['synthetic_candidate_count']=999
    p.write_bytes(canonical_json_bytes(r)+b'\n')
    m=json.loads((root/'manifest.json').read_text());m['files'][p.name]['sha256']=sha256(p.read_bytes()).hexdigest()
    (root/'manifest.json').write_bytes(canonical_json_bytes(m)+b'\n')
    with pytest.raises(ValueError,match='replay'):verify_artifact(root)
