"""Byte-identical SOURCE_PASSTHROUGH_V1 delivery; the first slice that writes CSV.

The delivered ``data/`` tree streams each source ZIP member's raw bytes straight
to its destination path. No member is decoded and re-encoded — the ``csv`` module
never appears here, so quoting, newline convention and the UTF-8 BOM all survive
verbatim. One canonical provenance record is emitted per delivered source data
row into ``provenance/row_provenance.jsonl``.
"""
from pathlib import Path
from zipfile import ZipFile

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.nanjing_source.locator import (
    SourceRecordRef, source_record_ref, validate_zip_member_path,
)
from grid_case_generator.io.source_bytes import (
    member_path_of, raw_member_bytes, split_raw_records,
)
from grid_case_generator.io.switch_projection_artifacts import check_output
from grid_case_generator.models.completion_export import (
    CROSS_CASE_RULE, CROSS_CASE_RULE_VERSION, PASSTHROUGH_RULE, RULE_VERSION,
    policy_sha256, provenance_id as provenance_id_of,
)

DELIVERY_DATA_DIR = 'data'
PROVENANCE_DIR = 'provenance'
ARCHIVE_NAME = 'nanjing-derived-v1.zip'
ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

PROVENANCE_KEYS = ('provenance_id', 'case_id', 'source_case_key', 'target_file',
    'row_index', 'row_kind', 'completion_status', 'confidence_class', 'tier', 'rule_id',
    'rule_version', 'source_record_ref', 'donor_source_record_ref', 'raw_field',
    'raw_reference_value', 'evidence_refs', 'policy_id', 'policy_sha256')


class _MemberCache:
    """Split each source member at most once, keyed by member path."""
    def __init__(self, archive):
        self._archive, self._records = archive, {}

    def records(self, member_path):
        if member_path not in self._records:
            self._records[member_path] = split_raw_records(
                raw_member_bytes(self._archive, member_path))
        return self._records[member_path]


def write_member(archive, member_path, destination, appended=()) -> bytes:
    """Stream one member's source bytes verbatim, then any appended donor rows.

    The ``endswith`` check is load-bearing: a member whose final record carries no
    terminator would otherwise have the appended block concatenated onto that record.
    The separator exists only to prevent two logical records from merging; it is not
    source normalization, so the source region stays verbatim and a member whose own
    terminators differ ends up mixed.
    """
    data = raw_member_bytes(archive, member_path)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
        if appended:
            if not data.endswith((b'\r\n', b'\n', b'\r')):
                stream.write(b'\r\n')
            stream.write(b'\r\n'.join(appended) + b'\r\n')
    return data


def passthrough_member(archive, member_path, destination) -> bytes:
    """Stream one source member's raw bytes to ``destination``, verbatim."""
    return write_member(archive, member_path, destination)


def write_delivery(root, *, archive_path, cases, policy, roots, append_plan=(), progress=None):
    """Write the v1 delivery tree: every source member byte-identical, plus provenance.

    ``cases`` is an iterable of ``(case_id, source_case_key, members)`` from a
    verified source-import artifact, so its ordering is already canonical; it is
    asserted here rather than re-derived. The inventory is ordered by
    ``source_case_key``; ``case_id`` is a sha256-derived hash and carries no
    ordering guarantee, so the assertion keys on ``source_case_key``.
    """
    root = Path(root)
    check_output(root, roots)
    resolved = root.resolve()
    if any(p.name == 'raw' and p.parent.name == 'data' for p in (resolved, *resolved.parents)):
        raise ValueError('v1 delivery output cannot be data/raw')
    if root.exists():
        raise FileExistsError(root)
    root.mkdir(parents=True)

    provenance_dir = root / PROVENANCE_DIR
    provenance_dir.mkdir(parents=True, exist_ok=True)
    provenance_path = provenance_dir / 'row_provenance.jsonl'

    policy_id = policy.policy_version
    policy_hash = policy_sha256(policy)

    append_by_member = {}
    for entry in append_plan:
        append_by_member.setdefault(entry['destination_member'], []).append(entry)

    case_count = 0
    member_count = 0
    source_rows = 0
    appended_rows = 0
    previous_case_key = None

    with ZipFile(archive_path, 'r') as archive, provenance_path.open('xb') as stream:
        cache = _MemberCache(archive)
        for case_index, (case_id, case_key, members) in enumerate(cases, 1):
            if previous_case_key is not None and case_key <= previous_case_key:
                raise ValueError('v1 delivery case ordering')
            previous_case_key = case_key
            case_count += 1
            for _file_type, member_path in members:
                validate_zip_member_path(member_path)
                if not member_path.startswith(case_key + '/'):
                    raise ValueError('v1 delivery member outside its case scope: ' + member_path)
                filename = member_path.rsplit('/', 1)[-1]
                planned = append_by_member.get(member_path, ())
                appended = []
                for entry in planned:
                    ref = SourceRecordRef(entry['donor_source_record_ref'])
                    appended.append(cache.records(member_path_of(ref))[ref.data_row])
                data = write_member(archive, member_path,
                                    root / DELIVERY_DATA_DIR / case_key / filename,
                                    appended=appended)
                records = split_raw_records(data)
                member_count += 1
                n_source = max(0, len(records) - 1)
                source_rows += n_source
                appended_rows += len(appended)
                for n in range(1, len(records)):
                    record = {
                        'case_id': case_id,
                        'source_case_key': case_key,
                        'target_file': filename,
                        'row_index': n - 1,
                        'row_kind': 'SOURCE',
                        'completion_status': 'CONFIRMED',
                        'confidence_class': 'EXACT_STRUCTURAL',
                        'tier': None,
                        'rule_id': PASSTHROUGH_RULE,
                        'rule_version': RULE_VERSION,
                        'source_record_ref': source_record_ref(member_path, data_row=n),
                        'donor_source_record_ref': None,
                        'raw_field': None,
                        'raw_reference_value': None,
                        'evidence_refs': [],
                        'policy_id': policy_id,
                        'policy_sha256': policy_hash,
                    }
                    record['provenance_id'] = provenance_id_of(
                        {k: record[k] for k in PROVENANCE_KEYS if k != 'provenance_id'})
                    stream.write(canonical_json_bytes(record) + b'\n')
                for j, entry in enumerate(planned):
                    record = {
                        'case_id': case_id,
                        'source_case_key': case_key,
                        'target_file': filename,
                        'row_index': n_source + j,
                        'row_kind': 'APPENDED',
                        'completion_status': 'PROPOSED',
                        'confidence_class': 'UNIQUE_EVIDENCE',
                        'tier': 'SAME_STATION',
                        'rule_id': CROSS_CASE_RULE,
                        'rule_version': CROSS_CASE_RULE_VERSION,
                        'source_record_ref': entry['source_record_ref'],
                        'donor_source_record_ref': entry['donor_source_record_ref'],
                        'raw_field': None,
                        'raw_reference_value': None,
                        'evidence_refs': list(entry['record_ids']),
                        'policy_id': policy_id,
                        'policy_sha256': policy_hash,
                    }
                    record['provenance_id'] = provenance_id_of(
                        {k: record[k] for k in PROVENANCE_KEYS if k != 'provenance_id'})
                    stream.write(canonical_json_bytes(record) + b'\n')
            if progress is not None:
                progress(case_index, case_id)

    return {'cases': case_count, 'members': member_count, 'source_rows': source_rows,
            'appended_rows': appended_rows}
