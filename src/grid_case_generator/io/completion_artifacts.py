"""Isolated D1 eligibility artifacts and semantic/input-bound verification."""
from contextlib import ExitStack
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path

from grid_case_generator.analysis.completion_contract import VERSION, RULE_VERSION
from grid_case_generator.analysis.completion_profiles import build_profile
from grid_case_generator.analysis.completion_summary import STREAMS, CompletionSummary, profile_records, render_report
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.source_artifacts import SourceArtifactWriter, _artifact_root, _artifact_member
from grid_case_generator.io.switch_projection_artifacts import check_output
from grid_case_generator.io.topology_recovery_artifacts import verify_inputs, verify_recovery_artifact, code_fingerprint

FILES = {'case_profiles.jsonl','summary.json','report.md',*(name+'.jsonl' for name in STREAMS)}
INPUTS = {'source','baseline','projection','feeder','recovery'}


def verify_completion_inputs(roots):
    if set(roots) != INPUTS: raise ValueError('five D1 input roots required')
    checks = verify_inputs({k:v for k,v in roots.items() if k!='recovery'})[-1]
    recovery = verify_recovery_artifact(roots['recovery'])
    if recovery['input_manifest_sha256'] != checks: raise ValueError('recovery input binding mismatch')
    return dict(checks, recovery=sha256((Path(roots['recovery'])/'manifest.json').read_bytes()).hexdigest())


def iter_completion_profiles(roots):
    """Called only after input verification; stream one source case at a time."""
    recovery=Path(roots['recovery'])
    names={'feeders':'feeder_details.jsonl','transformers':'transformer_evidence.jsonl',
           'connections':'connection_evidence.jsonl','blockers':'frontier_blockers.jsonl'}
    with ExitStack() as stack:
        groups={key:iter(groupby((json.loads(line) for line in stack.enter_context((recovery/name).open())),
                                key=lambda r:r['case_id'])) for key,name in names.items()}
        current={key:next(g,(None,())) for key,g in groups.items()}
        cases=stack.enter_context((recovery/'case_details.jsonl').open())
        projection=stack.enter_context((Path(roots['projection'])/'case_results.jsonl').open())
        feeder=stack.enter_context((Path(roots['feeder'])/'case_details.jsonl').open())
        previous=None
        for line in cases:
            case=json.loads(line);cid=case['case_id']
            if previous is not None and cid<=previous:raise ValueError('input case order')
            previous=cid
            records={}
            for key,g in groups.items():
                rid,rs=current[key]
                records[key]=list(rs) if rid==cid else []
                if rid==cid:current[key]=next(g,(None,()))
            case['feeders']=records['feeders']
            pc=json.loads(next(projection));fc=json.loads(next(feeder))
            if pc['case_id']!=cid or fc['case_id']!=cid:raise ValueError('input case inventory mismatch')
            for policy in ('S0','S2'):
                h=case['graphs'][policy]['graph_sha256']
                if pc['strategies'][policy]['graph_sha256']!=h or fc['policies'][policy]['graph_sha256']!=h:
                    raise ValueError('input graph binding mismatch')
            source_path=_artifact_member(Path(roots['source']),'cases/'+cid+'/row_accountability.jsonl')
            accounts=[json.loads(line) for line in source_path.open()]
            top=json.loads(_artifact_member(Path(roots['baseline']),'cases/'+cid+'/topology.json').read_text())
            yield build_profile(case,accounts,top,records['transformers'],records['connections'],records['blockers'])
        if any(cid is not None for cid,_ in current.values()) or next(projection,None) or next(feeder,None):
            raise ValueError('unconsumed input detail cases')


def write_completion_artifact(output, roots, checksums, profiles):
    check_output(output,roots)
    writer=SourceArtifactWriter(output,roots['source']);summary=CompletionSummary()
    with ExitStack() as stack:
        names=['case_profiles',*STREAMS]
        streams={name:stack.enter_context((writer.root/(name+'.jsonl')).open('xb')) for name in names}
        digests={name:sha256() for name in names};counts={name:0 for name in names}
        def emit(name,value):
            data=canonical_json_bytes(value)+b'\n';streams[name].write(data);digests[name].update(data);counts[name]+=1
        previous=None
        for profile in profiles:
            if previous is not None and profile['case_id']<=previous:raise ValueError('profile case order')
            previous=profile['case_id'];summary.add(profile);emit('case_profiles',profile)
            for name,rs in profile_records(profile).items():
                for row in rs:emit(name,row)
        for name in names:writer.entries[name+'.jsonl']={'sha256':digests[name].hexdigest(),'record_count':counts[name]}
    report=summary.finish();writer.write('summary.json',report)
    data=render_report(report).encode('utf-8');(writer.root/'report.md').write_bytes(data)
    writer.entries['report.md']={'sha256':sha256(data).hexdigest(),'record_count':len(data.splitlines())}
    manifest={'contract_version':VERSION,'schema_version':'1.0.0','rule_version':RULE_VERSION,
        'input_manifest_sha256':checksums,'code_sha256':code_fingerprint(),
        'case_count':report['case_count'],'feeder_count':report['feeder_count'],
        'synthetic_objects_created':0,'accepted_topology_changed':False,'s2_accepted':False,
        'e3_authorized':False,'files':dict(sorted(writer.entries.items()))}
    (writer.root/'manifest.json').write_bytes(canonical_json_bytes(manifest)+b'\n')
    return report


def verify_completion_artifact(root, roots=None):
    root=_artifact_root(root);mp=_artifact_member(root,'manifest.json');manifest=json.loads(mp.read_text())
    if (manifest['contract_version']!=VERSION or manifest['schema_version']!='1.0.0'
        or manifest['rule_version']!=RULE_VERSION or manifest['synthetic_objects_created']!=0
        or manifest['accepted_topology_changed'] is not False or manifest['s2_accepted'] is not False
        or manifest['e3_authorized'] is not False):raise ValueError('D1 schema/boundary mismatch')
    observed={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p!=mp}
    if observed!=FILES or set(manifest['files'])!=FILES:raise ValueError('D1 inventory mismatch')
    for name,entry in manifest['files'].items():
        digest=sha256();count=0
        with _artifact_member(root,name).open('rb') as stream:
            for line in stream:
                digest.update(line);count+=1
                if name.endswith(('.json','.jsonl')) and canonical_json_bytes(json.loads(line))+b'\n'!=line:
                    raise ValueError('noncanonical D1 stream')
        if digest.hexdigest()!=entry['sha256'] or count!=entry['record_count']:
            raise ValueError('D1 checksum/count mismatch: '+name)
    if roots is not None and verify_completion_inputs(roots)!=manifest['input_manifest_sha256']:
        raise ValueError('D1 input binding mismatch')
    authoritative=iter(iter_completion_profiles(roots)) if roots is not None else None
    summary=CompletionSummary()
    with ExitStack() as stack:
        streams={name:stack.enter_context((root/(name+'.jsonl')).open()) for name in STREAMS}
        cases=stack.enter_context((root/'case_profiles.jsonl').open())
        previous=None
        for line in cases:
            p=json.loads(line)
            if previous is not None and p['case_id']<=previous:raise ValueError('profile case order')
            previous=p['case_id']
            if authoritative is not None and canonical_json_bytes(p)!=canonical_json_bytes(next(authoritative,None)):
                raise ValueError('profile does not reproduce authoritative inputs')
            summary.add(p)
            for name,expected in profile_records(p).items():
                for row in expected:
                    actual=next(streams[name],None)
                    if actual is None or canonical_json_bytes(row)!=canonical_json_bytes(json.loads(actual)):
                        raise ValueError('D1 decision stream mismatch: '+name)
        if any(next(s,None) is not None for s in streams.values()):raise ValueError('extra D1 decision stream records')
    if authoritative is not None and next(authoritative,None) is not None:raise ValueError('missing D1 input case')
    s=summary.finish()
    if canonical_json_bytes(s)!=canonical_json_bytes(json.loads((root/'summary.json').read_text())):
        raise ValueError('D1 summary does not reproduce details')
    if render_report(s)!=(root/'report.md').read_text():raise ValueError('D1 report mismatch')
    if manifest['case_count']!=s['case_count'] or manifest['feeder_count']!=s['feeder_count']:
        raise ValueError('D1 manifest population mismatch')
    return manifest


def run_completion_analysis(roots, output, *, progress=None):
    check_output(output,roots)
    if Path(output).exists():raise FileExistsError(output)
    checks=verify_completion_inputs(roots)
    def profiles():
        for i,p in enumerate(iter_completion_profiles(roots),1):
            if progress:progress(i,p)
            yield p
    summary=write_completion_artifact(output,roots,checks,profiles())
    verify_completion_artifact(output)
    if checks!=verify_completion_inputs(roots):raise ValueError('D1 inputs changed during analysis')
    return summary
