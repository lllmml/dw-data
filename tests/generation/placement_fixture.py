"""Declarative D4.1 fixture with consistent accounts, Terminals, projections and accepted v2.

Entity specs carry an optional ``node`` (the derived node E2 projected for them) so the
fixture can express exactly which source endpoint already has an accepted structural
anchor and which one does not.
"""
from hashlib import sha256

ENTITY_TYPE = {'BUS': 'BUS', 'STATION': 'STATION', 'FEEDER': 'FEEDER'}
ID_FIELD = {'BUS': 'Bus_ID', 'STATION': 'Station_ID', 'SWITCH': 'Switch_ID',
            'TRANSFORMER': 'Transformer_ID', 'ACCESS_POINT': 'AccessPoint_ID',
            'LINE': 'Line_ID', 'FEEDER': 'Feeder_ID'}
ENDPOINTS = {'SWITCH': ('Switch_FromBus', 'Switch_ToBus'),
             'TRANSFORMER': ('Transformer_FromBus', 'Transformer_ToBus'),
             'ACCESS_POINT': ('AccessPoint_Bus',), 'LINE': ('Line_FromBus', 'Line_ToBus')}
KINDS = ('BUS', 'STATION', 'SWITCH', 'TRANSFORMER', 'ACCESS_POINT', 'LINE')
NODE_KIND = {'BUS': 'JUNCTION', 'TRANSFORMER': 'TRANSFORMER_MV'}
DEFAULT_KEY = '数据/测试变_10kV测试线101'
# One unreferenced Transformer makes the Fixture a backbone-required Feeder, which is
# the D4.1 cohort condition that eligibility derives from the accepted Case alone.
DEFAULT_TARGET = {'target_key': 'target:fixture', 'source_entity_id': 'equipment:fixture-target',
                  'identity_unique': True, 'reference_composition': 'NO_REFERENCE',
                  'hv_kv': None, 'lv_kv': None, 'source_record_refs': ['t-row']}


def _hash(*parts):
    return sha256('|'.join(parts).encode()).hexdigest()


def _values(kind, spec):
    names = ENDPOINTS.get(kind, ())
    if len(names) == 2:
        return [spec.get('from', ''), spec.get('to', '')]
    if len(names) == 1:
        return [spec.get('bus', '')]
    return []


def _extra_fields(kind, spec):
    if kind == 'SWITCH':
        return [('Switch_NormalState', spec.get('state', 'Closed')),
                ('Switch_IsTie', spec.get('tie', 'False'))]
    if kind == 'BUS':
        return [('Bus_BaseKV', spec.get('kv', '10.5')), ('Bus_IsSource', 'FALSE')]
    return []


def _account(kind, name, spec, key, row):
    fields = [(ID_FIELD[kind], spec['id'])]
    fields.extend(zip(ENDPOINTS.get(kind, ()), _values(kind, spec)))
    fields.extend(_extra_fields(kind, spec))
    return {'canonical_ref': {'entity_id': kind.lower() + ':' + _hash(kind, name),
                              'entity_type': ENTITY_TYPE.get(kind, 'EQUIPMENT')},
            'identity_status': spec.get('identity', 'UNIQUE'), 'issue_ids': [],
            'raw_record': {'data_row': row, 'fields': [[k, v] for k, v in fields],
                           'source_case_key': key, 'source_file_type': kind,
                           'source_record_ref':
                               f'zip-member:{key}/{row:02d}_{kind}.csv#data-row={row}'}}


def build(*, buses=(), stations=(), switches=(), accesspoints=(), transformers=(), lines=(),
          feeder_count=1, hard=(), states=(), targets=(DEFAULT_TARGET,), nominal='10.5',
          case_key=DEFAULT_KEY,
          duplicate_id=(), extra_accounts=(), head=True, edges=()):
    accounts = []
    case_id = 'case:' + _hash('case', case_key)
    specs = {'BUS': list(buses), 'STATION': list(stations), 'SWITCH': list(switches),
             'TRANSFORMER': list(transformers), 'ACCESS_POINT': list(accesspoints),
             'LINE': list(lines)}
    nodes = {}; voltages = {}; refs = {}; spec_of = {}; row = 0
    if head:
        nodes['feeder-head:' + _hash('head', case_key)] = 'HEAD'
        voltages[next(reversed(nodes))] = nominal
    for kind in KINDS:
        for spec in specs[kind]:
            row += 1
            account = _account(kind, kind + '|' + spec['id'], spec, case_key, row)
            accounts.append(account); refs[spec['id']] = account; spec_of[spec['id']] = spec
            if spec.get('node'):
                nodes[spec['node']] = NODE_KIND.get(kind, 'JUNCTION')
                voltages[spec['node']] = spec.get('kv', nominal)
    for kind, name in duplicate_id:
        row += 1
        spec = dict(next(s for s in specs[kind] if s['id'] == name), id=name)
        accounts.append(_account(kind, f'{kind}|{name}|copy', spec, case_key, row))
    accounts.extend(extra_accounts)
    terminals = []
    for account in accounts:
        kind = account['raw_record']['source_file_type']
        values = [v for _, v in account['raw_record']['fields'] if _ in ENDPOINTS.get(kind, ())]
        count = 1 if kind == 'ACCESS_POINT' else 2
        for number in range(1, count + 1):
            value = values[number - 1] if number <= len(values) else ''
            target = refs.get(value) if value else None
            terminals.append({'case_id': case_id,
                              'equipment_id': account['canonical_ref']['entity_id'],
                              'terminal_no': number,
                              'source_record_ref': account['raw_record']['source_record_ref'],
                              'raw_connected_ref': value or None,
                              'resolved_source_ref': target['canonical_ref'] if target else None,
                              'source_ref_status': 'EXACT' if target else 'MISSING',
                              'terminal_id': 'terminal:' + _hash(
                                  account['canonical_ref']['entity_id'], str(number))})
    by_owner = {}
    for t in terminals:
        by_owner.setdefault(t['equipment_id'], {})[t['terminal_no']] = t
    projections = []
    for spec in specs['LINE']:
        account = refs.get(spec['id'])
        if account is None:
            continue
        for number, value in enumerate(_values('LINE', spec), 1):
            node = (spec_of.get(value) or {}).get('node')
            if node:
                projections.append({'projection_status': 'PROJECTED', 'derived_target_ids': [node],
                                    'rule_id': 'BUS_JUNCTION_V1',
                                    'source_terminal_ref': {
                                        'entity_id': by_owner[account['canonical_ref']['entity_id']]
                                                             [number]['terminal_id'],
                                        'entity_type': 'TERMINAL'}})
    head_id = next((n for n, k in nodes.items() if k == 'HEAD'), None)
    base_nodes = [{'node_id': n, 'case_id': case_id, 'kind': k,
                   'voltage_kv': voltages.get(n, nominal), 'transformer_key': None}
                  for n, k in sorted(nodes.items())]
    accepted = {'case_id': case_id, 'source_case_key': case_key,
                'feeders': [{'feeder_id': 'feeder:' + _hash('feeder', case_key, str(i)),
                             'source_record_refs': ['f-row'], 'original_flags': [],
                             'd1_primary': 'FIXTURE'} for i in range(feeder_count)],
                'head_id': head_id, 'nominal_voltage_kv': nominal, 'hard_blockers': list(hard),
                'state_constraints': list(states), 'targets': list(targets), 'evidence_refs': [],
                's2_usable': False,
                'source_line_count': sum(1 for a in accounts
                                         if a['raw_record']['source_file_type'] == 'LINE'),
                'region_source_refs': {n: ['bus-row'] for n in nodes},
                'base_nodes': base_nodes, 'base_edges': list(edges)}
    source = {'accounts': accounts, 'terminals': terminals, 'projections': projections,
              'topology': {'nodes': [], 'branches': [], 'feeder_head_id': head_id,
                           'case_id': case_id, 'reachable_node_ids': [],
                           'reachable_transformer_ids': []},
              'base': dict(accepted)}
    return {'accepted': accepted, 'source': source}


def bus(name, node, kv='10.5'):
    return {'id': name, 'node': node, 'kv': kv}


def switch(name, *, source='', target='', state='Closed', tie='False', node=None):
    return {'id': name, 'from': source, 'to': target, 'state': state, 'tie': tie, 'node': node}


def accesspoint(name, *, connected=''):
    return {'id': name, 'bus': connected}


def line(name, source, target):
    return {'id': name, 'from': source, 'to': target}


def station(name):
    return {'id': name}


def transformer(name, *, source='', target='', node=None):
    return {'id': name, 'from': source, 'to': target, 'node': node}
