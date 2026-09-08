"""Source Import error categories and quality registry exports."""

from enum import StrEnum

from grid_case_generator.models.quality import (
    DEFAULT_SEVERITY_BY_CODE,
    QualityIssueCode,
)
from grid_case_generator.models.types import ImportStatus, Severity


class ImportErrorCategory(StrEnum):
    FIELD_RECOVERABLE = "FIELD_RECOVERABLE"
    RECORD_FATAL = "RECORD_FATAL"
    PARTIAL_PROCESSING = "PARTIAL_PROCESSING"
    RUN_FATAL = "RUN_FATAL"


def default_severity_for_issue(code: QualityIssueCode) -> Severity:
    """Return the Source Import foundation default for an issue code."""

    if not isinstance(code, QualityIssueCode):
        raise TypeError("code must be QualityIssueCode")
    return DEFAULT_SEVERITY_BY_CODE[code]


def import_status_for_error(
    category: ImportErrorCategory, *, accounted_for: bool
) -> ImportStatus:
    """Return the import status implied by a foundation error boundary."""

    if not isinstance(category, ImportErrorCategory):
        raise TypeError("category must be ImportErrorCategory")
    if type(accounted_for) is not bool:
        raise TypeError("accounted_for must be bool")
    if category is ImportErrorCategory.RUN_FATAL:
        return ImportStatus.FAILED
    if category is ImportErrorCategory.PARTIAL_PROCESSING or not accounted_for:
        return ImportStatus.INCOMPLETE
    return ImportStatus.COMPLETE
