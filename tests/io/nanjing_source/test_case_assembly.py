from collections import Counter

from grid_case_generator.io.nanjing_source.case_assembly import (
    CaseRowMappingOutcome,
    RowTerminalCategory,
    assemble_station_feeder_bus_case,
)
from grid_case_generator.io.nanjing_source.locator import source_record_ref
from grid_case_generator.io.nanjing_source.mapping import (
    map_bus,
    map_feeder,
    map_grid_case,
    map_station,
)
from grid_case_generator.io.nanjing_source.models import (
    RawCsvRecord,
    SourceCaseInventory,
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
    SourceId,
    SourceReferenceStatus,
)
from grid_case_generator.validation.identity import (
    SourceEntityType,
    SourceIdentityClassification,
    SourceIdentityRecord,
)


DATASET_ID = SourceImportIdFactory.dataset_id("a" * 64)
SOURCE_CASE_KEY = "data/case-1"
CASE_ID = SourceImportIdFactory.case_id(DATASET_ID, SOURCE_CASE_KEY)


def _grid_case():
    inventory = SourceCaseInventory(
        source_case_key=SOURCE_CASE_KEY,
        members=tuple(
            (schema.file_type, f"{SOURCE_CASE_KEY}/{schema.filename}")
            for schema in NANJING_SOURCE_SCHEMA.files
        ),
    )
    return map_grid_case(inventory, dataset_id=DATASET_ID)


def _raw(
    file_type: SourceFileType,
    values: tuple[str, ...],
    *,
    data_row: int,
) -> RawCsvRecord:
    schema = NANJING_SOURCE_SCHEMA.for_type(file_type)
    member_path = f"{SOURCE_CASE_KEY}/{schema.filename}"
    return RawCsvRecord(
        source_case_key=SOURCE_CASE_KEY,
        source_file_type=file_type,
        header=schema.header,
        data_row=data_row,
        source_record_ref=source_record_ref(member_path, data_row=data_row),
        values=values,
        fields=tuple(zip(schema.header, values, strict=True)),
    )


def _classification(
    raw: RawCsvRecord,
    source_entity_type: SourceEntityType,
    status: IdentityStatus,
) -> SourceIdentityClassification:
    assert raw.fields is not None
    source_id_field = {
        SourceEntityType.STATION: "Station_ID",
        SourceEntityType.FEEDER: "Feeder_ID",
        SourceEntityType.BUS: "Bus_ID",
    }[source_entity_type]
    return SourceIdentityClassification(
        record=SourceIdentityRecord(
            case_id=CASE_ID,
            source_entity_type=source_entity_type,
            source_id=SourceId(dict(raw.fields)[source_id_field]),
            source_record_ref=raw.source_record_ref,
            decoded_fields=raw.fields,
        ),
        identity_status=status,
    )


def _station_row(
    source_id: str,
    *,
    data_row: int,
    status: IdentityStatus,
    name: str = "station",
) -> CaseRowMappingOutcome:
    raw = _raw(
        SourceFileType.STATION,
        (source_id, "", name, "10", "", ""),
        data_row=data_row,
    )
    outcome = map_station(
        raw,
        dataset_id=DATASET_ID,
        case_id=CASE_ID,
        identity_status=status,
    )
    return CaseRowMappingOutcome(
        raw_record=raw,
        identity_status=status,
        mapping_outcome=outcome,
    )


def _bus_row(
    source_id: str,
    station_ref: str,
    *,
    data_row: int,
    status: IdentityStatus,
    name: str = "bus",
) -> CaseRowMappingOutcome:
    raw = _raw(
        SourceFileType.BUS,
        (source_id, name, "10", "", station_ref, "false"),
        data_row=data_row,
    )
    outcome = map_bus(
        raw,
        _classification(raw, SourceEntityType.BUS, status),
        dataset_id=DATASET_ID,
    )
    return CaseRowMappingOutcome(
        raw_record=raw,
        identity_status=status,
        mapping_outcome=outcome,
    )


def _feeder_row(
    source_id: str,
    bus_ref: str,
    *,
    data_row: int,
    status: IdentityStatus = IdentityStatus.UNIQUE,
) -> CaseRowMappingOutcome:
    raw = _raw(
        SourceFileType.FEEDER,
        (source_id, "feeder", bus_ref),
        data_row=data_row,
    )
    outcome = map_feeder(
        raw,
        dataset_id=DATASET_ID,
        case_id=CASE_ID,
        identity_status=status,
    )
    return CaseRowMappingOutcome(
        raw_record=raw,
        identity_status=status,
        mapping_outcome=outcome,
    )


def test_case_assembly_publishes_identical_representative_and_suppresses_conflict() -> None:
    station_second = _station_row(
        "station-1", data_row=2, status=IdentityStatus.DUPLICATE_IDENTICAL
    )
    station_first = _station_row(
        "station-1", data_row=1, status=IdentityStatus.DUPLICATE_IDENTICAL
    )
    conflicting_bus_first = _bus_row(
        "bus-conflict",
        "",
        data_row=1,
        status=IdentityStatus.DUPLICATE_CONFLICT,
        name="first",
    )
    conflicting_bus_second = _bus_row(
        "bus-conflict",
        "",
        data_row=2,
        status=IdentityStatus.DUPLICATE_CONFLICT,
        name="second",
    )
    owner_bus = _bus_row(
        "bus-owner",
        "station-1",
        data_row=3,
        status=IdentityStatus.UNIQUE,
    )
    feeder = _feeder_row("feeder-1", "bus-conflict", data_row=1)
    inputs = (
        station_second,
        conflicting_bus_second,
        feeder,
        owner_bus,
        station_first,
        conflicting_bus_first,
    )

    result = assemble_station_feeder_bus_case(
        _grid_case(), inputs, dataset_id=DATASET_ID
    )

    stations = tuple(record for record in result.records if isinstance(record, Station))
    buses = tuple(record for record in result.records if isinstance(record, Bus))
    feeders = tuple(record for record in result.records if isinstance(record, Feeder))
    assert len(stations) == 1
    assert stations[0].source_record_ref == station_first.raw_record.source_record_ref
    assert stations[0].identity_status is IdentityStatus.DUPLICATE_IDENTICAL
    assert tuple(bus.source_id for bus in buses) == (SourceId("bus-owner"),)
    assert len(feeders) == 1
    assert result.grid_case.feeder_ref is not None
    assert result.grid_case.feeder_ref.entity_id == feeders[0].feeder_id

    bus_resolution = next(
        item for item in result.resolutions if item.request.owner_source_id == "bus-owner"
    )
    assert bus_resolution.resolution_status is SourceReferenceStatus.AMBIGUOUS
    assert len(bus_resolution.candidates) == 1
    assert (
        bus_resolution.candidates[0].identity_status
        is IdentityStatus.DUPLICATE_IDENTICAL
    )

    feeder_resolution = next(
        item for item in result.resolutions if item.request.owner_source_id == "feeder-1"
    )
    assert feeder_resolution.resolution_status is SourceReferenceStatus.AMBIGUOUS
    assert feeder_resolution.candidates == ()
    assert len(feeder_resolution.identity_conflicts) == 1
    assert feeder_resolution.identity_conflicts[0].source_record_refs == tuple(
        sorted(
            (
                conflicting_bus_first.raw_record.source_record_ref,
                conflicting_bus_second.raw_record.source_record_ref,
            )
        )
    )

    code_counts = Counter(issue.code for issue in result.issues)
    assert code_counts == Counter(
        {
            QualityIssueCode.SOURCE_ID_DUPLICATE_IDENTICAL: 2,
            QualityIssueCode.SOURCE_ID_DUPLICATE_CONFLICT: 2,
            QualityIssueCode.SOURCE_REFERENCE_AMBIGUOUS: 2,
        }
    )
    identical_targets = {
        issue.target_ref
        for issue in result.issues
        if issue.code is QualityIssueCode.SOURCE_ID_DUPLICATE_IDENTICAL
    }
    assert len(identical_targets) == 1
    assert next(iter(identical_targets)).entity_id == stations[0].station_id
    station_ref = EntityRef(
        entity_type=Identifier("STATION"), entity_id=stations[0].station_id
    )
    for issue in result.issues:
        if issue.code is not QualityIssueCode.SOURCE_ID_DUPLICATE_IDENTICAL:
            continue
        assert issue.issue_id == SourceImportIdFactory.quality_issue_id(
            dataset_id=DATASET_ID,
            case_id=CASE_ID,
            target_ref=station_ref,
            field_path="station.source_id",
            code=QualityIssueCode.SOURCE_ID_DUPLICATE_IDENTICAL,
            source_record_ref=issue.source_record_ref,
            occurrence_key="",
        )
    assert all(
        issue.target_ref is None
        for issue in result.issues
        if issue.code is QualityIssueCode.SOURCE_ID_DUPLICATE_CONFLICT
    )

    categories = {
        entry.raw_record.source_record_ref: entry.terminal_category
        for entry in result.accounting
    }
    assert categories[station_first.raw_record.source_record_ref] is RowTerminalCategory.DUPLICATE
    assert categories[station_second.raw_record.source_record_ref] is RowTerminalCategory.DUPLICATE
    assert categories[conflicting_bus_first.raw_record.source_record_ref] is RowTerminalCategory.DUPLICATE
    assert categories[conflicting_bus_second.raw_record.source_record_ref] is RowTerminalCategory.DUPLICATE
    assert categories[owner_bus.raw_record.source_record_ref] is RowTerminalCategory.UNRESOLVED
    assert categories[feeder.raw_record.source_record_ref] is RowTerminalCategory.UNRESOLVED
    assert len(result.accounting) == len(inputs)
    assert result.issues == tuple(
        sorted(
            result.issues,
            key=lambda issue: (
                issue.case_id or "",
                issue.source_record_ref or "",
                issue.field_path or "",
                issue.code.value,
                issue.target_ref.entity_type if issue.target_ref else "",
                issue.target_ref.entity_id if issue.target_ref else "",
                issue.issue_id,
            ),
        )
    )

    reversed_result = assemble_station_feeder_bus_case(
        _grid_case(), reversed(inputs), dataset_id=DATASET_ID
    )
    assert reversed_result == result
    assert not hasattr(result, "import_status")


def test_case_assembly_accounts_for_rejected_row_and_missing_feeder() -> None:
    raw = _raw(
        SourceFileType.STATION,
        ("", "", "station", "10", "", ""),
        data_row=1,
    )
    mapping_outcome = map_station(
        raw,
        dataset_id=DATASET_ID,
        case_id=CASE_ID,
        identity_status=IdentityStatus.UNIQUE,
    )
    rejected = CaseRowMappingOutcome(
        raw_record=raw,
        identity_status=None,
        mapping_outcome=mapping_outcome,
    )

    result = assemble_station_feeder_bus_case(
        _grid_case(), (rejected,), dataset_id=DATASET_ID
    )

    assert result.records == ()
    assert len(result.unmapped_records) == 1
    assert len(result.accounting) == 1
    assert result.accounting[0].raw_record == raw
    assert result.accounting[0].terminal_category is RowTerminalCategory.REJECTED
    assert result.accounting[0].canonical_ref is None
    assert {issue.code for issue in result.issues} == {
        QualityIssueCode.SOURCE_REQUIRED_VALUE_MISSING,
        QualityIssueCode.GRID_CASE_FEEDER_MISSING,
    }


def test_multiple_unique_feeders_leave_grid_case_ambiguous() -> None:
    first = _feeder_row("feeder-1", "", data_row=1)
    second = _feeder_row("feeder-2", "", data_row=2)

    result = assemble_station_feeder_bus_case(
        _grid_case(), (second, first), dataset_id=DATASET_ID
    )

    assert result.grid_case.feeder_ref is None
    feeder_issues = tuple(
        issue
        for issue in result.issues
        if issue.code is QualityIssueCode.GRID_CASE_FEEDER_AMBIGUOUS
    )
    assert len(feeder_issues) == 1
    assert feeder_issues[0].field_path == "grid_case.feeder_ref"
    assert feeder_issues[0].source_record_ref is None
    assert feeder_issues[0].target_ref is not None
    assert feeder_issues[0].target_ref.entity_type == "GRID_CASE"
    assert feeder_issues[0].issue_id == SourceImportIdFactory.quality_issue_id(
        dataset_id=DATASET_ID,
        case_id=CASE_ID,
        target_ref=feeder_issues[0].target_ref,
        field_path="grid_case.feeder_ref",
        code=QualityIssueCode.GRID_CASE_FEEDER_AMBIGUOUS,
        source_record_ref=None,
        occurrence_key="",
    )
