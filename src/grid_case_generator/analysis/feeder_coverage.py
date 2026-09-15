"""Feeder-level observation of E2.2 graphs; no completion or topology rule changes."""
from collections import Counter, defaultdict
from hashlib import sha256

from grid_case_generator.analysis.switch_semantics import SourceMotifIndex, ratio
from grid_case_generator.analysis.switch_projection_analysis import analyze_projection_case, build_graph, graph_coverage
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.models.types import IdentityStatus
from grid_case_generator.validation.topology_switch import reachable

VERSION = 'feeder-coverage-v1'
POLICIES = ('S0', 'SEMANTIC_CONSERVATIVE', 'SEMANTIC_OPTIMISTIC', 'S2', 'S2_NORMAL_ONLY',
            'S2_UNKNOWN_NONCONDUCTING', 'S2_UNKNOWN_CONDUCTING')
REASONS = ('missing_source', 'switch_unknown', 'tie_unresolved', 'topology_disconnected', 'transformer_unreachable')
STATUSES = ('FULL', 'PARTIAL', 'FAILED')
KINDS = ('LINE', 'SWITCH', 'TRANSFORMER')


def group_owner(accounts):
    refs = {a.canonical_ref.entity_id for a in accounts if a.canonical_ref is not None}
    return next(iter(refs)) if len(refs) == 1 else None


def unique_owner(accounts):
    if len(accounts) == 1 and accounts[0].identity_status is IdentityStatus.UNIQUE:
        return group_owner(accounts)
    return None


def switch_state(device):
    return device.normal_state.value if device and device.normal_state else 'UNKNOWN'


def analyze_feeder_case(details, baseline, candidates=None):
    if candidates is None:
        candidates = analyze_projection_case(details, baseline)['candidates']
    candidates = sorted(candidates, key=lambda c: (c['case_id'], c['switch_id']))
    index = SourceMotifIndex(details)
    cid = str(index.case.case_id)
    if cid != baseline.topology.case_id or any(c['case_id'] != cid for c in candidates):
        raise ValueError('feeder analysis case mismatch')
    groups = {kind: [accounts for (k, _), accounts in sorted(index.groups.items()) if k == kind] for kind in (*KINDS, 'FEEDER')}
    totals = {kind: len(groups[kind]) for kind in KINDS}
    states = Counter({s: 0 for s in ('CLOSED', 'OPEN', 'UNKNOWN', 'UNPUBLISHED')})
    types = Counter({s: 0 for s in ('normal', 'tie', 'unknown_type')})
    tie_owners = set()
    for accounts in groups['SWITCH']:
        device = index.devices.get(group_owner(accounts))
        states[switch_state(device) if device else 'UNPUBLISHED'] += 1
        group = 'tie' if device and device.is_tie is True else 'normal' if device and device.is_tie is False else 'unknown_type'
        types[group] += 1
        if group == 'tie': tie_owners.add(group_owner(accounts))
    inventory = {'raw_rows': sum(map(len, groups['SWITCH'])), 'identity_groups': totals['SWITCH'],
                 'published_entities': sum(getattr(r, 'equipment_type', None) == 'SWITCH' for r in index.entities.values()),
                 'normal_state': dict(states), 'is_tie': dict(types), 'structural_candidates': len(candidates),
                 'eligible_normal_state_unknown': sum(c['normal_state'] == 'UNKNOWN' and c['decisions']['S3_A']['projected'] for c in candidates),
                 'semantic_unknown_candidates': sum(c['safety']['assessment'] == 'UNKNOWN' for c in candidates)}
    feeders = []
    unambiguous = len(groups['FEEDER']) == 1 and unique_owner(groups['FEEDER'][0]) is not None
    for accounts in groups['FEEDER']:
        fields = dict(accounts[0].raw_record.fields or ())
        feeders.append({'case_id': cid, 'source_case_key': index.case.source_case_key,
                        'feeder_id': group_owner(accounts), 'source_feeder_id': fields.get('Feeder_ID') or None,
                        'name': fields.get('Feeder_Name') or None,
                        'source_record_refs': sorted(str(a.raw_record.source_record_ref) for a in accounts),
                        'scope': 'SINGLE_FEEDER_SOURCE_CASE' if unambiguous else 'UNRESOLVED_CASE_OWNERSHIP',
                        'switch_count': totals['SWITCH'] if unambiguous else None,
                        'case_scope_switch_count': totals['SWITCH'], 'switch_inventory': inventory})
    policies = {}; cache = {}
    head = baseline.topology.feeder_head_id
    for policy in POLICIES:
        selection = 'S3_A' if policy.startswith('S2_UNKNOWN_') else 'S2'
        chosen = {c['source_entity_ref'].entity_id: c for c in candidates
                  if policy != 'S0' and c['decisions'][selection]['projected']
                  and (policy != 'S2_NORMAL_ONLY' or c['is_tie'] is False)}
        blocked = {owner for owner, c in chosen.items() if policy == 'SEMANTIC_CONSERVATIVE'
                   and c['safety']['assessment'] == 'UNKNOWN'
                   and c['decisions']['S2']['reason'] != 'BASELINE_PRESERVED'
                   and c['normal_state'] == 'CLOSED'}
        assumed = {owner for owner, c in chosen.items() if policy == 'S2_UNKNOWN_CONDUCTING' and c['normal_state'] == 'UNKNOWN'}
        key = tuple(sorted(chosen)), tuple(sorted(blocked)), tuple(sorted(assumed))
        if key not in cache:
            nodes, original_edges = build_graph(index, baseline, chosen)
            edges = [dict(e, conducting=False) if e['kind'] == 'switch' and e['owner'] in blocked else
                     dict(e, conducting=True) if e['kind'] == 'switch' and e['owner'] in assumed else e for e in original_edges]
            adjacency = defaultdict(list)
            for e in edges:
                if e['conducting']:
                    adjacency[e['a']].append((e['b'], e['id'])); adjacency[e['b']].append((e['a'], e['id']))
            seen = reachable(adjacency, head)
            owners = {kind: set() for kind in KINDS}
            for e in edges:
                if e['a'] in seen and e['b'] in seen:
                    owners['LINE' if e['kind'] == 'line' else 'SWITCH'].add(e['owner'])
            owners['TRANSFORMER'] = {node['owner'] for n, node in nodes.items() if n in seen and node['role'] == 'transformer-mv/mv'}
            counts = {kind: sum(unique_owner(accounts) in owners[kind] for accounts in groups[kind]) for kind in KINDS}
            coverage = graph_coverage(nodes, edges, head, totals['SWITCH'], baseline.coverage.counts['published_transformers'])
            strict = 'FULL' if coverage['cases_with_usable_subgraph'] and counts == totals else 'PARTIAL' if coverage['cases_with_usable_subgraph'] else 'FAILED'
            goal = 'FULL' if totals['TRANSFORMER'] > 0 and counts['TRANSFORMER'] == totals['TRANSFORMER'] else 'PARTIAL' if counts['TRANSFORMER'] else 'FAILED'
            unknown = sorted({c['source_entity_ref'].entity_id for c in candidates
                              if c['source_entity_ref'].entity_id not in owners['SWITCH']
                              and ((c['normal_state'] == 'UNKNOWN' and c['decisions']['S3_A']['projected']
                                    and c['source_entity_ref'].entity_id not in assumed)
                                   or c['source_entity_ref'].entity_id in blocked)})
            unresolved_ties = sorted(owner for owner in tie_owners if owner not in owners['SWITCH'])
            tags = []
            if head is None: tags.append('missing_source')
            if unknown: tags.append('switch_unknown')
            if unresolved_ties: tags.append('tie_unresolved')
            if totals['LINE'] == 0 or any(counts[k] < totals[k] for k in ('LINE', 'SWITCH')): tags.append('topology_disconnected')
            if totals['TRANSFORMER'] == 0 or counts['TRANSFORMER'] < totals['TRANSFORMER']: tags.append('transformer_unreachable')
            cache[key] = {'strict_topology_status': strict, 'transformer_goal_status': goal,
                'no_transformer_targets': totals['TRANSFORMER'] == 0, 'totals': totals, 'reachable': counts,
                'transformer_reachable_ratio': ratio(counts['TRANSFORMER'], totals['TRANSFORMER']),
                'coverage': coverage, 'graph_sha256': sha256(canonical_json_bytes({'nodes': nodes, 'edges': edges})).hexdigest(),
                'blocker_tags': tags, 'primary_failure_reason': tags[0] if goal != 'FULL' and tags else None,
                'blocker_evidence': {'unknown_switch_owner_ids': unknown, 'unresolved_tie_owner_ids': unresolved_ties,
                    'uncovered_source_group_counts': {k: totals[k] - counts[k] for k in KINDS},
                    'anchor_status': baseline.coverage.feeder_anchor_status,
                    'transformer_subreason': 'NO_SOURCE_TRANSFORMER_TARGETS' if not totals['TRANSFORMER'] else None},
                'semantic_unknown_blocked_switch_ids': sorted(blocked), 'assumed_conducting_switch_ids': sorted(assumed)}
        policies[policy] = cache[key]
    return {'case_id': cid, 'source_case_key': index.case.source_case_key,
            'feeders': feeders, 'raw_feeder_rows': sum(map(len, groups['FEEDER'])),
            'published_feeders': sum(getattr(r, 'feeder_id', None) is not None for r in index.entities.values()),
            'switch_inventory': inventory, 'policies': policies}


def empty_coverage():
    return {'transformer_goal_status': {s: 0 for s in STATUSES}, 'strict_topology_status': {s: 0 for s in STATUSES},
            'status_cross_table': {}, 'target_full_but_strict_incomplete': 0, 'no_transformer_targets': 0,
            'reachable_transformers': 0, 'source_transformer_groups': 0}


def add_coverage(total, value, count):
    for field in ('transformer_goal_status', 'strict_topology_status'):
        total[field][value[field]] += count
    pair = value['transformer_goal_status'] + '/' + value['strict_topology_status']
    total['status_cross_table'][pair] = total['status_cross_table'].get(pair, 0) + count
    total['target_full_but_strict_incomplete'] += count * (value['transformer_goal_status'] == 'FULL' and value['strict_topology_status'] != 'FULL')
    total['no_transformer_targets'] += count * value['no_transformer_targets']
    # Device totals cover distinct source cases; ambiguous multi-feeder cases do
    # not turn one source target set into several physical copies.
    total['reachable_transformers'] += bool(count) * value['reachable']['TRANSFORMER']
    total['source_transformer_groups'] += bool(count) * value['totals']['TRANSFORMER']


def empty_transition():
    return {k: 0 for k in ('baseline_failed', 'failed_to_full', 'failed_to_partial', 'still_failed',
                           'newly_full', 'strict_newly_full', 'strict_failed_to_full', 'strict_failed_to_partial')}


def transition(before, after):
    failed = before['transformer_goal_status'] == 'FAILED'
    return {'baseline_failed': int(failed),
            'failed_to_full': int(failed and after['transformer_goal_status'] == 'FULL'),
            'failed_to_partial': int(failed and after['transformer_goal_status'] == 'PARTIAL'),
            'still_failed': int(failed and after['transformer_goal_status'] == 'FAILED'),
            'newly_full': int(before['transformer_goal_status'] != 'FULL' and after['transformer_goal_status'] == 'FULL'),
            'strict_newly_full': int(before['strict_topology_status'] != 'FULL' and after['strict_topology_status'] == 'FULL'),
            'strict_failed_to_full': int(before['strict_topology_status'] == 'FAILED' and after['strict_topology_status'] == 'FULL'),
            'strict_failed_to_partial': int(before['strict_topology_status'] == 'FAILED' and after['strict_topology_status'] == 'PARTIAL')}


class FeederSummary:
    def __init__(self):
        self.case_ids = set(); self.raw_ids = set(); self.population = Counter()
        self.coverage = {p: empty_coverage() for p in POLICIES}
        self.case_coverage = {p: empty_coverage() for p in POLICIES}
        self.failure = {p: {scope: {kind: {r: 0 for r in REASONS} for kind in ('primary', 'overlapping_tags')}
                           for scope in ('failed', 'not_full')} for p in POLICIES}
        self.recovery_pairs = {'semantic_relaxation': ('SEMANTIC_CONSERVATIVE', 'SEMANTIC_OPTIMISTIC'),
            **{p: ('S2', p) for p in ('SEMANTIC_OPTIMISTIC', 'S2_UNKNOWN_NONCONDUCTING', 'S2_UNKNOWN_CONDUCTING')}}
        self.recovery = {name: {**empty_transition(),
            'by_primary_failure_reason': {r: empty_transition() for r in REASONS},
            'by_overlapping_failure_tag': {r: empty_transition() for r in REASONS}, 'status_transitions': {}}
            for name in self.recovery_pairs}

    def add(self, result):
        cid = result['case_id']
        if cid in self.case_ids: raise ValueError('duplicate feeder case')
        self.case_ids.add(cid)
        n = len(result['feeders'])
        self.population.update({'source_case_count': 1, 'raw_feeder_rows': result['raw_feeder_rows'],
            'feeder_identity_groups': n, 'published_feeders': result['published_feeders'],
            'cases_without_feeder': int(n == 0), 'cases_with_multiple_feeder_groups': int(n > 1),
            'unassigned_case_switch_groups': result['switch_inventory']['identity_groups'] if n == 0 else 0})
        self.raw_ids.update(f['source_feeder_id'] for f in result['feeders'] if f['source_feeder_id'] is not None)
        for policy, value in result['policies'].items():
            add_coverage(self.coverage[policy], value, n)
            add_coverage(self.case_coverage[policy], value, 1)
            for scope in ('failed', 'not_full'):
                eligible = value['transformer_goal_status'] == 'FAILED' if scope == 'failed' else value['transformer_goal_status'] != 'FULL'
                if eligible:
                    primary = value['primary_failure_reason']
                    if primary is None: raise ValueError('incomplete feeder requires a classification')
                    self.failure[policy][scope]['primary'][primary] += n
                    for reason in value['blocker_tags']: self.failure[policy][scope]['overlapping_tags'][reason] += n
        for name, (base, target) in self.recovery_pairs.items():
            before, after = result['policies'][base], result['policies'][target]
            counts = transition(before, after); report = self.recovery[name]
            for key, value in counts.items(): report[key] += n * value
            pair = before['transformer_goal_status'] + '->' + after['transformer_goal_status']
            report['status_transitions'][pair] = report['status_transitions'].get(pair, 0) + n
            if before['transformer_goal_status'] == 'FAILED':
                for key, value in counts.items():
                    report['by_primary_failure_reason'][before['primary_failure_reason']][key] += n * value
                    for tag in before['blocker_tags']: report['by_overlapping_failure_tag'][tag][key] += n * value

    def finish(self):
        metadata = {'analysis_version': VERSION, 'counterfactual_only': True, 'completion_implemented': False,
                    'main_metric': 'all source Transformer identity groups reachable; empty target is FAILED with explicit flag'}
        population = dict(self.population, distinct_raw_feeder_ids=len(self.raw_ids))
        for policy in POLICIES:
            for target, count in ((self.coverage, self.population['feeder_identity_groups']), (self.case_coverage, len(self.case_ids))):
                target[policy]['full_feeder_ratio'] = ratio(target[policy]['transformer_goal_status']['FULL'], count)
        return {'feeder_coverage': {**metadata, 'population': population, 'policies': self.coverage, 'case_cohort': self.case_coverage},
                'failure_analysis': {**metadata, 'primary_priority': REASONS,
                    'interpretation': 'observed blockers; overlapping tags are not additive or proven root causes', 'policies': self.failure},
                'policy_recovery': {**metadata, 'semantic_relaxation': self.recovery['semantic_relaxation'],
                    'from_S2': {name: value for name, value in self.recovery.items() if name != 'semantic_relaxation'}}}
