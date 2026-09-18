"""Read-only verbatim byte access for source ZIP members.

``csv_reader`` keeps only decoded field strings and ``SourceRecordRef`` exposes
no member path, so a later export slice that must copy a donor row byte-for-byte
cannot reconstruct the original bytes from the parsed model. This module adds a
narrow, read-only seam: re-derive the member path from a ``SourceRecordRef`` and
read one member's bytes verbatim, partitioning them into per-record byte slices
without decoding or normalizing anything.

The archive is always caller-owned: no function here opens the ZIP, so a whole
delivery run may open it exactly once.
"""

from urllib.parse import unquote_to_bytes
from zipfile import ZipFile

from .nanjing_source.locator import validate_zip_member_path


def member_path_of(ref) -> str:
    """Return the ZIP member path a ``SourceRecordRef`` does not expose."""
    text = str(ref)
    if not text.startswith('zip-member:') or '#data-row=' not in text:
        raise ValueError('v1 export: not a source record ref')
    encoded = text[len('zip-member:'):text.index('#data-row=')]
    return unquote_to_bytes(encoded).decode('utf-8')


def raw_member_bytes(archive: ZipFile, member_path: str) -> bytes:
    """Return one member's raw bytes from a caller-owned ``ZipFile``."""
    validate_zip_member_path(member_path)
    return archive.read(member_path)


def split_raw_records(member_bytes: bytes) -> tuple[bytes, ...]:
    """Partition member bytes into one verbatim slice per logical CSV record.

    Each slice excludes its record terminator (``\\r\\n``, lone ``\\n`` or lone
    ``\\r``). A terminator inside a double-quoted field is not a boundary, and
    ``""`` inside a quoted field is an escaped quote that does not close it. The
    leading UTF-8 BOM is retained in the first slice. No byte is dropped,
    altered, normalized or decoded; index 0 is the header record.
    """
    if not member_bytes:
        return ()

    records = []
    start = 0
    in_quotes = False
    at_field_start = True
    n = len(member_bytes)
    i = 0

    while i < n:
        byte = member_bytes[i]

        if in_quotes:
            if byte == 0x22:  # '"'
                if i + 1 < n and member_bytes[i + 1] == 0x22:
                    i += 2  # escaped quote
                    continue
                in_quotes = False
                i += 1
                continue
            i += 1
            continue

        # Not inside a quoted field.
        if at_field_start and byte == 0x22:  # '"'
            in_quotes = True
            at_field_start = False
            i += 1
            continue

        if byte == 0x2C:  # ','
            at_field_start = True
            i += 1
            continue

        if byte == 0x0A or byte == 0x0D:  # '\n' or '\r'
            records.append(member_bytes[start:i])
            if byte == 0x0D and i + 1 < n and member_bytes[i + 1] == 0x0A:
                i += 2  # \r\n
            else:
                i += 1
            start = i
            at_field_start = True
            continue

        at_field_start = False
        i += 1

    if in_quotes:
        raise ValueError('unterminated quoted field')

    if start < n:
        records.append(member_bytes[start:])

    return tuple(records)


def raw_record_bytes(member_bytes: bytes, data_row: int) -> bytes:
    """Return the raw bytes of one data row, indexed 1-based over data rows."""
    return split_raw_records(member_bytes)[data_row]
