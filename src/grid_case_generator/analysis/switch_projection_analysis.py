"""E2.2 design experiments. No accepted topology objects or source mutations."""
from collections import Counter, defaultdict
from hashlib import sha256

from grid_case_generator.analysis.switch_semantics import SourceMotifIndex, investigate_case, ratio
from grid_case_generator.generation.topology import _voltage_compatible
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.models import records as source
from grid_case_generator.models.topology import ProjectionStatus, DerivedRole
from grid_case_generator.models.types import IdentityStatus, SourceReferenceStatus
from grid_case_generator.validation.topology_switch import graph_risks, reachable

VERSION = 'switch-projection-design-v1'
STATUS = ('PROPOSED', 'NOT ACCEPTED', 'NOT IMPLEMENTED')
STRATEGIES = ('S0', 'S1', 'S2', 'S3_A', 'S3_B')
GROUPS = ('normal', 'tie', 'unknown_type')
IMPACT_KEYS = ('reachable_transformers', 'cases_with_reachable_transformers', 'cases_with_usable_subgraph')


def tie_group(candidate):
    return 'tie' if candidate['is_tie'] is True else 'normal' if candidate['is_tie'] is False else 'unknown_type'


def endpoint_safety(index, candidate):
    if candidate['semantic_assessment'] in ('COMPATIBLE_SOURCE_EVIDENCE', 'DIFFERENT_ABSTRACTION_EVIDENCE'):
        return {'assessment': 'COMPATIBLE', 'reason': candidate['semantic_assessment'], 'conflicts': []}
    conflicts = []
    for left, right in (('A', 'X'), ('B', 'Y')):
        endpoints = [candidate['endpoints'][k] for k in (left, right)]
        if any(e['source_reference_status'] != 'EXACT' for e in endpoints):
            continue
        entities = [index.entities[e['source_target_ref'].entity_id] for e in endpoints]
        if not all(isinstance(e, source.Bus) and e.identity_status is IdentityStatus.UNIQUE for e in entities):
            continue
        voltages = [e.base_voltage_kv for e in entities]
        if any(v is None or not v.is_finite() or v <= 0 for v in voltages):
            continue
        if not (_voltage_compatible(*voltages) or _voltage_compatible(*reversed(voltages))):
            conflicts.append({'side': left + '/' + right, 'source_bus_ids': [e.bus_id for e in entities],
                              'voltage_kv': voltages, 'source_refs': [str(e.source_record_ref) for e in entities]})
    return {'assessment': 'CONFLICTING' if conflicts else 'UNKNOWN',
            'reason': 'EXACT_SAME_SIDE_BUS_VOLTAGE_CONFLICT' if conflicts else 'SEMANTICS_NOT_PROVEN',
            'conflicts': conflicts}


def candidate_decision(candidate, strategy, baseline_owners):
    owner = candidate['source_entity_ref'].entity_id
    if owner in baseline_owners:
        return {'projected': True, 'conducting': candidate['normal_state'] == 'CLOSED', 'reason': 'BASELINE_PRESERVED'}
    reason = 'STRUCTURAL_SERIES_CANDIDATE'
    if strategy == 'S0': reason = 'BASELINE_EXCLUDED'
    elif not candidate['inner_references_exact']: reason = 'INNER_REFERENCE_NOT_EXACT'
    elif strategy != 'S1' and candidate['safety']['assessment'] == 'CONFLICTING': reason = 'ENDPOINT_VOLTAGE_CONFLICT'
    elif candidate['normal_state'] not in ('CLOSED', 'OPEN') and strategy != 'S3_A': reason = 'UNKNOWN_STATE_EXCLUDED'
    elif candidate['normal_state'] == 'UNKNOWN': reason = 'UNKNOWN_PROJECTED_NOT_CONDUCTING'
    elif candidate['normal_state'] == 'OPEN': reason = 'OPEN_PROJECTED_NOT_CONDUCTING'
    projected = reason in ('STRUCTURAL_SERIES_CANDIDATE', 'UNKNOWN_PROJECTED_NOT_CONDUCTING', 'OPEN_PROJECTED_NOT_CONDUCTING')
    return {'projected': projected, 'conducting': projected and candidate['normal_state'] == 'CLOSED', 'reason': reason}


def build_graph(index, baseline, chosen):
    nodes = {n.node_id: {'role': n.role.value, 'owner': n.source_entity_ref.entity_id,
                        'raw_bus_id': index.entities[n.source_entity_ref.entity_id].source_id if n.role is DerivedRole.BUS_JUNCTION else None}
             for n in baseline.topology.nodes}
    for n in baseline.topology.nodes:
        if n.role is DerivedRole.FEEDER_HEAD:
            feeder = index.entities[n.source_entity_ref.entity_id]
            nodes[n.node_id]['raw_bus_id'] = feeder.source_bus_source_ref.raw_ref
    edges = {b.source_entity_ref.entity_id: {'id': b.branch_id, 'a': b.from_node_id, 'b': b.to_node_id,
             'kind': 'line' if b.role is DerivedRole.LINE else 'switch', 'owner': b.source_entity_ref.entity_id,
             'conducting': b.conducting, 'added': False} for b in baseline.topology.branches}
    baseline_switches = {e['owner'] for e in edges.values() if e['kind'] == 'switch'}
    terminals = {p.source_terminal_ref.entity_id: p.derived_target_ids[0] for p in baseline.projections
                 if p.source_terminal_ref is not None and p.projection_status is ProjectionStatus.PROJECTED}
    for owner, candidate in sorted(chosen.items()):
        if owner in baseline_switches: continue
        a, b = 'analysis-only:' + owner + ':in', 'analysis-only:' + owner + ':out'
        for node_id, role in ((a, 'switch-port/in'), (b, 'switch-port/out')):
            nodes[node_id] = {'role': role, 'owner': owner, 'raw_bus_id': None}
        edges[owner] = {'id': 'analysis-only:' + owner, 'a': a, 'b': b, 'kind': 'switch',
                        'owner': owner, 'conducting': candidate['normal_state'] == 'CLOSED', 'added': True}
    for owner, record in sorted(index.entities.items()):
        if not isinstance(record, source.Equipment) or record.equipment_type.value != 'LINE' or owner in edges:
            continue
        terms = index.terminals[owner]
        if record.identity_status is not IdentityStatus.UNIQUE or [t.terminal_no for t in terms] != [1, 2]: continue
        targets = []
        for term in terms:
            ref = term.resolved_source_ref
            if term.source_ref_status is SourceReferenceStatus.EXACT and ref.entity_id in chosen and ref.entity_id not in baseline_switches:
                targets.append('analysis-only:' + ref.entity_id + (':in' if term.terminal_no == 2 else ':out'))
            else:
                targets.append(terminals.get(term.terminal_id))
        if all(t is not None for t in targets):
            edges[owner] = {'id': 'analysis-only:' + owner, 'a': targets[0], 'b': targets[1],
                            'kind': 'line', 'owner': owner, 'conducting': True, 'added': True}
    return nodes, sorted(edges.values(), key=lambda e: e['id'])


def graph_coverage(nodes, edges, head, total_switches, total_transformers):
    adjacency = defaultdict(list)
    for e in edges:
        if e['conducting']:
            adjacency[e['a']].append((e['b'], e['id'])); adjacency[e['b']].append((e['a'], e['id']))
    seen = reachable(adjacency, head)
    transformers = sum(n['role'] == 'transformer-mv/mv' and key in seen for key, n in nodes.items())
    switches = [e for e in edges if e['kind'] == 'switch']
    return {'total_cases': 1, 'total_switch_identity_groups': total_switches,
            'published_transformers': total_transformers,
            'switch_projected_count': len(switches), 'switch_conducting_count': sum(e['conducting'] for e in switches),
            'switch_excluded_count': total_switches - len(switches),
            'cases_with_feeder_head': int(head is not None),
            'cases_with_usable_subgraph': int(head is not None and any(e['kind'] == 'line' and e['conducting'] and e['a'] in seen for e in edges)),
            'reachable_transformers': transformers, 'cases_with_reachable_transformers': int(transformers > 0)}


def analyze_projection_case(details, baseline, regions=None):
    index = SourceMotifIndex(details)
    investigation = investigate_case(details, baseline)
    candidates = sorted(investigation['candidates'], key=lambda c: (c['case_id'], c['switch_id']))
    baseline_owners = {b.source_entity_ref.entity_id for b in baseline.topology.branches if b.role is DerivedRole.SWITCH}
    for c in candidates:
        c['safety'] = endpoint_safety(index, c)
        c['decisions'] = {s: candidate_decision(c, s, baseline_owners) for s in STRATEGIES}
    total_switches = baseline.coverage.counts['switch_candidates']
    total_transformers = baseline.coverage.counts['published_transformers']
    head = baseline.topology.feeder_head_id
    regions = regions or {}
    graph_cache = {}
    def evaluate(chosen, risks=False):
        key = tuple(sorted(chosen))
        if key not in graph_cache:
            nodes, edges = build_graph(index, baseline, chosen)
            graph_cache[key] = {'nodes': nodes, 'edges': edges,
                'coverage': graph_coverage(nodes, edges, head, total_switches, total_transformers),
                'graph_sha256': sha256(canonical_json_bytes({'nodes': nodes, 'edges': edges})).hexdigest()}
        entry = graph_cache[key]
        if risks and 'risk' not in entry:
            entry['risk'] = {kind: graph_risks(entry['nodes'], [e for e in entry['edges'] if kind == 'structural' or e['conducting']], head, regions, str(index.case.case_id))
                             for kind in ('structural', 'conducting')}
        return entry
    strategies = {}; tie_analysis = {}
    base = evaluate({})['coverage']
    expected = baseline.coverage
    for key, value in {'reachable_transformers': expected.counts['reachable_transformers'],
                       'switch_projected_count': expected.counts['switch_projected'],
                       'switch_conducting_count': expected.counts['switch_closed'],
                       'cases_with_usable_subgraph': int(expected.usable_subgraph),
                       'cases_with_reachable_transformers': int(expected.has_reachable_transformer),
                       'cases_with_feeder_head': expected.counts['synthetic_mv_heads']}.items():
        if base[key] != value: raise ValueError('S0 does not reproduce baseline: ' + key)
    for strategy in STRATEGIES:
        chosen = {c['source_entity_ref'].entity_id: c for c in candidates if c['decisions'][strategy]['projected']}
        result = evaluate(chosen, risks=True)
        blocked = [{'switch_id': c['switch_id'], 'side': side, 'endpoint': c['endpoints'][side]}
                   for c in chosen.values() for side in ('A', 'B')
                   if c['endpoints'][side]['source_reference_status'] == 'EXACT'
                   and c['endpoints'][side]['source_entity_type'] in ('ACCESS_POINT', 'DISCONNECTOR', 'EARTHING_SWITCH', 'LOAD', 'DER')]
        risk = dict(result['risk'], blocked_unsupported_path_count=len(blocked), blocked_unsupported_examples=blocked[:3],
                    projected_semantic_unknown_count=sum(c['safety']['assessment'] == 'UNKNOWN' for c in chosen.values()),
                    projected_endpoint_conflict_count=sum(c['safety']['assessment'] == 'CONFLICTING' for c in chosen.values()),
                    endpoint_conflicts_excluded_count=sum(c['decisions'][strategy]['reason'] == 'ENDPOINT_VOLTAGE_CONFLICT' for c in candidates))
        strategies[strategy] = {'coverage': result['coverage'], 'graph_sha256': result['graph_sha256'], 'risk': risk}
        tie_analysis[strategy] = {}
        for group in GROUPS:
            members = [c for c in candidates if tie_group(c) == group]
            only = {k: c for k, c in chosen.items() if tie_group(c) == group}
            without = {k: c for k, c in chosen.items() if tie_group(c) != group}
            one, removed = evaluate(only)['coverage'], evaluate(without)['coverage']
            states = {state: {'candidate_count': sum(c['normal_state'] == state for c in members),
                             'projected_count': sum(c['normal_state'] == state for c in only.values()),
                             'conducting_count': sum(c['normal_state'] == state and c['decisions'][strategy]['conducting'] for c in only.values())}
                      for state in ('CLOSED', 'OPEN', 'UNKNOWN')}
            tie_analysis[strategy][group] = {'candidate_count': len(members), 'projected_count': len(only),
                'states': states, 'only_group_coverage': one, 'without_group_coverage': removed,
                'only_group_delta': {k: one[k] - base[k] for k in IMPACT_KEYS},
                'remove_group_loss': {k: result['coverage'][k] - removed[k] for k in IMPACT_KEYS}}
    return {'case_id': str(index.case.case_id), 'source_case_key': index.case.source_case_key,
            'candidate_count': len(candidates), 'candidate_exclusion_reasons': investigation['candidate_exclusion_reasons'],
            'candidates': candidates, 'strategies': strategies, 'tie_analysis': tie_analysis}


def add_numbers(target, value):
    """Recursively add count dictionaries; lists of witnesses are handled separately."""
    for key, item in value.items():
        if isinstance(item, int): target[key] = target.get(key, 0) + item
        elif isinstance(item, dict): add_numbers(target.setdefault(key, {}), item)


class ProjectionSummary:
    def __init__(self):
        self.case_ids = set()
        self.coverage = {s: Counter() for s in STRATEGIES}
        self.risk = {s: {} for s in STRATEGIES}
        self.tie = {s: {} for s in STRATEGIES}
        self.examples = {s: defaultdict(list) for s in STRATEGIES}
        self.risk_examples = {s: defaultdict(list) for s in STRATEGIES}
        self.exclusions = Counter()
        self.safety = Counter()

    @staticmethod
    def keep_first(bucket, item, key):
        bucket.append(item); bucket.sort(key=key); del bucket[3:]

    def add(self, result):
        cid = result['case_id']
        if cid in self.case_ids: raise ValueError('duplicate analysis case')
        self.case_ids.add(cid); self.exclusions.update(result['candidate_exclusion_reasons'])
        self.safety.update(c['safety']['assessment'] for c in result['candidates'])
        for strategy in STRATEGIES:
            self.coverage[strategy].update(result['strategies'][strategy]['coverage'])
            risk = result['strategies'][strategy]['risk']
            add_numbers(self.risk[strategy], risk)
            add_numbers(self.tie[strategy], result['tie_analysis'][strategy])
            for kind in ('structural', 'conducting'):
                for name, items in risk[kind].items():
                    if name.endswith('_examples'):
                        for item in items:
                            self.keep_first(self.risk_examples[strategy][kind + ':' + name], {'case_id': cid, 'evidence': item}, canonical_json_bytes)
            for c in result['candidates']:
                decision = c['decisions'][strategy]
                categories = ['all', 'projected' if decision['projected'] else 'excluded']
                if c['normal_state'] in ('OPEN', 'UNKNOWN'): categories.append(c['normal_state'])
                if c['safety']['assessment'] == 'CONFLICTING': categories.append('endpoint_conflict')
                example = {k: c[k] for k in ('case_id', 'source_case_key', 'switch_id', 'incoming_line', 'outgoing_line',
                           'endpoints', 'normal_state', 'is_tie', 'switch_fields', 'safety', 'supporting_source_refs')}
                example['projection_decision'] = decision
                for category in categories:
                    self.keep_first(self.examples[strategy][category], example, lambda e: (e['case_id'], e['switch_id']))

    def finish(self):
        coverage = {}
        for s in STRATEGIES:
            coverage[s] = dict(self.coverage[s])
            coverage[s]['strategy_name'] = s
            coverage[s]['reachable_transformer_ratio'] = ratio(coverage[s].get('reachable_transformers', 0), coverage[s].get('published_transformers', 0))
        deltas = {s: {k: self.coverage[s][k] - self.coverage['S0'][k] for k in self.coverage[s]} for s in STRATEGIES}
        labels = {'analysis_version': VERSION, 'status': STATUS, 'accepted_topology': False, 'counterfactual_only': True}
        return {
            'strategy_comparison': {**labels, 'total_cases': len(self.case_ids), 'safety_assessments': dict(self.safety),
                'candidate_exclusion_reasons': dict(self.exclusions), 'delta_from_S0': deltas},
            'coverage_by_strategy': {**labels, 'ratio_denominator': 'all published source Transformers', 'strategies': coverage},
            'risk_analysis': {**labels, 'cross_feeder_scope': 'EXACT source Bus region contacts only; global ownership NOT ASSESSABLE',
                'cycle_definition': 'baseline-first deterministic fundamental cycle basis; size in edges including switch internal edges',
                'degree_thresholds': {'switch_port': 2, 'transformer': 1, 'bus_and_head_review_only': 4},
                'strategies': self.risk, 'examples': {s: dict(v) for s, v in self.risk_examples.items()}},
            'tie_switch_analysis': {**labels, 'impact_definition': 'only group vs S0; full strategy minus strategy without group; not additive', 'strategies': self.tie},
            'representative_examples': {**labels, 'selection': 'first 3 sorted(case_id, switch_id) per strategy/category',
                'strategies': {s: {key: self.examples[s][key] for key in ('all', 'projected', 'excluded', 'OPEN', 'UNKNOWN', 'endpoint_conflict')} for s in STRATEGIES}},
        }
