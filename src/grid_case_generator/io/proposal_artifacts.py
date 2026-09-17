"""D2 proposal-only artifact IO, authoritative binding and independent rebuild verifier."""
from contextlib import ExitStack
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path

from grid_case_generator.analysis.proposal_inputs import build_case_input
from grid_case_generator.analysis.topology_proposals import STREAMS, propose_case
from grid_case_generator.analysis.proposal_summary import ProposalSummary, render_report
from grid_case_generator.models.proposals import VERSION, RULE_VERSION, DECISION_SCHEMA, parse_decisions, decision_bytes, unknown_decision
from grid_case_generator.io.completion_artifacts import verify_completion_artifact
from grid_case_generator.io.source_artifacts import SourceArtifactWriter, _artifact_root, _artifact_member
from grid_case_generator.io.switch_projection_artifacts import check_output
from grid_case_generator.io.topology_recovery_artifacts import code_fingerprint
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.validation.topology_proposals import measure_graph

FILES={'case_inputs.jsonl','case_coverage.jsonl',*(n+'.jsonl' for n in STREAMS),'summary.json','coverage_impact.json',
       'business_confirmation_template.json','business_confirmation_snapshot.json','report.md'}
INPUTS={'source','baseline','projection','feeder','recovery','d1'}


def verify_proposal_inputs(roots):
    if set(roots)!=INPUTS:raise ValueError('six proposal input artifacts required')
    d1=verify_completion_artifact(roots['d1'],{k:v for k,v in roots.items() if k!='d1'})
    return dict(d1['input_manifest_sha256'],d1=sha256((Path(roots['d1'])/'manifest.json').read_bytes()).hexdigest())


def known_pairs(roots):
    with (Path(roots['d1'])/'feeder_completion_cohorts.jsonl').open() as stream:
        return {(r['case_id'],r['feeder_id']) for r in map(json.loads,stream)}


def iter_proposal_inputs(roots):
    with (Path(roots['recovery'])/'transformer_evidence.jsonl').open() as ts, (Path(roots['d1'])/'case_profiles.jsonl').open() as ps:
        groups=iter(groupby(map(json.loads,ts),key=lambda t:t['case_id']));cid,group=next(groups,(None,()))
        for p in map(json.loads,ps):
            targets=list(group) if cid==p['case_id'] else []
            if cid==p['case_id']:cid,group=next(groups,(None,()))
            prefix='cases/'+p['case_id']+'/'
            with _artifact_member(Path(roots['source']),prefix+'row_accountability.jsonl').open() as stream:accounts=list(map(json.loads,stream))
            top=json.loads(_artifact_member(Path(roots['baseline']),prefix+'topology.json').read_text())
            with _artifact_member(Path(roots['baseline']),prefix+'exclusions.jsonl').open() as stream:exclusions=list(map(json.loads,stream))
            c=build_case_input(p,accounts,top,targets,exclusions)
            m=measure_graph(c);expected=p['graphs']['S0']
            for k in ('reachable_transformers','reachable_lines','target_coverage'):
                if m[k]!=expected[k]:raise ValueError('D2 base graph does not reproduce accepted S0: '+k)
            yield c
        if cid is not None:raise ValueError('unconsumed Transformer case evidence')


def write_proposal_artifact(output,roots,checks,policy,cases):
    check_output(output,roots);writer=SourceArtifactWriter(output,roots['source'])
    decision_map={(d['case_id'],d['feeder_id']):d for d in policy['decisions']}
    config_hash=sha256(decision_bytes(policy)).hexdigest();summary=ProposalSummary();template=[]
    with ExitStack() as stack:
        names=['case_inputs','case_coverage',*STREAMS]
        handles={n:stack.enter_context((writer.root/(n+'.jsonl')).open('xb')) for n in names}
        digests={n:sha256() for n in names};counts={n:0 for n in names}
        def emit(n,r):
            data=canonical_json_bytes(r)+b'\n';handles[n].write(data);digests[n].update(data);counts[n]+=1
        previous=None
        for c in cases:
            if previous is not None and c['case_id']<=previous:raise ValueError('proposal input case ordering')
            previous=c['case_id'];r=propose_case(c,decision_map,config_hash);summary.add(c,r)
            emit('case_inputs',c);emit('case_coverage',r['coverage'])
            for name in STREAMS:
                for row in r[name]:emit(name,row)
            template.extend(unknown_decision(c['case_id'],f['feeder_id']) for f in c['feeders'])
        for n in names:writer.entries[n+'.jsonl']={'sha256':digests[n].hexdigest(),'record_count':counts[n]}
    s=summary.finish();writer.write('summary.json',s);writer.write('coverage_impact.json',summary.coverage())
    writer.write('business_confirmation_snapshot.json',policy)
    writer.write('business_confirmation_template.json',{'schema_version':DECISION_SCHEMA,'decision_version':'1.0.0',
        'input_manifest_sha256':policy['input_manifest_sha256'],'decisions':sorted(template,key=lambda d:(d['case_id'],d['feeder_id']))})
    data=render_report(s).encode();(writer.root/'report.md').write_bytes(data)
    writer.entries['report.md']={'sha256':sha256(data).hexdigest(),'record_count':len(data.splitlines())}
    manifest={'version':VERSION,'rule_version':RULE_VERSION,'schema_version':'1.0.0','input_manifest_sha256':checks,
        'business_input_sha256':config_hash,'code_sha256':code_fingerprint(),'case_count':s['case_count'],'feeder_count':s['feeder_count'],
        'approved_objects':0,'applied_objects':0,'accepted_topology_changed':False,'s2_accepted':False,
        'files':dict(sorted(writer.entries.items()))}
    (writer.root/'manifest.json').write_bytes(canonical_json_bytes(manifest)+b'\n')
    return s


def verify_proposal_artifact(root,roots=None):
    root=_artifact_root(root);mp=_artifact_member(root,'manifest.json');m=json.loads(mp.read_text())
    if (m['version']!=VERSION or m['rule_version']!=RULE_VERSION or m['schema_version']!='1.0.0'
        or m['approved_objects']!=0 or m['applied_objects']!=0 or m['accepted_topology_changed'] is not False
        or m['s2_accepted'] is not False):raise ValueError('proposal boundary/schema mismatch')
    observed={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p!=mp}
    if observed!=FILES or set(m['files'])!=FILES:raise ValueError('proposal artifact inventory mismatch')
    for name,entry in m['files'].items():
        digest=sha256();count=0
        with _artifact_member(root,name).open('rb') as stream:
            for line in stream:
                digest.update(line);count+=1
                if name.endswith(('.json','.jsonl')) and canonical_json_bytes(json.loads(line))+b'\n'!=line:raise ValueError('noncanonical proposal bytes')
        if digest.hexdigest()!=entry['sha256'] or count!=entry['record_count']:raise ValueError('proposal checksum/count mismatch')
    if roots is not None and verify_proposal_inputs(roots)!=m['input_manifest_sha256']:raise ValueError('proposal input binding mismatch')
    authoritative=iter(iter_proposal_inputs(roots)) if roots is not None else None
    pairs=set()
    with (root/'case_inputs.jsonl').open() as stream:
        for c in map(json.loads,stream):
            if set(c)!={'case_id','source_case_key','feeders','hard_blockers','state_constraints','head_id',
                        'nominal_voltage_kv','s2_usable','source_line_count','base_nodes','base_edges','targets','evidence_refs','region_source_refs'}:
                raise ValueError('proposal input schema mismatch')
            pairs.update((c['case_id'],f['feeder_id']) for f in c['feeders'])
    bindings={k:m['input_manifest_sha256'][k] for k in ('source','d1')}
    policy=parse_decisions((root/'business_confirmation_snapshot.json').read_text(),pairs,bindings)
    config_hash=sha256(decision_bytes(policy)).hexdigest()
    if config_hash!=m['business_input_sha256']:raise ValueError('business input hash mismatch')
    expected_template={'schema_version':DECISION_SCHEMA,'decision_version':'1.0.0','input_manifest_sha256':bindings,
                       'decisions':[unknown_decision(*pair) for pair in sorted(pairs)]}
    if json.loads((root/'business_confirmation_template.json').read_text())!=expected_template:raise ValueError('unsafe business template')
    decision_map={(d['case_id'],d['feeder_id']):d for d in policy['decisions']};summary=ProposalSummary()
    with ExitStack() as stack:
        handles={n:stack.enter_context((root/(n+'.jsonl')).open()) for n in [*STREAMS,'case_coverage']}
        previous=None
        with (root/'case_inputs.jsonl').open() as stream:
            for c in map(json.loads,stream):
                if previous is not None and c['case_id']<=previous:raise ValueError('D2 case ordering')
                previous=c['case_id']
                if authoritative is not None and canonical_json_bytes(c)!=canonical_json_bytes(next(authoritative,None)):
                    raise ValueError('D2 case inputs differ from authoritative evidence')
                result=propose_case(c,decision_map,config_hash);summary.add(c,result)
                for name in [*STREAMS,'case_coverage']:
                    rows=[result['coverage']] if name=='case_coverage' else result[name]
                    for row in rows:
                        actual=next(handles[name],None)
                        if actual is None or canonical_json_bytes(row)!=canonical_json_bytes(json.loads(actual)):
                            raise ValueError('proposal detail/validation rebuild mismatch: '+name)
        if any(next(h,None) is not None for h in handles.values()):raise ValueError('extra proposal details')
    if authoritative is not None and next(authoritative,None) is not None:raise ValueError('missing proposal case')
    s=summary.finish()
    if canonical_json_bytes(s)!=canonical_json_bytes(json.loads((root/'summary.json').read_text())):raise ValueError('proposal summary mismatch')
    if canonical_json_bytes(summary.coverage())!=canonical_json_bytes(json.loads((root/'coverage_impact.json').read_text())):raise ValueError('proposal coverage mismatch')
    if render_report(s)!=(root/'report.md').read_text():raise ValueError('proposal report mismatch')
    if m['case_count']!=s['case_count'] or m['feeder_count']!=s['feeder_count']:raise ValueError('proposal manifest counts')
    return m


def run_proposal_analysis(roots,decision_path,output,*,progress=None):
    check_output(output,dict(roots,decisions=decision_path))
    if Path(output).exists():raise FileExistsError(output)
    checks=verify_proposal_inputs(roots);data=Path(decision_path).read_bytes()
    policy=parse_decisions(data,known_pairs(roots),{k:checks[k] for k in ('source','d1')})
    def cases():
        for i,c in enumerate(iter_proposal_inputs(roots),1):
            if progress:progress(i,c)
            yield c
    result=write_proposal_artifact(output,roots,checks,policy,cases())
    verify_proposal_artifact(output)
    if checks!=verify_proposal_inputs(roots) or Path(decision_path).read_bytes()!=data:raise ValueError('D2 inputs changed')
    return result
