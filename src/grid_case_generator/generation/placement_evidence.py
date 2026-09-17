"""D4.1 source-constrained placement evidence; proposal-only, no input mutation.

The slice studies Feeder that own source Line rows but no accepted Line component.
It derives a discrete placement-evidence record per declared Line endpoint, proposes
engineering anchors only where the source structure is unique and case-local, and
represents real source Lines on those anchors. Nothing here approves, applies or edits
source facts, accepted topology v2 or any historical artifact, and no device is
generated.
"""
from collections import Counter, defaultdict
from hashlib import sha256

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.models.proposals import positive_voltage, voltage_compatible
from grid_case_generator.analysis.deterministic_recovery import eligibility
from grid_case_generator.validation.topology_proposals import base_hash

VERSION = '1.0.0'
RULE_VERSION = '1.0.0'
SCOPE = 'PROPOSAL_ONLY_COUNTERFACTUAL'
COMPOSITION = 'ACCEPTED_V2 + D4.1_PLACEMENT_PROPOSALS + D4_BACKBONE_REPLAY'
ACCESS_RULE = 'ACCESSPOINT_ENGINEERING_ANCHOR_V1'
LEAF_RULE = 'SWITCH_LEAF_PLACEMENT_ANCHOR_V1'
SERIES_RULE = 'SWITCH_SERIES_PLACEMENT_ANCHOR_V1'
DEFERRED_RULE = 'DERIVED_SHARED_REFERENCE_JUNCTION_V1'
LINE_RULE = 'PLACEMENT_LINE_REPRESENTATION_V1'
ANCHOR_RULES = (ACCESS_RULE, LEAF_RULE, SERIES_RULE)
DEFERRED_RULES = (DEFERRED_RULE,)
EVIDENCE_CLASSES = ('EXACT_STRUCTURAL_ANCHOR', 'DERIVED_LOCAL_ANCHOR',
                    'ENGINEERING_SHARED_REFERENCE_ANCHOR', 'AMBIGUOUS_ANCHOR',
                    'CONFLICTING_ANCHOR', 'NO_ANCHOR_EVIDENCE')
RESOLVER_STATUSES = ('NO_DECLARATION', 'EXACT_CASE_LOCAL', 'CASE_LOCAL_AMBIGUOUS',
                     'EXTERNAL_DEFINED', 'UNDEFINED_REFERENCE')
FEEDER_STATUSES = ('PLACEMENT_EVIDENCE_SUFFICIENT', 'ACCESSPOINT_POLICY_REQUIRED',
                   'REMOTE_SWITCH_POLICY_REQUIRED', 'NON_UNIQUE_PLACEMENT',
                   'HARD_SOURCE_CONTRADICTION', 'INSUFFICIENT_PLACEMENT_EVIDENCE')
LINE_OUTCOMES = ('LINE_PLACEMENT_PROPOSED', 'LINE_BLOCKED_ACCESSPOINT_POLICY',
                 'LINE_BLOCKED_REMOTE_SWITCH_POLICY', 'LINE_BLOCKED_NON_UNIQUE_PLACEMENT',
                 'LINE_BLOCKED_NO_ANCHOR_EVIDENCE', 'LINE_BLOCKED_HARD_SOURCE_CONTRADICTION',
                 'LINE_ALREADY_REPRESENTED', 'LINE_INCOMPLETE_ENDPOINT_EVIDENCE')
D4_REPLAY_STATUSES = ('STILL_VALID', 'SUPERSEDED_BY_BETTER_PLACEMENT', 'NOW_AMBIGUOUS', 'INVALID')
# Streams the engine fills directly. The three contract reviews are derived once by
# `reviews()`; listing them here as well would emit every review row twice.
REVIEW_STREAMS = ('accesspoint_reviews', 'remote_switch_reviews', 'shared_reference_reviews')
STREAMS = ('line_endpoint_evidence', 'placement_anchors', 'line_component_proposals',
           'rejected_candidates', 'feeder_classification', 'd4_replay')

ID_FIELDS = {'SWITCH': 'Switch_ID', 'LINE': 'Line_ID', 'TRANSFORMER': 'Transformer_ID',
             'BUS': 'Bus_ID', 'ACCESS_POINT': 'AccessPoint_ID', 'STATION': 'Station_ID'}
LINE_ENDPOINTS = ('Line_FromBus', 'Line_ToBus')
SWITCH_ENDPOINTS = ('Switch_FromBus', 'Switch_ToBus')
ACCESS_DECLARATIONS = ('AccessPoint_Bus', 'AccessPoint_Phase', 'AccessPoint_UserType',
                       'AccessPoint_ContractCapacity_kVA')

# Ambiguity classes: the source names several case-local readings, so fail closed.
AMBIGUOUS_ERRORS = ('SWITCH_IDENTITY_NOT_UNIQUE', 'SWITCH_DEGREE_NOT_UNIQUE',
                    'SERIES_INCIDENCE_NOT_PAIRED', 'ACCESSPOINT_IDENTITY_NOT_UNIQUE',
                    'TRANSFORMER_INCIDENCE_NOT_UNIQUE', 'BUS_JUNCTION_NOT_PROJECTED',
                    'COMPETING_ENTITY_TYPE', 'CASE_LOCAL_OUTER_DECLARATION_PRESENT',
                    'AMBIGUOUS_OUTER_DECLARATION', 'DUPLICATE_SIDE_INCIDENCE')
ACCESSPOINT_POLICY_ERRORS = ('ACCESSPOINT_DECLARATION_PRESENT',)
SWITCH_POLICY_ERRORS = ('TIE_OR_UNKNOWN_SWITCH_TYPE', 'KNOWN_SWITCH_STATE_REQUIRED',
                        'CLOSED_EARTHING_AT_ATTACHMENT', 'ALREADY_REPRESENTED_IN_ACCEPTED_V2',
                        'UNSUPPORTED_ANCHOR_ENTITY_TYPE')


def generated_id(kind, *parts):
    return 'd4.1-generated:' + kind + ':' + sha256(canonical_json_bytes([VERSION, *parts])).hexdigest()


def index_accounts(accounts):
    """Case-local raw identity index; a repeated identity stays a whole group."""
    local = defaultdict(list)
    for a in sorted(accounts, key=lambda a: a['raw_record']['source_record_ref']):
        raw = a['raw_record']; fields = dict(raw['fields'] or ())
        key = ID_FIELDS.get(raw['source_file_type'])
        if key and fields.get(key):
            local[fields[key]].append(a)
    return dict(local)


def sole_entity(accounts):
    """Exactly one published, unique, canonically referenced row for one raw id."""
    return accounts[0] if len(accounts) == 1 and accounts[0]['identity_status'] == 'UNIQUE' \
        and accounts[0]['canonical_ref'] else None


def entity_id(account):
    return account['canonical_ref']['entity_id'] if account and account['canonical_ref'] else None


def resolve(value, local, foreign):
    """Exact, case-local, unnormalized resolution of one raw endpoint text."""
    if not value:
        return 'NO_DECLARATION', None
    accounts = local.get(value, ())
    if len(accounts) > 1:
        return 'CASE_LOCAL_AMBIGUOUS', None
    if len(accounts) == 1:
        account = sole_entity(accounts)
        if account is None:
            return 'CASE_LOCAL_AMBIGUOUS', None
        return 'EXACT_CASE_LOCAL', account
    if foreign.get(value):
        return 'EXTERNAL_DEFINED', None
    return 'UNDEFINED_REFERENCE', None


def _terminal_map(terminals):
    groups = defaultdict(list)
    for t in terminals:
        groups[t['equipment_id']].append(t)
    return {k: sorted(v, key=lambda t: (t['terminal_no'], t['terminal_id'])) for k, v in groups.items()}


def _accepted_terminal_targets(projections):
    return {p['source_terminal_ref']['entity_id']: p['derived_target_ids'][0]
            for p in projections
            if p.get('source_terminal_ref') and p['projection_status'] == 'PROJECTED'
            and p['derived_target_ids']}


def _accepted_owners(model):
    return {n['source_entity_ref']['entity_id'] for n in model['base_nodes']
            if (n.get('source_entity_ref') or {}).get('entity_id')}


class CaseEvidence:
    """Everything D4.1 derives for one Case. Inputs are read, never written."""

    def __init__(self, x, foreign=None):
        self.x = x
        self.c = x['accepted']
        self.src = x['source']
        self.foreign = dict(foreign or {})
        self.case_id = self.c['case_id']
        self.feeder_id = sorted(f['feeder_id'] for f in self.c['feeders'])[0] if len(self.c['feeders']) == 1 else None
        self.local = index_accounts(self.src['accounts'])
        self.terminals = _terminal_map(self.src['terminals'])
        self.accepted_targets = _accepted_terminal_targets(self.src['projections'])
        self.accepted_owners = _accepted_owners(self.c)
        self.nodes = {n['node_id']: n for n in self.c['base_nodes']}
        self.nominal = self.c['nominal_voltage_kv']
        self.gate = self._gate_reasons()
        self.blocks = self._state_blocks()
        self.rows = {k: [] for k in STREAMS}
        self.shared_reviews = []
        self.anchors = {}
        self.port_of = {}
        self.nodes_out = []
        self.edges_out = []
        self.line_rows = []
        self.proposals = []
        self.graph_edges = []
        self.parallel_withdrawal = []
        self.withdrawn = None
        self._load_lines()

    # -- gates -------------------------------------------------------------

    def _gate_reasons(self):
        reasons = set()
        if len(self.c['feeders']) != 1:
            reasons.add('NON_UNIQUE_FEEDER')
        if self.c['hard_blockers'] or any(
                r['primary_class'] == 'HARD_SOURCE_CONTRADICTION' for r in eligibility(self.c)):
            reasons.add('HARD_SOURCE_CONTRADICTION')
        if not self.c['head_id'] or self.c['head_id'] not in self.nodes:
            reasons.add('NO_HEAD')
        try:
            positive_voltage(self.nominal)
        except ValueError:
            reasons.add('INVALID_MV_VOLTAGE')
        if any(n['case_id'] != self.case_id for n in self.c['base_nodes']) or \
                any(e['case_id'] != self.case_id for e in self.c['base_edges']):
            reasons.add('CROSS_CASE_CONNECTION')
        return sorted(reasons)

    def _state_blocks(self):
        """Raw endpoint texts that a CLOSED earthing or an OPEN cut forbids as an anchor."""
        blocks = {'CLOSED_EARTHING': set(), 'OPEN_CUT': set()}
        for s in self.c['state_constraints']:
            for value in (s.get('raw_endpoints') or {}).values():
                if not value:
                    continue
                if s['kind'] == 'EARTHING_SWITCH' and s['state'] == 'CLOSED':
                    blocks['CLOSED_EARTHING'].add(value)
                if s['state'] == 'OPEN':
                    blocks['OPEN_CUT'].add(value)
        return blocks

    def _terminal(self, owner, side):
        matches = [t for t in self.terminals.get(owner, ()) if t['terminal_no'] == side]
        return matches[0] if len(matches) == 1 else None

    # -- inventory ---------------------------------------------------------

    def _load_lines(self):
        records = []
        for a in self.src['accounts']:
            raw = a['raw_record']
            if raw['source_file_type'] != 'LINE':
                continue
            fields = dict(raw['fields'] or ())
            if fields.get('Line_ID') and sole_entity(self.local.get(fields['Line_ID'], ())):
                records.append(a)
        self.lines = sorted(records, key=lambda a: a['raw_record']['source_record_ref'])

    def _represented_lines(self):
        return {e['source_entity_ref']['entity_id'] for e in self.c['base_edges']
                if e['kind'] == 'LINE' and (e.get('source_entity_ref') or {}).get('entity_id')}

    def _endpoint_row(self, line, side):
        raw = line['raw_record']; fields = dict(raw['fields'] or ())
        value = fields.get(LINE_ENDPOINTS[side - 1], '')
        status, account = resolve(value, self.local, self.foreign)
        terminal = self._terminal(entity_id(line), side)
        row = {'case_id': self.case_id, 'feeder_id': self.feeder_id,
               'source_line_id': fields.get('Line_ID'),
               'source_line_record_ref': raw['source_record_ref'],
               'endpoint_side': side, 'raw_endpoint_value': value,
               'terminal_ref_status': terminal['source_ref_status'] if terminal else 'ABSENT',
               'resolver_status': status,
               'resolved_source_kind': account['raw_record']['source_file_type'] if account else None,
               'resolved_source_id': entity_id(account),
               'candidate_anchor_ids': [], 'source_incidence_witnesses': [raw['source_record_ref']],
               'voltage_evidence': None, 'switch_witnesses': [], 'accesspoint_witnesses': [],
               'identity_status': account['identity_status'] if account else None,
               'ownership_status': 'CASE_LOCAL' if account else
                                   'EXTERNAL' if status == 'EXTERNAL_DEFINED' else 'UNRESOLVED',
               'operating_state_constraint': None, 'competing_evidence': [],
               'contradiction_refs': [], 'placement_evidence_class': 'NO_ANCHOR_EVIDENCE'}
        if terminal is None:
            row['contradiction_refs'] = ['TERMINAL_CONTRACT_INCOMPLETE']
            return row, ('INCOMPLETE', 'TERMINAL_CONTRACT_INCOMPLETE')
        target = self.accepted_targets.get(terminal['terminal_id'])
        if target and target in self.nodes:
            node = self.nodes[target]
            row.update(candidate_anchor_ids=[target], voltage_evidence=node.get('voltage_kv'),
                       placement_evidence_class='EXACT_STRUCTURAL_ANCHOR',
                       source_incidence_witnesses=sorted(
                           {raw['source_record_ref']}
                           | set(self.c['region_source_refs'].get(target, []))))
            return row, ('ACCEPTED_NODE', target)
        if status != 'EXACT_CASE_LOCAL':
            if status == 'CASE_LOCAL_AMBIGUOUS':
                row['placement_evidence_class'] = 'AMBIGUOUS_ANCHOR'
                row['competing_evidence'] = sorted(a['raw_record']['source_record_ref']
                                                   for a in self.local.get(value, ()))
            return row, ('BLOCKED', status)
        if terminal['source_ref_status'] != 'EXACT':
            row['contradiction_refs'] = ['TERMINAL_REFERENCE_' + terminal['source_ref_status']]
            row['placement_evidence_class'] = ('AMBIGUOUS_ANCHOR'
                                               if terminal['source_ref_status'] == 'AMBIGUOUS'
                                               else 'NO_ANCHOR_EVIDENCE')
            return row, ('BLOCKED', 'TERMINAL_REFERENCE_' + terminal['source_ref_status'])
        return row, ('CANDIDATE', value, account)

    # -- anchors -----------------------------------------------------------

    def _switch_anchor(self, raw_id):
        accounts = self.local.get(raw_id, ())
        account = sole_entity(accounts)
        if account is None or account['raw_record']['source_file_type'] != 'SWITCH':
            return None, 'SWITCH_IDENTITY_NOT_UNIQUE'
        incident = self.incidence.get(raw_id, [])
        fields = dict(account['raw_record']['fields'] or ())
        reasons = set(self.gate)
        state = (fields.get('Switch_NormalState') or '').upper()
        if (fields.get('Switch_IsTie') or '').upper() != 'FALSE':
            reasons.add('TIE_OR_UNKNOWN_SWITCH_TYPE')
        if state not in ('OPEN', 'CLOSED'):
            reasons.add('KNOWN_SWITCH_STATE_REQUIRED')
        if entity_id(account) in self.accepted_owners:
            reasons.add('ALREADY_REPRESENTED_IN_ACCEPTED_V2')
        if raw_id in self.blocks['CLOSED_EARTHING']:
            reasons.add('CLOSED_EARTHING_AT_ATTACHMENT')
        for key in SWITCH_ENDPOINTS:
            status, _ = resolve(fields.get(key, ''), self.local, self.foreign)
            if status == 'EXACT_CASE_LOCAL':
                reasons.add('CASE_LOCAL_OUTER_DECLARATION_PRESENT')
            elif status == 'CASE_LOCAL_AMBIGUOUS':
                reasons.add('AMBIGUOUS_OUTER_DECLARATION')
        sides = [side for _, side in incident]
        if sides.count(1) > 1 or sides.count(2) > 1:
            reasons.add('DUPLICATE_SIDE_INCIDENCE')
        rule = ports = None
        if len(incident) == 1:
            rule, ports = LEAF_RULE, ('ATTACH', 'UNBOUND')
        elif len(incident) == 2 and sorted(sides) == [1, 2]:
            rule, ports = SERIES_RULE, ('IN', 'OUT')
        error = None
        if rule is None:
            error = 'SWITCH_DEGREE_NOT_UNIQUE' if len(incident) >= 3 else 'SERIES_INCIDENCE_NOT_PAIRED'
        return {'rule_id': rule, 'ports': ports, 'account': account, 'fields': fields, 'state': state,
                'incident': incident, 'reasons': sorted(reasons), 'error': error}, error

    def _accesspoint_anchor(self, raw_id):
        accounts = self.local.get(raw_id, ())
        account = sole_entity(accounts)
        if account is None or account['raw_record']['source_file_type'] != 'ACCESS_POINT':
            return None, 'ACCESSPOINT_IDENTITY_NOT_UNIQUE'
        fields = dict(account['raw_record']['fields'] or ())
        reasons = set(self.gate)
        if any(fields.get(k) for k in ACCESS_DECLARATIONS):
            reasons.add('ACCESSPOINT_DECLARATION_PRESENT')
        if entity_id(account) in self.accepted_owners:
            reasons.add('ALREADY_REPRESENTED_IN_ACCEPTED_V2')
        if raw_id in self.blocks['CLOSED_EARTHING']:
            reasons.add('CLOSED_EARTHING_AT_ATTACHMENT')
        return {'rule_id': ACCESS_RULE, 'ports': ('JUNCTION',), 'account': account, 'fields': fields,
                'state': None, 'incident': self.incidence.get(raw_id, []),
                'reasons': sorted(reasons), 'error': None}, None

    def _anchor_objects(self, raw_id, anchor):
        """Deterministic ports and internal Switch edge for one engineering anchor."""
        owner = entity_id(anchor['account'])
        common = {'case_id': self.case_id, 'feeder_id': self.feeder_id,
                  'source_entity_ref': anchor['account']['canonical_ref'], 'rule_id': anchor['rule_id'],
                  'rule_version': RULE_VERSION, 'evidence_class': 'RULE_INFERRED',
                  'voltage_basis_node_id': self.c['head_id'], 'scope': SCOPE, 'stage': 'PROPOSED',
                  'approved': False, 'applied': False}
        ports = [generated_id('port', self.case_id, self.feeder_id, anchor['rule_id'], owner, role)
                 for role in anchor['ports']]
        nodes = [dict(common, node_id=nid, kind='PLACEMENT_ANCHOR_PORT', port_role=role,
                      voltage_kv=self.nominal, transformer_key=None)
                 for nid, role in zip(ports, anchor['ports'])]
        edges = []
        if anchor['state'] is not None:
            edges.append(dict(common, edge_id=generated_id('switch', self.case_id, self.feeder_id,
                                                           anchor['rule_id'], owner, 'internal'),
                              a=ports[0], b=ports[1], kind='SWITCH',
                              conducting=anchor['state'] == 'CLOSED',
                              raw_source_state=anchor['fields'].get('Switch_NormalState')))
        return ports, nodes, edges

    def _attach_port(self, raw_id, side):
        anchor = self.anchors[raw_id]
        ports = self.port_of[raw_id]
        if anchor['rule_id'] == ACCESS_RULE:
            return ports[0]
        if anchor['rule_id'] == SERIES_RULE:
            return ports[0] if side == 2 else ports[1]
        return ports[0]  # a single incident Line claims no orientation

    # -- driver ------------------------------------------------------------

    def analyse(self):
        self.incidence = defaultdict(list)
        endpoints = {}
        for line in self.lines:
            record = {'line': line, 'endpoints': {}}
            for side in (1, 2):
                row, outcome = self._endpoint_row(line, side)
                record['endpoints'][side] = {'row': row, 'outcome': outcome}
                if outcome[0] == 'CANDIDATE':
                    self.incidence[outcome[1]].append(
                        (line['raw_record']['source_record_ref'], side))
            endpoints[line['raw_record']['source_record_ref']] = record
        self.endpoints = endpoints
        candidates = sorted(self.incidence)
        self._review_anchors(candidates)
        self._collect_lines()
        self._parallel_gate()
        self._cycle_gate()
        self._prune_anchors()
        self._emit_lines()
        self._classify_feeder()
        self.graph_edges = self.edges_out + self._line_edge_objects()
        return {'rows': self.rows, 'anchors': self.anchors, 'nodes': self.nodes_out,
                'edges': self.edges_out, 'graph_edges': self.graph_edges,
                'proposals': self.proposals, 'line_rows': self.line_rows,
                'gate': self.gate, 'withdrawn': self.withdrawn}

    def _line_edge_objects(self):
        """The counterfactual Line branches; they reuse the real source Line identity."""
        return [{'edge_id': p['edge_id'], 'case_id': self.case_id, 'feeder_id': self.feeder_id,
                 'a': p['endpoints'][0]['anchor_id'], 'b': p['endpoints'][1]['anchor_id'],
                 'kind': 'LINE', 'conducting': True, 'evidence_class': 'RULE_INFERRED',
                 'rule_id': p['rule_id'], 'rule_version': RULE_VERSION,
                 'source_entity_ref': p['source_line_ref'], 'proposal_id': p['proposal_id'],
                 'stage': 'PROPOSED', 'approved': False, 'applied': False, 'scope': SCOPE}
                for p in self.proposals]

    def _linked(self, nodes, edges, conducting, left, right):
        ids = [n['node_id'] for n in nodes]
        parent = {n: n for n in ids}

        def root(n):
            while parent[n] != n:
                parent[n] = parent[parent[n]]; n = parent[n]
            return n
        for e in edges:
            if conducting and not e['conducting']:
                continue
            parent[root(e['a'])] = root(e['b'])
        return root(left) == root(right)

    def _graph_rank(self, nodes, edges, conducting):
        """Cycle rank of the counterfactual graph; parallel edges count, as in D4."""
        ids = [n['node_id'] for n in nodes]
        active = [e for e in edges if not conducting or e['conducting']]
        parent = {n: n for n in ids}

        def root(n):
            while parent[n] != n:
                parent[n] = parent[parent[n]]; n = parent[n]
            return n
        for e in active:
            parent[root(e['a'])] = root(e['b'])
        return len(active) - len(ids) + len({root(n) for n in ids})

    def _parallel_gate(self):
        """Never choose between source Lines that declare the identical connection.

        Two distinct Line identities naming the same anchor pair are either one circuit
        declared twice or two parallel circuits; the source does not say which. Every
        member of such a group is withdrawn, so no ordering ever picks a representative.
        """
        groups = defaultdict(list)
        for proposal in self.proposals:
            key = tuple(sorted(e['anchor_id'] for e in proposal['endpoints']))
            groups[key].append(proposal)
        duplicates = [{'anchor_ids': list(k), 'line_refs': sorted(p['source_line_record_ref'] for p in v)}
                      for k, v in sorted(groups.items()) if len(v) > 1]
        if not duplicates:
            return
        withdrawn = {ref for group in duplicates for ref in group['line_refs']}
        for ref in sorted(withdrawn):
            outcome, reasons, proposal = self.line_decisions[ref]
            self.line_decisions[ref] = ('LINE_BLOCKED_NON_UNIQUE_PLACEMENT',
                                        ['PARALLEL_DUPLICATE_DECLARATION_NOT_REPRESENTABLE'], None)
        self.proposals = [p for p in self.proposals
                          if p['source_line_record_ref'] not in withdrawn]
        self.rows['rejected_candidates'].append(
            {'case_id': self.case_id, 'feeder_id': self.feeder_id,
             'withdrawal_reason': 'PARALLEL_DUPLICATE_DECLARATION_NOT_REPRESENTABLE',
             'duplicate_groups': duplicates,
             'withdrawn_line_refs': sorted(withdrawn), 'evidence_class': None,
             'approved': False, 'applied': False, 'scope': SCOPE})
        self.parallel_withdrawal = sorted(withdrawn)

    def _prune_anchors(self):
        """Keep generated objects only for anchors a surviving Line still attaches to.

        An anchor whose every Line was withdrawn would otherwise leave disconnected
        generated ports in the counterfactual graph.
        """
        attached = {e['anchor_id'] for p in self.proposals for e in p['endpoints']
                    if e['anchor_origin'] != 'ACCEPTED_NODE'}
        kept = []
        for anchor in self.rows['placement_anchors']:
            if attached & set(anchor['port_ids']):
                kept.append(anchor)
            elif anchor['structural_status'] == 'PROPOSED':
                anchor['structural_status'] = 'WITHDRAWN_UNUSED_ANCHOR'
        self.rows['placement_anchors'] = kept
        surviving = {port for anchor in kept for port in anchor['port_ids']}
        self.nodes_out = [n for n in self.nodes_out if n['node_id'] in surviving]
        self.edges_out = [e for e in self.edges_out if e['a'] in surviving and e['b'] in surviving]

    def _cycle_gate(self):
        """Fail closed when the representation would invent connectivity.

        Several declared source Lines can close a loop, including two Lines that declare
        the identical connection. The derived graph must not choose one member of such a
        group, so the whole Case is withdrawn rather than resolved by ordering.
        """
        self.withdrawn = None
        if not self.proposals:
            return
        nodes = self.c['base_nodes'] + self.nodes_out
        line_edges = [{'a': p['endpoints'][0]['anchor_id'], 'b': p['endpoints'][1]['anchor_id'],
                       'conducting': True} for p in self.proposals]
        edges = self.c['base_edges'] + self.edges_out + line_edges
        before = (self._graph_rank(self.c['base_nodes'], self.c['base_edges'], True),
                  self._graph_rank(self.c['base_nodes'], self.c['base_edges'], False))
        after = (self._graph_rank(nodes, edges, True), self._graph_rank(nodes, edges, False))
        reason = None
        if after != before:
            reason = 'PLACEMENT_WOULD_CREATE_CYCLE'
        else:
            for edge in self.c['base_edges']:
                if edge['conducting']:
                    continue
                if self._linked(self.c['base_nodes'], self.c['base_edges'], True, edge['a'], edge['b']):
                    continue
                if self._linked(nodes, edges, True, edge['a'], edge['b']):
                    reason = 'PLACEMENT_WOULD_BYPASS_OPEN_CUT'
                    break
        if reason is None:
            return
        self.withdrawn = {'reason': reason, 'cycle_rank_before': before[0],
                          'cycle_rank_after': after[0], 'conducting_rank_before': before[1],
                          'conducting_rank_after': after[1],
                          'withdrawn_line_refs': sorted(p['source_line_record_ref'] for p in self.proposals),
                          'withdrawn_anchor_ids': sorted(a['anchor_id']
                                                         for a in self.rows['placement_anchors'])}
        for anchor in self.rows['placement_anchors']:
            anchor['structural_status'] = 'WITHDRAWN_BY_CYCLE_GATE'
        self.proposals = []
        self.nodes_out = []
        self.edges_out = []

    def _review_anchors(self, candidates):
        for raw_id in candidates:
            accounts = self.local.get(raw_id, ())
            kinds = sorted({a['raw_record']['source_file_type'] for a in accounts})
            if len(kinds) > 1:
                self.anchors[raw_id] = {'rule_id': None, 'ports': None, 'account': sole_entity(accounts),
                                        'fields': {}, 'state': None,
                                        'incident': sorted(self.incidence[raw_id]),
                                        'reasons': ['COMPETING_ENTITY_TYPE'], 'error': 'COMPETING_ENTITY_TYPE'}
                continue
            if kinds[0] == 'ACCESS_POINT':
                anchor, error = self._accesspoint_anchor(raw_id)
            elif kinds[0] == 'SWITCH':
                anchor, error = self._switch_anchor(raw_id)
            else:
                anchor, error = None, {'TRANSFORMER': 'TRANSFORMER_INCIDENCE_NOT_UNIQUE',
                                       'BUS': 'BUS_JUNCTION_NOT_PROJECTED'}.get(
                    kinds[0], 'UNSUPPORTED_ANCHOR_ENTITY_TYPE')
            if anchor is None:
                anchor = {'rule_id': None, 'ports': None, 'account': sole_entity(accounts), 'fields': {},
                          'state': None, 'incident': sorted(self.incidence[raw_id]),
                          'reasons': [error], 'error': error}
            self.anchors[raw_id] = anchor
            if anchor['rule_id'] and not anchor['reasons']:
                ports, nodes, edges = self._anchor_objects(raw_id, anchor)
                self.port_of[raw_id] = ports
                self.nodes_out.extend(nodes)
                self.edges_out.extend(edges)
                self.rows['placement_anchors'].append(
                    self._anchor_record(raw_id, anchor, ports, nodes, edges))
        for raw_id in sorted(set(candidates) | set(self.referenced_external())):
            self.shared_reviews.append(self._shared_review(raw_id))

    def referenced_external(self):
        out = set()
        for record in self.endpoints.values():
            for side in (1, 2):
                row = record['endpoints'][side]['row']
                if row['resolver_status'] in ('EXTERNAL_DEFINED', 'UNDEFINED_REFERENCE') \
                        and row['raw_endpoint_value']:
                    out.add(row['raw_endpoint_value'])
        return out

    def _anchor_record(self, raw_id, anchor, ports, nodes, edges):
        return {'anchor_id': ports[0], 'anchor_type': anchor['rule_id'], 'rule_id': anchor['rule_id'],
                'rule_version': RULE_VERSION, 'case_id': self.case_id, 'feeder_id': self.feeder_id,
                'source_id': raw_id, 'source_entity_ref': anchor['account']['canonical_ref'],
                'source_refs': [anchor['account']['raw_record']['source_record_ref']],
                'voltage_kv': self.nominal, 'voltage_source': 'DERIVED_MV_DOMAIN',
                'port_ids': ports, 'port_roles': list(anchor['ports']),
                'internal_edge_id': edges[0]['edge_id'] if edges else None,
                'operating_state': anchor['state'],
                'conducting': None if anchor['state'] is None else anchor['state'] == 'CLOSED',
                'incident_line_refs': sorted({ref for ref, _ in anchor['incident']}),
                'degree': len(anchor['incident']), 'evidence_class': 'RULE_INFERRED',
                'structural_status': 'PROPOSED', 'stage': 'PROPOSED', 'approved': False,
                'applied': False, 'scope': SCOPE}

    def _review_common(self, raw_id):
        accounts = self.local.get(raw_id, ())
        account = sole_entity(accounts)
        incident = sorted(self.anchors.get(raw_id, {}).get('incident', self.incidence.get(raw_id, [])))
        return {'case_id': self.case_id, 'feeder_id': self.feeder_id, 'source_id': raw_id,
                'source_entity_ref': account['canonical_ref'] if account else None,
                'identity_status': account['identity_status'] if account else
                                   'CASE_LOCAL_AMBIGUOUS' if accounts else 'EXTERNAL_OR_UNDEFINED',
                'source_refs': sorted(a['raw_record']['source_record_ref'] for a in accounts),
                'incident_line_refs': sorted({ref for ref, _ in incident}),
                'incident_sides': sorted(side for _, side in incident), 'degree': len(incident),
                'evidence_class': 'UNRESOLVED', 'stage': 'PROPOSED', 'approved': False,
                'applied': False, 'scope': SCOPE, 'disposition': 'NEEDS_REVIEW', 'reason_codes': []}

    def _collect_lines(self):
        represented = self._represented_lines()
        self.line_decisions = {}
        for witness in sorted(self.endpoints):
            record = self.endpoints[witness]
            line = record['line']
            if entity_id(line) in represented:
                self.line_decisions[witness] = ('LINE_ALREADY_REPRESENTED',
                                                ['ACCEPTED_LINE_EDGE_PRESENT'], None)
                continue
            if self.gate:
                self.line_decisions[witness] = self._gate_outcome()
                continue
            resolved, blocked = [], []
            for side in (1, 2):
                outcome = record['endpoints'][side]['outcome']
                row = record['endpoints'][side]['row']
                if outcome[0] == 'ACCEPTED_NODE':
                    resolved.append({'side': side, 'anchor_id': outcome[1],
                                     'anchor_origin': 'ACCEPTED_NODE',
                                     'raw_endpoint_value': row['raw_endpoint_value']})
                    continue
                if outcome[0] == 'CANDIDATE':
                    anchor = self.anchors[outcome[1]]
                    if anchor['rule_id'] and not anchor['reasons']:
                        resolved.append({'side': side,
                                         'anchor_id': self._attach_port(outcome[1], side),
                                         'anchor_origin': anchor['rule_id'],
                                         'raw_endpoint_value': row['raw_endpoint_value']})
                        continue
                    blocked.append(self._rejection_outcome(anchor))
                    continue
                blocked.append(self._blocked_outcome(row))
            if len(resolved) != 2:
                outcome = blocked[0][0] if blocked else 'LINE_INCOMPLETE_ENDPOINT_EVIDENCE'
                self.line_decisions[witness] = (outcome,
                                                sorted({b[1] for b in blocked}) or [outcome], None)
                continue
            proposal = self._propose_line(record, resolved)
            if proposal['reasons']:
                self.line_decisions[witness] = ('LINE_BLOCKED_NON_UNIQUE_PLACEMENT',
                                                proposal['reasons'], None)
                continue
            self.proposals.append(proposal)
            self.line_decisions[witness] = ('LINE_PLACEMENT_PROPOSED', [], proposal)

    def _emit_lines(self):
        if self.withdrawn:
            for witness in sorted(self.line_decisions):
                outcome, reasons, proposal = self.line_decisions[witness]
                if outcome == 'LINE_PLACEMENT_PROPOSED':
                    self.line_decisions[witness] = ('LINE_BLOCKED_NON_UNIQUE_PLACEMENT',
                                                    ['PLACEMENT_WOULD_CREATE_CYCLE'], None)
        for witness in sorted(self.endpoints):
            record = self.endpoints[witness]
            for side in (1, 2):
                self.rows['line_endpoint_evidence'].append(self._final_endpoint_row(record, side))
            outcome, reasons, proposal = self.line_decisions[witness]
            self._line_row(record, outcome, reasons, proposal)
        if self.withdrawn:
            self.rows['rejected_candidates'].append(
                dict(self.withdrawn, case_id=self.case_id, feeder_id=self.feeder_id,
                     evidence_class=None, approved=False, applied=False, scope=SCOPE))

    def _final_endpoint_row(self, record, side):
        row = dict(record['endpoints'][side]['row'])
        outcome = record['endpoints'][side]['outcome']
        if outcome[0] == 'CANDIDATE':
            raw_id = outcome[1]
            anchor = self.anchors[raw_id]
            if row['resolved_source_kind'] == 'SWITCH':
                row['switch_witnesses'] = [self.local[raw_id][0]['raw_record']['source_record_ref']]
                row['operating_state_constraint'] = anchor['fields'].get('Switch_NormalState')
            if row['resolved_source_kind'] == 'ACCESS_POINT':
                row['accesspoint_witnesses'] = [self.local[raw_id][0]['raw_record']['source_record_ref']]
            if anchor['rule_id'] and not anchor['reasons']:
                row['placement_evidence_class'] = 'ENGINEERING_SHARED_REFERENCE_ANCHOR'
            elif anchor['error'] in ('SWITCH_DEGREE_NOT_UNIQUE', 'SERIES_INCIDENCE_NOT_PAIRED',
                                     'SWITCH_IDENTITY_NOT_UNIQUE', 'ACCESSPOINT_IDENTITY_NOT_UNIQUE',
                                     'TRANSFORMER_INCIDENCE_NOT_UNIQUE'):
                row['placement_evidence_class'] = 'AMBIGUOUS_ANCHOR'
                row['competing_evidence'] = sorted(
                    a['raw_record']['source_record_ref'] for a in self.local.get(raw_id, ()))
            else:
                row['placement_evidence_class'] = 'CONFLICTING_ANCHOR'
            row['candidate_anchor_ids'] = sorted(
                n['node_id'] for n in self.nodes_out
                if (n.get('source_entity_ref') or {}).get('entity_id') == entity_id(anchor['account']))
            row['contradiction_refs'] = sorted(set(row['contradiction_refs']) | set(anchor['reasons']))
        elif outcome[0] == 'BLOCKED':
            row['contradiction_refs'] = sorted(set(row['contradiction_refs']) | {outcome[1]})
        return row

    def _gate_outcome(self):
        """A Case-level gate blocks every Line; ownership and identity read as ambiguity."""
        reasons = list(self.gate)
        if set(self.gate) & {'NON_UNIQUE_FEEDER', 'CROSS_CASE_CONNECTION'}:
            outcome = 'LINE_BLOCKED_NON_UNIQUE_PLACEMENT'
        elif 'NO_HEAD' in self.gate:
            outcome = 'LINE_BLOCKED_NO_ANCHOR_EVIDENCE'
        else:
            outcome = 'LINE_BLOCKED_HARD_SOURCE_CONTRADICTION'
        return (outcome, reasons, None)

    def _blocked_outcome(self, row):
        status = row['resolver_status']
        if row['placement_evidence_class'] == 'AMBIGUOUS_ANCHOR':
            return ('LINE_BLOCKED_NON_UNIQUE_PLACEMENT', 'AMBIGUOUS_CASE_LOCAL_REFERENCE')
        return ('LINE_BLOCKED_NO_ANCHOR_EVIDENCE',
                {'EXTERNAL_DEFINED': 'CROSS_CASE_REFERENCE_NOT_FOLLOWED',
                 'NO_DECLARATION': 'NO_ENDPOINT_DECLARATION'}.get(status, 'UNDEFINED_REFERENCE'))

    def _rejection_outcome(self, anchor):
        """Classify a declined anchor by the strongest evidence-backed reason it carries."""
        for reason in sorted(anchor.get('reasons') or ()):
            if reason in ACCESSPOINT_POLICY_ERRORS or reason in AMBIGUOUS_ERRORS \
                    or reason in SWITCH_POLICY_ERRORS:
                return self._error_outcome(reason)
        return self._error_outcome(anchor.get('error') or 'NO_ANCHOR_EVIDENCE')

    def _error_outcome(self, error):
        if error in ACCESSPOINT_POLICY_ERRORS:
            return ('LINE_BLOCKED_ACCESSPOINT_POLICY', error)
        if error in AMBIGUOUS_ERRORS:
            return ('LINE_BLOCKED_NON_UNIQUE_PLACEMENT', error)
        if error in SWITCH_POLICY_ERRORS:
            return ('LINE_BLOCKED_REMOTE_SWITCH_POLICY', error)
        return ('LINE_BLOCKED_NO_ANCHOR_EVIDENCE', error)

    def _propose_line(self, record, resolved):
        line = record['line']; fields = dict(line['raw_record']['fields'] or ())
        reasons = set()
        endpoints = sorted(resolved, key=lambda e: e['side'])
        for item in endpoints:
            node = self.nodes.get(item['anchor_id'])
            if node:
                try:
                    if not voltage_compatible(node['voltage_kv'], self.nominal):
                        reasons.add('INCOMPATIBLE_VOLTAGE')
                except ValueError:
                    reasons.add('INCOMPATIBLE_VOLTAGE')
        if endpoints[0]['anchor_id'] == endpoints[1]['anchor_id']:
            reasons.add('COLLAPSED_ENDPOINTS')
        owner = entity_id(line)
        return {'proposal_id': generated_id('line-proposal', self.case_id, self.feeder_id, LINE_RULE, owner),
                'case_id': self.case_id, 'feeder_id': self.feeder_id,
                'source_line_ref': line['canonical_ref'], 'source_line_id': fields.get('Line_ID'),
                'source_line_record_ref': line['raw_record']['source_record_ref'],
                'endpoints': endpoints, 'reasons': sorted(reasons),
                'edge_id': generated_id('line', self.case_id, self.feeder_id, LINE_RULE, owner),
                'kind': 'LINE', 'conducting': True, 'rule_id': LINE_RULE,
                'rule_version': RULE_VERSION, 'evidence_class': 'RULE_INFERRED',
                'stage': 'PROPOSED', 'approved': False, 'applied': False, 'scope': SCOPE,
                'base_graph_sha256': base_hash(self.c),
                'assumptions': ['DERIVED_PLACEMENT_REPRESENTATION', 'NOT_A_NEW_LINE_DEVICE',
                                'NOT_A_SOURCE_CONNECTION']}

    def _line_row(self, record, outcome, reasons, proposal):
        line = record['line']; fields = dict(line['raw_record']['fields'] or ())
        row = {'case_id': self.case_id, 'feeder_id': self.feeder_id,
               'source_line_id': fields.get('Line_ID'),
               'source_line_record_ref': line['raw_record']['source_record_ref'],
               'outcome': outcome, 'reasons': sorted(set(reasons)),
               'endpoint_values': [record['endpoints'][s]['row']['raw_endpoint_value'] for s in (1, 2)],
               'endpoint_evidence_class': [record['endpoints'][s]['row']['placement_evidence_class']
                                           for s in (1, 2)],
               'proposal_id': proposal['proposal_id'] if proposal else None,
               'edge_id': proposal['edge_id'] if proposal else None,
               'evidence_class': 'RULE_INFERRED' if proposal else None,
               'approved': False, 'applied': False, 'scope': SCOPE}
        if proposal:
            # The proposal stream carries the whole object, not just the decision row.
            row = dict(proposal, outcome=row['outcome'],
                       endpoint_values=row['endpoint_values'],
                       endpoint_evidence_class=row['endpoint_evidence_class'])
        self.line_rows.append(row)
        self.rows['line_component_proposals' if proposal else 'rejected_candidates'].append(row)

    def _classify_feeder(self):
        proposals = {p['source_line_record_ref'] for p in self.proposals}
        blocked = [r for r in self.line_rows if r['outcome'] != 'LINE_PLACEMENT_PROPOSED']
        reasons = sorted({x for r in blocked for x in r['reasons']})
        outcomes = Counter(r['outcome'] for r in blocked)
        overlapping = sorted(set(outcomes))
        if self.gate and 'HARD_SOURCE_CONTRADICTION' in self.gate:
            primary = 'HARD_SOURCE_CONTRADICTION'
        elif proposals:
            primary = 'PLACEMENT_EVIDENCE_SUFFICIENT'
        elif outcomes.get('LINE_BLOCKED_NON_UNIQUE_PLACEMENT'):
            primary = 'NON_UNIQUE_PLACEMENT'
        elif outcomes.get('LINE_BLOCKED_ACCESSPOINT_POLICY'):
            primary = 'ACCESSPOINT_POLICY_REQUIRED'
        elif outcomes.get('LINE_BLOCKED_REMOTE_SWITCH_POLICY'):
            primary = 'REMOTE_SWITCH_POLICY_REQUIRED'
        elif outcomes.get('LINE_BLOCKED_HARD_SOURCE_CONTRADICTION'):
            primary = 'HARD_SOURCE_CONTRADICTION'
        else:
            primary = 'INSUFFICIENT_PLACEMENT_EVIDENCE'
        row = {'case_id': self.case_id, 'feeder_id': self.feeder_id,
               'source_case_key': self.c['source_case_key'],
               'd3_primary': self._d3_primary(), 'primary_status': primary,
               'overlapping_outcomes': overlapping,
               'overlapping_reasons': reasons,
               'source_line_count': sum(1 for a in self.src['accounts']
                                        if a['raw_record']['source_file_type'] == 'LINE'),
               'published_line_count': len(self.lines),
               'represented_line_count': len(self._represented_lines()),
               'proposed_line_count': len(self.proposals),
               'blocked_line_count': len(blocked),
               'proposed_anchor_count': 0 if self.withdrawn else len(self.rows['placement_anchors']),
               'proposal_ids': sorted(p['proposal_id'] for p in self.proposals),
               'withdrawal': self.withdrawn,
               'approved': False, 'applied': False, 'scope': SCOPE}
        self.rows['feeder_classification'].append(row)
        self.feeder_row = row

    def _d3_primary(self):
        for r in eligibility(self.c):
            if r['feeder_id'] == self.feeder_id:
                return r['primary_class']
        return None

    def _shared_review(self, raw_id):
        row = self._review_common(raw_id)
        anchor = self.anchors.get(raw_id)
        row.update(review_kind='SHARED_REFERENCE_JUNCTION', rule_id=DEFERRED_RULE,
                   rule_version=RULE_VERSION,
                   deterministic_rationale=('Shared raw text proves the same reference string, not an '
                                            'electrical junction; unbounded-degree anchors stay disabled'),
                   deferred_rules={DEFERRED_RULE: 'SHARED_REFERENCE_JUNCTION_SEMANTICS_NOT_PROVEN'})
        if anchor and anchor['rule_id'] and not anchor['reasons']:
            row['outcome'] = 'NARROW_RULE_ENABLED'
            row['reason_codes'] = []
        else:
            row['outcome'] = anchor['error'] if anchor else (
                'CROSS_CASE_REFERENCE_NOT_FOLLOWED' if self.foreign.get(raw_id) else 'UNDEFINED_REFERENCE')
            row['reason_codes'] = [row['outcome']]
        return row

    def _accesspoint_review(self, raw_id):
        row = self._review_common(raw_id)
        anchor = self.anchors.get(raw_id, {})
        row.update(review_kind='ACCESS_POINT_PLACEMENT', rule_id=ACCESS_RULE, rule_version=RULE_VERSION,
                   accesspoint_fields={k: v for k, v in (anchor.get('fields') or {}).items()
                                       if k != 'AccessPoint_ID'},
                   deterministic_rationale=('Unique case-local AccessPoint named by source Line endpoints; '
                                            'its electrical junction role is derived, never a source-confirmed Bus'),
                   reason_codes=list(anchor.get('reasons', [])))
        if anchor.get('rule_id') and not anchor.get('reasons'):
            row.update(disposition='ELIGIBLE', evidence_class='RULE_INFERRED')
        elif anchor.get('error') in ('ACCESSPOINT_IDENTITY_NOT_UNIQUE', 'COMPETING_ENTITY_TYPE'):
            row.update(disposition='REJECTED', reason_codes=sorted(set(row['reason_codes'])
                                                                   | {anchor['error']}))
        return row

    def _switch_review(self, raw_id):
        row = self._review_common(raw_id)
        anchor = self.anchors.get(raw_id, {})
        if not anchor.get('error') and not anchor.get('reasons') and anchor.get('rule_id'):
            row.update(disposition='ELIGIBLE', evidence_class='RULE_INFERRED')
        elif anchor.get('error') in ('SWITCH_IDENTITY_NOT_UNIQUE', 'SWITCH_DEGREE_NOT_UNIQUE',
                                     'SERIES_INCIDENCE_NOT_PAIRED'):
            row.update(disposition='REJECTED')
        row.update(review_kind='REMOTE_SWITCH_PORT_PLACEMENT',
                   rule_id=anchor.get('rule_id'), rule_version=RULE_VERSION,
                   raw_state=(anchor.get('fields') or {}).get('Switch_NormalState'),
                   raw_is_tie=(anchor.get('fields') or {}).get('Switch_IsTie'),
                   raw_endpoints={k: (anchor.get('fields') or {}).get(k, '') for k in SWITCH_ENDPOINTS},
                   outer_declaration_status=sorted(
                       resolve((anchor.get('fields') or {}).get(k, ''), self.local, self.foreign)[0]
                       for k in SWITCH_ENDPOINTS),
                   deterministic_rationale=('Unique case-local ordinary Switch with known state and no '
                                            'case-local outer declaration; orientation is claimed only when '
                                            'two Lines pair by endpoint side'),
                   reason_codes=sorted(set(anchor.get('reasons', []))
                                       | ({anchor['error']} if anchor.get('error') else set())))
        return row

    def reviews(self):
        out = {'accesspoint_reviews': [], 'remote_switch_reviews': [], 'shared_reference_reviews': []}
        for raw_id in sorted(self.anchors):
            account = sole_entity(self.local.get(raw_id, ()))
            kind = account['raw_record']['source_file_type'] if account else None
            if kind == 'ACCESS_POINT':
                out['accesspoint_reviews'].append(self._accesspoint_review(raw_id))
            if kind == 'SWITCH':
                out['remote_switch_reviews'].append(self._switch_review(raw_id))
        out['shared_reference_reviews'] = sorted(self.shared_reviews,
                                                  key=lambda r: r['source_id'])
        return out
