from collections.abc import Callable
from dataclasses import replace

import pytest

from grid_case_generator.io.nanjing_source.locator import source_record_ref
from grid_case_generator.io.nanjing_source.mapping import (
    map_bus,
    map_feeder,
    map_station,
)
from grid_case_generator.io.nanjing_source.models import RawCsvRecord
from grid_case_generator.io.nanjing_source.reference_integration import (
    build_nanjing_reference_candidate_index,
    integrate_bus_station_reference,
    integrate_feeder_source_bus_reference,
)
from grid_case_generator.io.nanjing_source.reference_issue_policy import (
    reference_issues_for_result,
)
from grid_case_generator.io.nanjing_source.schema import (
    NANJING_SOURCE_SCHEMA,
    SourceFileType,
)
from grid_case_generator.models.identifiers import SourceImportIdFactory
from grid_case_generator.models.quality import QualityIssueCode
from grid_case_generator.models.records import Bus, Feeder, Station
from grid_case_generator.models.types import (
    CanonicalId,
    EntityRef,
    Identifier,
    IdentityStatus,
    Severity,
    SourceId,
    SourceReferenceStatus,
)
from grid_case_generator.validation.identity import (
    SourceEntityType,
    SourceIdentityClassification,
    SourceIdentityRecord,
)


DATASET_ID = SourceImportIdFactory.dataset_id("a" * 64)
CASE_ID = SourceImportIdFactory.case_id(DATASET_ID, "case-a")


def _raw_record(
    file_type: SourceFileType,
    values: tuple[str, ...],
    *,
    data_row: int = 1,
) -> RawCsvRecord:
    schema = NANJING_SOURCE_SCHEMA.for_type(file_type)
    member_path = f"case-a/{schema.filename}"
    return RawCsvRecord(
        source_case_key="case-a",
        source_file_type=file_type,
        header=schema.header,
        data_row=data_row,
        source_record_ref=source_record_ref(member_path, data_row=data_row),
        values=values,
        fields=tuple(zip(schema.header, values, strict=True)),
    )


def _mapped_station(
    source_id: str,
    *,
    data_row: int = 1,
    name: str = "station",
    identity_status: IdentityStatus = IdentityStatus.UNIQUE,
) -> tuple[RawCsvRecord, Station]:
    raw = _raw_record(
        SourceFileType.STATION,
        (source_id, "", name, "10", "", ""),
        data_row=data_row,
    )
    outcome = map_station(
        raw,
        dataset_id=DATASET_ID,
        case_id=CASE_ID,
        identity_status=identity_status,
    )
    assert outcome.record is not None
    return raw, outcome.record


def _mapped_bus(
    source_id: str,
    station_reference: str,
    *,
    data_row: int = 1,
    identity_status: IdentityStatus = IdentityStatus.UNIQUE,
) -> tuple[RawCsvRecord, Bus]:
    raw = _raw_record(
        SourceFileType.BUS,
        (source_id, "bus", "10", "", station_reference, "false"),
        data_row=data_row,
    )
    assert raw.fields is not None
    identity = SourceIdentityRecord(
        case_id=CASE_ID,
        source_entity_type=SourceEntityType.BUS,
        source_id=SourceId(source_id),
        source_record_ref=raw.source_record_ref,
        decoded_fields=raw.fields,
    )
    outcome = map_bus(
        raw,
        SourceIdentityClassification(
            record=identity,
            identity_status=identity_status,
        ),
    )
    assert outcome.record is not None
    return raw, outcome.record


def _mapped_feeder(
    source_id: str,
    bus_reference: str,
) -> tuple[RawCsvRecord, Feeder]:
    raw = _raw_record(
        SourceFileType.FEEDER,
        (source_id, "feeder", bus_reference),
    )
    outcome = map_feeder(
        raw,
        dataset_id=DATASET_ID,
        case_id=CASE_ID,
        identity_status=IdentityStatus.UNIQUE,
    )
    assert outcome.record is not None
    return raw, outcome.record


def _owner_ref(bus: Bus) -> EntityRef:
    return EntityRef(entity_type=Identifier("BUS"), entity_id=bus.bus_id)


def test_candidate_builder_reuses_mapper_identity_and_provenance() -> None:
    _, leading_zero = _mapped_station("001", data_row=1)
    _, integer_text = _mapped_station("1", data_row=2)
    _, scientific_text = _mapped_station("1e0", data_row=3)

    index = build_nanjing_reference_candidate_index(
        (scientific_text, integer_text, leading_zero)
    )

    assert tuple(key[2] for key, _ in index.entries) == (
        SourceId("001"),
        SourceId("1"),
        SourceId("1e0"),
    )
    for _, candidates in index.entries:
        candidate = candidates[0]
        mapped = {
            station.source_id: station
            for station in (leading_zero, integer_text, scientific_text)
        }[candidate.source_id]
        assert candidate.source_id is mapped.source_id
        assert candidate.source_record_ref == mapped.source_record_ref
        assert candidate.identity_status is mapped.identity_status
        assert candidate.entity_ref.entity_id == mapped.station_id


def test_candidate_builder_rejects_non_adapter_provenance() -> None:
    _, station = _mapped_station("station-1")

    with pytest.raises(ValueError, match="provenance must match"):
        build_nanjing_reference_candidate_index(
            (replace(station, source_mapping_version="other-version"),)
        )


@pytest.mark.parametrize(
    ("identity_status", "names"),
    (
        (IdentityStatus.DUPLICATE_IDENTICAL, ("same", "same")),
        (IdentityStatus.DUPLICATE_CONFLICT, ("first", "second")),
    ),
)
def test_candidate_builder_preserves_all_duplicate_records(
    identity_status: IdentityStatus,
    names: tuple[str, str],
) -> None:
    _, first = _mapped_station(
        "duplicate",
        data_row=1,
        name=names[0],
        identity_status=identity_status,
    )
    _, second = _mapped_station(
        "duplicate",
        data_row=2,
        name=names[1],
        identity_status=identity_status,
    )

    index = build_nanjing_reference_candidate_index((second, first))

    assert len(index.entries) == 1
    key, candidates = index.entries[0]
    assert key == (CASE_ID, SourceEntityType.STATION, SourceId("duplicate"))
    assert len(candidates) == 2
    assert {candidate.source_record_ref for candidate in candidates} == {
        first.source_record_ref,
        second.source_record_ref,
    }
    assert {candidate.entity_ref.entity_id for candidate in candidates} == {
        first.station_id,
        second.station_id,
    }


def test_bus_reference_is_resolved_into_a_new_immutable_record() -> None:
    raw_station, station = _mapped_station("001")
    raw_bus, bus = _mapped_bus("bus-1", "001")
    original_reference = bus.station_source_ref
    index = build_nanjing_reference_candidate_index((station,))

    outcome = integrate_bus_station_reference(raw_bus, bus, index)

    assert outcome.record is not bus
    assert bus.station_source_ref is original_reference
    assert bus.station_source_ref is not None
    assert (
        bus.station_source_ref.resolution_status
        is SourceReferenceStatus.UNRESOLVED
    )
    assert outcome.resolution.request.raw_reference_value == "001"
    assert outcome.record.station_source_ref is not None
    assert (
        outcome.record.station_source_ref.resolution_status
        is SourceReferenceStatus.EXACT
    )
    assert outcome.record.station_source_ref.raw_ref == SourceId("001")
    assert outcome.record.station_source_ref.resolved_source_ref == EntityRef(
        entity_type=Identifier("STATION"), entity_id=station.station_id
    )
    assert station.source_record_ref == raw_station.source_record_ref
    assert reference_issues_for_result(
        outcome.resolution,
        dataset_id=DATASET_ID,
        target_ref=_owner_ref(outcome.record),
    ) == ()


def test_feeder_reference_is_resolved_into_a_new_immutable_record() -> None:
    _, bus = _mapped_bus("001_bs", "")
    raw_feeder, feeder = _mapped_feeder("feeder-1", "001_bs")
    original_reference = feeder.source_bus_source_ref
    index = build_nanjing_reference_candidate_index((bus,))

    outcome = integrate_feeder_source_bus_reference(raw_feeder, feeder, index)

    assert outcome.record is not feeder
    assert feeder.source_bus_source_ref is original_reference
    assert feeder.source_bus_source_ref is not None
    assert (
        feeder.source_bus_source_ref.resolution_status
        is SourceReferenceStatus.UNRESOLVED
    )
    assert outcome.record.source_bus_source_ref is not None
    assert (
        outcome.record.source_bus_source_ref.resolution_status
        is SourceReferenceStatus.EXACT
    )
    assert outcome.record.source_bus_source_ref.resolved_source_ref == EntityRef(
        entity_type=Identifier("BUS"), entity_id=bus.bus_id
    )


def test_missing_remains_empty_in_resolver_and_none_only_in_canonical() -> None:
    raw_bus, bus = _mapped_bus("bus-1", "")

    outcome = integrate_bus_station_reference(
        raw_bus,
        bus,
        build_nanjing_reference_candidate_index(()),
    )

    assert outcome.resolution.request.raw_reference_value == ""
    assert outcome.resolution.resolution_status is SourceReferenceStatus.MISSING
    assert outcome.record.station_source_ref is not None
    assert outcome.record.station_source_ref.raw_ref is None
    assert (
        outcome.record.station_source_ref.resolution_status
        is SourceReferenceStatus.MISSING
    )
    assert reference_issues_for_result(
        outcome.resolution,
        dataset_id=DATASET_ID,
        target_ref=_owner_ref(outcome.record),
    ) == ()


def test_duplicate_candidate_resolution_is_ambiguous_without_selection() -> None:
    _, first = _mapped_station(
        "station-1",
        data_row=1,
        identity_status=IdentityStatus.DUPLICATE_IDENTICAL,
    )
    _, second = _mapped_station(
        "station-1",
        data_row=2,
        identity_status=IdentityStatus.DUPLICATE_IDENTICAL,
    )
    raw_bus, bus = _mapped_bus("bus-1", "station-1")

    outcome = integrate_bus_station_reference(
        raw_bus,
        bus,
        build_nanjing_reference_candidate_index((second, first)),
    )

    assert outcome.resolution.resolution_status is SourceReferenceStatus.AMBIGUOUS
    assert len(outcome.resolution.candidates) == 2
    assert outcome.record.station_source_ref is not None
    assert outcome.record.station_source_ref.resolved_source_ref is None


def test_adapter_policy_maps_reference_status_to_issue_and_severity() -> None:
    raw_bus, bus = _mapped_bus("bus-1", "missing-station")
    outcome = integrate_bus_station_reference(
        raw_bus,
        bus,
        build_nanjing_reference_candidate_index(()),
    )

    issues = reference_issues_for_result(
        outcome.resolution,
        dataset_id=DATASET_ID,
        target_ref=_owner_ref(bus),
    )

    assert len(issues) == 1
    issue = issues[0]
    assert issue.code is QualityIssueCode.SOURCE_REFERENCE_UNRESOLVED
    assert issue.severity is Severity.WARNING
    assert issue.observed_value == "missing-station"
    assert issue.field_path == "bus.station_source_ref"
    assert issue.source_record_ref == raw_bus.source_record_ref


def test_adapter_policy_allows_explicit_severity_policy_override() -> None:
    _, first = _mapped_station(
        "station-1",
        data_row=1,
        identity_status=IdentityStatus.DUPLICATE_CONFLICT,
    )
    _, second = _mapped_station(
        "station-1",
        data_row=2,
        name="different",
        identity_status=IdentityStatus.DUPLICATE_CONFLICT,
    )
    raw_bus, bus = _mapped_bus("bus-1", "station-1")
    outcome = integrate_bus_station_reference(
        raw_bus,
        bus,
        build_nanjing_reference_candidate_index((first, second)),
    )
    observed_codes: list[QualityIssueCode] = []

    def override(code: QualityIssueCode) -> Severity:
        observed_codes.append(code)
        return Severity.INFO

    severity_policy: Callable[[QualityIssueCode], Severity] = override
    issues = reference_issues_for_result(
        outcome.resolution,
        dataset_id=DATASET_ID,
        target_ref=_owner_ref(bus),
        severity_for=severity_policy,
    )

    assert observed_codes == [QualityIssueCode.SOURCE_REFERENCE_AMBIGUOUS]
    assert issues[0].severity is Severity.INFO
