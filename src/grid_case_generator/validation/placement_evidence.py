"""Independent D4.1 validator: re-derives every claim from persisted evidence.

It does not import the placement engine's conclusions. Anchors, namespace, ownership,
voltage, endpoint text, device absence, cycles and OPEN cuts are all re-derived from the
Case input and the emitted objects alone.
"""
from collections import defaultdict

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.models.proposals import positive_voltage, voltage_compatible
from grid_case_generator.validation.topology_proposals import base_hash

GENERATED_PREFIX = 'd4.1-generated:'
DEVICE_KINDS = ('TRANSFORMER', 'LOAD', 'DER', 'SYNTHETIC_DEVICE')
ID_FIELDS = {'SWITCH': 'Switch_ID', 'LINE': 'Line_ID', 'TRANSFORMER': 'Transformer_ID',
             'BUS': 'Bus_ID', 'ACCESS_POINT': 'AccessPoint_ID', 'STATION': 'Station_ID'}
LINE_ENDPOINTS = ('Line_FromBus', 'Line_ToBus')


def _components(ids, edges, conducting):
    parent = {n: n for n in ids}

    def root(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]; n = parent[n]
        return n
    for e in edges:
        if conducting and not e.get('conducting'):
            continue
        parent[root(e['a'])] = root(e['b'])
    groups = defaultdict(set)
    for n in ids:
        groups[root(n)].add(n)
    return groups


def _linked(ids, edges, conducting, a, b):
    for group in _components(ids, edges, conducting).values():
        if a in group and b in group:
            return True
    return False


def _cycle_rank(ids, edges, conducting):
    active = [e for e in edges if not conducting or e.get('conducting')]
    return len(active) - len(ids) + len(_components(ids, edges, conducting))


def validate_case(x, ev):
    """Return the independent structural verdict for one Case."""
    c = x['accepted']; errors = set()
    base_nodes = {n['node_id']: n for n in c['base_nodes']}
    base_edges = {e['edge_id']: e for e in c['base_edges']}
    nodes = {n['node_id']: n for n in ev.nodes_out}
    edges = {e['edge_id']: e for e in ev.edges_out}
    feeder_ids = {f['feeder_id'] for f in c['feeders']}
    source_rows = {a['raw_record']['source_record_ref']: a for a in x['source']['accounts']}
    local = defaultdict(list)
    for a in x['source']['accounts']:
        raw = a['raw_record']; fields = dict(raw['fields'] or ())
        key = ID_FIELDS.get(raw['source_file_type'])
        if key and fields.get(key):
            local[fields[key]].append(a)
    if nodes.keys() & base_nodes.keys() or edges.keys() & base_edges.keys():
        errors.add('GENERATED_ID_COLLISION')
    for name in (*nodes, *edges):
        if not name.startswith(GENERATED_PREFIX):
            errors.add('UNNAMESPACED_GENERATED_OBJECT')
    for obj in [*ev.nodes_out, *ev.edges_out, *ev.rows['placement_anchors'], *ev.proposals]:
        if obj['case_id'] != c['case_id'] or obj.get('feeder_id') not in feeder_ids:
            errors.add('CROSS_CASE_CONNECTION')
        if obj.get('evidence_class') != 'UNRESOLVED':
            errors.add('UNAPPROVED_RULE_PROVENANCE')
        if obj.get('approved') is not False or obj.get('applied') is not False:
            errors.add('INVALID_LIFECYCLE')
        if obj.get('scope') != 'PROPOSAL_ONLY_COUNTERFACTUAL':
            errors.add('INVALID_LIFECYCLE')
    if c['hard_blockers']:
        errors.add('HARD_SOURCE_CONTRADICTION')
    try:
        positive_voltage(c['nominal_voltage_kv'])
    except ValueError:
        errors.add('INVALID_MV_VOLTAGE')
    all_nodes = {**base_nodes, **nodes}
    for node in ev.nodes_out:
        try:
            if not voltage_compatible(node['voltage_kv'], c['nominal_voltage_kv']):
                errors.add('INCOMPATIBLE_VOLTAGE')
        except ValueError:
            errors.add('INVALID_VOLTAGE')
        if node.get('transformer_key'):
            errors.add('UNREVIEWED_DEVICE_GENERATION')
    for obj in [*ev.nodes_out, *ev.edges_out, *ev.proposals]:
        if obj.get('kind') in DEVICE_KINDS or obj.get('device_id') or obj.get('devices'):
            errors.add('UNREVIEWED_DEVICE_GENERATION')
    anchors = {a['anchor_id']: a for a in ev.rows['placement_anchors']}
    for anchor in anchors.values():
        accounts = local.get(anchor['source_id'], ())
        if len(accounts) != 1 or accounts[0]['identity_status'] != 'UNIQUE' \
                or not accounts[0]['canonical_ref']:
            errors.add('AMBIGUOUS_IDENTITY')
        elif accounts[0]['canonical_ref'] != anchor['source_entity_ref']:
            errors.add('SOURCE_PROVENANCE_MISMATCH')
        if not all(pid.startswith(GENERATED_PREFIX) for pid in anchor['port_ids']):
            errors.add('UNNAMESPACED_GENERATED_OBJECT')
        if anchor['rule_id'] not in ('ACCESSPOINT_ENGINEERING_ANCHOR_V1',
                                     'SWITCH_LEAF_PLACEMENT_ANCHOR_V1',
                                     'SWITCH_SERIES_PLACEMENT_ANCHOR_V1'):
            errors.add('UNREVIEWED_PLACEMENT_RULE')
        if anchor['internal_edge_id'] and anchor['internal_edge_id'] not in edges:
            errors.add('MISSING_ANCHOR_BRANCH')
    for edge in edges.values():
        if edge['kind'] != 'SWITCH':
            errors.add('UNEXPECTED_GENERATED_BRANCH')
        if edge['a'] not in all_nodes or edge['b'] not in all_nodes:
            errors.add('DANGLING_GENERATED_REFERENCE')
        if not isinstance(edge.get('conducting'), bool):
            errors.add('UNREVIEWED_STATE')
    for proposal in ev.proposals:
        if proposal['base_graph_sha256'] != base_hash(c):
            errors.add('STALE_ACCEPTED_BASE')
        if len(proposal['endpoints']) != 2:
            errors.add('NONMINIMAL_LINE_REPRESENTATION')
        for endpoint in proposal['endpoints']:
            node = all_nodes.get(endpoint['anchor_id'])
            if node is None:
                errors.add('DANGLING_GENERATED_REFERENCE')
                continue
            try:
                if not voltage_compatible(node['voltage_kv'], c['nominal_voltage_kv']):
                    errors.add('INCOMPATIBLE_VOLTAGE')
            except ValueError:
                errors.add('INVALID_VOLTAGE')
        row = source_rows.get(proposal['source_line_record_ref'])
        if row is None:
            errors.add('SOURCE_PROVENANCE_MISMATCH')
            continue
        fields = dict(row['raw_record']['fields'] or ())
        if row['raw_record']['source_file_type'] != 'LINE' \
                or fields.get('Line_ID') != proposal['source_line_id']:
            errors.add('SOURCE_PROVENANCE_MISMATCH')
        for endpoint, key in zip(proposal['endpoints'], LINE_ENDPOINTS):
            if endpoint['raw_endpoint_value'] != fields.get(key, ''):
                errors.add('SOURCE_ENDPOINT_TEXT_CHANGED')
        if proposal['endpoints'][0]['anchor_id'] == proposal['endpoints'][1]['anchor_id']:
            errors.add('COLLAPSED_ENDPOINTS')
        if any((e.get('source_entity_ref') or {}).get('entity_id')
               == proposal['source_line_ref']['entity_id'] for e in c['base_edges']):
            errors.add('DUPLICATE_SOURCE_LINE')
    # Graph invariants on the counterfactual the proposal set would create.
    ids = list({*base_nodes, *nodes})
    combined = [*c['base_edges'], *ev.edges_out]
    line_edges = [{'a': p['endpoints'][0]['anchor_id'], 'b': p['endpoints'][1]['anchor_id'],
                   'conducting': True} for p in ev.proposals]
    after_edges = combined + line_edges
    for conducting in (True, False):
        if _cycle_rank(ids, after_edges, conducting) != _cycle_rank(ids, c['base_edges'], conducting):
            errors.add('NEW_CYCLE')
    for edge in c['base_edges']:
        if edge['conducting']:
            continue
        if _linked(ids, c['base_edges'], True, edge['a'], edge['b']):
            continue
        if _linked(ids, after_edges, True, edge['a'], edge['b']):
            errors.add('OPEN_CUT_BYPASSED')
    for state in c['state_constraints']:
        if state['kind'] == 'EARTHING_SWITCH' and state['state'] == 'CLOSED':
            texts = {v for v in (state.get('raw_endpoints') or {}).values() if v}
            if texts & {a['source_id'] for a in ev.rows['placement_anchors']}:
                errors.add('CLOSED_EARTHING_AT_ATTACHMENT')
        if state['state'] == 'OPEN':
            texts = {v for v in (state.get('raw_endpoints') or {}).values() if v}
            if texts & {p['source_line_record_ref'] for p in ev.proposals}:
                errors.add('UNRESOLVED_OPEN_CUT')
    return {'case_id': c['case_id'], 'feeder_id': ev.feeder_id, 'reasons': sorted(errors),
            'structural_status': 'REJECTED' if errors else 'PASS',
            'evidence_class': 'UNRESOLVED', 'scope': 'PROPOSAL_ONLY_COUNTERFACTUAL',
            'rule_version': '1.1.0', 'approved': False, 'applied': False,
            'open_cuts_preserved': 'OPEN_CUT_BYPASSED' not in errors,
            'source_endpoint_text_preserved': 'SOURCE_ENDPOINT_TEXT_CHANGED' not in errors,
            'accepted_base_bound': 'STALE_ACCEPTED_BASE' not in errors,
            'digest': canonical_json_bytes({'case': c['case_id'], 'reasons': sorted(errors)}).hex()[:32]}
