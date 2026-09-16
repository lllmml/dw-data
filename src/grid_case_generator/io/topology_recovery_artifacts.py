"""Versioned, isolated E2.3-A artifacts from four verified input artifacts."""
from collections import defaultdict
from contextlib import ExitStack
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path
from types import MappingProxyType

from grid_case_generator.analysis.topology_recovery import VERSION, RULE_VERSION, RULES, analyze_recovery_case
from grid_case_generator.analysis.topology_recovery_summary import RecoverySummary, render_report
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.source_artifacts import (SourceArtifactWriter, VerifiedSourceArtifact, verify_source_artifact,
    read_source_case_details, _artifact_root, _artifact_member)
from grid_case_generator.io.topology_artifacts import verify_topology_artifact, read_topology_case
from grid_case_generator.io.switch_projection_artifacts import check_output, verify_projection_analysis
from grid_case_generator.io.feeder_coverage_artifacts import verify_feeder_analysis
from grid_case_generator.models.types import EntityRef, Identifier, CanonicalId

STREAMS = {'transformers':'transformer_evidence.jsonl', 'blockers':'frontier_blockers.jsonl',
           'connections':'connection_evidence.jsonl', 'candidates':'candidate_rule_witnesses.jsonl',
           'feeders':'feeder_details.jsonl'}
FILES = {'summary.json','case_details.jsonl','recovery_cohorts.jsonl','report.md',*STREAMS.values()}


def code_fingerprint():
    root=Path(__file__).resolve().parents[1]
    entries={str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*.py'))}
    return sha256(canonical_json_bytes(entries)).hexdigest()


def cohort_record(feeder):
    return {k:feeder[k] for k in ('case_id','source_feeder_id','feeder_id','source_record_refs','scope',
        'source_evidence_cohort','completion_cohorts','recovery_readiness','readiness_reasons','constraint_tags','constraint_refs','e3_ready')}


def write_recovery_artifact(output, roots, checksums, results):
    check_output(output,roots)
    writer=SourceArtifactWriter(output,roots['source']); summary=RecoverySummary()
    with ExitStack() as stack:
        names=[*STREAMS.values(),'case_details.jsonl','recovery_cohorts.jsonl']
        streams={name:stack.enter_context((writer.root/name).open('xb')) for name in names}
        digests={name:sha256() for name in names};counts={name:0 for name in names}
        def emit(name,row):
            data=canonical_json_bytes(row)+b'\n';streams[name].write(data);digests[name].update(data);counts[name]+=1
        previous=None
        for result in results:
            if previous is not None and result['case_id']<=previous:raise ValueError('case order must be strictly increasing')
            previous=result['case_id'];summary.add(result)
            for key,name in STREAMS.items():
                for row in result[key]:emit(name,row)
            emit('case_details.jsonl',{k:v for k,v in result.items() if k not in STREAMS})
            for feeder in result['feeders']:emit('recovery_cohorts.jsonl',cohort_record(feeder))
        for name in names:writer.entries[name]={'sha256':digests[name].hexdigest(),'record_count':counts[name]}
    report=summary.finish();writer.write('summary.json',report)
    data=render_report(report).encode('utf-8');(writer.root/'report.md').write_bytes(data)
    writer.entries['report.md']={'sha256':sha256(data).hexdigest(),'record_count':len(data.splitlines())}
    manifest={'analysis_version':VERSION,'schema_version':'1.0.0','rule_versions':{r:RULE_VERSION for r in RULES},
              'accepted_topology_changed':False,'synthetic_topology_implemented':False,
              'input_manifest_sha256':checksums,'code_sha256':code_fingerprint(),
              'case_count':report['case_count'],'feeder_count':report['feeder_count'],'files':dict(sorted(writer.entries.items()))}
    (writer.root/'manifest.json').write_bytes(canonical_json_bytes(manifest)+b'\n')
    return report


def _groups(stream):
    return iter(groupby((json.loads(line) for line in stream),key=lambda row:row['case_id']))


def verify_recovery_artifact(root):
    root=_artifact_root(root);mp=_artifact_member(root,'manifest.json');manifest=json.loads(mp.read_text())
    if (manifest['analysis_version']!=VERSION or manifest['schema_version']!='1.0.0'
            or manifest['accepted_topology_changed'] is not False or manifest['synthetic_topology_implemented'] is not False
            or manifest['rule_versions']!={r:RULE_VERSION for r in RULES}):raise ValueError('unsupported recovery artifact schema/flags')
    observed={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p!=mp}
    if set(manifest['files'])!=FILES or observed!=FILES:raise ValueError('recovery artifact inventory mismatch')
    for name,entry in manifest['files'].items():
        digest=sha256();count=0
        with _artifact_member(root,name).open('rb') as stream:
            for line in stream:
                digest.update(line);count+=1
                if name.endswith(('.json','.jsonl')):
                    try: normalized=canonical_json_bytes(json.loads(line))+b'\n'
                    except ValueError as exc: raise ValueError('noncanonical recovery record: '+name) from exc
                    if normalized!=line: raise ValueError('noncanonical recovery record: '+name)
        if digest.hexdigest()!=entry['sha256'] or count!=entry['record_count']:raise ValueError('recovery checksum/count mismatch: '+name)
    summary=RecoverySummary()
    with ExitStack() as stack:
        grouped={key:_groups(stack.enter_context((root/name).open())) for key,name in STREAMS.items()}
        current={key:next(g,(None,())) for key,g in grouped.items()}
        cohorts=stack.enter_context((root/'recovery_cohorts.jsonl').open())
        cases=stack.enter_context((root/'case_details.jsonl').open())
        previous=None
        for line in cases:
            result=json.loads(line);cid=result['case_id']
            if previous is not None and cid<=previous:raise ValueError('recovery case order mismatch')
            previous=cid
            for key,g in grouped.items():
                rid,rows=current[key]
                result[key]=list(rows) if rid==cid else []
                if rid==cid:current[key]=next(g,(None,()))
                values=result[key]
                if key!='feeders' and [r['evidence_id'] for r in values]!=sorted({r['evidence_id'] for r in values}):
                    raise ValueError('recovery detail ordering/identity mismatch')
                for row in values:
                    if key in ('connections','candidates') and (row['evidence_class']=='RULE_GENERATED' or (key=='candidates' and row['approved'])):
                        raise ValueError('recovery evidence illegally promoted')
            for f in result['feeders']:
                if f['e3_ready'] or f['evidence_composition']['synthetic_connections']!=0:raise ValueError('recovery readiness illegally promoted')
                if json.loads(next(cohorts))!=cohort_record(f):raise ValueError('recovery cohort detail mismatch')
            summary.add(result)
        if any(cid is not None for cid,rows in current.values()) or next(cohorts,None) is not None:raise ValueError('unexpected recovery detail cases')
    report=summary.finish()
    if canonical_json_bytes(report)!=canonical_json_bytes(json.loads((root/'summary.json').read_text())):
        raise ValueError('recovery summary does not reproduce details')
    if (root/'report.md').read_text()!=render_report(report):raise ValueError('recovery report does not reproduce details')
    if manifest['case_count']!=report['case_count'] or manifest['feeder_count']!=report['feeder_count']:raise ValueError('recovery manifest population mismatch')
    return manifest


def verify_inputs(roots):
    source=verify_source_artifact(roots['source']);baseline=verify_topology_artifact(roots['baseline'])
    projection=verify_projection_analysis(roots['projection']);feeder=verify_feeder_analysis(roots['feeder'])
    checksums={k:sha256((Path(p)/'manifest.json').read_bytes()).hexdigest() for k,p in roots.items()}
    if baseline.manifest['input_source_artifact_checksum']!='sha256:'+checksums['source']:raise ValueError('E2/source binding mismatch')
    if projection['inputs']!={'source_manifest_sha256':checksums['source'],'baseline_manifest_sha256':checksums['baseline']}:
        raise ValueError('projection input binding mismatch')
    if feeder['input_manifest_sha256']!={k:checksums[k] for k in ('source','baseline','projection')}:
        raise ValueError('feeder input binding mismatch')
    return source,baseline,projection,feeder,checksums


def run_recovery_analysis(source_root,baseline_root,projection_root,feeder_root,output,*,progress=None):
    roots={'source':source_root,'baseline':baseline_root,'projection':projection_root,'feeder':feeder_root}
    check_output(output,roots)
    if Path(output).exists():raise FileExistsError(output)
    source,baseline,projection,feeder,checksums=verify_inputs(roots)
    case_files=defaultdict(dict)
    for name,entry in source.manifest['files'].items():
        parts=name.split('/')
        if parts[0]=='cases':case_files[parts[1]][name]=entry
    inventory=json.loads((source.root/'inventory.json').read_text())
    report=json.loads((source.root/'import_report.json').read_text())
    if (set(case_files)!=set(baseline.manifest['case_ids']) or set(case_files)!={c['case_id'] for c in report['cases']}
            or len(case_files)!=len(inventory['cases']) or len(case_files)!=projection['case_count'] or len(case_files)!=feeder['case_count']):
        raise ValueError('recovery input case inventory mismatch')
    def results():
        with ExitStack() as stack:
            candidate_stream=stack.enter_context((Path(projection_root)/'candidate_decisions.jsonl').open())
            candidate_groups=_groups(candidate_stream);current_id,group=next(candidate_groups,(None,()))
            ps=stack.enter_context((Path(projection_root)/'case_results.jsonl').open())
            fs=stack.enter_context((Path(feeder_root)/'case_details.jsonl').open())
            feeder_rows=stack.enter_context((Path(feeder_root)/'feeder_details.jsonl').open())
            for i,cid in enumerate(sorted(case_files),1):
                projection_case=json.loads(next(ps));feeder_case=json.loads(next(fs))
                if projection_case['case_id']!=cid or feeder_case['case_id']!=cid:raise ValueError('input detail case order mismatch')
                for f in feeder_case['feeders']:
                    if json.loads(next(feeder_rows))!=dict(f,policies=feeder_case['policies']):raise ValueError('feeder/case detail mismatch')
                candidates=list(group) if current_id==cid else []
                if current_id==cid:current_id,group=next(candidate_groups,(None,()))
                if len(candidates)!=projection_case['candidate_count']:raise ValueError('candidate inventory mismatch')
                for c in candidates:
                    er=c['source_entity_ref'];c['source_entity_ref']=EntityRef(entity_type=Identifier(er['entity_type']),entity_id=CanonicalId(er['entity_id']))
                scoped=VerifiedSourceArtifact(source.root,MappingProxyType(dict(source.manifest,files=MappingProxyType(case_files[cid]))))
                details=read_source_case_details(source.root,cid,verified_artifact=scoped)
                topology=read_topology_case(baseline.root,cid,verified_artifact=baseline)
                files=json.loads((source.root/'cases'/cid/'file_accounting.json').read_text())['files']
                result=analyze_recovery_case(details,topology,files,candidates,feeder_case)
                for policy in ('S0','S2'):
                    if result['graphs'][policy]['graph_sha256']!=projection_case['strategies'][policy]['graph_sha256']:
                        raise ValueError('projection graph hash mismatch')
                if progress:progress(i,len(case_files),result)
                yield result
            if current_id is not None or any(next(s,None) is not None for s in (ps,fs,feeder_rows)):raise ValueError('unexpected input detail rows')
    result=write_recovery_artifact(output,roots,checksums,results())
    verify_recovery_artifact(output)
    after=verify_inputs(roots)[-1]
    if after!=checksums:raise ValueError('input artifacts changed during analysis')
    return result
