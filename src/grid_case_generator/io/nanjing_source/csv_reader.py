"""BOM-safe, string-preserving raw CSV member reader."""

import csv
from io import TextIOWrapper
from zipfile import BadZipFile, ZipFile

from .locator import source_record_ref, validate_zip_member_path
from .models import IntakeDiagnostic, IntakeDiagnosticCode, RawCsvFile, RawCsvRow
from .schema import SourceFileSchema


def _diagnostic(
    *,
    code: IntakeDiagnosticCode,
    message: str,
    source_case_key: str,
    member_path: str,
    row_ref: str | None = None,
    expected_header: tuple[str, ...] | None = None,
    observed_header: tuple[str, ...] | None = None,
) -> IntakeDiagnostic:
    return IntakeDiagnostic(
        code=code,
        message=message,
        source_case_key=source_case_key,
        member_path=member_path,
        source_record_ref=row_ref,
        expected_header=expected_header,
        observed_header=observed_header,
    )


def read_raw_csv_member(
    archive: ZipFile,
    *,
    source_case_key: str,
    member_path: str,
    file_schema: SourceFileSchema,
) -> RawCsvFile:
    """Read one expected member without mapping or normalizing any field."""

    validate_zip_member_path(member_path)
    rows: list[RawCsvRow] = []
    diagnostics: list[IntakeDiagnostic] = []
    header: tuple[str, ...] | None = None

    try:
        with archive.open(member_path, mode="r") as binary_stream:
            with TextIOWrapper(
                binary_stream, encoding="utf-8-sig", errors="strict", newline=""
            ) as text_stream:
                reader = csv.reader(text_stream, strict=True)
                try:
                    header = tuple(next(reader))
                except StopIteration:
                    header = ()

                if header != file_schema.header:
                    diagnostics.append(
                        _diagnostic(
                            code=IntakeDiagnosticCode.SOURCE_HEADER_MISMATCH,
                            message="source header does not match the versioned schema",
                            source_case_key=source_case_key,
                            member_path=member_path,
                            expected_header=file_schema.header,
                            observed_header=header,
                        )
                    )
                    return RawCsvFile(
                        source_case_key=source_case_key,
                        file_type=file_schema.file_type,
                        member_path=member_path,
                        header=header,
                        rows=(),
                        diagnostics=tuple(diagnostics),
                    )

                data_row = 0
                while True:
                    next_data_row = data_row + 1
                    try:
                        values = tuple(next(reader))
                    except StopIteration:
                        break
                    except csv.Error as error:
                        row_ref = source_record_ref(
                            member_path, data_row=next_data_row
                        )
                        diagnostics.append(
                            _diagnostic(
                                code=IntakeDiagnosticCode.SOURCE_ROW_MALFORMED,
                                message=(
                                    "CSV logical record could not be parsed: "
                                    f"{error}"
                                ),
                                source_case_key=source_case_key,
                                member_path=member_path,
                                row_ref=row_ref,
                            )
                        )
                        break

                    data_row = next_data_row
                    row_ref = source_record_ref(member_path, data_row=data_row)
                    fields = (
                        tuple(zip(header, values, strict=True))
                        if len(values) == len(header)
                        else None
                    )
                    rows.append(
                        RawCsvRow(
                            data_row=data_row,
                            source_record_ref=row_ref,
                            values=values,
                            fields=fields,
                        )
                    )
                    if fields is None:
                        diagnostics.append(
                            _diagnostic(
                                code=IntakeDiagnosticCode.SOURCE_ROW_MALFORMED,
                                message=(
                                    "CSV logical record field count does not match "
                                    "the recognized header"
                                ),
                                source_case_key=source_case_key,
                                member_path=member_path,
                                row_ref=row_ref,
                                expected_header=header,
                            )
                        )
    except (
        BadZipFile,
        KeyError,
        OSError,
        RuntimeError,
        UnicodeError,
        csv.Error,
    ) as error:
        diagnostics.append(
            _diagnostic(
                code=IntakeDiagnosticCode.SOURCE_FILE_READ_FAILED,
                message=f"source member could not be read: {error}",
                source_case_key=source_case_key,
                member_path=member_path,
            )
        )
        return RawCsvFile(
            source_case_key=source_case_key,
            file_type=file_schema.file_type,
            member_path=member_path,
            header=header,
            rows=tuple(rows),
            diagnostics=tuple(diagnostics),
        )

    if not rows and not diagnostics:
        diagnostics.append(
            _diagnostic(
                code=IntakeDiagnosticCode.SOURCE_FILE_NO_DATA_ROWS,
                message="source file has a recognized header but no data rows",
                source_case_key=source_case_key,
                member_path=member_path,
            )
        )

    return RawCsvFile(
        source_case_key=source_case_key,
        file_type=file_schema.file_type,
        member_path=member_path,
        header=header,
        rows=tuple(rows),
        diagnostics=tuple(diagnostics),
    )
