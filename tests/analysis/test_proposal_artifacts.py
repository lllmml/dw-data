import json
from hashlib import sha256
import pytest
from test_topology_proposals import case_input
from grid_case_generator.io.proposal_artifacts import write_proposal_artifact, verify_proposal_artifact, INPUTS
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.models.proposals import DECISION_SCHEMA


def artifact(tmp_path):
    roots={k:tmp_path/k for k in INPUTS}
    for p in roots.values():p.mkdir()
    checks={k:'a'*64 for k in INPUTS}
    policy={'schema_version':DECISION_SCHEMA,'decision_version':'1.0.0',
            'input_manifest_sha256':{k:checks[k] for k in ('source','d1')},'decisions':[]}
    out=tmp_path/'proposal'
    write_proposal_artifact(out,roots,checks,policy,[case_input()])
    return out


def rehash(root,name):
    m=json.loads((root/'manifest.json').read_text());data=(root/name).read_bytes()
    m['files'][name]={'sha256':sha256(data).hexdigest(),'record_count':len(data.splitlines())}
    (root/'manifest.json').write_bytes(canonical_json_bytes(m)+b'\n')


def test_detail_rebuild_and_no_apply(tmp_path):
    out=artifact(tmp_path)
    assert verify_proposal_artifact(out)['applied_objects']==0
    rows=[json.loads(x) for x in (out/'proposal_edges.jsonl').read_text().splitlines()]
    rows[0]['b']='invented'
    (out/'proposal_edges.jsonl').write_bytes(b''.join(canonical_json_bytes(r)+b'\n' for r in rows))
    rehash(out,'proposal_edges.jsonl')
    with pytest.raises(ValueError,match='rebuild'):verify_proposal_artifact(out)


def test_summary_cannot_be_rehashed_to_fake_coverage(tmp_path):
    out=artifact(tmp_path);p=out/'summary.json';s=json.loads(p.read_text());s['applied_objects']=1
    p.write_bytes(canonical_json_bytes(s)+b'\n');rehash(out,'summary.json')
    with pytest.raises(ValueError,match='summary'):verify_proposal_artifact(out)


def test_hash_seed_independent_artifact(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    code='from pathlib import Path; from test_proposal_artifacts import artifact; import sys; p=Path(sys.argv[1]); p.mkdir(); artifact(p)'
    for name,seed in [('one','1'),('two','999')]:
        subprocess.run([sys.executable,'-c',code,str(tmp_path/name)],check=True,
                       env=dict(os.environ,PYTHONHASHSEED=seed,PYTHONPATH=str(Path(__file__).parent.resolve())))
    snapshot=lambda p:{f.name:f.read_bytes() for f in p.iterdir()}
    assert snapshot(tmp_path/'one'/'proposal')==snapshot(tmp_path/'two'/'proposal')


def test_case_input_schema_cannot_hide_applied_payload(tmp_path):
    out=artifact(tmp_path);p=out/'case_inputs.jsonl';c=json.loads(p.read_text());c['applied_topology']={}
    p.write_bytes(canonical_json_bytes(c)+b'\n');rehash(out,p.name)
    with pytest.raises(ValueError,match='input schema'):verify_proposal_artifact(out)
