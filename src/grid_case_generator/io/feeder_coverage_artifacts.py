"""Isolated feeder-level reports from verified E1, E2 and E2.2 evidence."""
from collections import defaultdict
import csv
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path
from types import MappingProxyType

from grid_case_generator.analysis.feeder_coverage import VERSION, POLICIES, FeederSummary, analyze_feeder_case
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.source_artifacts import (
    SourceArtifactWriter, VerifiedSourceArtifact, verify_source_artifact, read_source_case_details,
    _artifact_root, _artifact_member,
)
from grid_case_generator.io.topology_artifacts import verify_topology_artifact, read_topology_case
from grid_case_generator.io.switch_projection_artifacts import check_output, verify_projection_analysis
from grid_case_generator.models.types import EntityRef, Identifier, CanonicalId

FILES = {'feeder_coverage.json', 'failure_analysis.json', 'policy_recovery.json',
         'feeder_details.jsonl', 'case_details.jsonl', 'feeder_switch_counts.csv', 'report.md'}
CSV_FIELDS = ['case_id', 'source_case_key', 'source_feeder_id', 'name', 'feeder_id', 'scope',
              'switch_count', 'case_scope_switch_count', 'switch_raw_rows', 'switch_published_entities',
              'switch_structural_candidates', 'eligible_normal_state_unknown', 'semantic_unknown_candidates',
              *[p + '_' + metric for p in POLICIES for metric in ('transformer_goal_status', 'strict_topology_status')]]


def write_feeder_analysis(output, roots, checksums, results, report_renderer):
    check_output(output, roots)
    writer = SourceArtifactWriter(output, roots['source'])
    summary = FeederSummary(); feeder_digest = sha256(); feeder_count = 0
    with (writer.root / 'feeder_details.jsonl').open('xb') as feeder_stream, (writer.root / 'feeder_switch_counts.csv').open('x', newline='', encoding='utf-8') as csv_stream:
        csv_writer = csv.DictWriter(csv_stream, fieldnames=CSV_FIELDS); csv_writer.writeheader()
        def case_rows():
            nonlocal feeder_count
            for result in results:
                summary.add(result)
                for feeder in result['feeders']:
                    row = dict(feeder, policies=result['policies'])
                    data = canonical_json_bytes(row) + b'\n'
                    feeder_stream.write(data); feeder_digest.update(data); feeder_count += 1
                    flat = {k: feeder[k] for k in CSV_FIELDS if k in feeder}
                    flat.update({'switch_raw_rows': feeder['switch_inventory']['raw_rows'],
                                 'switch_published_entities': feeder['switch_inventory']['published_entities'],
                                 'switch_structural_candidates': feeder['switch_inventory']['structural_candidates'],
                                 'eligible_normal_state_unknown': feeder['switch_inventory']['eligible_normal_state_unknown'],
                                 'semantic_unknown_candidates': feeder['switch_inventory']['semantic_unknown_candidates']})
                    for policy, values in result['policies'].items():
                        for metric in ('transformer_goal_status', 'strict_topology_status'):
                            flat[policy + '_' + metric] = values[metric]
                    csv_writer.writerow(flat)
                yield result
        writer.write('case_details.jsonl', case_rows(), lines=True)
    writer.entries['feeder_details.jsonl'] = {'sha256': feeder_digest.hexdigest(), 'record_count': feeder_count}
    writer.entries['feeder_switch_counts.csv'] = {'sha256': sha256((writer.root / 'feeder_switch_counts.csv').read_bytes()).hexdigest(), 'record_count': feeder_count + 1}
    reports = summary.finish()
    reports['feeder_coverage']['input_manifest_sha256'] = checksums
    for name, report in reports.items(): writer.write(name + '.json', report)
    data = report_renderer(reports).encode('utf-8')
    (writer.root / 'report.md').write_bytes(data)
    writer.entries['report.md'] = {'sha256': sha256(data).hexdigest(), 'record_count': len(data.splitlines())}
    manifest = {'analysis_version': VERSION, 'counterfactual_only': True, 'completion_implemented': False,
                'input_manifest_sha256': checksums, 'case_count': len(summary.case_ids),
                'feeder_count': feeder_count, 'files': dict(sorted(writer.entries.items()))}
    (writer.root / 'manifest.json').write_bytes(canonical_json_bytes(manifest) + b'\n')
    return reports


def verify_feeder_analysis(root):
    root = _artifact_root(root)
    manifest_path = _artifact_member(root, 'manifest.json')
    manifest = json.loads(manifest_path.read_text())
    if manifest['analysis_version'] != VERSION or manifest['counterfactual_only'] is not True or manifest['completion_implemented'] is not False:
        raise ValueError('unsupported feeder analysis artifact')
    if set(manifest['files']) != FILES: raise ValueError('feeder analysis inventory mismatch')
    for name, entry in manifest['files'].items():
        path = _artifact_member(root, name)
        digest = sha256(); count = 0
        with path.open('rb') as stream:
            for line in stream: digest.update(line); count += 1
        if name.endswith('.csv'):
            with path.open(newline='', encoding='utf-8') as stream: count = sum(1 for _ in csv.reader(stream))
        if digest.hexdigest() != entry['sha256'] or count != entry['record_count']:
            raise ValueError('feeder analysis checksum/count mismatch: ' + name)
    observed = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p != manifest_path}
    if observed != FILES: raise ValueError('unexpected feeder analysis file')
    return manifest


def run_feeder_analysis(source_root, baseline_root, projection_root, output, report_renderer, *, progress=None):
    roots = {'source': source_root, 'baseline': baseline_root, 'projection': projection_root}
    check_output(output, roots)
    if Path(output).exists(): raise FileExistsError(output)
    source = verify_source_artifact(source_root)
    baseline = verify_topology_artifact(baseline_root)
    projection_manifest = verify_projection_analysis(projection_root)
    checksums = {name: sha256((Path(root) / 'manifest.json').read_bytes()).hexdigest() for name, root in roots.items()}
    if baseline.manifest['input_source_artifact_checksum'] != 'sha256:' + checksums['source']:
        raise ValueError('E2/source checksum mismatch')
    if projection_manifest['inputs'] != {'source_manifest_sha256': checksums['source'], 'baseline_manifest_sha256': checksums['baseline']}:
        raise ValueError('E2.2/input checksum mismatch')
    case_files = defaultdict(dict)
    for name, entry in source.manifest['files'].items():
        parts = name.split('/')
        if parts[0] == 'cases': case_files[parts[1]][name] = entry
    source_report = json.loads((source.root / 'import_report.json').read_text())
    inventory = json.loads((source.root / 'inventory.json').read_text())
    if set(case_files) != set(baseline.manifest['case_ids']) or set(case_files) != {c['case_id'] for c in source_report['cases']} or len(case_files) != len(inventory['cases']) or len(case_files) != projection_manifest['case_count']:
        raise ValueError('feeder analysis case inventory mismatch')
    def results():
        with (Path(projection_root) / 'candidate_decisions.jsonl').open() as candidate_stream, (Path(projection_root) / 'case_results.jsonl').open() as case_stream:
            groups = iter(groupby((json.loads(line) for line in candidate_stream), key=lambda c: c['case_id']))
            current_id, group = next(groups, (None, ()))
            for i, cid in enumerate(sorted(case_files), 1):
                expected = json.loads(next(case_stream))
                if expected['case_id'] != cid: raise ValueError('E2.2 case order/inventory mismatch')
                candidates = list(group) if current_id == cid else []
                if current_id == cid: current_id, group = next(groups, (None, ()))
                if len(candidates) != expected['candidate_count']: raise ValueError('E2.2 candidate count mismatch')
                for c in candidates:
                    ref = c['source_entity_ref']
                    c['source_entity_ref'] = EntityRef(entity_type=Identifier(ref['entity_type']), entity_id=CanonicalId(ref['entity_id']))
                manifest = dict(source.manifest); manifest['files'] = MappingProxyType(case_files[cid])
                scoped = VerifiedSourceArtifact(source.root, MappingProxyType(manifest))
                details = read_source_case_details(source.root, cid, verified_artifact=scoped)
                topology = read_topology_case(baseline.root, cid, verified_artifact=baseline)
                result = analyze_feeder_case(details, topology, candidates)
                for policy in ('S0', 'S2'):
                    for field in ('coverage', 'graph_sha256'):
                        if result['policies'][policy][field] != expected['strategies'][policy][field]:
                            raise ValueError('E2.2 graph/coverage mismatch: ' + cid + '/' + policy + '/' + field)
                if progress: progress(i, len(case_files), result)
                yield result
            if next(case_stream, None) is not None or current_id is not None: raise ValueError('unexpected E2.2 case/candidates')
    return write_feeder_analysis(output, roots, checksums, results(), report_renderer)
