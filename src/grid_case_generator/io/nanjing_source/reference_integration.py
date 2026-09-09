"""Nanjing adapter integration for exact source-reference resolution."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Generic, TypeVar

from grid_case_generator.models.records import Bus, Feeder, Station
from grid_case_generator.models.types import (
    EntityRef,
    Identifier,
    RecordOrigin,
    SourceId,
    SourceReference,
    SourceReferenceStatus,
)
from grid_case_generator.validation.identity import SourceEntityType
from grid_case_generator.validation.reference_resolution import (
    ReferenceCandidate,
    ReferenceCandidateIndex,
    ReferenceResolutionRequest,
    ReferenceResolutionResult,
    build_reference_candidate_index,
    resolve_source_reference,
)

from .models import RawCsvRecord
from .schema import NANJING_SOURCE_SCHEMA, SourceFileType


_T = TypeVar("_T", Bus, Feeder)
_MappedCandidateRecord = Station | Feeder | Bus
_MAPPING_ID = NANJING_SOURCE_SCHEMA.mapping_id
_MAPPING_VERSION = NANJING_SOURCE_SCHEMA.mapping_version


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceIntegrationOutcome(Generic[_T]):
    record: _T
    resolution: ReferenceResolutionResult


def _mapped_identity(
    record: _MappedCandidateRecord,
) -> tuple[SourceEntityType, SourceId, EntityRef]:
    if record.record_origin is not RecordOrigin.SOURCE:
        raise ValueError("reference candidates must be SOURCE records")
    if (
        record.source_mapping_id != _MAPPING_ID
        or record.source_mapping_version != _MAPPING_VERSION
    ):
        raise ValueError("reference candidate provenance must match the adapter")
    if record.source_record_ref is None:
        raise ValueError("reference candidate requires source_record_ref provenance")
    if record.source_id is None:
        raise ValueError("reference candidate requires mapper-produced source_id")

    if isinstance(record, Station):
        return (
            SourceEntityType.STATION,
            record.source_id,
            EntityRef(
                entity_type=Identifier("STATION"), entity_id=record.station_id
            ),
        )
    if isinstance(record, Feeder):
        return (
            SourceEntityType.FEEDER,
            record.source_id,
            EntityRef(
                entity_type=Identifier("FEEDER"), entity_id=record.feeder_id
            ),
        )
    if isinstance(record, Bus):
        return (
            SourceEntityType.BUS,
            record.source_id,
            EntityRef(entity_type=Identifier("BUS"), entity_id=record.bus_id),
        )
    raise TypeError("unsupported mapped reference candidate record")


def reference_candidate_from_mapped_record(
    record: _MappedCandidateRecord,
) -> ReferenceCandidate:
    """Reuse mapper-produced identity and provenance without normalization."""

    if not isinstance(record, (Station, Feeder, Bus)):
        raise TypeError("record must be a mapped Station, Feeder, or Bus")
    source_entity_type, source_id, entity_ref = _mapped_identity(record)
    assert record.source_record_ref is not None
    return ReferenceCandidate(
        case_id=record.case_id,
        candidate_source_entity_type=source_entity_type,
        source_id=source_id,
        source_record_ref=record.source_record_ref,
        identity_status=record.identity_status,
        entity_ref=entity_ref,
    )


def build_nanjing_reference_candidate_index(
    records: Iterable[_MappedCandidateRecord],
) -> ReferenceCandidateIndex:
    """Build the resolver index from successful mapper outputs only."""

    return build_reference_candidate_index(
        reference_candidate_from_mapped_record(record) for record in records
    )


def _validated_owner_fields(
    raw_record: RawCsvRecord,
    owner: Bus | Feeder,
    *,
    source_file_type: SourceFileType,
    source_id_field: str,
) -> dict[str, str]:
    if not isinstance(raw_record, RawCsvRecord):
        raise TypeError("raw_record must be RawCsvRecord")
    if raw_record.source_file_type is not source_file_type:
        raise ValueError("raw record source type does not match reference owner")
    expected_header = NANJING_SOURCE_SCHEMA.for_type(source_file_type).header
    if raw_record.header != expected_header or raw_record.fields is None:
        raise ValueError("raw record must have the recognized adapter schema")
    if owner.record_origin is not RecordOrigin.SOURCE:
        raise ValueError("reference owner must be a SOURCE record")
    if (
        owner.source_mapping_id != _MAPPING_ID
        or owner.source_mapping_version != _MAPPING_VERSION
    ):
        raise ValueError("reference owner provenance must match the adapter")
    if owner.source_record_ref != raw_record.source_record_ref:
        raise ValueError("raw record and reference owner provenance must match")
    fields = dict(raw_record.fields)
    if owner.source_id is None or owner.source_id != fields[source_id_field]:
        raise ValueError("raw record and mapper-produced owner identity must match")
    return fields


def _canonical_source_reference(
    result: ReferenceResolutionResult,
) -> SourceReference:
    # Resolver retains the source empty string; Canonical requires null for MISSING.
    raw_ref = (
        None
        if result.resolution_status is SourceReferenceStatus.MISSING
        else SourceId(result.request.raw_reference_value)
    )
    return SourceReference(
        raw_ref=raw_ref,
        resolved_source_ref=result.resolved_ref,
        resolution_status=result.resolution_status,
    )


def integrate_bus_station_reference(
    raw_record: RawCsvRecord,
    bus: Bus,
    index: ReferenceCandidateIndex,
) -> ReferenceIntegrationOutcome[Bus]:
    """Resolve Bus_Station_ID and return a new immutable Bus."""

    if not isinstance(bus, Bus):
        raise TypeError("bus must be Bus")
    fields = _validated_owner_fields(
        raw_record,
        bus,
        source_file_type=SourceFileType.BUS,
        source_id_field="Bus_ID",
    )
    assert bus.source_id is not None
    assert bus.source_record_ref is not None
    request = ReferenceResolutionRequest(
        case_id=bus.case_id,
        owner_source_entity_type=Identifier(SourceEntityType.BUS.value),
        owner_source_id=bus.source_id,
        owner_source_record_ref=bus.source_record_ref,
        reference_field_path="bus.station_source_ref",
        raw_reference_value=fields["Bus_Station_ID"],
        allowed_candidate_source_entity_types=(SourceEntityType.STATION,),
    )
    result = resolve_source_reference(index, request)
    return ReferenceIntegrationOutcome(
        record=replace(bus, station_source_ref=_canonical_source_reference(result)),
        resolution=result,
    )


def integrate_feeder_source_bus_reference(
    raw_record: RawCsvRecord,
    feeder: Feeder,
    index: ReferenceCandidateIndex,
) -> ReferenceIntegrationOutcome[Feeder]:
    """Resolve Feeder_SourceBus and return a new immutable Feeder."""

    if not isinstance(feeder, Feeder):
        raise TypeError("feeder must be Feeder")
    fields = _validated_owner_fields(
        raw_record,
        feeder,
        source_file_type=SourceFileType.FEEDER,
        source_id_field="Feeder_ID",
    )
    assert feeder.source_id is not None
    assert feeder.source_record_ref is not None
    request = ReferenceResolutionRequest(
        case_id=feeder.case_id,
        owner_source_entity_type=Identifier(SourceEntityType.FEEDER.value),
        owner_source_id=feeder.source_id,
        owner_source_record_ref=feeder.source_record_ref,
        reference_field_path="feeder.source_bus_source_ref",
        raw_reference_value=fields["Feeder_SourceBus"],
        allowed_candidate_source_entity_types=(SourceEntityType.BUS,),
    )
    result = resolve_source_reference(index, request)
    return ReferenceIntegrationOutcome(
        record=replace(
            feeder,
            source_bus_source_ref=_canonical_source_reference(result),
        ),
        resolution=result,
    )
