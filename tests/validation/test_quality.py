import pytest

from grid_case_generator.models.records import DataQualityIssue
from grid_case_generator.models.types import (
    CanonicalId,
    ImportStatus,
    RecordOrigin,
    Severity,
)
from grid_case_generator.validation.quality import (
    DEFAULT_SEVERITY_BY_CODE,
    ImportErrorCategory,
    QualityIssueCode,
    import_status_for_error,
)


EXPECTED_DEFAULTS = {
    "SOURCE_FILE_MISSING": "ERROR",
    "SOURCE_FILE_READ_FAILED": "ERROR",
    "SOURCE_HEADER_MISMATCH": "ERROR",
    "SOURCE_FILE_NO_DATA_ROWS": "INFO",
    "SOURCE_ROW_MALFORMED": "ERROR",
    "SOURCE_REQUIRED_VALUE_MISSING": "ERROR",
    "SOURCE_VALUE_PARSE_FAILED": "WARNING",
    "SOURCE_VALUE_OUT_OF_RANGE": "ERROR",
    "SOURCE_ENUM_UNKNOWN": "WARNING",
    "SOURCE_IDENTIFIER_SUSPICIOUS_FORMAT": "WARNING",
    "SOURCE_ID_DUPLICATE_IDENTICAL": "WARNING",
    "SOURCE_ID_DUPLICATE_CONFLICT": "ERROR",
    "SOURCE_REFERENCE_INVALID_LITERAL": "WARNING",
    "SOURCE_REFERENCE_AMBIGUOUS": "ERROR",
    "SOURCE_REFERENCE_UNRESOLVED": "WARNING",
    "SOURCE_MEASUREMENT_TIME_UNKNOWN": "WARNING",
    "GRID_CASE_FEEDER_MISSING": "WARNING",
    "GRID_CASE_FEEDER_AMBIGUOUS": "ERROR",
    "CANONICAL_REQUIRED_FIELD_MISSING": "ERROR",
    "CANONICAL_UNIQUE_CONSTRAINT_VIOLATION": "ERROR",
    "CANONICAL_REFERENCE_INTEGRITY_ERROR": "ERROR",
}


def test_issue_code_registry_has_one_frozen_default_severity_per_code() -> None:
    assert {code.value for code in QualityIssueCode} == set(EXPECTED_DEFAULTS)
    assert {
        code.value: DEFAULT_SEVERITY_BY_CODE[code].value for code in QualityIssueCode
    } == EXPECTED_DEFAULTS


def test_data_quality_issue_rejects_non_default_severity() -> None:
    with pytest.raises(ValueError):
        DataQualityIssue(
            record_origin=RecordOrigin.DERIVED,
            source_record_ref=None,
            source_mapping_id=None,
            source_mapping_version=None,
            issue_id=CanonicalId("quality-issue:one"),
            case_id=None,
            target_ref=None,
            field_path=None,
            code=QualityIssueCode.SOURCE_FILE_NO_DATA_ROWS,
            severity=Severity.ERROR,
            observed_value=None,
            message="wrong severity",
        )


@pytest.mark.parametrize(
    ("category", "accounted_for", "expected"),
    [
        (ImportErrorCategory.FIELD_RECOVERABLE, True, ImportStatus.COMPLETE),
        (ImportErrorCategory.FIELD_RECOVERABLE, False, ImportStatus.INCOMPLETE),
        (ImportErrorCategory.RECORD_FATAL, True, ImportStatus.COMPLETE),
        (ImportErrorCategory.RECORD_FATAL, False, ImportStatus.INCOMPLETE),
        (ImportErrorCategory.PARTIAL_PROCESSING, True, ImportStatus.INCOMPLETE),
        (ImportErrorCategory.PARTIAL_PROCESSING, False, ImportStatus.INCOMPLETE),
        (ImportErrorCategory.RUN_FATAL, True, ImportStatus.FAILED),
        (ImportErrorCategory.RUN_FATAL, False, ImportStatus.FAILED),
    ],
)
def test_import_error_boundaries_are_independent_from_issue_severity(
    category: ImportErrorCategory,
    accounted_for: bool,
    expected: ImportStatus,
) -> None:
    assert import_status_for_error(category, accounted_for=accounted_for) is expected
