"""Source identity grouping and duplicate classification primitives."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from grid_case_generator.models.identifiers import SourceImportIdFactory
from grid_case_generator.models.quality import QualityIssueCode
from grid_case_generator.models.records import DataQualityIssue
from grid_case_generator.models.types import (
    CanonicalId,
    EntityRef,
    EquipmentType,
    Identifier,
    IdentityStatus,
    RecordOrigin,
    SourceId,
)
from grid_case_generator.validation.quality import default_severity_for_issue


class SourceEntityType(StrEnum):
    STATION = "STATION"
    FEEDER = "FEEDER"
    BUS = "BUS"
    LINE = "LINE"
    SWITCH = "SWITCH"
    DISCONNECTOR = "DISCONNECTOR"
    EARTHING_SWITCH = "EARTHING_SWITCH"
    TRANSFORMER = "TRANSFORMER"
    ACCESS_POINT = "ACCESS_POINT"
    LOAD = "LOAD"
    DER = "DER"


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceIdentityRecord:
    case_id: CanonicalId
    source_entity_type: SourceEntityType
    source_id: SourceId
    source_record_ref: str
    decoded_fields: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, CanonicalId):
            raise TypeError("case_id must be CanonicalId")
        if not isinstance(self.source_entity_type, SourceEntityType):
            raise TypeError("source_entity_type must be SourceEntityType")
        if not isinstance(self.source_id, SourceId):
            raise TypeError("source_id must be SourceId")
        if not isinstance(self.source_record_ref, str):
            raise TypeError("source_record_ref must be str")
        if self.source_record_ref == "":
            raise ValueError("source_record_ref must be non-empty")
        if not all(
            type(name) is str and type(value) is str
            for name, value in self.decoded_fields
        ):
            raise TypeError("decoded field names and values must be str")


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceIdentityClassification:
    record: SourceIdentityRecord
    identity_status: IdentityStatus
    issue: DataQualityIssue | None

    def __post_init__(self) -> None:
        if self.identity_status is IdentityStatus.UNIQUE:
            if self.issue is not None:
                raise ValueError("UNIQUE identity must not have a duplicate issue")
        elif self.issue is None:
            raise ValueError("duplicate identity must have a duplicate issue")


def _target_ref(record: SourceIdentityRecord) -> EntityRef:
    if record.source_entity_type is SourceEntityType.STATION:
        entity_type = "STATION"
        entity_id = SourceImportIdFactory.station_id(
            record.case_id, record.source_id, record.source_record_ref
        )
    elif record.source_entity_type is SourceEntityType.FEEDER:
        entity_type = "FEEDER"
        entity_id = SourceImportIdFactory.feeder_id(
            record.case_id, record.source_id, record.source_record_ref
        )
    elif record.source_entity_type is SourceEntityType.BUS:
        entity_type = "BUS"
        entity_id = SourceImportIdFactory.bus_id(
            record.case_id, record.source_id, record.source_record_ref
        )
    else:
        entity_type = "EQUIPMENT"
        entity_id = SourceImportIdFactory.equipment_id(
            record.case_id,
            EquipmentType(record.source_entity_type.value),
            record.source_id,
            record.source_record_ref,
        )
    return EntityRef(entity_type=Identifier(entity_type), entity_id=entity_id)


def _duplicate_issue(
    record: SourceIdentityRecord,
    *,
    dataset_id: CanonicalId,
    status: IdentityStatus,
    source_mapping_id: str,
    source_mapping_version: str,
) -> DataQualityIssue:
    if status is IdentityStatus.DUPLICATE_IDENTICAL:
        code = QualityIssueCode.SOURCE_ID_DUPLICATE_IDENTICAL
        message = "source identity has multiple records with identical decoded fields"
    elif status is IdentityStatus.DUPLICATE_CONFLICT:
        code = QualityIssueCode.SOURCE_ID_DUPLICATE_CONFLICT
        message = "source identity has multiple records with conflicting decoded fields"
    else:
        raise ValueError("duplicate issue requires a duplicate identity status")

    target_ref = _target_ref(record)
    issue_id = SourceImportIdFactory.quality_issue_id(
        dataset_id=dataset_id,
        case_id=record.case_id,
        target_ref=target_ref,
        field_path="identity_status",
        code=code,
        source_record_ref=record.source_record_ref,
        occurrence_key="",
    )
    return DataQualityIssue(
        record_origin=RecordOrigin.DERIVED,
        source_record_ref=record.source_record_ref,
        source_mapping_id=source_mapping_id,
        source_mapping_version=source_mapping_version,
        issue_id=issue_id,
        case_id=record.case_id,
        target_ref=target_ref,
        field_path="identity_status",
        code=code,
        severity=default_severity_for_issue(code),
        observed_value=record.source_id,
        message=message,
    )


def _sort_key(
    record: SourceIdentityRecord,
) -> tuple[str, str, str, str]:
    return (
        record.case_id,
        record.source_entity_type.value,
        record.source_id,
        record.source_record_ref,
    )


def classify_source_identities(
    records: Iterable[SourceIdentityRecord],
    *,
    dataset_id: CanonicalId,
    source_mapping_id: str,
    source_mapping_version: str,
) -> tuple[SourceIdentityClassification, ...]:
    """Classify exact source identity groups without merging any records."""

    if not isinstance(dataset_id, CanonicalId):
        raise TypeError("dataset_id must be CanonicalId")
    if not isinstance(source_mapping_id, str) or not isinstance(
        source_mapping_version, str
    ):
        raise TypeError("source mapping identity and version must be str")
    if not source_mapping_id or not source_mapping_version:
        raise ValueError("source mapping identity and version must be non-empty")

    input_records = tuple(records)
    if not all(isinstance(record, SourceIdentityRecord) for record in input_records):
        raise TypeError("records must contain SourceIdentityRecord values")
    source_record_refs = tuple(record.source_record_ref for record in input_records)
    if len(set(source_record_refs)) != len(source_record_refs):
        raise ValueError("source_record_ref must be unique within a dataset")
    ordered_records = tuple(sorted(input_records, key=_sort_key))

    groups: dict[
        tuple[CanonicalId, SourceEntityType, SourceId],
        list[SourceIdentityRecord],
    ] = {}
    for record in ordered_records:
        key = (record.case_id, record.source_entity_type, record.source_id)
        groups.setdefault(key, []).append(record)

    classifications: list[SourceIdentityClassification] = []
    for group in groups.values():
        if len(group) == 1:
            classifications.append(
                SourceIdentityClassification(
                    record=group[0],
                    identity_status=IdentityStatus.UNIQUE,
                    issue=None,
                )
            )
            continue

        first_fields = group[0].decoded_fields
        status = (
            IdentityStatus.DUPLICATE_IDENTICAL
            if all(record.decoded_fields == first_fields for record in group[1:])
            else IdentityStatus.DUPLICATE_CONFLICT
        )
        for record in group:
            classifications.append(
                SourceIdentityClassification(
                    record=record,
                    identity_status=status,
                    issue=_duplicate_issue(
                        record,
                        dataset_id=dataset_id,
                        status=status,
                        source_mapping_id=source_mapping_id,
                        source_mapping_version=source_mapping_version,
                    ),
                )
            )

    return tuple(classifications)
