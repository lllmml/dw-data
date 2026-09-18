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
    source_record_ref, validate_zip_member_path,
)
from grid_case_generator.io.source_bytes import raw_member_bytes, split_raw_records
from grid_case_generator.io.switch_projection_artifacts import check_output
from grid_case_generator.models.completion_export import (
    PASSTHROUGH_RULE, RULE_VERSION, policy_sha256, provenance_id as provenance_id_of,
)

DELIVERY_DATA_DIR = 'data'
PROVENANCE_DIR = 'provenance'
ARCHIVE_NAME = 'nanjing-derived-v1.zip'
ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

PROVENANCE_KEYS = ('provenance_id', 'case_id', 'source_case_key', 'target_file',
    'row_index', 'row_kind', 'completion_status', 'confidence_class', 'tier', 'rule_id',
    'rule_version', 'source_record_ref', 'donor_source_record_ref', 'raw_field',
    'raw_reference_value', 'evidence_refs', 'policy_id', 'policy_sha256')


def passthrough_member(archive, member_path, destination) -> bytes:
    """Stream one source member's raw bytes to ``destination``, verbatim."""
    data = raw_member_bytes(archive, member_path)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
    return data


def write_delivery(root, *, archive_path, cases, policy, roots, progress=None):
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

    case_count = 0
    member_count = 0
    source_rows = 0
    previous_case_key = None

    with ZipFile(archive_path, 'r') as archive, provenance_path.open('xb') as stream:
        for case_index, (case_id, case_key, members) in enumerate(cases, 1):
            if previous_case_key is not None and case_key <= previous_case_key:
                raise ValueError('v1 delivery case ordering')
            previous_case_key = case_key
            case_count += 1
            for _file_type, member_path in members:
                validate_zip_member_path(member_path)
                filename = member_path.rsplit('/', 1)[-1]
                member_bytes = passthrough_member(
                    archive, member_path, root / DELIVERY_DATA_DIR / case_key / filename)
                records = split_raw_records(member_bytes)
                member_count += 1
                source_rows += max(0, len(records) - 1)
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
            if progress is not None:
                progress(case_index, case_id)

    return {'cases': case_count, 'members': member_count, 'source_rows': source_rows}
