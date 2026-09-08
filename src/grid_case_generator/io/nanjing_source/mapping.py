"""Lowest-risk Nanjing intake-to-Canonical mapping primitives."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Generic, TypeVar

from grid_case_generator.models.identifiers import SourceImportIdFactory
from grid_case_generator.models.quality import QualityIssueCode
from grid_case_generator.models.records import (
    DataQualityIssue,
    Dataset,
    Feeder,
    GridCase,
    Station,
)
from grid_case_generator.models.types import (
    CanonicalId,
    EntityRef,
    Identifier,
    IdentityStatus,
    ImportStatus,
    RecordOrigin,
    SourceId,
    SourceReference,
    SourceReferenceStatus,
)
from grid_case_generator.validation.quality import (
    ImportErrorCategory,
    default_severity_for_issue,
)

from .locator import SourceRecordRef
from .models import RawCsvRecord, SourceCaseInventory, SourceDatasetInventory
from .schema import NANJING_SOURCE_SCHEMA, SourceFileType


CANONICAL_SPEC_VERSION = "0.3.0"
_MAPPING_ID = NANJING_SOURCE_SCHEMA.mapping_id
_MAPPING_VERSION = NANJING_SOURCE_SCHEMA.mapping_version
_T = TypeVar("_T")


@dataclass(frozen=True, slots=True, kw_only=True)
class UnmappedSourceRecord:
    """A record-fatal source row retained for later report writing."""

    source_record_ref: SourceRecordRef
    source_case_key: str
    source_file_type: SourceFileType
    header: tuple[str, ...]
    values: tuple[str, ...]
    fields: tuple[tuple[str, str], ...] | None
    issue_ids: tuple[CanonicalId, ...]
    issue_codes: tuple[QualityIssueCode, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordMappingOutcome(Generic[_T]):
    record: _T | None
    issues: tuple[DataQualityIssue, ...]
    unmapped_record: UnmappedSourceRecord | None
    error_category: ImportErrorCategory | None

    def __post_init__(self) -> None:
        if (self.record is None) == (self.unmapped_record is None):
            raise ValueError(
                "mapping outcome requires either record or unmapped_record"
            )


def _source_trace(source_record_ref: SourceRecordRef | None) -> dict[str, object]:
    return {
        "record_origin": RecordOrigin.SOURCE,
        "source_record_ref": source_record_ref,
        "source_mapping_id": _MAPPING_ID,
        "source_mapping_version": _MAPPING_VERSION,
    }


def map_dataset(
    inventory: SourceDatasetInventory,
    *,
    name: str,
    imported_at: str,
    import_status: ImportStatus,
) -> Dataset:
    """Map intake inventory and explicit run metadata without reopening the artifact."""

    checksum_hex = inventory.source_checksum.removeprefix("sha256:")
    dataset_id = SourceImportIdFactory.dataset_id(checksum_hex)
    return Dataset(
        **_source_trace(None),
        dataset_id=dataset_id,
        name=name,
        source_uri=inventory.source_uri,
        source_checksum=inventory.source_checksum,
        canonical_spec_version=CANONICAL_SPEC_VERSION,
        imported_at=imported_at,
        import_status=import_status,
    )


def map_grid_case(
    inventory: SourceCaseInventory, *, dataset_id: CanonicalId
) -> GridCase:
    """Map one discovered case without selecting or inferring a Feeder."""

    return GridCase(
        **_source_trace(None),
        case_id=SourceImportIdFactory.case_id(
            dataset_id, inventory.source_case_key
        ),
        dataset_id=dataset_id,
        source_case_key=inventory.source_case_key,
        feeder_ref=None,
    )


def _issue(
    *,
    dataset_id: CanonicalId,
    case_id: CanonicalId,
    record: RawCsvRecord,
    target_ref: EntityRef | None,
    field_path: str | None,
    code: QualityIssueCode,
    observed_value: str | None,
    occurrence_key: str,
    message: str,
) -> DataQualityIssue:
    issue_id = SourceImportIdFactory.quality_issue_id(
        dataset_id=dataset_id,
        case_id=case_id,
        target_ref=target_ref,
        field_path=field_path,
        code=code,
        source_record_ref=record.source_record_ref,
        occurrence_key=occurrence_key,
    )
    return DataQualityIssue(
        record_origin=RecordOrigin.DERIVED,
        source_record_ref=record.source_record_ref,
        source_mapping_id=_MAPPING_ID,
        source_mapping_version=_MAPPING_VERSION,
        issue_id=issue_id,
        case_id=case_id,
        target_ref=target_ref,
        field_path=field_path,
        code=code,
        severity=default_severity_for_issue(code),
        observed_value=observed_value,
        message=message,
    )


def _unmapped(
    record: RawCsvRecord, issues: tuple[DataQualityIssue, ...]
) -> UnmappedSourceRecord:
    return UnmappedSourceRecord(
        source_record_ref=record.source_record_ref,
        source_case_key=record.source_case_key,
        source_file_type=record.source_file_type,
        header=record.header,
        values=record.values,
        fields=record.fields,
        issue_ids=tuple(issue.issue_id for issue in issues),
        issue_codes=tuple(issue.code for issue in issues),
    )


def _validated_fields(
    record: RawCsvRecord,
    *,
    expected_file_type: SourceFileType,
) -> dict[str, str] | None:
    if record.source_file_type is not expected_file_type:
        raise ValueError(
            f"expected {expected_file_type.value}, got {record.source_file_type.value}"
        )
    expected_header = NANJING_SOURCE_SCHEMA.for_type(expected_file_type).header
    if record.header != expected_header:
        raise ValueError("raw record header does not match the mapping registry")
    return dict(record.fields) if record.fields is not None else None


def _malformed_outcome(
    record: RawCsvRecord,
    *,
    dataset_id: CanonicalId,
    case_id: CanonicalId,
) -> RecordMappingOutcome[_T]:
    issue = _issue(
        dataset_id=dataset_id,
        case_id=case_id,
        record=record,
        target_ref=None,
        field_path=None,
        code=QualityIssueCode.SOURCE_ROW_MALFORMED,
        observed_value=None,
        occurrence_key="raw-row",
        message="raw source record does not align with the recognized header",
    )
    issues = (issue,)
    return RecordMappingOutcome(
        record=None,
        issues=issues,
        unmapped_record=_unmapped(record, issues),
        error_category=ImportErrorCategory.RECORD_FATAL,
    )


def _missing_id_outcome(
    record: RawCsvRecord,
    *,
    dataset_id: CanonicalId,
    case_id: CanonicalId,
    field_path: str,
    source_field: str,
) -> RecordMappingOutcome[_T]:
    issue = _issue(
        dataset_id=dataset_id,
        case_id=case_id,
        record=record,
        target_ref=None,
        field_path=field_path,
        code=QualityIssueCode.SOURCE_REQUIRED_VALUE_MISSING,
        observed_value="",
        occurrence_key=source_field,
        message=f"required source identity field {source_field} is empty",
    )
    issues = (issue,)
    return RecordMappingOutcome(
        record=None,
        issues=issues,
        unmapped_record=_unmapped(record, issues),
        error_category=ImportErrorCategory.RECORD_FATAL,
    )


def _nullable_text(value: str) -> str | None:
    return None if value == "" else value


def _optional_decimal(
    raw_value: str,
    *,
    dataset_id: CanonicalId,
    case_id: CanonicalId,
    record: RawCsvRecord,
    target_ref: EntityRef,
    field_path: str,
    source_field: str,
) -> tuple[Decimal | None, DataQualityIssue | None]:
    if raw_value == "":
        return None, None
    try:
        value = Decimal(raw_value)
    except InvalidOperation:
        value = None
    if value is None or not value.is_finite():
        return None, _issue(
            dataset_id=dataset_id,
            case_id=case_id,
            record=record,
            target_ref=target_ref,
            field_path=field_path,
            code=QualityIssueCode.SOURCE_VALUE_PARSE_FAILED,
            observed_value=raw_value,
            occurrence_key=source_field,
            message=f"optional Decimal field {source_field} could not be parsed",
        )
    return value, None


def map_station(
    record: RawCsvRecord,
    *,
    dataset_id: CanonicalId,
    case_id: CanonicalId,
    identity_status: IdentityStatus,
) -> RecordMappingOutcome[Station]:
    fields = _validated_fields(record, expected_file_type=SourceFileType.STATION)
    if fields is None:
        return _malformed_outcome(
            record, dataset_id=dataset_id, case_id=case_id
        )
    if fields["Station_ID"] == "":
        return _missing_id_outcome(
            record,
            dataset_id=dataset_id,
            case_id=case_id,
            field_path="station.source_id",
            source_field="Station_ID",
        )

    source_id = SourceId(fields["Station_ID"])
    station_id = SourceImportIdFactory.station_id(
        case_id, source_id, record.source_record_ref
    )
    target_ref = EntityRef(
        entity_type=Identifier("STATION"), entity_id=station_id
    )
    issues: list[DataQualityIssue] = []

    decimals: dict[str, Decimal | None] = {}
    for source_field, field_path in (
        ("Station_Voltage_Level", "station.nominal_voltage_kv"),
        ("Station_Lon", "station.longitude"),
        ("Station_Lat", "station.latitude"),
    ):
        value, issue = _optional_decimal(
            fields[source_field],
            dataset_id=dataset_id,
            case_id=case_id,
            record=record,
            target_ref=target_ref,
            field_path=field_path,
            source_field=source_field,
        )
        decimals[source_field] = value
        if issue is not None:
            issues.append(issue)

    station = Station(
        **_source_trace(record.source_record_ref),
        station_id=station_id,
        case_id=case_id,
        source_id=source_id,
        identity_status=identity_status,
        station_type=_nullable_text(fields["Station_Type"]),
        name=_nullable_text(fields["Station_Name"]),
        nominal_voltage_kv=decimals["Station_Voltage_Level"],
        longitude=decimals["Station_Lon"],
        latitude=decimals["Station_Lat"],
        coordinate_crs=None,
    )
    return RecordMappingOutcome(
        record=station,
        issues=tuple(issues),
        unmapped_record=None,
        error_category=(
            ImportErrorCategory.FIELD_RECOVERABLE if issues else None
        ),
    )


def map_feeder(
    record: RawCsvRecord,
    *,
    dataset_id: CanonicalId,
    case_id: CanonicalId,
    identity_status: IdentityStatus,
) -> RecordMappingOutcome[Feeder]:
    fields = _validated_fields(record, expected_file_type=SourceFileType.FEEDER)
    if fields is None:
        return _malformed_outcome(
            record, dataset_id=dataset_id, case_id=case_id
        )
    if fields["Feeder_ID"] == "":
        return _missing_id_outcome(
            record,
            dataset_id=dataset_id,
            case_id=case_id,
            field_path="feeder.source_id",
            source_field="Feeder_ID",
        )

    source_id = SourceId(fields["Feeder_ID"])
    feeder_id = SourceImportIdFactory.feeder_id(
        case_id, source_id, record.source_record_ref
    )
    raw_source_bus = fields["Feeder_SourceBus"]
    source_bus_source_ref = SourceReference(
        raw_ref=SourceId(raw_source_bus) if raw_source_bus != "" else None,
        resolved_source_ref=None,
        resolution_status=(
            SourceReferenceStatus.UNRESOLVED
            if raw_source_bus != ""
            else SourceReferenceStatus.MISSING
        ),
    )
    feeder = Feeder(
        **_source_trace(record.source_record_ref),
        feeder_id=feeder_id,
        case_id=case_id,
        source_id=source_id,
        identity_status=identity_status,
        name=_nullable_text(fields["Feeder_Name"]),
        source_bus_source_ref=source_bus_source_ref,
    )
    return RecordMappingOutcome(
        record=feeder,
        issues=(),
        unmapped_record=None,
        error_category=None,
    )
