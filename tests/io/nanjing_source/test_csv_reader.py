import io
from collections.abc import Iterator
from contextlib import contextmanager
from zipfile import ZipFile

from grid_case_generator.io.nanjing_source.csv_reader import read_raw_csv_member
from grid_case_generator.io.nanjing_source.models import IntakeDiagnosticCode
from grid_case_generator.io.nanjing_source.schema import (
    NANJING_SOURCE_SCHEMA,
    SourceFileType,
)


CASE_KEY = "数据/case space%#?"
STATION_SCHEMA = NANJING_SOURCE_SCHEMA.for_type(SourceFileType.STATION)
MEMBER_PATH = f"{CASE_KEY}/{STATION_SCHEMA.filename}"


@contextmanager
def _open_archive(payload: bytes) -> Iterator[ZipFile]:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(MEMBER_PATH, payload)
    buffer.seek(0)
    with ZipFile(buffer, "r") as archive:
        yield archive


def test_reader_is_bom_safe_and_preserves_every_field_as_exact_string() -> None:
    source = (
        "\ufeff"
        + ",".join(STATION_SCHEMA.header)
        + "\r\n"
        + '0012345678901234567,1e+19," 甲%#? ",1.0,,\r\n'
    ).encode("utf-8")
    with _open_archive(source) as archive:
        result = read_raw_csv_member(
            archive,
            source_case_key=CASE_KEY,
            member_path=MEMBER_PATH,
            file_schema=STATION_SCHEMA,
        )

    assert result.header == STATION_SCHEMA.header
    assert result.diagnostics == ()
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.data_row == 1
    assert row.values == (
        "0012345678901234567",
        "1e+19",
        " 甲%#? ",
        "1.0",
        "",
        "",
    )
    assert all(type(value) is str for value in row.values)
    assert row.fields == tuple(zip(STATION_SCHEMA.header, row.values, strict=True))


def test_embedded_newline_is_one_logical_record_for_locator_numbering() -> None:
    source = (
        "\ufeff"
        + ",".join(STATION_SCHEMA.header)
        + "\r\n"
        + '001,T,"line one\nline two",10,,\r\n'
        + "002,T,name,10,,\r\n"
    ).encode("utf-8")
    with _open_archive(source) as archive:
        result = read_raw_csv_member(
            archive,
            source_case_key=CASE_KEY,
            member_path=MEMBER_PATH,
            file_schema=STATION_SCHEMA,
        )

    assert [row.data_row for row in result.rows] == [1, 2]
    assert result.rows[0].values[2] == "line one\nline two"
    assert result.rows[1].source_record_ref.endswith("#data-row=2")
    assert "%20" in result.rows[0].source_record_ref
    assert "%25%23%3F" in result.rows[0].source_record_ref


def test_header_mismatch_is_a_structured_file_diagnostic() -> None:
    with _open_archive(b"\xef\xbb\xbfWrong,Header\r\n1,2\r\n") as archive:
        result = read_raw_csv_member(
            archive,
            source_case_key=CASE_KEY,
            member_path=MEMBER_PATH,
            file_schema=STATION_SCHEMA,
        )

    assert result.rows == ()
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.code is IntakeDiagnosticCode.SOURCE_HEADER_MISMATCH
    assert diagnostic.expected_header == STATION_SCHEMA.header
    assert diagnostic.observed_header == ("Wrong", "Header")
    assert diagnostic.source_record_ref is None


def test_zero_byte_file_is_reported_as_header_mismatch() -> None:
    with _open_archive(b"") as archive:
        result = read_raw_csv_member(
            archive,
            source_case_key=CASE_KEY,
            member_path=MEMBER_PATH,
            file_schema=STATION_SCHEMA,
        )

    assert result.header == ()
    assert result.rows == ()
    assert result.diagnostics[0].code is IntakeDiagnosticCode.SOURCE_HEADER_MISMATCH


def test_only_header_is_reported_without_creating_a_raw_row() -> None:
    source = ("\ufeff" + ",".join(STATION_SCHEMA.header) + "\r\n").encode()
    with _open_archive(source) as archive:
        result = read_raw_csv_member(
            archive,
            source_case_key=CASE_KEY,
            member_path=MEMBER_PATH,
            file_schema=STATION_SCHEMA,
        )

    assert result.rows == ()
    assert result.diagnostics[0].code is IntakeDiagnosticCode.SOURCE_FILE_NO_DATA_ROWS


def test_wrong_field_count_preserves_raw_values_and_reports_logical_row() -> None:
    source = (
        "\ufeff"
        + ",".join(STATION_SCHEMA.header)
        + "\r\n001,T,missing-columns\r\n"
    ).encode()
    with _open_archive(source) as archive:
        result = read_raw_csv_member(
            archive,
            source_case_key=CASE_KEY,
            member_path=MEMBER_PATH,
            file_schema=STATION_SCHEMA,
        )

    row = result.rows[0]
    assert row.values == ("001", "T", "missing-columns")
    assert row.fields is None
    diagnostic = result.diagnostics[0]
    assert diagnostic.code is IntakeDiagnosticCode.SOURCE_ROW_MALFORMED
    assert diagnostic.source_record_ref == row.source_record_ref
    assert diagnostic.source_record_ref.endswith("#data-row=1")


def test_invalid_csv_quoting_is_a_structured_raw_row_diagnostic() -> None:
    source = (
        "\ufeff"
        + ",".join(STATION_SCHEMA.header)
        + '\r\n001,T,"unterminated,10,,\r\n'
    ).encode()
    with _open_archive(source) as archive:
        result = read_raw_csv_member(
            archive,
            source_case_key=CASE_KEY,
            member_path=MEMBER_PATH,
            file_schema=STATION_SCHEMA,
        )

    assert result.rows == ()
    assert result.diagnostics[0].code is IntakeDiagnosticCode.SOURCE_ROW_MALFORMED
    assert result.diagnostics[0].source_record_ref is not None
    assert result.diagnostics[0].source_record_ref.endswith("#data-row=1")


def test_invalid_utf8_is_a_structured_file_read_failure() -> None:
    with _open_archive(b"\xff\xfe\x00") as archive:
        result = read_raw_csv_member(
            archive,
            source_case_key=CASE_KEY,
            member_path=MEMBER_PATH,
            file_schema=STATION_SCHEMA,
        )

    assert result.rows == ()
    assert result.diagnostics[0].code is IntakeDiagnosticCode.SOURCE_FILE_READ_FAILED
    assert result.diagnostics[0].source_record_ref is None
