"""Independent v1 delivery validator: re-derives every claim from persisted evidence.

It shares no code with ``generation/completion_ledger.py``. Row identity, byte fidelity,
identifier provenance, tier membership, closure bounds and the provenance joins are all
re-derived here from the delivered tree, the ledger artifact, the source archive and the
placement artifact, so a defect that the engine and the writer agree on is still caught.

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
    CROSS_CASE_RULE, PLACEMENT_BUS_RULE, policy_sha256)

REASONS = (
    'SOURCE_ROW_NOT_VERBATIM',
    'APPENDED_ROW_NOT_DONOR_BYTES',
    'MINTED_IDENTIFIER',
    'TIER_NOT_ENABLED',
    'CLOSURE_NOT_BOUNDED',
    'PROVENANCE_INCOMPLETE',
    'PROVENANCE_UNKNOWN_ROW',
    'UNRESOLVED_ROW_WRITTEN',
    'DUPLICATE_APPENDED_ROW',
    'CSV_COLUMN_SCHEMA_CHANGED',
    'POLICY_HASH_MISMATCH',
    'LEDGER_BINDING_MISMATCH',
    'STALE_LEDGER_BASE',
    'MEMBER_MISSING',
    'ARCHIVE_INVENTORY_MISMATCH',
)
PROVENANCE_NAME = 'row_provenance.jsonl'
# The one placement reason that withholds a row, rather than nulling a field on one.
WITHHOLDING_REASON = 'EVIDENCE_JOIN_MISMATCH'
ARCHIVE_NAME = 'nanjing-derived-v1.zip'
LEDGER_COPIES = ('completion_records.jsonl', 'unresolved_records.jsonl')
PROVENANCE_KEYS = ('provenance_id', 'case_id', 'source_case_key', 'target_file',
    'row_index', 'row_kind', 'completion_status', 'confidence_class', 'tier', 'rule_id',
    'rule_version', 'source_record_ref', 'donor_source_record_ref', 'raw_field',
    'raw_reference_value', 'evidence_refs', 'policy_id', 'policy_sha256')


def _rows(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def _fields(raw_row):
    return next(csv.reader(io.StringIO(raw_row.decode('utf-8-sig'), newline='')), [])


def _documents(root):
    """Yield ``(source_case_key, filename, bytes)`` for every delivered CSV, in order."""
    data_root = root / 'data'
    for path in sorted(data_root.rglob('*.csv')):
        relative = path.relative_to(data_root)
        yield relative.parent.as_posix(), path.name, path.read_bytes()


def _has_member(archive, member):
    try:
        archive.getinfo(member)
    except KeyError:
        return False
    return True


def _member_rows(archive, member_records, member):
    """The member's records, or ``None`` when the archive does not carry it.

    A verifier that raises on a tampered tree is a verifier a caller cannot use: the
    missing member is the finding, so it becomes a reason rather than a traceback.
    """
    if not _has_member(archive, member):
        return None
    try:
        return member_records(member)
    except (KeyError, ValueError, OSError):
        return None


def _recorded_archive(source_root):
    """The source ZIP the import artifact recorded, held to its recorded checksum.

    Derived here rather than shared with the ledger loader: the validator must be able to
    disagree with the pipeline, which it cannot do if it inherits the pipeline's own
    reading of the same artifact.
    """
    dataset = json.loads((Path(source_root) / 'dataset.json').read_text())
    path = Path(dataset['source_uri'])
    if not path.is_file():
        return None
    if sha256(path.read_bytes()).hexdigest() != str(dataset['source_checksum']).split(':', 1)[-1]:
        return None
    return path


def _placement_endpoint_values(roots):
    """The source-declared unresolved endpoint values a generated ``Bus_ID`` may be."""
    if roots is None or 'placement' not in roots:
        return None
    path = Path(roots['placement']) / 'line_component_proposals.jsonl'
    if not path.is_file():
        return None
    values = set()
    for line in path.read_bytes().splitlines():
        for endpoint in json.loads(line)['endpoints']:
            if endpoint['anchor_origin'] != 'ACCEPTED_NODE' and endpoint['raw_endpoint_value']:
                values.add(endpoint['raw_endpoint_value'])
    return values


def _check_inventory(root, manifest, archive_name, errors, measured):
    """The tree is the manifest's inventory plus the carve-outs, and it re-hashes.

    Re-hashing matters as much as the key set: without it the manifest is an unchecked
    claim, and a tree edited after the manifest was written would pass on names alone.
    """
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


def _check_members(root, roots, errors, measured):
    """Every source member is present, and every delivered header is the source schema's."""
    headers = {schema.filename: tuple(schema.header) for schema in NANJING_SOURCE_SCHEMA.files}
    delivered = {f'{key}/{name}' for key, name, _data in _documents(root)}
    if roots is not None and 'source' in roots:
        inventory = Path(roots['source']) / 'inventory.json'
        if inventory.is_file():
            expected = {member for case in json.loads(inventory.read_text())['cases']
                        for _file_type, member in case['members']}
            if expected - delivered:
                errors.add('MEMBER_MISSING')
            measured['members_expected'] = len(expected)
    for _key, name, data in _documents(root):
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


def _check_provenance(root, source_archive, unresolved, endpoint_values, errors, measured):
    """Join every delivered row to exactly one provenance record, and re-derive its bytes."""
    provenance_path = root / 'provenance' / PROVENANCE_NAME
    if not provenance_path.is_file():
        errors.add('PROVENANCE_INCOMPLETE')
        return
    provenance = _rows(provenance_path)
    by_key = {}
    for record in provenance:
        key = (record['source_case_key'], record['target_file'], record['row_index'])
        if key in by_key or set(record) != set(PROVENANCE_KEYS):
            errors.add('DUPLICATE_APPENDED_ROW' if key in by_key else 'PROVENANCE_INCOMPLETE')
        by_key[key] = record
    delivered = set()
    appended = []
    with ZipFile(source_archive, 'r') as archive:
        cache = {}

        def member_records(member):
            if member not in cache:
                cache[member] = split_raw_records(raw_member_bytes(archive, member))
            return cache[member]

        for key, name, data in _documents(root):
            # split_raw_records, not a terminator split: the source region and the
            # appended block may use different terminators, and a quoted field may hold
            # a newline, so only an RFC-4180 scan finds the record boundaries.
            member = f'{key}/{name}'
            source_rows = member_records(member) if _has_member(archive, member) else ()
            n_source = max(0, len(source_rows) - 1)
            for row_index, raw_row in enumerate(split_raw_records(data)[1:]):
                identity = (key, name, row_index)
                delivered.add(identity)
                if row_index >= n_source:
                    # Anything past the source region is an appended row, whether or not
                    # it has a provenance record — a row written without one is exactly
                    # the case this must not lose.
                    appended.append((key, name, raw_row))
                record = by_key.get(identity)
                if record is None:
                    errors.add('PROVENANCE_INCOMPLETE')
                    continue
                # The rule that wrote a row decides which byte test applies, so the
                # record's own claims are checked before they are believed: a row that
                # calls itself SOURCE, or an appended row that names a rule which never
                # appends, must not be able to pick the cheapest check.
                if record['row_kind'] not in ('SOURCE', 'APPENDED'):
                    errors.add('PROVENANCE_INCOMPLETE')
                    continue
                if record['row_kind'] == 'APPENDED':
                    if record['rule_id'] not in (CROSS_CASE_RULE, PLACEMENT_BUS_RULE):
                        errors.add('PROVENANCE_INCOMPLETE')
                        continue
                    if record['rule_id'] == CROSS_CASE_RULE and not record['donor_source_record_ref']:
                        errors.add('PROVENANCE_INCOMPLETE')
                        continue
                if record['row_kind'] == 'SOURCE':
                    ref = SourceRecordRef(record['source_record_ref'])
                    member = member_path_of(ref)
                    source = _member_rows(archive, member_records, member)
                    if source is None:
                        errors.add('MEMBER_MISSING')
                        continue
                    # A SOURCE row mirrors the row at its own position in its own member.
                    # Without the positional half, a row could call itself a verbatim
                    # copy of *any* matching source row and be believed.
                    if member != f'{key}/{name}' or ref.data_row != row_index + 1:
                        errors.add('SOURCE_ROW_NOT_VERBATIM')
                    elif ref.data_row >= len(source) or source[ref.data_row] != raw_row:
                        errors.add('SOURCE_ROW_NOT_VERBATIM')
                    continue
                if record['rule_id'] == CROSS_CASE_RULE:
                    ref = SourceRecordRef(record['donor_source_record_ref'])
                    donor = _member_rows(archive, member_records, member_path_of(ref))
                    if donor is None:
                        errors.add('MEMBER_MISSING')
                    elif ref.data_row >= len(donor) or donor[ref.data_row] != raw_row:
                        errors.add('APPENDED_ROW_NOT_DONOR_BYTES')
                if record['rule_id'] == PLACEMENT_BUS_RULE and endpoint_values is not None:
                    fields = _fields(raw_row)
                    if fields and fields[0] and fields[0] not in endpoint_values:
                        errors.add('MINTED_IDENTIFIER')
    for key in by_key:
        if key not in delivered:
            errors.add('PROVENANCE_UNKNOWN_ROW')
    if len(set(appended)) != len(appended):
        errors.add('DUPLICATE_APPENDED_ROW')
    if unresolved is not None:
        # Only a reason that withholds the row can be written by mistake. The other
        # placement reasons record a *field* left null on a row that was still written,
        # so they legitimately share `raw_reference_value` with a delivered row.
        withheld = {r['raw_reference_value'] for r in unresolved
                    if r.get('rule_id') == PLACEMENT_BUS_RULE
                    and r.get('raw_reference_value')
                    and r.get('reason') == WITHHOLDING_REASON}
        written = {_fields(raw)[0] for _key, _name, raw in appended if _fields(raw)}
        if withheld & written:
            errors.add('UNRESOLVED_ROW_WRITTEN')
    measured['provenance_records'] = len(provenance)
    measured['delivered_rows'] = len(delivered)
    measured['appended_rows'] = len(appended)


def validate_delivery(root, *, ledger_root=None, roots=None, policy=None,
                      archive=None, archive_name=ARCHIVE_NAME):
    """Return the independent structural verdict for one delivery.

    ``roots`` supplies the source archive and the placement artifact; without them the
    byte-fidelity and identifier checks cannot run, and the verdict names them in
    ``measured['checks_skipped']`` rather than reporting a pass it did not establish.
    """
    root = Path(root)
    errors, measured, skipped = set(), {}, []
    manifest_path = root / 'manifest.json'
    if not manifest_path.is_file():
        return {'reasons': ['ARCHIVE_INVENTORY_MISMATCH'], 'structural_status': 'REJECTED',
                'measured': measured}
    manifest = json.loads(manifest_path.read_text())
    _check_inventory(root, manifest, archive_name, errors, measured)
    _check_ledger(ledger_root, roots, policy, manifest, errors, measured)
    _check_members(root, roots, errors, measured)
    endpoint_values = _placement_endpoint_values(roots)
    source_archive = archive or (
        _recorded_archive(roots['source']) if roots and 'source' in roots else None)
    if source_archive is None:
        skipped.extend(('SOURCE_ROW_NOT_VERBATIM', 'APPENDED_ROW_NOT_DONOR_BYTES'))
    else:
        _check_provenance(root, source_archive, _ledger_unresolved(ledger_root),
                          endpoint_values, errors, measured)
    if endpoint_values is None:
        skipped.append('MINTED_IDENTIFIER')
    if ledger_root is None:
        skipped.append('STALE_LEDGER_BASE')
    if policy is None:
        skipped.extend(('POLICY_HASH_MISMATCH', 'TIER_NOT_ENABLED', 'CLOSURE_NOT_BOUNDED'))
    measured['checks_skipped'] = sorted(set(skipped))
    return {'reasons': sorted(errors),
            'structural_status': 'REJECTED' if errors else 'PASS',
            'measured': measured,
            'manifest_sha256': sha256(manifest_path.read_bytes()).hexdigest()}


def _ledger_unresolved(ledger_root):
    if ledger_root is None:
        return None
    path = Path(ledger_root) / 'unresolved_records.jsonl'
    return _rows(path) if path.is_file() else None
