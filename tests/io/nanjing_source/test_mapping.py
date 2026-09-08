from decimal import Decimal

from grid_case_generator.io.nanjing_source.locator import source_record_ref
from grid_case_generator.io.nanjing_source.mapping import (
    CANONICAL_SPEC_VERSION,
    map_bus,
    map_dataset,
    map_feeder,
    map_grid_case,
    map_station,
)
from grid_case_generator.io.nanjing_source.models import (
    RawCsvRecord,
    SourceCaseInventory,
    SourceDatasetInventory,
)
from grid_case_generator.io.nanjing_source.schema import (
    NANJING_SOURCE_SCHEMA,
    SourceFileType,
)
from grid_case_generator.models.identifiers import SourceImportIdFactory
from grid_case_generator.models.quality import QualityIssueCode
from grid_case_generator.models.types import (
    CanonicalId,
    IdentityStatus,
    ImportStatus,
    RecordOrigin,
    Severity,
    SourceId,
    SourceReferenceStatus,
)
from grid_case_generator.validation.identity import (
    SourceEntityType,
    SourceIdentityClassification,
    SourceIdentityRecord,
    classify_source_identities,
)
from grid_case_generator.validation.quality import ImportErrorCategory


CHECKSUM_HEX = "a" * 64
DATASET_ID = SourceImportIdFactory.dataset_id(CHECKSUM_HEX)
CASE_ID = SourceImportIdFactory.case_id(DATASET_ID, "数据/case 001")


def _dataset_inventory(checksum_hex: str = CHECKSUM_HEX) -> SourceDatasetInventory:
    return SourceDatasetInventory(
        source_uri="data/raw/nanjing.zip",
        source_checksum=f"sha256:{checksum_hex}",
        member_count=12,
        csv_member_count=12,
        cases=(),
        diagnostics=(),
    )


def _case_inventory() -> SourceCaseInventory:
    return SourceCaseInventory(
        source_case_key="数据/case 001",
        members=tuple(
            (schema.file_type, f"数据/case 001/{schema.filename}")
            for schema in NANJING_SOURCE_SCHEMA.files
        ),
    )


def _raw_record(
    file_type: SourceFileType, values: tuple[str, ...], *, data_row: int = 1
) -> RawCsvRecord:
    schema = NANJING_SOURCE_SCHEMA.for_type(file_type)
    member_path = f"数据/case 001/{schema.filename}"
    return RawCsvRecord(
        source_case_key="数据/case 001",
        source_file_type=file_type,
        header=schema.header,
        data_row=data_row,
        source_record_ref=source_record_ref(member_path, data_row=data_row),
        values=values,
        fields=tuple(zip(schema.header, values, strict=True)),
    )


def _bus_identity_record(raw: RawCsvRecord) -> SourceIdentityRecord:
    assert raw.source_file_type is SourceFileType.BUS
    assert raw.fields is not None
    fields = dict(raw.fields)
    return SourceIdentityRecord(
        case_id=CASE_ID,
        source_entity_type=SourceEntityType.BUS,
        source_id=SourceId(fields["Bus_ID"]),
        source_record_ref=raw.source_record_ref,
        decoded_fields=raw.fields,
    )


def _classification(raw: RawCsvRecord) -> SourceIdentityClassification:
    return classify_source_identities((_bus_identity_record(raw),))[0]


def test_dataset_mapper_uses_intake_checksum_and_explicit_import_metadata() -> None:
    inventory = _dataset_inventory()

    first = map_dataset(
        inventory,
        name="南京 Source Dataset",
        imported_at="2026-09-08T12:00:00+08:00",
        import_status=ImportStatus.COMPLETE,
    )
    later = map_dataset(
        inventory,
        name="renamed display",
        imported_at="2027-01-01T00:00:00+00:00",
        import_status=ImportStatus.INCOMPLETE,
    )

    assert first.dataset_id == DATASET_ID == later.dataset_id
    assert first.source_checksum == f"sha256:{CHECKSUM_HEX}"
    assert first.source_uri == "data/raw/nanjing.zip"
    assert first.canonical_spec_version == CANONICAL_SPEC_VERSION == "0.3.0"
    assert first.imported_at == "2026-09-08T12:00:00+08:00"
    assert first.import_status is ImportStatus.COMPLETE
    assert first.record_origin is RecordOrigin.SOURCE
    assert first.source_record_ref is None
    assert first.source_mapping_id == NANJING_SOURCE_SCHEMA.mapping_id
    assert first.source_mapping_version == NANJING_SOURCE_SCHEMA.mapping_version


def test_dataset_checksum_change_changes_deterministic_id() -> None:
    first = map_dataset(
        _dataset_inventory("a" * 64),
        name="dataset",
        imported_at="2026-09-08T00:00:00+00:00",
        import_status=ImportStatus.COMPLETE,
    )
    second = map_dataset(
        _dataset_inventory("b" * 64),
        name="dataset",
        imported_at="2026-09-08T00:00:00+00:00",
        import_status=ImportStatus.COMPLETE,
    )

    assert first.dataset_id != second.dataset_id


def test_grid_case_mapper_preserves_key_and_does_not_infer_feeder() -> None:
    inventory = _case_inventory()

    first = map_grid_case(inventory, dataset_id=DATASET_ID)
    second = map_grid_case(inventory, dataset_id=DATASET_ID)

    assert first == second
    assert first.case_id == CASE_ID
    assert first.dataset_id == DATASET_ID
    assert first.source_case_key == "数据/case 001"
    assert first.feeder_ref is None
    assert first.record_origin is RecordOrigin.SOURCE
    assert first.source_record_ref is None
    assert first.source_mapping_id == "nanjing_csv"
    assert first.source_mapping_version == "0.2.0"


def test_station_mapper_preserves_source_identity_trace_and_nulls() -> None:
    raw = _raw_record(
        SourceFileType.STATION,
        ("0012345678901234567", "", "", "10.50", "", ""),
    )

    outcome = map_station(
        raw,
        dataset_id=DATASET_ID,
        case_id=CASE_ID,
        identity_status=IdentityStatus.DUPLICATE_IDENTICAL,
    )

    assert outcome.unmapped_record is None
    assert outcome.issues == ()
    assert outcome.error_category is None
    assert outcome.record is not None
    station = outcome.record
    assert station.source_id == SourceId("0012345678901234567")
    assert station.identity_status is IdentityStatus.DUPLICATE_IDENTICAL
    assert station.station_id == SourceImportIdFactory.station_id(
        CASE_ID, station.source_id, raw.source_record_ref
    )
    assert station.source_record_ref == raw.source_record_ref
    assert station.source_mapping_id == "nanjing_csv"
    assert station.source_mapping_version == "0.2.0"
    assert station.station_type is None
    assert station.name is None
    assert station.nominal_voltage_kv == Decimal("10.50")
    assert station.longitude is None
    assert station.latitude is None
    assert station.coordinate_crs is None


def test_bus_mapper_maps_unique_classified_record_without_resolving_reference() -> None:
    raw = _raw_record(
        SourceFileType.BUS,
        ("0000000000000000001_bs", " bus name ", "10.50", "", "0007", "TRUE"),
    )
    classification = _classification(raw)

    outcome = map_bus(raw, classification)

    assert outcome.record is not None
    bus = outcome.record
    assert bus.bus_id == SourceImportIdFactory.bus_id(
        CASE_ID, SourceId("0000000000000000001_bs"), raw.source_record_ref
    )
    assert bus.case_id == CASE_ID
    assert bus.source_id == SourceId("0000000000000000001_bs")
    assert bus.identity_status is IdentityStatus.UNIQUE
    assert bus.name == " bus name "
    assert bus.base_voltage_kv == Decimal("10.50")
    assert bus.phases is None
    assert bus.station_source_ref is not None
    assert bus.station_source_ref.raw_ref == SourceId("0007")
    assert bus.station_source_ref.resolved_source_ref is None
    assert (
        bus.station_source_ref.resolution_status
        is SourceReferenceStatus.UNRESOLVED
    )
    assert bus.is_source is True
    assert bus.record_origin is RecordOrigin.SOURCE
    assert bus.source_record_ref == raw.source_record_ref
    assert bus.source_mapping_id == "nanjing_csv"
    assert bus.source_mapping_version == "0.2.0"
    assert outcome.issues == ()
    assert outcome.unmapped_record is None
    assert outcome.error_category is None


def test_bus_mapper_keeps_every_duplicate_source_record() -> None:
    values = ("bus-1", "name", "10", "", "", "false")
    first_raw = _raw_record(SourceFileType.BUS, values, data_row=1)
    second_raw = _raw_record(SourceFileType.BUS, values, data_row=2)
    raw_by_ref = {
        raw.source_record_ref: raw for raw in (first_raw, second_raw)
    }
    classifications = classify_source_identities(
        (_bus_identity_record(first_raw), _bus_identity_record(second_raw))
    )

    buses = tuple(
        map_bus(raw_by_ref[item.record.source_record_ref], item).record
        for item in classifications
    )

    assert len(buses) == 2
    assert all(bus is not None for bus in buses)
    assert {bus.source_record_ref for bus in buses if bus is not None} == {
        first_raw.source_record_ref,
        second_raw.source_record_ref,
    }
    assert {bus.identity_status for bus in buses if bus is not None} == {
        IdentityStatus.DUPLICATE_IDENTICAL
    }
    assert len({bus.bus_id for bus in buses if bus is not None}) == 2


def test_bus_mapper_output_is_deterministic() -> None:
    raw = _raw_record(
        SourceFileType.BUS,
        ("001_bs", "name", "10.00", "", "", "False"),
    )
    classification = _classification(raw)

    first = map_bus(raw, classification)
    second = map_bus(raw, classification)

    assert first == second


def test_station_optional_decimal_failure_is_recoverable() -> None:
    raw = _raw_record(
        SourceFileType.STATION,
        ("station-1", "sub_?", "name", "not-a-decimal", "", ""),
    )

    outcome = map_station(
        raw,
        dataset_id=DATASET_ID,
        case_id=CASE_ID,
        identity_status=IdentityStatus.UNIQUE,
    )

    assert outcome.record is not None
    assert outcome.record.nominal_voltage_kv is None
    assert outcome.unmapped_record is None
    assert outcome.error_category is ImportErrorCategory.FIELD_RECOVERABLE
    assert len(outcome.issues) == 1
    issue = outcome.issues[0]
    assert issue.code is QualityIssueCode.SOURCE_VALUE_PARSE_FAILED
    assert issue.severity is Severity.WARNING
    assert issue.field_path == "station.nominal_voltage_kv"
    assert issue.observed_value == "not-a-decimal"
    assert issue.source_record_ref == raw.source_record_ref


def test_station_missing_required_source_id_is_record_fatal_and_accounted() -> None:
    raw = _raw_record(
        SourceFileType.STATION,
        ("", "substation", "name", "10", "", ""),
    )

    outcome = map_station(
        raw,
        dataset_id=DATASET_ID,
        case_id=CASE_ID,
        identity_status=IdentityStatus.UNIQUE,
    )

    assert outcome.record is None
    assert len(outcome.issues) == 1
    assert outcome.issues[0].code is QualityIssueCode.SOURCE_REQUIRED_VALUE_MISSING
    assert outcome.issues[0].severity is Severity.ERROR
    assert outcome.unmapped_record is not None
    assert outcome.unmapped_record.source_record_ref == raw.source_record_ref
    assert outcome.unmapped_record.header == raw.header
    assert outcome.unmapped_record.values == raw.values
    assert outcome.unmapped_record.fields == raw.fields
    assert outcome.unmapped_record.issue_ids == (outcome.issues[0].issue_id,)
    assert outcome.unmapped_record.issue_codes == (outcome.issues[0].code,)
    assert outcome.error_category is ImportErrorCategory.RECORD_FATAL


def test_feeder_mapper_preserves_raw_reference_without_resolving_connectivity() -> None:
    raw = _raw_record(
        SourceFileType.FEEDER,
        ("0000000000000000001", " feeder name ", "001_bs"),
    )

    outcome = map_feeder(
        raw,
        dataset_id=DATASET_ID,
        case_id=CASE_ID,
        identity_status=IdentityStatus.UNIQUE,
    )

    assert outcome.record is not None
    feeder = outcome.record
    assert feeder.source_id == SourceId("0000000000000000001")
    assert feeder.identity_status is IdentityStatus.UNIQUE
    assert feeder.name == " feeder name "
    assert feeder.feeder_id == SourceImportIdFactory.feeder_id(
        CASE_ID, feeder.source_id, raw.source_record_ref
    )
    assert feeder.source_bus_source_ref is not None
    assert feeder.source_record_ref == raw.source_record_ref
    assert feeder.source_mapping_id == "nanjing_csv"
    assert feeder.source_mapping_version == "0.2.0"
    assert feeder.source_bus_source_ref.raw_ref == SourceId("001_bs")
    assert feeder.source_bus_source_ref.resolved_source_ref is None
    assert (
        feeder.source_bus_source_ref.resolution_status
        is SourceReferenceStatus.UNRESOLVED
    )
    assert not hasattr(feeder, "connectivity_status")
    assert outcome.issues == ()


def test_feeder_empty_source_bus_is_missing_and_grid_case_remains_unassigned() -> None:
    raw = _raw_record(SourceFileType.FEEDER, ("feeder-1", "", ""))
    grid_case = map_grid_case(_case_inventory(), dataset_id=DATASET_ID)

    outcome = map_feeder(
        raw,
        dataset_id=DATASET_ID,
        case_id=CASE_ID,
        identity_status=IdentityStatus.UNIQUE,
    )

    assert outcome.record is not None
    assert outcome.record.name is None
    assert outcome.record.source_bus_source_ref is not None
    assert outcome.record.source_bus_source_ref.raw_ref is None
    assert (
        outcome.record.source_bus_source_ref.resolution_status
        is SourceReferenceStatus.MISSING
    )
    assert grid_case.feeder_ref is None


def test_feeder_missing_required_source_id_is_record_fatal() -> None:
    raw = _raw_record(SourceFileType.FEEDER, ("", "name", "source-bus"))

    outcome = map_feeder(
        raw,
        dataset_id=DATASET_ID,
        case_id=CASE_ID,
        identity_status=IdentityStatus.UNIQUE,
    )

    assert outcome.record is None
    assert outcome.unmapped_record is not None
    assert outcome.issues[0].code is QualityIssueCode.SOURCE_REQUIRED_VALUE_MISSING
    assert outcome.error_category is ImportErrorCategory.RECORD_FATAL
