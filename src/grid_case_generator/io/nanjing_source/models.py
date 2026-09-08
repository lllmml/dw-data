"""Structured results from Nanjing archive and raw CSV intake."""

from dataclasses import dataclass
from enum import StrEnum
import re

from .locator import SourceRecordRef, source_record_ref, validate_zip_member_path
from .schema import SourceFileType


_SOURCE_CHECKSUM = re.compile(r"sha256:[0-9a-f]{64}\Z")


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
    source_record_ref: SourceRecordRef | None
    expected_header: tuple[str, ...] | None = None
    observed_header: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceCaseInventory:
    source_case_key: str
    members: tuple[tuple[SourceFileType, str | None], ...]

    def __post_init__(self) -> None:
        if not self.source_case_key:
            raise ValueError("source_case_key must be non-empty")
        file_types = tuple(file_type for file_type, _ in self.members)
        if len(set(file_types)) != len(file_types) or set(file_types) != set(
            SourceFileType
        ):
            raise ValueError(
                "each source file type must occur exactly once within a case"
            )
        for _, member_path in self.members:
            if member_path is None:
                continue
            validate_zip_member_path(member_path)
            parent, separator, _ = member_path.rpartition("/")
            if not separator or parent != self.source_case_key:
                raise ValueError("case member parent must equal source_case_key")

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
class SourceDatasetInventory:
    source_uri: str
    source_checksum: str
    member_count: int
    csv_member_count: int
    cases: tuple[SourceCaseInventory, ...]
    diagnostics: tuple[IntakeDiagnostic, ...]

    def __post_init__(self) -> None:
        if not self.source_uri:
            raise ValueError("source_uri must be non-empty")
        if _SOURCE_CHECKSUM.fullmatch(self.source_checksum) is None:
            raise ValueError("source_checksum must be sha256:<64 lowercase hex digits>")
        if type(self.member_count) is not int or self.member_count < 0:
            raise ValueError("member_count must be a non-negative int")
        if type(self.csv_member_count) is not int or not (
            0 <= self.csv_member_count <= self.member_count
        ):
            raise ValueError("csv_member_count must be between zero and member_count")
        case_keys = tuple(case.source_case_key for case in self.cases)
        if case_keys != tuple(sorted(case_keys)) or len(set(case_keys)) != len(
            case_keys
        ):
            raise ValueError("cases must have unique, sorted source_case_key values")


@dataclass(frozen=True, slots=True, kw_only=True)
class RawCsvRecord:
    source_case_key: str
    source_file_type: SourceFileType
    header: tuple[str, ...]
    data_row: int
    source_record_ref: SourceRecordRef
    values: tuple[str, ...]
    fields: tuple[tuple[str, str], ...] | None

    def __post_init__(self) -> None:
        if not self.source_case_key:
            raise ValueError("source_case_key must be non-empty")
        if type(self.data_row) is not int or self.data_row < 1:
            raise ValueError("data_row must be a positive int")
        if not isinstance(self.source_record_ref, SourceRecordRef):
            raise TypeError("source_record_ref must be SourceRecordRef")
        if self.source_record_ref.data_row != self.data_row:
            raise ValueError("source_record_ref data row must match data_row")
        if not all(type(value) is str for value in self.values):
            raise TypeError("raw CSV values must all be str")
        if self.fields is not None:
            if tuple(name for name, _ in self.fields) != self.header:
                raise ValueError("field names must equal the recognized header")
            if tuple(value for _, value in self.fields) != self.values:
                raise ValueError("field values must equal raw values")


@dataclass(frozen=True, slots=True, kw_only=True)
class RawSourceFile:
    source_case_key: str
    source_file_type: SourceFileType
    member_path: str
    header: tuple[str, ...] | None
    records: tuple[RawCsvRecord, ...]
    diagnostics: tuple[IntakeDiagnostic, ...]

    def __post_init__(self) -> None:
        validate_zip_member_path(self.member_path)
        parent, separator, _ = self.member_path.rpartition("/")
        if not separator or parent != self.source_case_key:
            raise ValueError("source file parent must equal source_case_key")
        for record in self.records:
            if record.source_case_key != self.source_case_key:
                raise ValueError("record source_case_key must match its source file")
            if record.source_file_type is not self.source_file_type:
                raise ValueError("record source_file_type must match its source file")
            if self.header is None or record.header != self.header:
                raise ValueError("record header must match its source file")
            if record.source_record_ref != source_record_ref(
                self.member_path, data_row=record.data_row
            ):
                raise ValueError("record locator must identify its source file and row")
