"""Source identity grouping and duplicate classification primitives."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from grid_case_generator.models.types import (
    CanonicalId,
    IdentityStatus,
    SourceId,
)


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

    def __post_init__(self) -> None:
        if not isinstance(self.record, SourceIdentityRecord):
            raise TypeError("record must be SourceIdentityRecord")
        if not isinstance(self.identity_status, IdentityStatus):
            raise TypeError("identity_status must be IdentityStatus")


def _sort_key(
    record: SourceIdentityRecord,
) -> tuple[str, str, str, str, tuple[tuple[str, str], ...]]:
    return (
        record.case_id,
        record.source_entity_type.value,
        record.source_id,
        record.source_record_ref,
        record.decoded_fields,
    )


def classify_source_identities(
    records: Iterable[SourceIdentityRecord],
) -> tuple[SourceIdentityClassification, ...]:
    """Classify exact source identity groups without merging any records."""

    input_records = tuple(records)
    if not all(isinstance(record, SourceIdentityRecord) for record in input_records):
        raise TypeError("records must contain SourceIdentityRecord values")
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
                )
            )

    return tuple(classifications)
