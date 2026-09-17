"""D3 exact-evidence overlay. No source edits, engineering placement or S2 import."""
from collections import defaultdict
from hashlib import sha256

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.models.proposals import positive_voltage, voltage_compatible
from grid_case_generator.validation.topology_proposals import measure_graph

VERSION = 'deterministic-topology-recovery-v1'
RULE_VERSION = '1.0.0'
SERIES = 'SERIES_EXACT_DIRECT_V2'
LEAF = 'LEAF_SWITCH_REPRESENTATION_V2'
ID_FIELDS = {'SWITCH': 'Switch_ID', 'LINE': 'Line_ID', 'TRANSFORMER': 'Transformer_ID',
             'BUS': 'Bus_ID', 'STATION': 'Station_ID', 'ACCESS_POINT': 'AccessPoint_ID',
             'FEEDER': 'Feeder_ID', 'DISCONNECTOR': 'Disconnector_ID',
             'EARTHING_SWITCH': 'EarthingSwitch_ID', 'LOAD': 'Load_ID', 'DER': 'DER_ID'}
ENDPOINTS = {'LINE': ('Line_FromBus', 'Line_ToBus'), 'SWITCH': ('Switch_FromBus', 'Switch_ToBus'),
             'TRANSFORMER': ('Transformer_FromBus', 'Transformer_ToBus'),
             'ACCESS_POINT': ('AccessPoint_Bus',), 'DISCONNECTOR': ('Disconnector_FromBus', 'Disconnector_ToBus'),
             'EARTHING_SWITCH': ('EarthingSwitch_Bus',), 'LOAD': ('Load_Bus',), 'DER': ('DER_Bus',)}
FAMILIES = ('SERIES_SWITCH_RECOVERY', 'SWITCH_TERMINAL_REPRESENTATION',
            'REFERENCED_TRANSFORMER_RECOVERY', 'ACCESS_POINT_RECOVERY',
            'MULTI_INCOMING_TRANSFORMER_REVIEW', 'OTHER_DETERMINISTIC_REVIEW')


def derived_id(kind, cid, owner, role):
    return 'deterministic-v2:' + sha256(canonical_json_bytes(
        [VERSION, RULE_VERSION, kind, cid, owner, role])).hexdigest()


def recover_case(c):
    """Consume the explicit case evidence contract, return a new graph and all decisions."""
    base = c['base']; cid = base['case_id']; top = c['topology']
    if top['case_id'] != cid or any(t['case_id'] != cid for t in c['terminals']):
        raise ValueError('D3 source/topology case mismatch')
    rows = sorted(c['accounts'], key=lambda a: a['raw_record']['source_record_ref'])
    if any(a['raw_record']['source_case_key'] != base['source_case_key'] for a in rows):
        raise ValueError('D3 raw source case mismatch')
    groups = defaultdict(list); lookup = defaultdict(list); incidence = defaultdict(list)
    incoming = defaultdict(list); terms = defaultdict(list)
    for t in c['terminals']:
        terms[(t['source_record_ref'], t['terminal_no'])].append(t)
    malformed = False
    for a in rows:
        r = a['raw_record']; kind = r['source_file_type']; f = dict(r['fields'] or [])
        rid = f.get(ID_FIELDS.get(kind, ''))
        if kind in ID_FIELDS:
            groups[(kind, rid or r['source_record_ref'])].append(a)
        if rid: lookup[rid].append(a)
        if kind == 'LINE' and r['fields'] is None: malformed = True
        for number, field in enumerate(ENDPOINTS.get(kind, ()), 1):
            value = f.get(field)
            if value:
                incoming[value].append((a, number, field))
                if kind == 'LINE': incidence[value].append((a, number))

    def unique(a):
        r = a['raw_record']; f = dict(r['fields'] or [])
        key = f.get(ID_FIELDS.get(r['source_file_type'], ''))
        return bool(key and len(lookup[key]) == 1 and a['identity_status'] == 'UNIQUE' and a['canonical_ref'])

    def endpoint(a, number):
        ts = terms[(a['raw_record']['source_record_ref'], number)]
        if len(ts) != 1: return None
        t = ts[0]; ref = t['resolved_source_ref']
        candidates = lookup.get(t['raw_connected_ref'], ())
        if (t['source_ref_status'] != 'EXACT' or ref is None or len(candidates) != 1
                or not unique(candidates[0]) or candidates[0]['canonical_ref'] != ref):
            return None
        return candidates[0]

    def owner(a):
        return a['canonical_ref']['entity_id'] if a['canonical_ref'] else None

    def voltage_ok(a):
        field = {'BUS':'Bus_BaseKV', 'TRANSFORMER':'Transformer_HighVoltage_kV'}.get(a['raw_record']['source_file_type'])
        if field is None: return True
        raw = dict(a['raw_record']['fields'] or []).get(field)
        # Missing voltage follows the existing E2 BUS rule; it is a derived MV domain.
        if not raw: return True
        try: return voltage_compatible(raw, base['nominal_voltage_kv'])
        except ValueError: return False

    mappings = {p['source_terminal_ref']['entity_id']: p['derived_target_ids'][0]
                for p in c['projections'] if p['source_terminal_ref'] and
                p['projection_status'] == 'PROJECTED' and p['derived_target_ids']}
    candidates = []; additions = []; accepted = {}
    baseline_owner = {n['source_entity_ref']['entity_id'] for n in top['nodes']
                      if n['role'].startswith('switch-port/')}
    hard = sorted({b['code'] for b in base['hard_blockers']})
    conflicts = sorted({r for b in base['hard_blockers'] for r in b['source_refs']})
    targets = {t['source_entity_id']: t for t in base['targets'] if t['source_entity_id']}
    projected_t = {n['transformer_key'] for n in base['base_nodes'] if n.get('transformer_key')}
    for (kind, key), accounts in sorted(groups.items()):
        if kind not in ('SWITCH', 'TRANSFORMER', 'ACCESS_POINT'): continue
        # A repeated identity remains a whole evidence group, never a selected row.
        a = accounts[0] if len(accounts) == 1 else None
        raw_id = dict(a['raw_record']['fields'] or []).get(ID_FIELDS[kind]) if a else key
        inc = incidence.get(raw_id, ())
        refs = incoming.get(raw_id, ())
        if kind == 'TRANSFORMER' and not refs and not any(
                dict(x['raw_record']['fields'] or []).get(k) for x in accounts for k in ENDPOINTS[kind]):
            continue
        line_groups = {dict(x['raw_record']['fields'] or []).get('Line_ID') or x['raw_record']['source_record_ref'] for x, _ in inc}
        family = ('SERIES_SWITCH_RECOVERY' if kind == 'SWITCH' and len(line_groups) == 2 else
                  'SWITCH_TERMINAL_REPRESENTATION' if kind == 'SWITCH' and len(line_groups) == 1 else
                  'OTHER_DETERMINISTIC_REVIEW' if kind == 'SWITCH' else
                  'MULTI_INCOMING_TRANSFORMER_REVIEW' if kind == 'TRANSFORMER' and len(line_groups) > 1 else
                  'REFERENCED_TRANSFORMER_RECOVERY' if kind == 'TRANSFORMER' else 'ACCESS_POINT_RECOVERY')
        oid = owner(a) if a else None
        f = dict(a['raw_record']['fields'] or []) if a else {}
        evidence = {x['raw_record']['source_record_ref']: x['raw_record'] for x in accounts}
        for x, _, _ in refs: evidence[x['raw_record']['source_record_ref']] = x['raw_record']
        source_refs = sorted(evidence)
        rid = SERIES if family == 'SERIES_SWITCH_RECOVERY' else LEAF if family == 'SWITCH_TERMINAL_REPRESENTATION' else family + '_V1'
        state = (f.get('Switch_NormalState') or '').upper() if kind == 'SWITCH' else None
        variant = family
        if family == 'SERIES_SWITCH_RECOVERY' and a:
            ins = [x for x, number in inc if number == 2]
            outs = [x for x, number in inc if number == 1]
            if f.get('Switch_IsTie', '').upper() != 'FALSE': variant = 'SERIES_TIE_OR_UNKNOWN_TYPE'
            elif len(ins) != 1 or len(outs) != 1: variant = 'SERIES_INVALID_INCIDENCE'
            else:
                ep = [endpoint(ins[0],1), endpoint(outs[0],2), endpoint(a,1), endpoint(a,2)]
                if any(x is None for x in ep): variant = 'SERIES_UNRESOLVED_ENDPOINT'
                elif ep[0]['canonical_ref'] == ep[2]['canonical_ref'] and ep[1]['canonical_ref'] == ep[3]['canonical_ref']:
                    variant = 'SERIES_EXACT_DIRECT'
                elif ep[0]['canonical_ref'] == ep[3]['canonical_ref'] and ep[1]['canonical_ref'] == ep[2]['canonical_ref']:
                    variant = 'SERIES_EXACT_REVERSE'
                else: variant = 'SERIES_DIFFERENT_OR_PARTIAL_ENDPOINT'
            if variant != 'SERIES_EXACT_DIRECT': rid = variant + '_REVIEW_V1'
        row = {'candidate_id': derived_id('candidate', cid, key, family), 'case_id': cid,
               'feeder_ids': [x['feeder_id'] for x in base['feeders']], 'family': family,
               'rule_variant': variant, 'rule_id': rid, 'rule_version': RULE_VERSION, 'source_entity_ref': a['canonical_ref'] if a else None,
               'source_id': raw_id, 'source_kind': kind, 'status': 'NEEDS_REVIEW', 'reason_codes': [],
               'supporting_source_refs': source_refs, 'conflict_refs': conflicts,
               'source_records': [evidence[k] for k in sorted(evidence)],
               'line_incidence_count': len(line_groups),
               'reference_composition': targets.get(oid, {}).get('reference_composition'),
               'raw_state': f.get('Switch_NormalState') if kind == 'SWITCH' else None,
               'source_state': state, 'structural_inclusion': False, 'conducting': False,
               'identity_safe': bool(a and unique(a)), 'voltage_compatibility': 'UNASSESSED',
               'state_preserved': True, 'case_local': True, 'source_endpoint_text_preserved': True,
               'evidence_class': 'UNRESOLVED', 'derived_ids': []}
        reasons = row['reason_codes']
        if not a or not unique(a): reasons.append('IDENTITY_NOT_UNIQUE')
        if hard: reasons.extend(hard)
        if reasons: row['status'] = 'REJECTED'
        elif kind == 'TRANSFORMER':
            if targets.get(oid, {}).get('target_key') in projected_t:
                row['status'] = 'BASELINE_PRESERVED'; reasons.append('EXISTING_V1_MV_ATTACHMENT')
            else: reasons.append('MULTIPLE_POSSIBLE_PORTS' if len(line_groups) > 1 else 'DECLARED_REFERENCE_PORT_SEMANTICS_UNPROVEN')
        elif kind == 'ACCESS_POINT': reasons.append('ACCESS_POINT_PHYSICAL_ROLE_UNPROVEN')
        elif oid in baseline_owner:
            row['status'] = 'BASELINE_PRESERVED'; reasons.append('EXISTING_V1_SWITCH')
        else:
            if family == 'OTHER_DETERMINISTIC_REVIEW': reasons.append('INCIDENCE_NOT_SUPPORTED')
            if malformed: reasons.append('MALFORMED_LINE_EVIDENCE')
            if state not in ('OPEN', 'CLOSED'): reasons.append('KNOWN_STATE_REQUIRED')
            if f.get('Switch_IsTie', '').upper() != 'FALSE': reasons.append('ORDINARY_SWITCH_REQUIRED')
            try: positive_voltage(base['nominal_voltage_kv'])
            except ValueError: reasons.append('MV_VOLTAGE_REQUIRED')
            if not base['head_id']: reasons.append('ACCEPTED_HEAD_REQUIRED')
            count = 2 if family == 'SERIES_SWITCH_RECOVERY' else 1
            if len(inc) != count or len(line_groups) != count or any(not unique(x) for x, _ in inc):
                reasons.append('FULL_UNIQUE_INCIDENCE_REQUIRED')
            ins = [x for x, number in inc if number == 2]
            outs = [x for x, number in inc if number == 1]
            if len(ins) != 1 or len(outs) != count - 1: reasons.append('INCIDENCE_DIRECTION_REQUIRED')
            if any(endpoint(x, number) is None or owner(endpoint(x, number)) != oid for x, number in inc):
                reasons.append('EXACT_INNER_REFERENCE_REQUIRED')
            outer = []
            if len(ins) == 1 and len(outs) == count - 1:
                pairs = [(ins[0], 1, 1)] + ([(outs[0], 2, 2)] if count == 2 else [])
                for line, number, sw_number in pairs:
                    left, right = endpoint(line, number), endpoint(a, sw_number)
                    if left is None or right is None:
                        reasons.append('EXACT_OUTER_REFERENCE_REQUIRED'); continue
                    outer.extend([left, right])
                    lf = dict(line['raw_record']['fields'])
                    raw_left = lf['Line_FromBus' if number == 1 else 'Line_ToBus']
                    raw_right = f['Switch_FromBus' if sw_number == 1 else 'Switch_ToBus']
                    if raw_left != raw_right or left['canonical_ref'] != right['canonical_ref']:
                        reasons.append('DIRECT_DECLARATIONS_REQUIRED')
                    if owner(left) == oid: reasons.append('SELF_ENDPOINT_UNPROVEN')
                    if left['raw_record']['source_file_type'] not in ('BUS', 'STATION', 'SWITCH', 'TRANSFORMER'):
                        reasons.append('UNSUPPORTED_OUTER_ENTITY_TYPE')
                if count == 1 and f.get('Switch_ToBus'): reasons.append('REMOTE_ENDPOINT_NOT_EMPTY')
                if count == 2 and f.get('Switch_FromBus') == f.get('Switch_ToBus'):
                    reasons.append('COLLAPSED_ENDPOINTS_UNPROVEN')
            for x in outer:
                evidence[x['raw_record']['source_record_ref']] = x['raw_record']
            if outer and not all(voltage_ok(x) for x in outer): reasons.append('INCOMPATIBLE_VOLTAGE')
            row['voltage_compatibility'] = 'INCOMPATIBLE' if 'INCOMPATIBLE_VOLTAGE' in reasons else 'DERIVED_MV_DOMAIN' if not reasons else 'UNRESOLVED'
            if not reasons:
                row.update(status='ACCEPTED', structural_inclusion=True, conducting=state == 'CLOSED', evidence_class='RULE_INFERRED')
                accepted[oid] = row
                ports = [derived_id('port', cid, oid, role) for role in ('in', 'out')]
                common = {'case_id': cid, 'source_entity_ref': a['canonical_ref'], 'rule_id': rid,
                          'rule_version': RULE_VERSION, 'evidence_class': 'RULE_INFERRED',
                          'candidate_id': row['candidate_id'], 'supporting_source_refs': sorted(set(evidence) |
                              {ref for feeder in base['feeders'] for ref in feeder['source_record_refs']}),
                          'voltage_basis_node_id': base['head_id']}
                for nid, role in zip(ports, ('IN', 'OUT' if count == 2 else 'UNBOUND')):
                    additions.append(dict(common, node_id=nid, kind='SWITCH_PORT', port_role=role,
                                          voltage_kv=base['nominal_voltage_kv'], transformer_key=None))
                additions.append(dict(common, edge_id=derived_id('switch', cid, oid, 'internal'),
                                      a=ports[0], b=ports[1], conducting=state == 'CLOSED', kind='SWITCH',
                                      raw_source_state=f['Switch_NormalState']))
                row['derived_ids'] = ports + [additions[-1]['edge_id']]
                for line, number in inc:
                    t, = terms[(line['raw_record']['source_record_ref'], number)]
                    mappings[t['terminal_id']] = ports[0 if number == 2 else 1]
                reasons.append('EXACT_DIRECT_SERIES' if count == 2 else 'EXACT_LEAF_UNBOUND_REMOTE')
            elif any(x in reasons for x in ('INCOMPATIBLE_VOLTAGE', 'FULL_UNIQUE_INCIDENCE_REQUIRED', 'MALFORMED_LINE_EVIDENCE')):
                row['status'] = 'REJECTED'
        if row['status'] == 'REJECTED':
            row['conflict_refs'] = sorted(set(row['conflict_refs']) | set(evidence))
        row['supporting_source_refs'] = sorted(evidence)
        row['source_records'] = [evidence[k] for k in sorted(evidence)]
        row['reason_codes'] = sorted(set(reasons))
        candidates.append(row)
    # Reconstruct only actual source Lines with two accepted terminal mappings.
    existing_lines = {e['source_entity_ref']['entity_id'] for e in top['branches'] if e['role'] == 'line/connection'}
    ns = {n['node_id']: n for n in base['base_nodes']}
    ns.update({n['node_id']: n for n in additions if 'node_id' in n})
    for (kind, key), accounts in sorted(groups.items()):
        if kind != 'LINE' or len(accounts) != 1: continue
        a, = accounts; oid = owner(a)
        if not unique(a) or oid in existing_lines or hard: continue
        ts = [terms[(a['raw_record']['source_record_ref'], number)] for number in (1, 2)]
        if any(len(t) != 1 for t in ts): continue
        ends = [mappings.get(t[0]['terminal_id']) for t in ts]
        if any(n not in ns for n in ends): continue
        refs = [t[0]['resolved_source_ref'] for t in ts]
        dependencies = [accepted[r['entity_id']] for r in refs if r and r['entity_id'] in accepted]
        if not dependencies: continue
        if not voltage_compatible(ns[ends[0]]['voltage_kv'], ns[ends[1]]['voltage_kv']):
            raise ValueError('D3 accepted terminal voltage contradiction')
        additions.append({'edge_id': derived_id('line', cid, oid, 'connection'), 'case_id': cid,
            'a': ends[0], 'b': ends[1], 'kind': 'LINE', 'conducting': True,
            'source_entity_ref': a['canonical_ref'], 'rule_id': 'EXACT_LINE_ENDPOINTS_V2',
            'rule_version': RULE_VERSION, 'evidence_class': 'RULE_INFERRED',
            'candidate_id': derived_id('line-candidate', cid, oid, 'connection'),
            'supporting_source_refs': sorted({a['raw_record']['source_record_ref'],
                *(r for d in dependencies for r in d['supporting_source_refs'])}),
            'dependency_candidate_ids': sorted(d['candidate_id'] for d in dependencies)})
    additions.sort(key=lambda x: x.get('node_id', x.get('edge_id')))
    after = dict(base, base_nodes=sorted([*base['base_nodes'], *(x for x in additions if 'node_id' in x)], key=lambda n:n['node_id']),
                 base_edges=sorted([*base['base_edges'], *(x for x in additions if 'edge_id' in x)], key=lambda e:e['edge_id']))
    if len(ns) != len(after['base_nodes']) or len({e['edge_id'] for e in after['base_edges']}) != len(after['base_edges']):
        raise ValueError('duplicate deterministic graph identity')
    if any(e['a'] not in ns or e['b'] not in ns for e in after['base_edges']):
        raise ValueError('dangling deterministic graph endpoint')
    coverage = {'case_id': cid, 'feeder_count': len(base['feeders']), 'source_state_preserved': True}
    for mode in ('physical', 'conducting'):
        before_m = measure_graph(base, physical=mode == 'physical')
        after_m = measure_graph(after, physical=mode == 'physical')
        coverage[mode] = {'before': before_m, 'after': after_m,
                         'delta': {k: after_m[k] - before_m[k] for k in ('reachable_lines', 'reachable_transformers', 'components', 'cycle_rank')}}
        totals = {k: sum(kind == k for kind, _ in groups) for k in ('LINE', 'SWITCH', 'TRANSFORMER')}
        # Strict topology fullness also requires every device identity covered and reachable.
        for label, model, metrics in (('before', base, before_m), ('after', after, after_m)):
            metrics['active_edge_count'] = sum(mode == 'physical' or e['conducting'] for e in model['base_edges'])
            if metrics['cycle_rank'] != metrics['active_edge_count'] - metrics['node_count'] + metrics['components']:
                raise ValueError('D3 cycle rank does not satisfy m-n+c')
            represented = len([e for e in model['base_edges'] if e['kind'] == 'SWITCH'])
            full = (metrics['reachable_lines'] == totals['LINE'] and totals['LINE'] > 0 and
                    metrics['reachable_transformers'] == totals['TRANSFORMER'] and represented == totals['SWITCH'] and
                    metrics['components'] == 1 and not hard)
            metrics['topology_coverage_scope'] = 'SOURCE_LINE_SWITCH_TRANSFORMER_ONLY'
            metrics['topology_coverage'] = 'FULL' if full else 'PARTIAL' if metrics['reachable_lines'] else 'FAILED'
    family_impact = {}
    for family in FAMILIES:
        selected = {r['candidate_id'] for r in candidates if r['family'] == family and r['status'] == 'ACCEPTED'}
        objects = [o for o in additions if o['candidate_id'] in selected or
                   (o.get('dependency_candidate_ids') and set(o['dependency_candidate_ids']) <= selected)]
        model = dict(base, base_nodes=base['base_nodes']+[o for o in objects if 'node_id' in o],
                     base_edges=base['base_edges']+[o for o in objects if 'edge_id' in o])
        family_impact[family] = {}
        for mode in ('physical', 'conducting'):
            measured = measure_graph(model, physical=mode == 'physical')
            family_impact[family][mode] = {k: measured[k] - coverage[mode]['before'][k]
                for k in ('reachable_lines', 'reachable_transformers', 'components', 'cycle_rank')}
    coverage['single_family_delta'] = family_impact
    return {'case_id': cid, 'candidates': sorted(candidates, key=lambda r:r['candidate_id']),
            'additions': additions, 'topology': after, 'coverage': coverage}
