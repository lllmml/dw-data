"""D3 isolated artifact writer and source-bound deterministic replay verifier."""
from contextlib import ExitStack
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path

from grid_case_generator.analysis.deterministic_recovery import (
    eligibility, taxonomy, rule_reviews, RecoverySummary, render_report,
)
from grid_case_generator.generation.deterministic_recovery import recover_case, VERSION, RULE_VERSION
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.proposal_artifacts import INPUTS as D2_INPUTS, verify_proposal_artifact
from grid_case_generator.io.topology_artifacts import verify_topology_artifact
from grid_case_generator.io.source_artifacts import _artifact_root, _artifact_member
from grid_case_generator.io.switch_projection_artifacts import check_output
from grid_case_generator.io.topology_recovery_artifacts import code_fingerprint

INPUTS = D2_INPUTS | {'d2', 'frozen'}
ANALYSIS_STREAMS = ('case_inputs', 'candidate_connections', 'accepted_connections',
                    'rejected_connections', 'feeder_recovery', 'case_coverage', 'd2_eligibility', 'rule_review')
ANALYSIS_FILES = {n+'.jsonl' for n in ANALYSIS_STREAMS} | {
    'summary.json', 'rule_summary.json', 'coverage_impact.json', 'd2_reclassification.json', 'report.md'}
ACCEPTED_FILES = {'case_topologies.jsonl', 'additions.jsonl'}


def read_json(root, name):
    return json.loads(_artifact_member(Path(root), name).read_text())


def read_lines(root, name):
    with _artifact_member(Path(root), name).open() as f:
        yield from map(json.loads, f)


def input_hashes(roots):
    if set(roots) != INPUTS: raise ValueError('D3 requires all eight authoritative roots')
    return {k:sha256(_artifact_member(Path(v), 'manifest.json').read_bytes()).hexdigest() for k,v in sorted(roots.items())}


def verify_inputs(roots):
    checks = input_hashes(roots)
    verify_proposal_artifact(roots['d2'], {k:roots[k] for k in D2_INPUTS})
    verify_topology_artifact(roots['frozen'])
    if checks != input_hashes(roots): raise ValueError('D3 input changed during verification')
    return checks


def iter_inputs(roots):
    for base in read_lines(roots['d2'], 'case_inputs.jsonl'):
        prefix = 'cases/'+base['case_id']+'/'
        yield {'base':base,
               'accounts':sorted(read_lines(roots['source'], prefix+'row_accountability.jsonl'), key=lambda a:a['raw_record']['source_record_ref']),
               'terminals':sorted(read_lines(roots['source'], prefix+'records/Terminal.jsonl'), key=lambda t:t['terminal_id'])
                   if (Path(roots['source'])/prefix/'records/Terminal.jsonl').exists() else [],
               'topology':read_json(roots['baseline'], prefix+'topology.json'),
               'projections':sorted(read_lines(roots['baseline'], prefix+'projections.jsonl'), key=lambda p:repr(p))}


def policy_map(roots):
    p = read_json(roots['d2'], 'business_confirmation_snapshot.json')
    return {(d['case_id'],d['feeder_id']):d for d in p['decisions']}


def events(cases, decisions=None):
    summary = RecoverySummary(); previous = None
    for row in rule_reviews(): yield 'rule_review.jsonl', row
    for c in cases:
        cid = c['base']['case_id']
        if previous is not None and cid <= previous: raise ValueError('D3 case ordering/duplication')
        previous = cid
        r = recover_case(c); before = eligibility(c['base'], decisions); after = eligibility(r['topology'], decisions)
        feeders = [taxonomy(c['base'], r, b) for b in before]
        summary.add(c, r, before, after, feeders)
        yield 'case_inputs.jsonl', c
        for row in r['candidates']:
            yield 'candidate_connections.jsonl', row
            if row['status'] in ('REJECTED','NEEDS_REVIEW'): yield 'rejected_connections.jsonl', row
        for row in r['additions']:
            yield '@additions.jsonl', row
            if 'edge_id' in row: yield 'accepted_connections.jsonl', row
        for row in feeders: yield 'feeder_recovery.jsonl', row
        yield 'case_coverage.jsonl', r['coverage']
        for b,a in zip(before,after): yield 'd2_eligibility.jsonl', {'before':b, 'after':a}
        yield '@case_topologies.jsonl', r['topology']
    s = summary.finish()
    yield 'summary.json', s
    for name in ('rule_summary','coverage_impact','d2_reclassification'): yield name+'.json', s[name]
    yield 'report.md', render_report(s)


def check_paths(roots, analysis, accepted):
    for output in (analysis, accepted):
        check_output(output, roots)
        path = Path(output).resolve()
        if any(p.name == 'raw' and p.parent.name == 'data' for p in (path, *path.parents)):
            raise ValueError('D3 output may not be under data/raw')
    check_output(analysis, {'accepted':accepted})


def write_artifacts(cases, analysis, accepted, bindings, decisions=None):
    analysis, accepted = Path(analysis), Path(accepted)
    check_paths({}, analysis, accepted)
    if analysis.exists() or accepted.exists(): raise FileExistsError('D3 output already exists')
    analysis.mkdir(parents=True); accepted.mkdir(parents=True)
    inventories = {False:{}, True:{}}
    with ExitStack() as stack:
        handles = {}; digests = {}; counts = {}
        for flag, root, files in ((False,analysis,ANALYSIS_FILES),(True,accepted,ACCEPTED_FILES)):
            for name in sorted(files):
                key = ('@' if flag else '')+name
                handles[key] = stack.enter_context((root/name).open('xb'))
                digests[key] = sha256(); counts[key] = 0
        for key, row in events(cases, decisions):
            data = row.encode() if key == 'report.md' else canonical_json_bytes(row)+b'\n'
            handles[key].write(data); digests[key].update(data); counts[key] += len(data.splitlines()) if key=='report.md' else 1
        for key in handles:
            inventories[key.startswith('@')][key.lstrip('@')] = {'sha256':digests[key].hexdigest(), 'record_count':counts[key]}
    shared = {'version':VERSION, 'rule_version':RULE_VERSION, 'schema_version':'1.0.0',
              'input_manifest_sha256':bindings, 'code_sha256':code_fingerprint(),
              'new_rule_generated_objects':0, 'frozen_v1_changed':False, 'source_changed':False,
              's2_blanket_accepted':False, 'e3_ready':False}
    manifest = dict(shared, artifact_kind='DETERMINISTIC_RULE_REVIEW', files=inventories[False])
    (analysis/'manifest.json').write_bytes(canonical_json_bytes(manifest)+b'\n')
    accepted_manifest = dict(shared, artifact_kind='ACCEPTED_DETERMINISTIC_TOPOLOGY_V2',
        analysis_manifest_sha256=sha256((analysis/'manifest.json').read_bytes()).hexdigest(), files=inventories[True])
    (accepted/'manifest.json').write_bytes(canonical_json_bytes(accepted_manifest)+b'\n')
    return read_json(analysis, 'summary.json')


def check_inventory(root, expected, kind):
    root = _artifact_root(root); m = read_json(root, 'manifest.json')
    if (root/'manifest.json').read_bytes() != canonical_json_bytes(m)+b'\n': raise ValueError('D3 noncanonical manifest')
    if (m.get('version') != VERSION or m.get('rule_version') != RULE_VERSION or m.get('schema_version') != '1.0.0'
            or m.get('artifact_kind') != kind or m.get('new_rule_generated_objects') != 0
            or m.get('frozen_v1_changed') is not False or m.get('source_changed') is not False
            or m.get('s2_blanket_accepted') is not False or m.get('e3_ready') is not False):
        raise ValueError('D3 manifest boundary/schema mismatch')
    if set(m.get('input_manifest_sha256', {})) != INPUTS or any(
            not isinstance(v,str) or len(v)!=64 or any(ch not in '0123456789abcdef' for ch in v)
            for v in m['input_manifest_sha256'].values()): raise ValueError('D3 input binding schema')
    observed = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    if observed != expected | {'manifest.json'} or set(m['files']) != expected: raise ValueError('D3 inventory mismatch')
    for name in sorted(expected):
        digest = sha256(); count = 0
        with _artifact_member(root,name).open('rb') as f:
            for line in f:
                digest.update(line); count += 1
                if name.endswith(('.json','.jsonl')) and canonical_json_bytes(json.loads(line))+b'\n' != line:
                    raise ValueError('D3 noncanonical detail')
        if {'sha256':digest.hexdigest(),'record_count':count} != m['files'][name]: raise ValueError('D3 checksum/count mismatch: '+name)
    return m


def verify_artifacts(analysis, accepted, roots=None):
    analysis, accepted = Path(analysis), Path(accepted)
    m = check_inventory(analysis, ANALYSIS_FILES, 'DETERMINISTIC_RULE_REVIEW')
    v = check_inventory(accepted, ACCEPTED_FILES, 'ACCEPTED_DETERMINISTIC_TOPOLOGY_V2')
    if v['code_sha256'] != m['code_sha256']: raise ValueError('D3 code binding mismatch')
    if v['input_manifest_sha256'] != m['input_manifest_sha256'] or v['analysis_manifest_sha256'] != sha256((analysis/'manifest.json').read_bytes()).hexdigest():
        raise ValueError('D3 accepted/input binding mismatch')
    if roots is not None and verify_inputs(roots) != m['input_manifest_sha256']:
        raise ValueError('D3 authoritative input binding mismatch')
    authoritative = iter(iter_inputs(roots)) if roots is not None else None
    def cases():
        for c in read_lines(analysis, 'case_inputs.jsonl'):
            if authoritative is not None and canonical_json_bytes(c) != canonical_json_bytes(next(authoritative,None)):
                raise ValueError('D3 evidence differs from authoritative inputs')
            yield c
        if authoritative is not None and next(authoritative,None) is not None: raise ValueError('D3 missing case')
    with ExitStack() as stack:
        handles = {('@' if flag else '')+name:stack.enter_context((root/name).open('rb'))
                   for flag,root,names in ((False,analysis,ANALYSIS_FILES),(True,accepted,ACCEPTED_FILES)) for name in names}
        for key,row in events(cases(), policy_map(roots) if roots else None):
            expected = row.encode() if key=='report.md' else canonical_json_bytes(row)+b'\n'
            actual = handles[key].read() if key=='report.md' else handles[key].readline()
            if actual != expected: raise ValueError('D3 semantic replay mismatch: '+key)
        if any(f.read(1) for f in handles.values()): raise ValueError('D3 extra detail records')
    if roots is not None: check_d2_before(analysis, roots)
    return {'verified':True, 'input_bound':roots is not None, 'analysis_manifest_sha256':sha256((analysis/'manifest.json').read_bytes()).hexdigest(),
            'accepted_manifest_sha256':sha256((accepted/'manifest.json').read_bytes()).hexdigest()}


def check_d2_before(analysis, roots):
    """The independent eligibility evaluator must agree with actual D2 detail streams."""
    old = {(r['case_id'],r['feeder_id']):r for r in read_lines(roots['d2'],'feeder_eligibility.jsonl')}
    counts = defaultdict(Counter)
    for r in read_lines(roots['d2'],'proposal_bundles.jsonl'):
        counts[(r['case_id'],r['feeder_id'])]['eligible'] += 1
    for r in read_lines(roots['d2'],'rejected_candidates.jsonl'):
        if set(r['reasons']) & {'NO_ACCEPTED_PHYSICAL_BACKBONE','ATTACHMENT_REGION_UNDETERMINED'}:
            counts[(r['case_id'],r['feeder_id'])]['missing'] += 1
    seen = set()
    for row in read_lines(analysis,'d2_eligibility.jsonl'):
        b = row['before']; key = (b['case_id'],b['feeder_id']); seen.add(key); expected = old[key]
        if (b['primary_class'] != expected['primary_class'] or
                b['accepted_physical_backbone'] != expected['structure_sufficiency']['accepted_physical_backbone'] or
                b['candidate_region_count'] != expected['structure_sufficiency']['candidate_region_count'] or
                b['synthetic_candidate_count'] != counts[key]['eligible'] or
                b['missing_backbone_or_region_count'] != counts[key]['missing']):
            raise ValueError('D3 before eligibility does not reproduce D2: '+str(key))
    if seen != set(old): raise ValueError('D3 before Feeder inventory differs from D2')


def run_recovery(roots, analysis, accepted, *, progress=None):
    check_paths(roots, analysis, accepted)
    if Path(analysis).exists() or Path(accepted).exists(): raise FileExistsError('D3 output already exists')
    checks = verify_inputs(roots)
    def cases():
        for i,c in enumerate(iter_inputs(roots),1):
            if progress: progress(i,c['base']['case_id'])
            yield c
    summary = write_artifacts(cases(), analysis, accepted, checks, policy_map(roots))
    check_d2_before(analysis, roots)
    verify_artifacts(analysis, accepted)
    if checks != verify_inputs(roots): raise ValueError('D3 inputs changed during run')
    return summary
