"""Independent, deterministic E2.1 diagnostic artifacts over verified E1/E2."""
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType

from grid_case_generator.analysis.switch_semantics import VERSION, InvestigationSummary, investigate_case
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.source_artifacts import (
    SourceArtifactWriter, VerifiedSourceArtifact, verify_source_artifact,
    read_source_case_details, _artifact_root, _artifact_member,
)
from grid_case_generator.io.topology_artifacts import verify_topology_artifact, read_topology_case


FILES = ('dataset_summary.json','switch_candidates.jsonl','motif_distribution.json',
    'endpoint_type_distribution.json','case_pattern_summary.jsonl','explicit_endpoint_breakdown.json',
    'degree_distribution.json','counterfactual_reachability.json','representative_examples.json')


def write_investigation(output,source_root,baseline_root,source_checksum,baseline_checksum,results):
    output_path=Path(output).resolve()
    for input_root in (source_root,baseline_root):
        input_path=Path(input_root).resolve()
        if output_path==input_path or input_path in output_path.parents or output_path in input_path.parents:
            raise ValueError('diagnostics must be separate from both source and baseline')
    writer=SourceArtifactWriter(output,source_root)
    summary=InvestigationSummary()
    def candidates():
        for result in results:
            summary.add(result)
            yield from result['candidates']
    writer.write('switch_candidates.jsonl',candidates(),lines=True)
    reports=summary.finish()
    metadata={'source_artifact_checksum':'sha256:'+source_checksum,
        'baseline_topology_artifact_checksum':'sha256:'+baseline_checksum}
    reports['dataset_summary'].update(metadata)
    for name,report in reports.items():
        lines=name=='case_pattern_summary'
        writer.write(name+('.jsonl' if lines else '.json'),report,lines=lines)
    manifest={'analysis_version':VERSION,'accepted_topology':False,**metadata,
        'files':dict(sorted(writer.entries.items()))}
    (writer.root/'manifest.json').write_bytes(canonical_json_bytes(manifest)+b'\n')
    return reports['dataset_summary']


def verify_investigation_artifact(root):
    root=_artifact_root(root)
    manifest_path=_artifact_member(root,'manifest.json')
    manifest=json.loads(manifest_path.read_text())
    if manifest['analysis_version']!=VERSION or manifest['accepted_topology'] is not False:
        raise ValueError('unsupported diagnostic artifact')
    if set(manifest['files'])!=set(FILES): raise ValueError('diagnostic inventory mismatch')
    for name,entry in manifest['files'].items():
        digest=sha256(); count=0
        with _artifact_member(root,name).open('rb') as stream:
            for line in stream: digest.update(line); count+=1
        if digest.hexdigest()!=entry['sha256'] or count!=entry['record_count']:
            raise ValueError('diagnostic checksum/count mismatch: '+name)
    observed={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p!=manifest_path}
    if observed!=set(FILES): raise ValueError('unexpected diagnostic file')
    return manifest


def run_investigation(source_root,baseline_root,output,*,case_id=None,progress=None):
    source=verify_source_artifact(source_root)
    baseline=verify_topology_artifact(baseline_root)
    source_checksum=sha256((source.root/'manifest.json').read_bytes()).hexdigest()
    baseline_checksum=sha256((baseline.root/'manifest.json').read_bytes()).hexdigest()
    if baseline.manifest['input_source_artifact_checksum']!='sha256:'+source_checksum:
        raise ValueError('baseline was not derived from this E1 artifact')
    case_files=defaultdict(dict)
    for name,entry in source.manifest['files'].items():
        parts=name.split('/')
        if parts[0]=='cases': case_files[parts[1]][name]=entry
    source_report=json.loads((source.root/'import_report.json').read_text())
    inventory=json.loads((source.root/'inventory.json').read_text())
    if set(case_files)!=set(baseline.manifest['case_ids']) or set(case_files)!={c['case_id'] for c in source_report['cases']} or len(case_files)!=len(inventory['cases']):
        raise ValueError('source/baseline inventory mismatch')
    selected=sorted(case_files) if case_id is None else [case_id]
    if any(cid not in case_files for cid in selected): raise ValueError('unknown source case')
    def results():
        for i,cid in enumerate(selected,1):
            manifest=dict(source.manifest); manifest['files']=MappingProxyType(case_files[cid])
            scoped=VerifiedSourceArtifact(source.root,MappingProxyType(manifest))
            details=read_source_case_details(source.root,cid,verified_artifact=scoped)
            topology=read_topology_case(baseline.root,cid,verified_artifact=baseline)
            result=investigate_case(details,topology)
            if progress: progress(i,len(selected),result)
            yield result
    return write_investigation(output,source_root,baseline_root,source_checksum,baseline_checksum,results())
