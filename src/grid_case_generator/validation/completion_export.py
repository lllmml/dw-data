"""Independent v1 delivery validator: re-derives every claim from persisted evidence.

It shares no code with ``generation/completion_ledger.py`` and does not call the engine's
rule bodies, renderers or constants: row identity, the generated Bus columns, tier
membership, the byte layout and the provenance joins are all re-derived here from the
delivered tree, the ledger artifact, the source archive and the placement artifact. A
defect that the engine and the writer agree on is therefore still caught.

Every verdict is a sorted reason set; an empty set is a pass. Nothing here writes.
"""
import csv
import io
import json
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

from grid_case_generator.io.nanjing_source.locator import SourceRecordRef
from grid_case_generator.io.nanjing_source.schema import NANJING_SOURCE_SCHEMA
from grid_case_generator.io.source_bytes import (
    member_path_of, raw_member_bytes, split_raw_records)
from grid_case_generator.models.completion_export import (
    CROSS_CASE_RULE, PLACEMENT_BUS_RULE, PROVENANCE_NAMESPACE, RECOVERY_RULE,
    policy_sha256)

REASONS = (
    'SOURCE_ROW_NOT_VERBATIM',
    'APPENDED_ROW_NOT_DONOR_BYTES',
    'APPENDED_EVIDENCE_MISMATCH',
    'MINTED_IDENTIFIER',
    'PLACEMENT_FIELD_MISMATCH',
    'TIER_NOT_ENABLED',
    'CLOSURE_NOT_BOUNDED',
    'PROVENANCE_INCOMPLETE',
    'PROVENANCE_UNKNOWN_ROW',
    'PROVENANCE_ID_MISMATCH',
    'UNRESOLVED_ROW_WRITTEN',
    'DUPLICATE_APPENDED_ROW',
    'CSV_COLUMN_SCHEMA_CHANGED',
    'POLICY_HASH_MISMATCH',
    'LEDGER_BINDING_MISMATCH',
    'LEDGER_STREAM_MISMATCH',
    'STALE_LEDGER_BASE',
    'UPSTREAM_INTEGRITY',
    'MEMBER_MISSING',
    'ARCHIVE_INVENTORY_MISMATCH',
    'ARCHIVE_CONTENT_MISMATCH',
    'SIDECAR_MISMATCH',
    'UNRESOLVED_TAXONOMY_MISMATCH',
)
PROVENANCE_NAME = 'row_provenance.jsonl'
ARCHIVE_NAME = 'nanjing-derived-v1.zip'
LEDGER_COPIES = ('completion_records.jsonl', 'unresolved_records.jsonl')
PROVENANCE_KEYS = ('provenance_id', 'case_id', 'source_case_key', 'target_file',
    'row_index', 'row_kind', 'completion_status', 'confidence_class', 'tier', 'rule_id',
    'rule_version', 'source_record_ref', 'donor_source_record_ref', 'raw_field',
    'raw_reference_value', 'evidence_refs', 'policy_id', 'policy_sha256')
# The one placement reason that withholds a row, rather than nulling a field on one.
WITHHOLDING_REASON = 'EVIDENCE_JOIN_MISMATCH'
# What each appending rule's rows must say about themselves. The tier is not here: it is
# the licensing record's value, checked against the record rather than against a literal.
APPENDED_CONTRACT = {
    CROSS_CASE_RULE: {'completion_status': 'PROPOSED',
                      'confidence_class': 'UNIQUE_EVIDENCE'},
    PLACEMENT_BUS_RULE: {'completion_status': 'PROPOSED',
                         'confidence_class': 'ENGINEERING_DEFAULT'},
}
BUS_FILE = '02_Bus.csv'
TERMINATORS = (b'\r\n', b'\n', b'\r')


def _bus_columns():
    """The generated Bus row's column order, from the source schema, not the engine."""
    schema = next(s for s in NANJING_SOURCE_SCHEMA.files if s.filename == BUS_FILE)
    return tuple(schema.header)


def _rows(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def _fields(raw_row):
    return next(csv.reader(io.StringIO(raw_row.decode('utf-8-sig'), newline='')), [])


def _render(values):
    """Serialize one Bus row exactly as the source format would; ``None`` is empty."""
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\r\n')
    writer.writerow(['' if values[name] is None else values[name] for name in values])
    return stream.getvalue().encode('utf-8').removesuffix(b'\r\n')


def _documents(root):
    """``(source_case_key, filename, bytes)`` for every delivered CSV, in path order.

    Read exactly once per validation run and passed to every checker. Scanning the tree
    again inside a per-member loop is quadratic in the number of members — on the real
    intake that is ~60k full re-reads of a 1.3 GB tree, which is not a slow check but a
    hung one. Nothing is cached between runs: these bytes are this run's evidence.
    """
    data_root = Path(root) / 'data'
    documents = []
    for path in sorted(data_root.rglob('*.csv')):
        relative = path.relative_to(data_root)
        documents.append((relative.parent.as_posix(), path.name, path.read_bytes()))
    return tuple(documents)


def _has_member(archive, member):
    try:
        archive.getinfo(member)
    except KeyError:
        return False
    return True


def _station_from_bus_member(bus_bytes):
    """The single distinct non-empty ``Bus_Station_ID``, else ``None``; no tie-break."""
    if not bus_bytes:
        return None
    rows = list(csv.reader(io.StringIO(bus_bytes.decode('utf-8-sig'), newline='')))
    if not rows or 'Bus_Station_ID' not in rows[0]:
        return None
    index = rows[0].index('Bus_Station_ID')
    values = {row[index] for row in rows[1:] if len(row) > index and row[index]}
    return values.pop() if len(values) == 1 else None


def _recorded_archive(source_root):
    """The source ZIP the import artifact recorded, held to its recorded checksum."""
    dataset = json.loads((Path(source_root) / 'dataset.json').read_text())
    path = Path(dataset['source_uri'])
    if not path.is_file():
        return None
    if sha256(path.read_bytes()).hexdigest() != str(dataset['source_checksum']).split(':', 1)[-1]:
        return None
    return path


def _placement_inputs(roots):
    """``(proposals_by_case, evidence)`` from the placement artifact, or ``(None, None)``."""
    if roots is None or 'placement' not in roots:
        return None, None
    root = Path(roots['placement'])
    proposals, evidence = root / 'line_component_proposals.jsonl', root / 'line_endpoint_evidence.jsonl'
    if not proposals.is_file() or not evidence.is_file():
        return None, None
    by_case = {}
    for line in proposals.read_bytes().splitlines():
        row = json.loads(line)
        by_case.setdefault(row['case_id'], []).append(row)
    joined = {}
    for line in evidence.read_bytes().splitlines():
        row = json.loads(line)
        joined[(row['case_id'], row['source_line_id'], row['endpoint_side'])] = row
    return by_case, joined


def _placement_group(case_id, raw_value, proposals, evidence):
    """Re-derive one generated Bus row's values, or ``None`` when it is not licensed.

    Returns ``(values, malformed)``: ``malformed`` is true when the evidence join fails,
    which is the contract's reason for withholding the row entirely.
    """
    ports = [(p, e) for p in proposals.get(case_id, ()) for e in p['endpoints']
             if e['anchor_origin'] != 'ACCEPTED_NODE' and e['raw_endpoint_value'] == raw_value]
    if not ports:
        return None, False
    voltages, malformed = set(), False
    for proposal, endpoint in ports:
        row = evidence.get((case_id, proposal['source_line_id'], endpoint['side']))
        if row is None or row['raw_endpoint_value'] != raw_value:
            malformed = True
            continue
        if row.get('voltage_evidence') is not None:
            voltages.add(row['voltage_evidence'])
    if malformed:
        return None, True
    return voltages, False


def _check_inventory(root, manifest, archive_name, errors, measured):
    """The tree is the manifest's inventory plus the carve-outs, and it re-hashes."""
    on_disk = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    expected = set(manifest.get('files', {})) | {'manifest.json'}
    if (root / archive_name).is_file():
        expected.add(archive_name)
    if on_disk != expected:
        errors.add('ARCHIVE_INVENTORY_MISMATCH')
    if archive_name in manifest.get('files', {}):
        errors.add('ARCHIVE_INVENTORY_MISMATCH')
    for name, entry in manifest.get('files', {}).items():
        path = root / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if sha256(data).hexdigest() != entry.get('sha256'):
            errors.add('ARCHIVE_INVENTORY_MISMATCH')
        if len(data.splitlines()) != entry.get('record_count'):
            errors.add('ARCHIVE_INVENTORY_MISMATCH')
    # A manifest that claims approval is the failure the whole sidecar exists to prevent.
    for flag in ('approved', 'applied', 'canonical_changed', 'accepted_v2_changed',
                 'source_changed', 'e3_ready', 'opendss_ready'):
        if manifest.get(flag) is not False:
            errors.add('LEDGER_BINDING_MISMATCH')
    measured['files_delivered'] = len(on_disk)


def _check_archive(root, archive_name, errors, measured):
    """The archive is the tree: same entries, and each entry's bytes are the file's.

    A digest match against the sidecar is not a substitute — it only says the archive
    has not changed, not that it still agrees with what is on disk beside it.
    """
    path = root / archive_name
    on_disk = {str(p.relative_to(root)) for p in root.rglob('*')
               if p.is_file() and p.name != archive_name}
    if not path.is_file():
        errors.add('ARCHIVE_INVENTORY_MISMATCH')
        return
    try:
        with ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != on_disk:
                errors.add('ARCHIVE_CONTENT_MISMATCH')
            for name in sorted(set(names) & on_disk):
                if archive.read(name) != (root / name).read_bytes():
                    errors.add('ARCHIVE_CONTENT_MISMATCH')
        measured['archive_entries'] = len(names)
    except (OSError, KeyError, ValueError):
        errors.add('ARCHIVE_CONTENT_MISMATCH')


def _check_ledger(ledger_root, roots, policy, manifest, errors, measured):
    """Policy binding, ledger binding, stale base, closure bound and tier membership."""
    if policy is not None and manifest.get('policy_sha256') != policy_sha256(policy):
        errors.add('POLICY_HASH_MISMATCH')
    if ledger_root is None:
        return None, None
    ledger_root = Path(ledger_root)
    ledger_manifest_path = ledger_root / 'manifest.json'
    if not ledger_manifest_path.is_file():
        errors.add('LEDGER_BINDING_MISMATCH')
        return None, None
    ledger_manifest = json.loads(ledger_manifest_path.read_text())
    if manifest.get('ledger_manifest_sha256') != sha256(
            ledger_manifest_path.read_bytes()).hexdigest():
        errors.add('LEDGER_BINDING_MISMATCH')
    if ledger_manifest.get('policy_sha256') != manifest.get('policy_sha256'):
        errors.add('POLICY_HASH_MISMATCH')
    if roots is not None and 'accepted_v2' in roots:
        current = sha256((Path(roots['accepted_v2']) / 'manifest.json').read_bytes()).hexdigest()
        if ledger_manifest.get('input_manifest_sha256', {}).get('accepted_v2') != current:
            errors.add('STALE_LEDGER_BASE')
    completion = _rows(ledger_root / 'completion_records.jsonl')
    unresolved = _rows(ledger_root / 'unresolved_records.jsonl')
    bound = policy.max_reference_closure_depth if policy is not None else None
    tiers = set(policy.materialize_tiers) if policy is not None else None
    for row in (*completion, *unresolved):
        depth = row.get('closure_depth')
        if bound is not None and depth is not None and depth > bound:
            errors.add('CLOSURE_NOT_BOUNDED')
        # Only a record that materializes a row is held to the tier gate. An UNRESOLVED
        # record names the tier it was refused *for*, so `TIER_NOT_MATERIALIZED` carries
        # `CROSS_STATION` by design whenever that tier is switched off.
        tier = row.get('tier')
        if (tiers is not None and tier is not None and tier not in tiers
                and row.get('completion_status') != 'UNRESOLVED'):
            errors.add('TIER_NOT_ENABLED')
    measured['ledger_completion_records'] = len(completion)
    measured['ledger_unresolved_records'] = len(unresolved)
    return completion, unresolved


def _check_ledger_streams(root, ledger_root, errors):
    """The copies under ``provenance/`` are the ledger's streams, byte for byte."""
    if ledger_root is None:
        return
    for name in LEDGER_COPIES:
        copy = root / 'provenance' / name
        origin = Path(ledger_root) / name
        if not copy.is_file() or not origin.is_file():
            errors.add('LEDGER_STREAM_MISMATCH')
        elif copy.read_bytes() != origin.read_bytes():
            errors.add('LEDGER_STREAM_MISMATCH')


def _check_upstreams(roots, errors, measured):
    """Every upstream file exists and still hashes to what its manifest recorded."""
    if roots is None:
        return
    checked = 0
    for name in sorted(roots):
        root = Path(roots[name])
        manifest_path = root / 'manifest.json'
        if not manifest_path.is_file():
            errors.add('UPSTREAM_INTEGRITY')
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except (ValueError, OSError):
            errors.add('UPSTREAM_INTEGRITY')
            continue
        for relative, entry in sorted(manifest.get('files', {}).items()):
            if relative == 'manifest.json':
                continue
            path = root / relative
            if not path.is_file():
                errors.add('UPSTREAM_INTEGRITY')
                continue
            data = path.read_bytes()
            if sha256(data).hexdigest() != entry.get('sha256'):
                errors.add('UPSTREAM_INTEGRITY')
            if len(data.splitlines()) != entry.get('record_count'):
                errors.add('UPSTREAM_INTEGRITY')
            if relative.endswith(('.json', '.jsonl')):
                for line in data.splitlines():
                    try:
                        json.loads(line)
                    except ValueError:
                        errors.add('UPSTREAM_INTEGRITY')
                        break
            checked += 1
    measured['upstream_files_checked'] = checked


def _check_members(documents, roots, errors, measured):
    """Every source member present, and every delivered header the source schema's."""
    headers = {schema.filename: tuple(schema.header) for schema in NANJING_SOURCE_SCHEMA.files}
    delivered = {f'{key}/{name}' for key, name, _data in documents}
    if roots is not None and 'source' in roots:
        inventory = Path(roots['source']) / 'inventory.json'
        if inventory.is_file():
            try:
                expected = {member for case in json.loads(inventory.read_text())['cases']
                            for _file_type, member in case['members']}
            except (ValueError, KeyError):
                errors.add('UPSTREAM_INTEGRITY')
                expected = set()
            if expected - delivered:
                errors.add('MEMBER_MISSING')
            measured['members_expected'] = len(expected)
    for _key, name, data in documents:
        want = headers.get(name)
        if want is None:
            continue
        try:
            parsed = list(csv.reader(io.StringIO(data.decode('utf-8-sig'), newline='')))
        except (UnicodeDecodeError, csv.Error):
            errors.add('CSV_COLUMN_SCHEMA_CHANGED')
            continue
        if not parsed or tuple(parsed[0]) != want:
            errors.add('CSV_COLUMN_SCHEMA_CHANGED')
    measured['members_delivered'] = len(delivered)


def _append_block(source_bytes, appended):
    separator = b'' if source_bytes.endswith(TERMINATORS) else b'\r\n'
    return separator + b'\r\n'.join(appended) + b'\r\n'


def _audit_eligible(row, tiers, cases):
    """The contract's nine preconditions, re-derived here rather than imported.

    Reading the engine's ``eligible`` would make this check agree with the engine by
    construction; the point is to disagree when the engine is wrong.
    """
    if row.get('classification') != 'UNIQUE_EXTERNAL_MATCH':
        return False, row.get('classification')
    if row.get('external_candidate_count') != 1:
        return False, 'MULTIPLE_EXTERNAL_MATCH'
    candidate = (row.get('candidates') or [None])[0]
    if candidate is None:
        return False, 'NO_CANONICAL_CANDIDATE'
    if candidate.get('identity_status') != 'UNIQUE':
        return False, 'AMBIGUOUS_IDENTITY'
    if not candidate.get('type_compatible'):
        return False, 'TYPE_INCOMPATIBLE'
    if not candidate.get('canonical_ref'):
        return False, 'NO_CANONICAL_CANDIDATE'
    if candidate.get('voltage_relationship') != 'COMPATIBLE':
        return False, 'VOLTAGE_NOT_COMPATIBLE'
    if row.get('local_candidate_count'):
        return False, 'ALSO_RESOLVES_CASE_LOCALLY'
    if cases.get(row.get('case_id'), {}).get('hard_blockers'):
        return False, 'REFERRING_CASE_HARD_BLOCKER'
    if cases.get(candidate.get('case_id'), {}).get('hard_blockers'):
        return False, 'DONOR_CASE_HARD_BLOCKER'
    if candidate.get('station_relationship') not in tiers:
        return False, 'TIER_NOT_MATERIALIZED'
    return True, ''


def _audit_streams(roots):
    """``(audit rows, case inventory)`` read straight from the audit artifact."""
    if roots is None or 'audit' not in roots:
        return None, None
    root = Path(roots['audit'])
    references, inventory = root / 'cross_case_references.jsonl', root / 'case_inventory.jsonl'
    if not references.is_file() or not inventory.is_file():
        return None, None
    try:
        rows = [json.loads(line) for line in references.read_bytes().splitlines()]
        cases = {r['case_id']: r for r in
                 (json.loads(line) for line in inventory.read_bytes().splitlines())}
    except (ValueError, KeyError):
        return None, None
    return rows, cases


def _cross_case_events(roots, policy, errors):
    """Re-derive the cross-case rule's materialized set and failure taxonomy.

    Every materialized reference must appear as a delivered row, and the failure
    taxonomy must be exactly the one the audit rows imply — a ledger that quietly
    dropped or reclassified a reference is caught even when it agrees with the delivery.
    """
    rows, cases = _audit_streams(roots)
    if rows is None:
        return {}, None
    enabled = policy is not None and CROSS_CASE_RULE in policy.enabled_rules
    tiers = tuple(policy.materialize_tiers) if policy is not None else ()
    expected, failures = {}, {}
    for row in rows:
        ok, reason = _audit_eligible(row, tiers, cases)
        if not ok:
            failures[reason] = failures.get(reason, 0) + 1
            continue
        if not enabled:
            continue
        candidate = row['candidates'][0]
        key = row.get('source_case_key')
        if key is None:
            errors.add('UPSTREAM_INTEGRITY')
            continue
        donor = member_path_of(SourceRecordRef(candidate['source_record_ref']))
        expected.setdefault((key, donor.rsplit('/', 1)[-1]), set()).add(
            candidate['source_record_ref'])
    return expected, failures


def _check_cross_case(roots, policy, ledger_records, unresolved, errors):
    """Bind the ledger's taxonomy to the audit's own verdict, not to the delivery."""
    _, failures = _cross_case_events(roots, policy, errors)
    if failures is None or ledger_records is None or unresolved is None:
        return
    observed = {}
    for record in unresolved:
        if record.get('rule_id') != 'COHORT_TAXONOMY_V1':
            continue
        if record.get('reason') in failures or record.get('reason', '').endswith(
                ('CASE_HARD_BLOCKER', 'NOT_COMPATIBLE', 'RESOLVES_CASE_LOCALLY',
                 'TIER_NOT_MATERIALIZED', 'EXTERNAL_MATCH', 'UNDEFINED_GLOBAL',
                 'LOCAL_UNRESOLVED_ONLY')):
            observed[record['reason']] = observed.get(record['reason'], 0) + 1
    for reason, count in failures.items():
        if reason not in observed:
            errors.add('UNRESOLVED_TAXONOMY_MISMATCH')
        elif observed[reason] != count:
            errors.add('UNRESOLVED_TAXONOMY_MISMATCH')


def _expected_rows(completion, archive, member_records, proposals, evidence, columns,
                   errors, cross_from_audit=False):
    """The rows the ledger requires, keyed by ``(case_key, filename)``.

    Derived from the completion records and the evidence, never from the delivered
    provenance: a file whose appended row *and* its provenance record were both deleted
    would otherwise reconstruct as an untouched file and pass.
    """
    expected = {}
    if completion is None:
        return expected
    for record in completion:
        if record.get('completion_status') != 'PROPOSED':
            continue
        key, rule = record.get('source_case_key'), record.get('rule_id')
        if rule == CROSS_CASE_RULE:
            # When the audit is available the cross-case expectation comes from it, not
            # from the ledger: a ledger that invents or drops a reference must not be
            # able to license its own delivery.
            if cross_from_audit:
                continue
            ref = _ref(record.get('donor_source_record_ref') or '')
            if ref is None:
                errors.add('APPENDED_EVIDENCE_MISMATCH')
                continue
            member = member_path_of(ref)
            if not _has_member(archive, member):
                errors.add('MEMBER_MISSING')
                continue
            donor = member_records(member)
            if ref.data_row >= len(donor):
                errors.add('APPENDED_ROW_NOT_DONOR_BYTES')
                continue
            expected.setdefault((key, member.rsplit('/', 1)[-1]), set()).add(donor[ref.data_row])
        elif rule == PLACEMENT_BUS_RULE:
            if proposals is None:
                continue
            group, malformed = _placement_group(record['case_id'], record.get('raw_reference_value'),
                                                proposals, evidence)
            if group is None or malformed:
                continue
            voltages = sorted(group)
            values = {'Bus_ID': record.get('raw_reference_value'), 'Bus_Name': None,
                      'Bus_BaseKV': voltages[0] if len(voltages) == 1 else None,
                      'Bus_Phase': None,
                      'Bus_Station_ID': _station_from_bus_member(
                          raw_member_bytes(archive, f'{key}/{BUS_FILE}')
                          if _has_member(archive, f'{key}/{BUS_FILE}') else b''),
                      'Bus_IsSource': None}
            expected.setdefault((key, BUS_FILE), set()).add(
                _render({name: values.get(name) for name in columns}))
    return expected


def _check_member_identity(name, key, records, errors, policy=None):
    """Provenance rows for one member: contiguous, ordered, unique, exactly keyed."""
    ordered = sorted(records, key=lambda r: r['row_index'])
    if [r['row_index'] for r in ordered] != list(range(len(ordered))):
        errors.add('PROVENANCE_INCOMPLETE')
    if len(ordered) != len({r['row_index'] for r in ordered}):
        errors.add('DUPLICATE_APPENDED_ROW')
    for record in ordered:
        if set(record) != set(PROVENANCE_KEYS):
            errors.add('PROVENANCE_INCOMPLETE')
            continue
        payload = {k: record[k] for k in PROVENANCE_KEYS if k != 'provenance_id'}
        expected = PROVENANCE_NAMESPACE + sha256(
            json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':'),
                       sort_keys=True).encode('utf-8')).hexdigest()
        if record['provenance_id'] != expected:
            errors.add('PROVENANCE_ID_MISMATCH')
        if record['source_case_key'] != key or record['target_file'] != name:
            errors.add('PROVENANCE_UNKNOWN_ROW')
        # The sidecar's own policy binding must be the policy, on every row: a row that
        # carries a different digest is a row produced under different rules.
        if policy is not None and (record['policy_sha256'] != policy_sha256(policy)
                                   or record['policy_id'] != policy.policy_version):
            errors.add('POLICY_HASH_MISMATCH')
    return ordered


def _check_provenance(root, documents, roots, source_archive, ledger_records, unresolved,
                      errors, measured, policy=None, cross_expected=None):
    """Re-derive every delivered member from the source member plus its provenance."""
    provenance_path = root / 'provenance' / PROVENANCE_NAME
    if not provenance_path.is_file():
        errors.add('PROVENANCE_INCOMPLETE')
        return
    provenance = _rows(provenance_path)
    by_member = {}
    for record in provenance:
        by_member.setdefault((record['source_case_key'], record['target_file']),
                             []).append(record)
    proposals, evidence = _placement_inputs(roots)
    if proposals is None:
        errors.add('PLACEMENT_FIELD_MISMATCH') if False else None
    licensed = _licensed_records(ledger_records)
    _check_confirmed_records(ledger_records, errors)
    cited = set()
    appended_seen, delivered_rows = [], 0
    columns = _bus_columns()
    delivered_members = {(key, name) for key, name, _data in documents}
    with ZipFile(source_archive, 'r') as archive:
        cache, bus_cache = {}, {}

        def member_records(member):
            if member not in cache:
                cache[member] = split_raw_records(raw_member_bytes(archive, member))
            return cache[member]

        expected_by_member = _expected_rows(
            ledger_records, archive, member_records, proposals, evidence, columns, errors,
            cross_from_audit=cross_expected is not None)
        # The cross-case rule's expectation is re-derived from the audit, not from the
        # ledger: a ledger and a delivery that agree on a row the audit never licensed
        # must still be rejected.
        for (key, filename), donor_refs in (cross_expected or {}).items():
            for donor_ref in donor_refs:
                ref = _ref(donor_ref)
                member = member_path_of(ref)
                if not _has_member(archive, member):
                    errors.add('MEMBER_MISSING')
                    continue
                donor = member_records(member)
                if ref.data_row >= len(donor):
                    errors.add('APPENDED_ROW_NOT_DONOR_BYTES')
                    continue
                expected_by_member.setdefault((key, filename), set()).add(donor[ref.data_row])

        for key, name, data in documents:
            member = f'{key}/{name}'
            records = by_member.get((key, name), [])
            ordered = _check_member_identity(name, key, records, errors, policy)
            keys = [(r['row_index'], r['rule_id'], r['donor_source_record_ref'],
                     r['raw_reference_value']) for r in records]
            if len(set(keys)) != len(keys):
                errors.add('DUPLICATE_APPENDED_ROW')
            if not _has_member(archive, member):
                errors.add('MEMBER_MISSING')
                continue
            source_bytes = raw_member_bytes(archive, member)
            source_data = split_raw_records(source_bytes)[1:]
            rows = split_raw_records(data)[1:]
            delivered_rows += len(rows)
            # One provenance record per delivered row, counted from the file rather than
            # from the records present: a member whose whole provenance was deleted would
            # otherwise leave nothing to check and pass.
            if len(ordered) != len(rows):
                errors.add('PROVENANCE_INCOMPLETE')
            if list(rows[:len(source_data)]) != list(source_data):
                errors.add('SOURCE_ROW_NOT_VERBATIM')
            # The source region must be a verbatim prefix, then exactly one separator
            # when the source does not already end in a terminator, then the block.
            appended = rows[len(source_data):]
            want_prefix = b'' if source_bytes.endswith(TERMINATORS) else b'\r\n'
            if not data.startswith(source_bytes):
                errors.add('SOURCE_ROW_NOT_VERBATIM')
            else:
                # An empty remainder is an untouched member; only a member that gained
                # rows has a separator and a block to check.
                rest = data[len(source_bytes):]
                if rest:
                    if not rest.startswith(want_prefix):
                        errors.add('SOURCE_ROW_NOT_VERBATIM')
                    if not rest[len(want_prefix):].endswith(b'\r\n'):
                        errors.add('SOURCE_ROW_NOT_VERBATIM')
            # Independent of provenance: what the ledger says must be here.
            want_rows = expected_by_member.get((key, name), set())
            if set(appended) != want_rows:
                errors.add('APPENDED_EVIDENCE_MISMATCH')
            for record in ordered:
                index = record['row_index']
                delivered = rows[index] if index < len(rows) else None
                if record['row_kind'] not in ('SOURCE', 'APPENDED'):
                    errors.add('PROVENANCE_INCOMPLETE')
                    continue
                if record['row_kind'] == 'SOURCE':
                    if index >= len(source_data):
                        errors.add('PROVENANCE_INCOMPLETE')
                        continue
                    ref = _ref(record['source_record_ref'])
                    if ref is None or member_path_of(ref) != member \
                            or ref.data_row != index + 1:
                        errors.add('SOURCE_ROW_NOT_VERBATIM')
                    continue
                _appended_row(record, key, member, columns, archive, member_records,
                              proposals, evidence, bus_cache, licensed, cited, errors,
                              delivered)
            appended_seen.extend((key, name, row) for row in appended)
    for key in by_member:
        if key not in delivered_members:
            errors.add('PROVENANCE_UNKNOWN_ROW')
    if len(set(appended_seen)) != len(appended_seen):
        errors.add('DUPLICATE_APPENDED_ROW')
    if licensed is not None and cited != set(licensed):
        errors.add('APPENDED_EVIDENCE_MISMATCH')
    if unresolved is not None:
        # Only a reason that withholds the row can be written by mistake. The other
        # placement reasons record a *field* left null on a row that was still written,
        # so they legitimately share `raw_reference_value` with a delivered row.
        withheld = {r['raw_reference_value'] for r in unresolved
                    if r.get('rule_id') == PLACEMENT_BUS_RULE
                    and r.get('raw_reference_value')
                    and r.get('reason') == WITHHOLDING_REASON}
        written = {_fields(row)[0] for _k, _n, row in appended_seen if _fields(row)}
        if withheld & written:
            errors.add('UNRESOLVED_ROW_WRITTEN')
    measured['provenance_records'] = len(provenance)
    measured['delivered_rows'] = delivered_rows
    measured['appended_rows'] = len(appended_seen)


def _ref(text):
    try:
        return SourceRecordRef(text)
    except (ValueError, TypeError):
        return None


def _licensed_records(ledger_records):
    """The ``PROPOSED`` records — the only ones that license an appended row.

    ``ACCEPTED_DETERMINISTIC_RECOVERY_V1`` is ``CONFIRMED`` and appends no CSV row by
    contract, so requiring the appended rows to cite it would reject every real delivery.
    A ``CONFIRMED`` record is still evidence in its own right and is checked below; it is
    simply not a row licence.
    """
    if ledger_records is None:
        return None
    return {r['record_id']: r for r in ledger_records
            if r.get('completion_status') == 'PROPOSED'}


def _check_confirmed_records(ledger_records, errors):
    """Every ``CONFIRMED`` record must carry the evidence that confirms it.

    Confirmation is not a row licence, but it is still a claim about the source: a
    CONFIRMED record with no cited evidence, or from a rule that does not confirm
    anything, is a record the delivery cannot stand behind.
    """
    if ledger_records is None:
        return
    for record in ledger_records:
        if record.get('completion_status') != 'CONFIRMED':
            continue
        if not record.get('evidence_refs'):
            errors.add('APPENDED_EVIDENCE_MISMATCH')
        if record.get('rule_id') not in (RECOVERY_RULE,):
            errors.add('APPENDED_EVIDENCE_MISMATCH')


def _appended_row(record, key, member, columns, archive, member_records, proposals,
                  evidence, bus_cache, licensed, cited, errors, delivered=None):
    """Re-derive one appended row's bytes and check the record that licenses it."""
    if set(record) != set(PROVENANCE_KEYS):
        # Already reported as incomplete; reading the missing keys would just crash.
        errors.add('PROVENANCE_INCOMPLETE')
        return b''
    rule = record['rule_id']
    contract = APPENDED_CONTRACT.get(rule)
    if contract is None or not record['evidence_refs']:
        errors.add('APPENDED_EVIDENCE_MISMATCH')
        return b''
    if (record['completion_status'] != contract['completion_status']
            or record['confidence_class'] != contract['confidence_class']):
        errors.add('APPENDED_EVIDENCE_MISMATCH')
    cited.update(record['evidence_refs'])
    if licensed is not None:
        owners = [licensed.get(rid) for rid in record['evidence_refs']]
        if any(o is None for o in owners):
            errors.add('APPENDED_EVIDENCE_MISMATCH')
        else:
            for owner in owners:
                if (owner['rule_id'] != rule or owner['tier'] != record['tier']
                        or owner['completion_status'] != record['completion_status']
                        or owner['confidence_class'] != record['confidence_class']):
                    errors.add('APPENDED_EVIDENCE_MISMATCH')
            if rule == PLACEMENT_BUS_RULE:
                if any(o['raw_reference_value'] != record['raw_reference_value']
                       for o in owners):
                    errors.add('APPENDED_EVIDENCE_MISMATCH')
                if record['raw_field'] != owners[0]['raw_field']:
                    errors.add('APPENDED_EVIDENCE_MISMATCH')
            else:
                if any(o['donor_source_record_ref'] != record['donor_source_record_ref']
                       for o in owners):
                    errors.add('APPENDED_EVIDENCE_MISMATCH')
            for owner in owners:
                if record['rule_version'] != owner['rule_version']:
                    errors.add('APPENDED_EVIDENCE_MISMATCH')
    if rule == CROSS_CASE_RULE:
        ref = _ref(record['donor_source_record_ref'] or '')
        if ref is None:
            errors.add('PROVENANCE_INCOMPLETE')
            return b''
        donor_member = member_path_of(ref)
        if not _has_member(archive, donor_member):
            errors.add('MEMBER_MISSING')
            return b''
        donor = member_records(donor_member)
        if ref.data_row >= len(donor):
            errors.add('APPENDED_ROW_NOT_DONOR_BYTES')
            return b''
        if delivered is not None and delivered != donor[ref.data_row]:
            errors.add('APPENDED_ROW_NOT_DONOR_BYTES')
        return donor[ref.data_row]
    return _generated_row(record, key, member, columns, archive, member_records,
                          proposals, evidence, bus_cache, errors, delivered)


def _generated_row(record, key, member, columns, archive, member_records, proposals,
                   evidence, bus_cache, errors, delivered=None):
    """Re-render a placement Bus row from the placement and station evidence.

    The delivered row is compared against the re-derived one field by field, so a row
    that names a real endpoint but carries a value the evidence does not support is
    caught even when it and its provenance agree with each other.
    """
    raw_value = record['raw_reference_value']
    if proposals is None:
        errors.add('PLACEMENT_FIELD_MISMATCH')
        return b''
    case_id = record['case_id']
    group, malformed = _placement_group(case_id, raw_value, proposals, evidence)
    if group is None:
        # No endpoint in this Case declares the value, so nothing licenses the row.
        errors.add('MINTED_IDENTIFIER')
        return b''
    if malformed:
        errors.add('UNRESOLVED_ROW_WRITTEN')
        return b''
    voltages = sorted(group)
    base_kv = voltages[0] if len(voltages) == 1 else None
    if key not in bus_cache:
        bus_member = f'{key}/{BUS_FILE}'
        bus_cache[key] = (raw_member_bytes(archive, bus_member)
                          if _has_member(archive, bus_member) else b'')
    values = {'Bus_ID': raw_value, 'Bus_Name': None, 'Bus_BaseKV': base_kv,
              'Bus_Phase': None,
              'Bus_Station_ID': _station_from_bus_member(bus_cache[key]),
              'Bus_IsSource': None}
    rendered = _render({name: values.get(name) for name in columns})
    if record['raw_field'] not in ('Line_FromBus', 'Line_ToBus'):
        errors.add('PLACEMENT_FIELD_MISMATCH')
    bus_id = _fields(rendered)
    if not bus_id or bus_id[0] != raw_value:
        errors.add('MINTED_IDENTIFIER')
    return rendered


def validate_delivery(root, *, ledger_root=None, roots=None, policy=None,
                      archive=None, archive_name=ARCHIVE_NAME):
    """Return the independent structural verdict for one delivery.

    ``roots`` supplies the source archive and the placement artifact; without them the
    byte-fidelity, upstream and identifier checks cannot run, and the verdict names them
    in ``measured['checks_skipped']`` rather than reporting a pass it did not establish.
    """
    root = Path(root)
    errors, measured, skipped = set(), {}, []
    manifest_path = root / 'manifest.json'
    if not manifest_path.is_file():
        return {'reasons': ['ARCHIVE_INVENTORY_MISMATCH'], 'structural_status': 'REJECTED',
                'measured': measured, 'checks_skipped': []}
    manifest = json.loads(manifest_path.read_text())
    _check_inventory(root, manifest, archive_name, errors, measured)
    _check_archive(root, archive_name, errors, measured)
    completion, unresolved = _check_ledger(ledger_root, roots, policy, manifest, errors,
                                           measured)
    _check_ledger_streams(root, ledger_root, errors)
    documents = _documents(root)
    _check_members(documents, roots, errors, measured)
    if roots is None:
        skipped.extend(('SOURCE_ROW_NOT_VERBATIM', 'APPENDED_ROW_NOT_DONOR_BYTES',
                        'APPENDED_EVIDENCE_MISMATCH', 'PLACEMENT_FIELD_MISMATCH',
                        'MINTED_IDENTIFIER', 'MEMBER_MISSING', 'UPSTREAM_INTEGRITY'))
    else:
        _check_upstreams(roots, errors, measured)
        source_archive = archive or _recorded_archive(roots['source'])
        if source_archive is None:
            errors.add('UPSTREAM_INTEGRITY')
            skipped.extend(('SOURCE_ROW_NOT_VERBATIM', 'APPENDED_ROW_NOT_DONOR_BYTES',
                            'APPENDED_EVIDENCE_MISMATCH', 'PLACEMENT_FIELD_MISMATCH'))
        else:
            _check_cross_case(roots, policy, completion, unresolved, errors)
            _check_provenance(root, documents, roots, source_archive, completion, unresolved,
                              errors, measured, policy,
                              cross_expected=_cross_case_events(roots, policy, errors)[0])
    if ledger_root is None:
        skipped.append('STALE_LEDGER_BASE')
    if policy is None:
        skipped.extend(('POLICY_HASH_MISMATCH', 'TIER_NOT_ENABLED', 'CLOSURE_NOT_BOUNDED'))
    measured['checks_skipped'] = sorted(set(skipped))
    return {'reasons': sorted(errors),
            'structural_status': 'REJECTED' if errors else 'PASS',
            'measured': measured,
            'checks_skipped': measured['checks_skipped'],
            'manifest_sha256': sha256(manifest_path.read_bytes()).hexdigest()}
