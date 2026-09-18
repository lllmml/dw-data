"""Source-bound D4.2 loading and immutable canonical audit artifacts."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
import logging
from pathlib import Path

from grid_case_generator.analysis.case_boundary_audit import audit, VERSION, SCOPE
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.nanjing_source.schema import NANJING_SOURCE_SCHEMA

PREFIX = {'STATION': 'Station', 'BUS': 'Bus', 'FEEDER': 'Feeder', 'SWITCH': 'Switch',
          'LINE': 'Line', 'TRANSFORMER': 'Transformer', 'DISCONNECTOR': 'Disconnector',
          'EARTHING_SWITCH': 'EarthingSwitch', 'ACCESS_POINT': 'AccessPoint', 'LOAD': 'Load', 'DER': 'DER'}
NETWORK_TYPES = ['BUS', 'SWITCH', 'STATION', 'TRANSFORMER', 'ACCESS_POINT']


def read_lines(path):
    with Path(path).open('rb') as handle:
        for line in handle:
            yield json.loads(line)


def digest(path):
    h = sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def reference_fields(kind, fields):
    schema = NANJING_SOURCE_SCHEMA.for_type(next(s.file_type for s in NANJING_SOURCE_SCHEMA.files if s.file_type.value == kind))
    result = [k for k in schema.header if k.endswith(('_FromBus', '_ToBus', '_Bus'))
              or k in ('Bus_Station_ID', 'Feeder_SourceBus')]
    if kind == 'SIM_CONFIG' and fields.get('Config_Key') in ('SourceBus', 'OutputVoltageBus'):
        result.append('Config_Value')
    return result


def witness(ref, field, value):
    return {'source_record_ref': ref, 'raw_field': field, 'raw_value': value}


def positive(value):
    from grid_case_generator.models.proposals import positive_voltage
    try:
        positive_voltage(value)
        return True
    except ValueError:
        return False


def load_cases(source, accepted):
    source = Path(source)
    accepted_context = {c['case_id']: c['hard_blockers'] for c in read_lines(Path(accepted) / 'case_topologies.jsonl')}
    inventory = json.loads((source / 'inventory.json').read_text())
    expected = {c['source_case_key'] for c in inventory['cases']}
    result = []
    for directory in sorted((source / 'cases').iterdir()):
        grid, = list(read_lines(directory / 'records/GridCase.jsonl'))
        if grid['case_id'] != directory.name or grid['source_case_key'] not in expected:
            raise ValueError('Source case inventory mismatch')
        accounts = list(read_lines(directory / 'row_accountability.jsonl'))
        resolutions = defaultdict(list)
        for r in read_lines(directory / 'resolutions.jsonl'):
            resolutions[r['request']['owner_source_record_ref']].append(r)
        by_kind = defaultdict(list)
        for a in accounts:
            raw = a['raw_record']; fields = dict(raw['fields'] or ())
            by_kind[raw['source_file_type']].append((a, fields))
        feeder_ids = []; feeder_names = []; feeder_refs = []; station_ids = set()
        stations = []; voltages = []; head_voltage = set()
        for a, f in by_kind['FEEDER']:
            if f.get('Feeder_ID'): feeder_ids.append(f['Feeder_ID'])
            if f.get('Feeder_Name'): feeder_names.append(f['Feeder_Name'])
            if a['canonical_ref']: feeder_refs.append(a['canonical_ref']['entity_id'])
            buses = [(b, bf) for b, bf in by_kind['BUS'] if bf.get('Bus_ID') == f.get('Feeder_SourceBus') and f.get('Feeder_SourceBus')]
            if len(buses) == 1 and buses[0][0]['identity_status'] == 'UNIQUE':
                b, bf = buses[0]; bref = b['raw_record']['source_record_ref']
                if bf.get('Bus_Station_ID'):
                    station_ids.add(bf['Bus_Station_ID'])
                    stations.extend([witness(a['raw_record']['source_record_ref'], 'Feeder_SourceBus', f['Feeder_SourceBus']),
                                     witness(bref, 'Bus_Station_ID', bf['Bus_Station_ID'])])
                if positive(bf.get('Bus_BaseKV')):
                    head_voltage.add(bf['Bus_BaseKV']); voltages.append(witness(bref, 'Bus_BaseKV', bf['Bus_BaseKV']))
        context_voltage = next(iter(head_voltage)) if len(head_voltage) == 1 else None
        entities = []; references = []; empty = 0
        for a in accounts:
            raw = a['raw_record']; fields = dict(raw['fields'] or ()); kind = raw['source_file_type']
            sid = fields.get(PREFIX.get(kind, '') + '_ID')
            own_v = []; own_w = []; voltage_basis = 'UNKNOWN'
            keys = ('Bus_BaseKV',) if kind == 'BUS' else ('Transformer_HighVoltage_kV', 'Transformer_LowVoltage_kV') if kind == 'TRANSFORMER' else ()
            for key in keys:
                if positive(fields.get(key)):
                    voltage_basis = 'DIRECT_SOURCE_FIELD'
                    own_v.append(fields[key]); own_w.append(witness(raw['source_record_ref'], key, fields[key]))
            if not own_v and kind not in ('STATION', 'TRANSFORMER') and context_voltage \
                    and not any(fields.get(key) for key in keys):
                own_v = [context_voltage]; own_w = voltages; voltage_basis = 'SOURCE_HEAD_CONTEXT'
            if sid:
                entities.append({'source_entity_type': kind, 'source_file_type': kind, 'raw_source_id': sid,
                    'source_record_ref': raw['source_record_ref'], 'identity_status': a['identity_status'],
                    'canonical_ref': a['canonical_ref'], 'voltage_values': sorted(set(own_v)),
                    'voltage_witnesses': own_w, 'voltage_basis': voltage_basis, 'fields': fields})
            for field in reference_fields(kind, fields):
                value = fields.get(field, '')
                if not value:
                    empty += 1; continue
                matches = [r for r in resolutions[raw['source_record_ref']]
                           if r['request']['raw_reference_value'] == value]
                # Side-specific paths distinguish two equal raw endpoint declarations.
                side = 2 if field.endswith('_ToBus') else 1
                terminal_path = f'terminal[{side}].raw_connected_ref'
                side_matches = [r for r in matches if r['request']['reference_field_path'] == terminal_path]
                if side_matches: matches = side_matches
                status = matches[0]['resolution_status'] if len(matches) == 1 else 'NOT_RESOLVED'
                allowed = ['STATION'] if field == 'Bus_Station_ID' else ['BUS'] if field in ('Feeder_SourceBus', 'Config_Value') else NETWORK_TYPES
                v = list(own_v); vw = own_w; vb = voltage_basis
                if kind == 'TRANSFORMER':
                    key = 'Transformer_HighVoltage_kV' if side == 1 else 'Transformer_LowVoltage_kV'
                    v = [fields[key]] if positive(fields.get(key)) else []
                    vw = [witness(raw['source_record_ref'], key, fields[key])] if v else []
                    vb = 'DIRECT_SOURCE_FIELD' if v else 'UNKNOWN'
                references.append({'source_entity_type': kind, 'source_record_ref': raw['source_record_ref'],
                    'owner_source_id': sid, 'raw_field': field, 'raw_reference_value': value,
                    'local_resolution_status': status, 'allowed_types': allowed,
                    'voltage_values': sorted(set(v)), 'voltage_witnesses': vw, 'voltage_basis': vb})
        result.append({'case_id': grid['case_id'], 'source_case_key': grid['source_case_key'],
            'feeder_ids': sorted(set(feeder_ids)), 'feeder_names': sorted(set(feeder_names)),
            'feeder_refs': sorted(set(feeder_refs)), 'station_ids': sorted(station_ids),
            'station_witnesses': stations, 'voltage_kv': context_voltage, 'voltage_witnesses': voltages,
            'entities': entities, 'references': references, 'empty_reference_count': empty,
            'source_type_counts': {s.file_type.value: len(by_kind[s.file_type.value]) for s in NANJING_SOURCE_SCHEMA.files},
            'hard_blockers': accepted_context[grid['case_id']]})
    if len(result) != len(expected) or {c['source_case_key'] for c in result} != expected:
        raise ValueError('Source inventory missing or duplicate case')
    return result


def input_bindings(roots):
    bound = {}
    for label, root in sorted(roots.items()):
        root = Path(root); manifest_path = root / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        names = set(manifest['files'])
        for name, metadata in manifest['files'].items():
            path = root / name
            if digest(path) != metadata['sha256']:
                raise ValueError('Source binding checksum mismatch: ' + label + '/' + name)
        # Source inventory is separately bound even if a legacy manifest excludes it.
        extras = {n: digest(root / n) for n in ('inventory.json', 'dataset.json') if (root / n).exists() and n not in names}
        bound[label] = {'manifest_sha256': digest(manifest_path), 'extra_files': extras}
    return bound


def code_hash():
    root = Path(__file__).resolve().parents[1]
    names = ['analysis/case_boundary_audit.py', 'analysis/case_boundary_impact.py',
             'io/case_boundary_audit.py', 'analysis/case_boundary_audit_cli.py']
    return sha256(canonical_json_bytes({n: digest(root / n) for n in names})).hexdigest()


def build(roots):
    from grid_case_generator.analysis.case_boundary_impact import impact
    logging.info('Loading all source cases')
    cases = load_cases(roots['source'], roots['accepted'])
    logging.info('Classifying references across %s cases', len(cases))
    result = audit(cases)
    logging.info('Computing counterfactual impact: %s external references', result['summary']['cross_case_reference_count'])
    result.update(impact(cases, result, roots))
    logging.info('Counterfactual analysis complete')
    result['summary']['target_78_classification'] = dict(sorted(Counter(r['classification'] for r in result['target_78_feeders']).items()))
    result['summary']['no_source_line_feeders'] = result['counterfactual_impact']['no_source_line_feeders']
    return result


def serialized(result):
    for name in sorted(result):
        rows = result[name]
        suffix = '.jsonl' if isinstance(rows, list) else '.json'
        if not isinstance(rows, list): rows = [rows]
        yield name + suffix, (canonical_json_bytes(r) + b'\n' for r in rows)
    yield 'report.md', [('''# D4.2 Case boundary audit\n\nANALYSIS_ONLY_CROSS_CASE_COUNTERFACTUAL. No approval or apply.\nQ-CASE-001 remains OPEN; directory = GridCase and the local resolver are unchanged.\n\nIdentity matches do not prove electrical attachment or feeder ownership.\nReciprocity describes directory directions, not confirmed electrical circuits.\n\n```json\n''' + json.dumps({'summary': result['summary'], 'impact': result['counterfactual_impact']},
        ensure_ascii=False, sort_keys=True, indent=2) + '\n```\n').encode()]


def write_artifact(roots, output):
    output = Path(output).resolve()
    if output.exists(): raise FileExistsError(output)
    if any(output == Path(r).resolve() or Path(r).resolve() in output.parents or output in Path(r).resolve().parents for r in roots.values()):
        raise ValueError('Audit output overlaps input')
    if any(p.name == 'raw' and p.parent.name == 'data' for p in (output, *output.parents)):
        raise ValueError('Audit output cannot be raw source')
    logging.info('Checking input manifests and file hashes')
    bindings = input_bindings(roots)
    result = build(roots); output.mkdir(parents=True)
    files = {}
    for name, chunks in serialized(result):
        count = 0; h = sha256()
        with (output / name).open('xb') as handle:
            for data in chunks:
                handle.write(data); h.update(data); count += len(data.splitlines())
        files[name] = {'sha256': h.hexdigest(), 'record_count': count}
    manifest = {'scope': SCOPE, 'version': VERSION, 'code_sha256': code_hash(),
                'input_bindings': bindings, 'files': files, 'approved': False, 'applied': False,
                'topology_written': False, 'proposal_created': False}
    if input_bindings(roots) != bindings: raise ValueError('Audit inputs changed during build')
    (output / 'manifest.json').write_bytes(canonical_json_bytes(manifest) + b'\n')
    return result['summary']


def verify_artifact(roots, output):
    output = Path(output); manifest = json.loads((output / 'manifest.json').read_text())
    if (output / 'manifest.json').read_bytes() != canonical_json_bytes(manifest) + b'\n':
        raise ValueError('Audit manifest serialization')
    if manifest['input_bindings'] != input_bindings(roots):
        raise ValueError('Audit source binding mismatch')
    if manifest['version'] != VERSION or manifest['scope'] != SCOPE or manifest['code_sha256'] != code_hash():
        raise ValueError('Audit manifest version/code mismatch')
    if any(manifest[k] is not False for k in ('approved', 'applied', 'topology_written', 'proposal_created')):
        raise ValueError('Audit scope violation')
    result = build(roots); expected = {'manifest.json'}
    for name, chunks in serialized(result):
        expected.add(name); h = sha256(); count = 0
        with (output / name).open('rb') as handle:
            for data in chunks:
                if handle.read(len(data)) != data: raise ValueError('Audit source replay mismatch: ' + name)
                h.update(data); count += len(data.splitlines())
            if handle.read(1): raise ValueError('Audit extra records: ' + name)
        if manifest['files'].get(name) != {'sha256': h.hexdigest(), 'record_count': count}:
            raise ValueError('Audit manifest checksum mismatch: ' + name)
    if set(manifest['files']) != expected - {'manifest.json'} or {p.name for p in output.iterdir()} != expected:
        raise ValueError('Audit inventory mismatch')
    return {'verified': True, 'input_bound': True, 'manifest_sha256': digest(output / 'manifest.json')}
