"""Verified E1/E2 inputs and isolated E2.2 counterfactual report artifacts."""
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType

from grid_case_generator.analysis.switch_projection_analysis import VERSION, STATUS, ProjectionSummary, analyze_projection_case
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.source_artifacts import (
    SourceArtifactWriter, VerifiedSourceArtifact, verify_source_artifact,
    read_source_case_details, _artifact_root, _artifact_member,
)
from grid_case_generator.io.topology_artifacts import verify_topology_artifact, read_topology_case

FILES = {'strategy_comparison.json', 'coverage_by_strategy.json', 'risk_analysis.json',
         'tie_switch_analysis.json', 'representative_examples.json', 'proposal.md',
         'case_results.jsonl', 'candidate_decisions.jsonl'}


def check_output(output, roots):
    path = Path(output).resolve()
    for root in roots.values():
        source = Path(root).resolve()
        if path == source or path in source.parents or source in path.parents:
            raise ValueError('analysis output must be separate from every input')


def write_projection_analysis(output, roots, checksums, results, proposal):
    check_output(output, roots)
    writer = SourceArtifactWriter(output, roots['source'])
    summary = ProjectionSummary()
    digest = sha256(); count = 0
    with (writer.root / 'candidate_decisions.jsonl').open('xb') as candidate_stream:
        def cases():
            nonlocal count
            for result in results:
                summary.add(result)
                for c in result['candidates']:
                    # Complete endpoint evidence retained; E2.1 ID-pattern features are not needed.
                    row = {k: v for k, v in c.items() if k not in ('id_patterns', 'relations')}
                    data = canonical_json_bytes(row) + b'\n'
                    candidate_stream.write(data); digest.update(data); count += 1
                yield {k: v for k, v in result.items() if k != 'candidates'}
        writer.write('case_results.jsonl', cases(), lines=True)
    writer.entries['candidate_decisions.jsonl'] = {'sha256': digest.hexdigest(), 'record_count': count}
    reports = summary.finish()
    metadata = {k + '_manifest_sha256': value for k, value in sorted(checksums.items())}
    reports['strategy_comparison']['inputs'] = metadata
    for name, report in reports.items(): writer.write(name + '.json', report)
    proposal_text = proposal(reports) if callable(proposal) else proposal
    data = proposal_text.encode('utf-8')
    (writer.root / 'proposal.md').write_bytes(data)
    writer.entries['proposal.md'] = {'sha256': sha256(data).hexdigest(), 'record_count': len(data.splitlines())}
    manifest = {'analysis_version': VERSION, 'status': STATUS, 'accepted_topology': False,
                'inputs': metadata, 'case_count': len(summary.case_ids), 'files': dict(sorted(writer.entries.items()))}
    (writer.root / 'manifest.json').write_bytes(canonical_json_bytes(manifest) + b'\n')
    return reports


def verify_projection_analysis(root):
    root = _artifact_root(root)
    path = _artifact_member(root, 'manifest.json')
    manifest = json.loads(path.read_text())
    if manifest['analysis_version'] != VERSION or manifest['accepted_topology'] is not False or manifest['status'] != list(STATUS):
        raise ValueError('unsupported projection analysis artifact')
    if set(manifest['files']) != FILES: raise ValueError('analysis inventory mismatch')
    for name, entry in manifest['files'].items():
        digest = sha256(); count = 0
        with _artifact_member(root, name).open('rb') as stream:
            for line in stream: digest.update(line); count += 1
        if digest.hexdigest() != entry['sha256'] or count != entry['record_count']:
            raise ValueError('analysis checksum/count mismatch: ' + name)
    observed = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p != path}
    if observed != FILES: raise ValueError('unexpected analysis file')
    return manifest


def source_regions(source):
    """EXACT Feeder->Bus raw IDs only, without creating global entity identity."""
    regions = defaultdict(set)
    for name in sorted(source.manifest['files']):
        if not name.endswith('/records/Feeder.jsonl'): continue
        for line in (source.root / name).read_text().splitlines():
            feeder = json.loads(line)
            ref = feeder['source_bus_source_ref']
            if feeder['identity_status'] == 'UNIQUE' and ref and ref['resolution_status'] == 'EXACT' and ref['resolved_source_ref']['entity_type'] == 'BUS':
                regions[ref['raw_ref']].add(feeder['case_id'] + '|' + feeder['feeder_id'])
    return {key: tuple(sorted(value)) for key, value in sorted(regions.items())}


def run_projection_analysis(source_root, baseline_root, output, proposal, *, progress=None):
    roots = {'source': source_root, 'baseline': baseline_root}
    check_output(output, roots)
    if Path(output).exists(): raise FileExistsError(output)
    source = verify_source_artifact(source_root)
    baseline = verify_topology_artifact(baseline_root)
    checksums = {name: sha256((Path(root) / 'manifest.json').read_bytes()).hexdigest() for name, root in roots.items()}
    if baseline.manifest['input_source_artifact_checksum'] != 'sha256:' + checksums['source']:
        raise ValueError('baseline does not belong to this source artifact')
    case_files = defaultdict(dict)
    for name, entry in source.manifest['files'].items():
        parts = name.split('/')
        if parts[0] == 'cases': case_files[parts[1]][name] = entry
    source_report = json.loads((source.root / 'import_report.json').read_text())
    inventory = json.loads((source.root / 'inventory.json').read_text())
    if set(case_files) != set(baseline.manifest['case_ids']) or set(case_files) != {c['case_id'] for c in source_report['cases']} or len(case_files) != len(inventory['cases']):
        raise ValueError('source/baseline case inventory mismatch')
    regions = source_regions(source)
    def results():
        for i, cid in enumerate(sorted(case_files), 1):
            manifest = dict(source.manifest); manifest['files'] = MappingProxyType(case_files[cid])
            scoped = VerifiedSourceArtifact(source.root, MappingProxyType(manifest))
            details = read_source_case_details(source.root, cid, verified_artifact=scoped)
            topology = read_topology_case(baseline.root, cid, verified_artifact=baseline)
            result = analyze_projection_case(details, topology, regions)
            if progress: progress(i, len(case_files), result)
            yield result
    return write_projection_analysis(output, roots, checksums, results(), proposal)
