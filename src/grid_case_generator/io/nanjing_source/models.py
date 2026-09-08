"""Structured results from Nanjing archive and raw CSV intake."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .schema import SourceFileType


class IntakeDiagnosticCode(StrEnum):
    SOURCE_FILE_MISSING = "SOURCE_FILE_MISSING"
    SOURCE_FILE_READ_FAILED = "SOURCE_FILE_READ_FAILED"
    SOURCE_HEADER_MISMATCH = "SOURCE_HEADER_MISMATCH"
    SOURCE_FILE_NO_DATA_ROWS = "SOURCE_FILE_NO_DATA_ROWS"
    SOURCE_ROW_MALFORMED = "SOURCE_ROW_MALFORMED"


@dataclass(frozen=True, slots=True, kw_only=True)
class IntakeDiagnostic:
    code: IntakeDiagnosticCode
    message: str
    source_case_key: str | None
    member_path: str | None
    source_record_ref: str | None
    expected_header: tuple[str, ...] | None = None
    observed_header: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceCaseInventory:
    source_case_key: str
    members: tuple[tuple[SourceFileType, str | None], ...]

    def member_for(self, file_type: SourceFileType) -> str | None:
        for candidate_type, member_path in self.members:
            if candidate_type is file_type:
                return member_path
        raise KeyError(file_type)

    @property
    def missing_file_types(self) -> tuple[SourceFileType, ...]:
        return tuple(
            file_type for file_type, member_path in self.members if member_path is None
        )

    @property
    def is_complete(self) -> bool:
        return not self.missing_file_types


@dataclass(frozen=True, slots=True, kw_only=True)
class ArchiveInventory:
    archive_path: Path
    member_count: int
    csv_member_count: int
    cases: tuple[SourceCaseInventory, ...]
    diagnostics: tuple[IntakeDiagnostic, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class RawCsvRow:
    data_row: int
    source_record_ref: str
    values: tuple[str, ...]
    fields: tuple[tuple[str, str], ...] | None


@dataclass(frozen=True, slots=True, kw_only=True)
class RawCsvFile:
    source_case_key: str
    file_type: SourceFileType
    member_path: str
    header: tuple[str, ...] | None
    rows: tuple[RawCsvRow, ...]
    diagnostics: tuple[IntakeDiagnostic, ...]
