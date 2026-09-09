"""Nanjing adapter policy for source-reference quality issues."""

from collections.abc import Callable

from grid_case_generator.models.identifiers import SourceImportIdFactory
from grid_case_generator.models.quality import QualityIssueCode
from grid_case_generator.models.records import DataQualityIssue
from grid_case_generator.models.types import (
    CanonicalId,
    EntityRef,
    RecordOrigin,
    Severity,
    SourceReferenceStatus,
)
from grid_case_generator.validation.quality import default_severity_for_issue
from grid_case_generator.validation.reference_resolution import (
    ReferenceResolutionResult,
)

from .schema import NANJING_SOURCE_SCHEMA


SeverityPolicy = Callable[[QualityIssueCode], Severity]
_ISSUE_CODE_BY_STATUS = {
    SourceReferenceStatus.AMBIGUOUS: (
        QualityIssueCode.SOURCE_REFERENCE_AMBIGUOUS
    ),
    SourceReferenceStatus.UNRESOLVED: (
        QualityIssueCode.SOURCE_REFERENCE_UNRESOLVED
    ),
}
_MESSAGE_BY_STATUS = {
    SourceReferenceStatus.AMBIGUOUS: (
        "source reference does not identify a unique exact candidate"
    ),
    SourceReferenceStatus.UNRESOLVED: (
        "source reference has no exact candidate in the allowed scope"
    ),
}


def reference_issues_for_result(
    result: ReferenceResolutionResult,
    *,
    dataset_id: CanonicalId,
    target_ref: EntityRef,
    severity_for: SeverityPolicy = default_severity_for_issue,
) -> tuple[DataQualityIssue, ...]:
    """Apply adapter issue policy without changing the resolution result."""

    if not isinstance(result, ReferenceResolutionResult):
        raise TypeError("result must be ReferenceResolutionResult")
    if not isinstance(dataset_id, CanonicalId):
        raise TypeError("dataset_id must be CanonicalId")
    if not isinstance(target_ref, EntityRef):
        raise TypeError("target_ref must be EntityRef")
    code = _ISSUE_CODE_BY_STATUS.get(result.resolution_status)
    if code is None:
        return ()
    severity = severity_for(code)
    if not isinstance(severity, Severity):
        raise TypeError("severity policy must return Severity")

    request = result.request
    issue_id = SourceImportIdFactory.quality_issue_id(
        dataset_id=dataset_id,
        case_id=request.case_id,
        target_ref=target_ref,
        field_path=request.reference_field_path,
        code=code,
        source_record_ref=request.owner_source_record_ref,
        occurrence_key="",
    )
    return (
        DataQualityIssue(
            record_origin=RecordOrigin.DERIVED,
            source_record_ref=request.owner_source_record_ref,
            source_mapping_id=NANJING_SOURCE_SCHEMA.mapping_id,
            source_mapping_version=NANJING_SOURCE_SCHEMA.mapping_version,
            issue_id=issue_id,
            case_id=request.case_id,
            target_ref=target_ref,
            field_path=request.reference_field_path,
            code=code,
            severity=severity,
            observed_value=request.raw_reference_value,
            message=_MESSAGE_BY_STATUS[result.resolution_status],
        ),
    )
