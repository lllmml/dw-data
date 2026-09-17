"""Canonical D4.1 streams, the D4 replay and source-bound independent replay."""
from collections import Counter, defaultdict
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import re

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.deterministic_recovery_artifacts import (
    read_json, verify_artifacts as verify_d3, input_hashes as d3_hashes,
)
from grid_case_generator.io.synthetic_backbone_artifacts import inputs as d4_inputs, events as d4_events
from grid_case_generator.io.switch_projection_artifacts import check_output
from grid_case_generator.generation.placement_evidence import (
    CaseEvidence, STREAMS, REVIEW_STREAMS, VERSION, RULE_VERSION, SCOPE, COMPOSITION,
    FEEDER_STATUSES, LINE_OUTCOMES, ANCHOR_RULES, DEFERRED_RULES,
)
from grid_case_generator.validation.placement_evidence import validate_case

EXTRA_STREAMS = ('case_inputs', 'target_feeders', 'd4_replay', 'placement_validation')
ALL_STREAMS = (*EXTRA_STREAMS, *STREAMS, *REVIEW_STREAMS)
FILES = {s + '.jsonl' for s in ALL_STREAMS} | {
    'counterfactual_coverage.json', 'engineering_metrics.json', 'summary.json', 'report.md'}
BACKBONE_REQUIRED = 'SYNTHETIC_BACKBONE_REQUIRED'
AMBIGUOUS_REASONS = {'NON_UNIQUE_ANCHOR', 'NON_UNIQUE_COMPONENT', 'NO_ENGINEERING_ANCHOR',
                     'COMPETING_SOURCE_REFERENCE_COMPONENTS', 'NON_UNIQUE_FEEDER'}
ID_PATTERN = re.compile(rb'\["([A-Za-z_]+_ID)","([^"]+)"\]')


def code_hash():
    root = Path(__file__).resolve().parents[1]
    files = [root / 'generation/placement_evidence.py', root / 'validation/placement_evidence.py',
             root / 'io/placement_evidence_artifacts.py', root / 'analysis/placement_evidence_cli.py']
    return sha256(canonical_json_bytes({str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
                                        for p in files})).hexdigest()


def foreign_index(source_root, wanted):
    """Raw identities defined outside the analysed Cases; read-only and bounded.

    It is descriptive evidence about the intake and never places anything. Only the
    raw texts that failed to resolve case-locally are retained.
    """
    wanted = set(wanted); found = defaultdict(set)
    if not wanted:
        return {}
    for path in sorted((Path(source_root) / 'cases').glob('*/row_accountability.jsonl')):
        for key, value in ID_PATTERN.findall(path.read_bytes()):
            text = value.decode()
            if text in wanted:
                found[text].add(key.decode())
    return {k: sorted(v) for k, v in sorted(found.items())}


def bindings(analysis, accepted, roots, d4):
    return dict(d3_hashes(roots), d3=sha256((Path(analysis) / 'manifest.json').read_bytes()).hexdigest(),
                accepted_v2=sha256((Path(accepted) / 'manifest.json').read_bytes()).hexdigest(),
                d4=sha256((Path(d4) / 'manifest.json').read_bytes()).hexdigest())


def overlaid(case, additions):
    return dict(case, base_nodes=sorted([*case['base_nodes'], *additions['nodes']],
                                        key=lambda n: n['node_id']),
                base_edges=sorted([*case['base_edges'], *additions['edges']],
                                  key=lambda e: e['edge_id']))


def replay_cases(cases, additions, apply):
    for x in cases:
        if apply:
            found = additions.get(x['accepted']['case_id'])
            if found:
                x = {'accepted': overlaid(x['accepted'], found), 'source': x['source']}
        yield x


def collect(cases, cohort_cases=None):
    """One streaming pass of the D4 engine; returns summary, edges and taxonomy.

    Case snapshots are never materialized: only the Feeder that reach the D4.1 cohort
    are retained, and only when a caller asks for them.
    """
    summary = None; edges = []; taxonomy = []; current = None
    for name, row in d4_events(cases):
        if name == 'case_inputs.jsonl':
            current = row
        elif name == 'summary.json':
            summary = row
        elif name == 'proposal_edges.jsonl':
            edges.append(row)
        elif name == 'feeder_gap_taxonomy.jsonl':
            taxonomy.append(row)
            if cohort_cases is not None and row['d3_primary'] == BACKBONE_REQUIRED \
                    and row['source_line_count'] > 0 and not row['line_components']:
                cohort_cases[(row['case_id'], row['feeder_id'])] = current
    if summary is None:
        raise ValueError('D4 replay produced no summary')
    return summary, edges, taxonomy


def classify_replay(before_edges, after_edges, after_taxonomy):
    """Reclassify every D4 proposal on the placement counterfactual; nothing is applied."""
    after_by_feeder = defaultdict(list)
    for e in after_edges:
        after_by_feeder[(e['case_id'], e['feeder_id'])].append(e)
    taxonomy = {(r['case_id'], r['feeder_id']): r for r in after_taxonomy}
    rows = []
    for e in sorted(before_edges, key=lambda r: (r['case_id'], r['feeder_id'], r['edge_id'])):
        key = (e['case_id'], e['feeder_id'])
        pair = tuple(sorted((e['a'], e['b'])))
        now = sorted(after_by_feeder.get(key, []), key=lambda r: r['edge_id'])
        reasons = set(taxonomy.get(key, {}).get('reasons', ()))
        if any(tuple(sorted((n['a'], n['b']))) == pair for n in now):
            status = 'STILL_VALID'; note = 'SAME_UNIQUE_ATTACHMENT_ON_PLACEMENT_COUNTERFACTUAL'
        elif 'BACKBONE_ALREADY_REACHABLE' in reasons:
            status = 'SUPERSEDED_BY_BETTER_PLACEMENT'; note = 'PLACEMENT_ALREADY_CONNECTS_COMPONENT'
        elif now:
            status = 'SUPERSEDED_BY_BETTER_PLACEMENT'; note = 'DIFFERENT_ATTACHMENT_NOW_UNIQUE'
        elif reasons & AMBIGUOUS_REASONS:
            status = 'NOW_AMBIGUOUS'; note = 'PLACEMENT_INTRODUCED_COMPETING_STRUCTURE'
        else:
            status = 'INVALID'; note = 'NO_UNIQUE_ATTACHMENT_ON_PLACEMENT_COUNTERFACTUAL'
        rows.append({'scope': SCOPE, 'case_id': e['case_id'], 'feeder_id': e['feeder_id'],
                     'd4_edge_id': e['edge_id'], 'attachment_pair': list(pair),
                     'replay_status': status, 'replay_note': note,
                     'after_reasons': sorted(reasons),
                     'after_replay_edge_ids': [n['edge_id'] for n in now],
                     'origin': 'BEFORE', 'evidence_class': None,
                     'approved': False, 'applied': False,
                     'rule_version': e.get('rule_version'), 'version': VERSION})
    covered = {(e['case_id'], e['feeder_id'], e['a'], e['b']) for e in before_edges}
    for e in sorted(after_edges, key=lambda r: (r['case_id'], r['feeder_id'], r['edge_id'])):
        if (e['case_id'], e['feeder_id'], e['a'], e['b']) in covered:
            continue
        rows.append({'scope': SCOPE, 'case_id': e['case_id'], 'feeder_id': e['feeder_id'],
                     'd4_edge_id': e['edge_id'],
                     'attachment_pair': sorted((e['a'], e['b'])),
                     'replay_status': 'NEW_ON_PLACEMENT_COUNTERFACTUAL',
                     'replay_note': 'PLACEMENT_MADE_THE_COMPONENT_AUTOMATICALLY_ELIGIBLE',
                     'after_reasons': [], 'after_replay_edge_ids': [e['edge_id']],
                     'origin': 'NEW', 'evidence_class': e.get('evidence_class'),
                     'approved': False, 'applied': False,
                     'rule_version': e.get('rule_version'), 'version': VERSION})
    return sorted(rows, key=lambda r: (r['origin'], r['case_id'], r['feeder_id'], r['d4_edge_id']))


def metrics(summary):
    d2 = summary['d2_eligibility']; phys = summary['coverage_impact']['physical']
    return {'physical_backbone': d2['after']['counts']['accepted_physical_backbone'],
            'reachable_source_lines': phys['metrics_after']['reachable_lines'],
            'reachable_source_line_components': phys['metrics_after']['reachable_source_line_components'],
            'reachable_transformers': phys['metrics_after']['reachable_transformers'],
            'reachable_model_transformers': phys['metrics_after']['reachable_model_transformers'],
            'attachment_eligible_feeders': d2['after']['primary']['SYNTHETIC_ATTACHMENT_ELIGIBLE'],
            'eligible_transformer_candidates': d2['after']['counts']['synthetic_candidate_count'],
            'missing_backbone_candidates': d2['after']['counts']['missing_backbone_count'],
            'missing_backbone_or_region_candidates':
                d2['after']['counts']['missing_backbone_or_region_count'],
            'backbone_required_feeders': d2['after']['primary'].get(BACKBONE_REQUIRED, 0),
            'd2_primary_after': d2['after']['primary'],
            'physical_metrics_after': phys['metrics_after'],
            'physical_metrics_before': phys['metrics_before']}


class Analysis:
    """One deterministic analysis pass over the cohort plus the D4 replay."""

    def __init__(self, factory, source_root):
        self.source_root = source_root
        cohort_cases = {}
        self.before, before_edges, self.before_taxonomy = collect(factory(), cohort_cases)
        self.cohort = set(cohort_cases)
        # Every field value, not just the ::_ID definitions: the texts that need
        # classifying are endpoint references, which are values rather than keys.
        wanted = set()
        for x in cohort_cases.values():
            wanted |= {v for a in x['source']['accounts']
                       for _, v in (a['raw_record']['fields'] or ()) if v}
        self.foreign = foreign_index(source_root, wanted)
        self.additions = {}; self.results = {}; self.overlay = {}
        for key in sorted(cohort_cases):
            x = cohort_cases[key]
            ev = CaseEvidence(x, self.foreign)
            self.results[key] = (x, ev, ev.analyse(), ev.reviews(), validate_case(x, ev))
            self.overlay[key[0]] = {'nodes': ev.nodes_out, 'edges': ev.graph_edges}
            if ev.graph_edges:
                self.additions[key[0]] = {'nodes': len(ev.nodes_out), 'edges': len(ev.graph_edges)}
        self.after, after_edges, after_taxonomy = collect(
            replay_cases(factory(), self.overlay, True))
        self.replay = classify_replay(before_edges, after_edges, after_taxonomy)
        self.coverage = {
            'scope': SCOPE, 'composition': COMPOSITION,
            'before': metrics(self.before), 'after': metrics(self.after),
            'd4_proposals_before': len(before_edges), 'd4_proposals_after': len(after_edges),
            'd4_proposals_added': len(after_edges) - len(before_edges),
            'd4_replay_status': dict(sorted(Counter(r['replay_status'] for r in self.replay).items())),
            'new_proposal_feeders': sorted({(r['case_id'], r['feeder_id']) for r in self.replay
                                            if r['origin'] == 'NEW'}),
            'cohort_new_proposal_feeders': sorted({(r['case_id'], r['feeder_id']) for r in self.replay
                                                   if r['origin'] == 'NEW'
                                                   and (r['case_id'], r['feeder_id']) in self.cohort}),
            'placement_additions': {cid: dict(v)
                                    for cid, v in sorted(self.additions.items())}}

    def summary(self):
        counts = Counter(); evidence = Counter(); anchors = Counter(); reviews = Counter()
        outcomes = Counter(); statuses = Counter(); reasons = Counter(); per_feeder = []
        for key, (x, ev, result, review, level) in sorted(self.results.items()):
            cid = key[0]
            if level['reasons']:
                raise ValueError('D4.1 internally invalid case: ' + str(level))
            counts['cases'] += 1; counts['feeders'] += len(x['accepted']['feeders'])
            counts['endpoints'] += len(result['rows']['line_endpoint_evidence'])
            counts['lines'] += len(result['line_rows'])
            counts['proposals'] += len(ev.proposals)
            counts['parallel_withdrawn_lines'] += len(ev.parallel_withdrawal)
            counts['cycle_withdrawn_cases'] += bool(ev.withdrawn)
            for row in result['rows']['line_endpoint_evidence']:
                evidence[row['placement_evidence_class']] += 1
            for row in result['rows']['placement_anchors']:
                anchors[row['rule_id']] += 1
            for stream in REVIEW_STREAMS:
                for row in review[stream]:
                    reviews[stream + ':' + row['disposition']] += 1
            for row in result['line_rows']:
                outcomes[row['outcome']] += 1; reasons.update(row['reasons'])
            row_class = ev.feeder_row
            statuses[row_class['primary_status']] += 1
            per_feeder.append({'case_id': cid, 'feeder_id': row_class['feeder_id'],
                               'primary_status': row_class['primary_status'],
                               'overlapping_outcomes': row_class['overlapping_outcomes'],
                               'overlapping_reasons': row_class['overlapping_reasons'],
                               'proposed_line_count': row_class['proposed_line_count'],
                               'blocked_line_count': row_class['blocked_line_count'],
                               'proposed_anchor_count': row_class['proposed_anchor_count']})
        coverage = self.coverage
        return {'scope': SCOPE, 'version': VERSION, 'rule_version': RULE_VERSION,
                'composition': COMPOSITION, 'cases': counts['cases'], 'feeders': counts['feeders'],
                'target_feeders': len(self.cohort), 'lines': counts['lines'],
                'endpoints': counts['endpoints'], 'proposals': counts['proposals'],
                'parallel_withdrawn_lines': counts['parallel_withdrawn_lines'],
                'cycle_withdrawn_cases': counts['cycle_withdrawn_cases'],
                'feeder_primary_status': {k: statuses.get(k, 0) for k in FEEDER_STATUSES},
                'line_outcomes': {k: outcomes.get(k, 0) for k in LINE_OUTCOMES},
                'line_block_reasons': dict(sorted(reasons.items())),
                'endpoint_evidence_classes': dict(sorted(evidence.items())),
                'anchor_rules': {k: anchors.get(k, 0) for k in ANCHOR_RULES},
                'disabled_rules': list(DEFERRED_RULES),
                'review_dispositions': dict(sorted(reviews.items())),
                'recovered_line_components': counts['proposals'],
                'new_proposed_anchors': sum(anchors.get(k, 0) for k in ANCHOR_RULES),
                'd4_replay_status': coverage['d4_replay_status'],
                'per_feeder': per_feeder,
                'approved': False, 'applied': False, 'accepted_v2_changed': False,
                'source_changed': False, 'd4_artifact_changed': False,
                'approved_d4_proposals': 0, 'e3_ready': False}

    def events(self):
        for key, (x, ev, result, review, level) in sorted(self.results.items()):
            yield 'case_inputs.jsonl', x
            yield 'placement_validation.jsonl', level
            for stream in STREAMS:
                for row in result['rows'][stream]:
                    yield stream + '.jsonl', row
            for stream in REVIEW_STREAMS:
                for row in review[stream]:
                    yield stream + '.jsonl', row
            if key in self.cohort:
                yield 'target_feeders.jsonl', ev.feeder_row
        for row in self.replay:
            yield 'd4_replay.jsonl', row
        summary = self.summary()
        yield 'counterfactual_coverage.json', self.coverage
        yield 'engineering_metrics.json', {k: v for k, v in summary.items()
                                           if k not in ('per_feeder', 'line_outcomes',
                                                        'line_block_reasons',
                                                        'endpoint_evidence_classes')}
        yield 'summary.json', summary
        yield 'report.md', report(summary, self.coverage)


def payload(name, row):
    return row.encode() if name == 'report.md' else canonical_json_bytes(row) + b'\n'


def report(summary, coverage):
    body = {'summary': summary, 'counterfactual_coverage': coverage}
    return ('# E2.3-D4.1 source-constrained placement evidence\n\n'
            'PROPOSAL_ONLY_COUNTERFACTUAL. No approval, no apply, accepted v2 unchanged.\n'
            'Composition: ' + COMPOSITION + '\n\n```json\n'
            + json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + '\n```\n')


def write_artifact(factory, output, input_bindings, source_root):
    output = Path(output)
    resolved = output.resolve()
    if any(p.name == 'raw' and p.parent.name == 'data' for p in (resolved, *resolved.parents)):
        raise ValueError('D4.1 output cannot be data/raw')
    if output.exists():
        raise FileExistsError(output)
    analysis = Analysis(factory, source_root)
    output.mkdir(parents=True)
    with ExitStack() as stack:
        handles = {n: stack.enter_context((output / n).open('xb')) for n in sorted(FILES)}
        hashes = {n: sha256() for n in FILES}; records = Counter()
        for name, row in analysis.events():
            name = name if name.endswith(('.json', '.md')) else name
            key = name if name in FILES else name + '.jsonl'
            data = payload(key, row); handles[key].write(data); hashes[key].update(data)
            records[key] += len(data.splitlines()) if key == 'report.md' else 1
    manifest = {'artifact_kind': SCOPE, 'version': VERSION, 'rule_version': RULE_VERSION,
                'schema_version': VERSION, 'composition': COMPOSITION,
                'input_manifest_sha256': input_bindings, 'code_sha256': code_hash(),
                'approved': False, 'applied': False, 'accepted_v2_changed': False,
                'source_changed': False, 'd4_artifact_changed': False, 'e3_ready': False,
                'files': {n: {'sha256': hashes[n].hexdigest(), 'record_count': records[n]}
                          for n in sorted(FILES)}}
    (output / 'manifest.json').write_bytes(canonical_json_bytes(manifest) + b'\n')
    return read_json(output, 'summary.json')


def verify_artifact(output, *, factory=None, source_root=None, expected_bindings=None):
    output = Path(output); manifest = read_json(output, 'manifest.json')
    if (output / 'manifest.json').read_bytes() != canonical_json_bytes(manifest) + b'\n':
        raise ValueError('D4.1 manifest serialization')
    if manifest['artifact_kind'] != SCOPE or manifest['version'] != VERSION \
            or manifest['rule_version'] != RULE_VERSION or manifest['schema_version'] != VERSION \
            or manifest['composition'] != COMPOSITION or manifest['code_sha256'] != code_hash():
        raise ValueError('D4.1 version/code mismatch')
    if any(manifest[k] is not False for k in ('approved', 'applied', 'accepted_v2_changed',
                                              'source_changed', 'd4_artifact_changed', 'e3_ready')):
        raise ValueError('D4.1 scope violation')
    if expected_bindings is not None and manifest['input_manifest_sha256'] != expected_bindings:
        raise ValueError('D4.1 stale source/D3/v2/D4 binding')
    if set(manifest['files']) != FILES or {p.name for p in output.iterdir()} != FILES | {'manifest.json'}:
        raise ValueError('D4.1 inventory mismatch')
    for name in FILES:
        digest = sha256(); count = 0
        with (output / name).open('rb') as f:
            for line in f:
                digest.update(line); count += 1
                if name != 'report.md' and line != canonical_json_bytes(json.loads(line)) + b'\n':
                    raise ValueError('D4.1 noncanonical detail: ' + name)
        if manifest['files'][name] != {'sha256': digest.hexdigest(), 'record_count': count}:
            raise ValueError('D4.1 checksum/count mismatch: ' + name)
    if factory is None or source_root is None:
        return {'verified': True, 'input_bound': False}
    analysis = Analysis(factory, source_root)
    with ExitStack() as stack:
        handles = {n: stack.enter_context((output / n).open('rb')) for n in FILES}
        for name, row in analysis.events():
            key = name if name in FILES else name + '.jsonl'
            actual = handles[key].read() if key == 'report.md' else handles[key].readline()
            if actual != payload(key, row):
                raise ValueError('D4.1 semantic replay mismatch: ' + key)
        if any(f.read(1) for f in handles.values()):
            raise ValueError('D4.1 extra records')
    return {'verified': True, 'input_bound': True,
            'manifest_sha256': sha256((output / 'manifest.json').read_bytes()).hexdigest()}


def run(analysis, accepted, roots, d4, output, verify=False):
    protected = dict(roots, d3=analysis, accepted_v2=accepted, d4=d4)
    check_output(output, protected)
    before = bindings(analysis, accepted, roots, d4)
    verify_d3(analysis, accepted, roots)
    factory = lambda: d4_inputs(analysis, accepted)
    if verify:
        result = verify_artifact(output, factory=factory, source_root=roots['source'],
                                 expected_bindings=before)
    else:
        result = write_artifact(factory, output, before, roots['source'])
        verify_artifact(output, factory=factory, source_root=roots['source'], expected_bindings=before)
    if bindings(analysis, accepted, roots, d4) != before:
        raise ValueError('D4.1 inputs changed during run')
    return result
