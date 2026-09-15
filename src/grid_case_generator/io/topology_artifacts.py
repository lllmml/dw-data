"""Deterministic E2 artifacts, verified typed reload, and dataset aggregation."""
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from collections.abc import Mapping

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.source_artifacts import (
    SourceArtifactWriter, _artifact_root, _artifact_member, _decode,
    verify_source_artifact, read_source_case_details, VerifiedSourceArtifact,
)
from grid_case_generator.models.topology import (
    ElectricalTopology, TopologyProjectionRecord, TopologyCoverage, TopologyCaseResult,
    TopologyConfig, ProjectionStatus, RuleId, RULE_VERSION, DerivedIdFactory,
)
from grid_case_generator.validation.topology import validate_topology

FORMAT_VERSION = 'nanjing-derived-topology-v1'


def write_topology_artifact(output, source_root, source_checksum, config, results):
    output_path, input_path = Path(output).resolve(), Path(source_root).resolve()
    if output_path == input_path or input_path in output_path.parents or output_path in input_path.parents:
        raise ValueError('E2 output must be separate from E1 input')
    writer = SourceArtifactWriter(output, source_root)
    writer.write('config.json', config)
    totals, statuses, reasons, anchors = Counter(), Counter(), Counter(), Counter()
    rules = defaultdict(Counter)
    case_ids = []
    for result in results:
        validate_topology(result)
        case_id = result.topology.case_id
        if case_id in case_ids:
            raise ValueError('duplicate case result')
        case_ids.append(case_id)
        prefix = f'cases/{case_id}/'
        writer.write(prefix+'topology.json',result.topology)
        writer.write(prefix+'projections.jsonl',result.projections,lines=True)
        writer.write(prefix+'exclusions.jsonl',(p for p in result.projections if p.projection_status is not ProjectionStatus.PROJECTED),lines=True)
        writer.write(prefix+'case_report.json',result.coverage)
        report=result.coverage
        anchors[report.feeder_anchor_status] += 1
        totals.update(report.counts)
        totals['total_cases'] += 1
        totals['cases_with_reachable_transformer'] += int(report.has_reachable_transformer)
        totals['cases_with_usable_subgraph'] += int(report.usable_subgraph)
        statuses.update(report.projection_status_counts)
        reasons.update(report.exclusion_reasons)
        for rule,counts in report.rule_counts.items():
            rules[rule].update(counts)
    coverage = {'feeder_anchor_status_counts':dict(sorted(anchors.items())), 'counts':dict(sorted(totals.items())), 'projection_status_counts':dict(sorted(statuses.items())),
        'exclusion_reasons':dict(sorted(reasons.items())),
        'rule_counts':{rule:dict(sorted(counts.items())) for rule,counts in sorted(rules.items())}}
    writer.write('dataset_coverage_report.json',coverage)
    manifest = {'format_version':FORMAT_VERSION, 'id_namespace':DerivedIdFactory.namespace,
        'input_source_artifact_checksum':'sha256:'+source_checksum,
        'rule_versions':{rule.value:RULE_VERSION for rule in RuleId},
        'case_ids':sorted(case_ids), 'files':dict(sorted(writer.entries.items()))}
    (writer.root/'manifest.json').write_bytes(canonical_json_bytes(manifest)+b'\n')
    return coverage


@dataclass(frozen=True, slots=True)
class VerifiedTopologyArtifact:
    root: Path
    manifest: Mapping[str, object]


def verify_topology_artifact(root):
    root = _artifact_root(root)
    manifest_path = _artifact_member(root,'manifest.json')
    manifest = json.loads(manifest_path.read_text())
    if manifest['format_version'] != FORMAT_VERSION or manifest['id_namespace'] != DerivedIdFactory.namespace:
        raise ValueError('unsupported topology artifact version')
    if manifest['rule_versions'] != {r.value:RULE_VERSION for r in RuleId}:
        raise ValueError('unsupported topology rules')
    case_ids = manifest['case_ids']
    if case_ids != sorted(set(case_ids)):
        raise ValueError('case inventory must be sorted and unique')
    required = {'config.json','dataset_coverage_report.json'}
    for case_id in case_ids:
        if not isinstance(case_id,str) or not case_id.startswith('case:') or len(case_id)!=69 or any(c not in '0123456789abcdef' for c in case_id[5:]):
            raise ValueError('invalid case ID')
        required.update(f'cases/{case_id}/{name}' for name in ('topology.json','projections.jsonl','exclusions.jsonl','case_report.json'))
    if set(manifest['files']) != required:
        raise ValueError('topology file inventory mismatch')
    for name,entry in manifest['files'].items():
        digest, count = sha256(), 0
        with _artifact_member(root,name).open('rb') as stream:
            for line in stream:
                digest.update(line); count += 1
        if digest.hexdigest()!=entry['sha256'] or count!=entry['record_count']:
            raise ValueError('topology checksum/count mismatch: '+name)
    observed = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p != manifest_path}
    if observed != required:
        raise ValueError('unmanifested topology file')
    _decode(json.loads((root/'config.json').read_text()), TopologyConfig)
    manifest['files'] = MappingProxyType({k:MappingProxyType(v) for k,v in manifest['files'].items()})
    return VerifiedTopologyArtifact(root,MappingProxyType(manifest))


def read_topology_case(root, case_id, *, verified_artifact=None):
    verified = verified_artifact or verify_topology_artifact(root)
    if not isinstance(verified,VerifiedTopologyArtifact) or verified.root != _artifact_root(root):
        raise ValueError('verification root mismatch')
    if case_id not in verified.manifest['case_ids']:
        raise ValueError('case absent from topology artifact')
    prefix=f'cases/{case_id}/'
    def read(name,kind):
        return _decode(json.loads(_artifact_member(verified.root,prefix+name).read_text()),kind)
    topology=read('topology.json',ElectricalTopology)
    coverage=read('case_report.json',TopologyCoverage)
    with _artifact_member(verified.root,prefix+'projections.jsonl').open() as stream:
        projections=tuple(_decode(json.loads(line),TopologyProjectionRecord) for line in stream)
    result=TopologyCaseResult(topology,projections,coverage)
    validate_topology(result)
    return result


def audit_source_artifact(source_root, output, config, *, case_id=None, progress=None):
    from grid_case_generator.generation.topology import interpret_topology
    verified=verify_source_artifact(source_root)
    checksum=sha256((verified.root/'manifest.json').read_bytes()).hexdigest()
    # Index already-verified manifest entries once, avoiding 5159 whole-manifest
    # scans/sorts while still using the E1 typed reader and its root-bound token.
    case_files=defaultdict(dict)
    for relative,entry in verified.manifest['files'].items():
        parts=relative.split('/')
        if parts[0]=='cases':
            case_files[parts[1]][relative]=entry
    inventory=json.loads((verified.root/'inventory.json').read_text())
    source_report=json.loads((verified.root/'import_report.json').read_text())
    if len(case_files) != len(inventory['cases']) or set(case_files) != {c['case_id'] for c in source_report['cases']}:
        raise ValueError('source case inventory mismatch')
    source_summaries={c['case_id']:c for c in source_report['cases']}
    selected=sorted(case_files) if case_id is None else [case_id]
    if any(cid not in case_files for cid in selected):
        raise ValueError('case absent from source artifact')
    def results():
        for index,cid in enumerate(selected,1):
            manifest=dict(verified.manifest)
            manifest['files']=MappingProxyType(case_files[cid])
            scoped=VerifiedSourceArtifact(verified.root,MappingProxyType(manifest))
            details=read_source_case_details(verified.root,cid,verified_artifact=scoped)
            result=interpret_topology(details,config)
            counts=dict(result.coverage.counts)
            counts['canonical_invalid_source_cases']=int(not source_summaries[cid]['canonical_valid'])
            result=replace(result,coverage=replace(result.coverage,counts=counts))
            if progress: progress(index,len(selected),result)
            yield result
    return write_topology_artifact(output,source_root,checksum,config,results())
