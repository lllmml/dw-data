"""Immutable Station/Feeder/Bus assembly over existing mapper outcomes."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import StrEnum

from grid_case_generator.models.identifiers import SourceImportIdFactory
from grid_case_generator.models.quality import QualityIssueCode
from grid_case_generator.models.records import (
    Bus,
    DataQualityIssue,
    Feeder,
    GridCase,
    Station,
)
from grid_case_generator.models.types import (
    CanonicalId,
    EntityRef,
    Identifier,
    IdentityStatus,
    RecordOrigin,
    SourceId,
    SourceReferenceStatus,
)
from grid_case_generator.validation.identity import SourceEntityType
from grid_case_generator.validation.quality import (
    ImportErrorCategory,
    default_severity_for_issue,
)
from grid_case_generator.validation.reference_resolution import (
    ReferenceIdentityConflict,
    ReferenceResolutionResult,
)

from .mapping import RecordMappingOutcome, UnmappedSourceRecord
from .models import RawCsvRecord
from .reference_integration import (
    build_nanjing_reference_candidate_index,
    integrate_bus_station_reference,
    integrate_feeder_source_bus_reference,
)
from .reference_issue_policy import reference_issues_for_result
from .schema import NANJING_SOURCE_SCHEMA, SourceFileType


_MappedRecord = Station | Feeder | Bus
_SOURCE_TYPE_BY_FILE_TYPE = {
    SourceFileType.STATION: SourceEntityType.STATION,
    SourceFileType.FEEDER: SourceEntityType.FEEDER,
    SourceFileType.BUS: SourceEntityType.BUS,
}
_ID_FIELD_BY_FILE_TYPE = {
    SourceFileType.STATION: "Station_ID",
    SourceFileType.FEEDER: "Feeder_ID",
    SourceFileType.BUS: "Bus_ID",
}
_FIELD_PATH_BY_FILE_TYPE = {
    SourceFileType.STATION: "station.source_id",
    SourceFileType.FEEDER: "feeder.source_id",
    SourceFileType.BUS: "bus.source_id",
}
_RECORD_ORDER = {Station: 0, Feeder: 1, Bus: 2}
_MAPPER_OCCURRENCE_KEY_BY_FIELD_PATH = {
    "station.nominal_voltage_kv": "Station_Voltage_Level",
    "station.longitude": "Station_Lon",
    "station.latitude": "Station_Lat",
    "bus.base_voltage_kv": "Bus_BaseKV",
    "bus.is_source": "Bus_IsSource",
}


class RowTerminalCategory(StrEnum):
    MAPPED = "MAPPED"
    DUPLICATE = "DUPLICATE"
    UNRESOLVED = "UNRESOLVED"
    REJECTED = "REJECTED"


def _entity_ref(record: _MappedRecord) -> EntityRef:
    if isinstance(record, Station):
        return EntityRef(
            entity_type=Identifier("STATION"), entity_id=record.station_id
        )
    if isinstance(record, Feeder):
        return EntityRef(
            entity_type=Identifier("FEEDER"), entity_id=record.feeder_id
        )
    return EntityRef(entity_type=Identifier("BUS"), entity_id=record.bus_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class CaseRowMappingOutcome:
    """Associate one Intake row with its already-produced mapper outcome."""

    raw_record: RawCsvRecord
    identity_status: IdentityStatus | None
    mapping_outcome: RecordMappingOutcome[_MappedRecord]

    def __post_init__(self) -> None:
        if not isinstance(self.raw_record, RawCsvRecord):
            raise TypeError("raw_record must be RawCsvRecord")
        if self.raw_record.source_file_type not in _SOURCE_TYPE_BY_FILE_TYPE:
            raise ValueError("case assembly only accepts Station, Feeder, and Bus rows")
        if not isinstance(self.mapping_outcome, RecordMappingOutcome):
            raise TypeError("mapping_outcome must be RecordMappingOutcome")

        mapped = self.mapping_outcome.record
        if mapped is None:
            if self.identity_status is not None:
                raise ValueError("record-fatal row must not have identity_status")
            if self.mapping_outcome.error_category is not ImportErrorCategory.RECORD_FATAL:
                raise ValueError("unmapped row must be a record-fatal mapper outcome")
            unmapped = self.mapping_outcome.unmapped_record
            assert unmapped is not None
            if (
                unmapped.source_record_ref != self.raw_record.source_record_ref
                or unmapped.source_case_key != self.raw_record.source_case_key
                or unmapped.source_file_type is not self.raw_record.source_file_type
                or unmapped.header != self.raw_record.header
                or unmapped.values != self.raw_record.values
                or unmapped.fields != self.raw_record.fields
            ):
                raise ValueError("unmapped record must preserve the associated raw row")
            return

        expected_class = {
            SourceFileType.STATION: Station,
            SourceFileType.FEEDER: Feeder,
            SourceFileType.BUS: Bus,
        }[self.raw_record.source_file_type]
        if not isinstance(mapped, expected_class):
            raise ValueError("mapped record type does not match raw source file type")
        if self.identity_status is None or mapped.identity_status is not self.identity_status:
            raise ValueError("identity status must match the mapped record")
        if (
            mapped.record_origin is not RecordOrigin.SOURCE
            or mapped.source_mapping_id != NANJING_SOURCE_SCHEMA.mapping_id
            or mapped.source_mapping_version
            != NANJING_SOURCE_SCHEMA.mapping_version
        ):
            raise ValueError("mapped record provenance must match the adapter")
        if mapped.source_record_ref != self.raw_record.source_record_ref:
            raise ValueError("mapped record must preserve the associated row locator")
        if self.raw_record.fields is None:
            raise ValueError("successful mapper outcome requires aligned raw fields")
        source_id = dict(self.raw_record.fields)[
            _ID_FIELD_BY_FILE_TYPE[self.raw_record.source_file_type]
        ]
        if mapped.source_id != source_id:
            raise ValueError("mapped source identity must match the associated raw row")


@dataclass(frozen=True, slots=True, kw_only=True)
class RowAccountability:
    raw_record: RawCsvRecord
    terminal_category: RowTerminalCategory
    identity_status: IdentityStatus | None
    canonical_ref: EntityRef | None
    issue_ids: tuple[CanonicalId, ...]
    resolution_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class CaseAssemblyResult:
    grid_case: GridCase
    records: tuple[_MappedRecord, ...]
    issues: tuple[DataQualityIssue, ...]
    unmapped_records: tuple[UnmappedSourceRecord, ...]
    resolutions: tuple[ReferenceResolutionResult, ...]
    accounting: tuple[RowAccountability, ...]


def _issue_sort_key(issue: DataQualityIssue) -> tuple[str, ...]:
    target = issue.target_ref
    return (
        issue.case_id or "",
        issue.source_record_ref or "",
        issue.field_path or "",
        issue.code.value,
        target.entity_type if target else "",
        target.entity_id if target else "",
        issue.issue_id,
    )


def _record_sort_key(record: _MappedRecord) -> tuple[int, str, str]:
    ref = _entity_ref(record)
    return (
        _RECORD_ORDER[type(record)],
        record.source_record_ref or "",
        ref.entity_id,
    )


def _make_issue(
    *,
    dataset_id: CanonicalId,
    case_id: CanonicalId,
    target_ref: EntityRef | None,
    field_path: str,
    code: QualityIssueCode,
    source_record_ref: str | None,
    occurrence_key: str,
    observed_value: str | None,
    message: str,
) -> DataQualityIssue:
    return DataQualityIssue(
        record_origin=RecordOrigin.DERIVED,
        source_record_ref=source_record_ref,
        source_mapping_id=NANJING_SOURCE_SCHEMA.mapping_id,
        source_mapping_version=NANJING_SOURCE_SCHEMA.mapping_version,
        issue_id=SourceImportIdFactory.quality_issue_id(
            dataset_id=dataset_id,
            case_id=case_id,
            target_ref=target_ref,
            field_path=field_path,
            code=code,
            source_record_ref=source_record_ref,
            occurrence_key=occurrence_key,
        ),
        case_id=case_id,
        target_ref=target_ref,
        field_path=field_path,
        code=code,
        severity=default_severity_for_issue(code),
        observed_value=observed_value,
        message=message,
    )


def _retarget_mapper_issue(
    issue: DataQualityIssue,
    *,
    dataset_id: CanonicalId,
    target_ref: EntityRef | None,
) -> DataQualityIssue:
    if issue.target_ref == target_ref:
        return issue
    if issue.field_path is None:
        raise ValueError("targeted mapper issue requires field_path")
    try:
        occurrence_key = _MAPPER_OCCURRENCE_KEY_BY_FIELD_PATH[issue.field_path]
    except KeyError as error:
        raise ValueError(
            "case assembly cannot deterministically retarget this mapper issue"
        ) from error
    return replace(
        issue,
        issue_id=SourceImportIdFactory.quality_issue_id(
            dataset_id=dataset_id,
            case_id=issue.case_id,
            target_ref=target_ref,
            field_path=issue.field_path,
            code=issue.code,
            source_record_ref=issue.source_record_ref,
            occurrence_key=occurrence_key,
        ),
        target_ref=target_ref,
    )


def _resolution_sort_key(result: ReferenceResolutionResult) -> tuple[str, str, str]:
    return (
        result.request.owner_source_entity_type,
        result.request.owner_source_record_ref,
        result.request.reference_field_path,
    )


def assemble_station_feeder_bus_case(
    grid_case: GridCase,
    row_mappings: Iterable[CaseRowMappingOutcome],
    *,
    dataset_id: CanonicalId,
) -> CaseAssemblyResult:
    """Assemble one case without reading source files or deciding ImportStatus."""

    if not isinstance(grid_case, GridCase):
        raise TypeError("grid_case must be GridCase")
    if grid_case.dataset_id != dataset_id:
        raise ValueError("grid_case dataset_id must match assembly dataset_id")

    rows = tuple(row_mappings)
    if not all(isinstance(item, CaseRowMappingOutcome) for item in rows):
        raise TypeError("row_mappings must contain CaseRowMappingOutcome values")
    locators = tuple(item.raw_record.source_record_ref for item in rows)
    if len(set(locators)) != len(locators):
        raise ValueError("source_record_ref must be unique within case assembly")
    if any(
        item.raw_record.source_case_key != grid_case.source_case_key
        for item in rows
    ):
        raise ValueError("all row mappings must belong to the assembled case")
    if any(
        item.mapping_outcome.record is not None
        and item.mapping_outcome.record.case_id != grid_case.case_id
        for item in rows
    ):
        raise ValueError("all mapped records must belong to the assembled case")

    successful = tuple(item for item in rows if item.mapping_outcome.record is not None)
    groups: dict[
        tuple[SourceFileType, SourceId], list[CaseRowMappingOutcome]
    ] = {}
    for item in successful:
        record = item.mapping_outcome.record
        assert record is not None and record.source_id is not None
        groups.setdefault(
            (item.raw_record.source_file_type, record.source_id), []
        ).append(item)

    published_by_row: dict[str, _MappedRecord] = {}
    published_for_input_row: dict[str, _MappedRecord | None] = {}
    conflicts: list[ReferenceIdentityConflict] = []
    duplicate_issues: list[DataQualityIssue] = []
    mapper_issues: list[DataQualityIssue] = []

    for (file_type, source_id), group in groups.items():
        ordered_group = tuple(
            sorted(group, key=lambda item: item.raw_record.source_record_ref)
        )
        statuses = {item.identity_status for item in ordered_group}
        if len(statuses) != 1:
            raise ValueError("source identity group must have one consistent status")
        status = ordered_group[0].identity_status
        assert status is not None

        if status is IdentityStatus.UNIQUE:
            if len(ordered_group) != 1:
                raise ValueError("multiple rows with one source identity cannot be UNIQUE")
            published = ordered_group[0].mapping_outcome.record
            assert published is not None
        elif status is IdentityStatus.DUPLICATE_IDENTICAL:
            if len(ordered_group) < 2 or any(
                item.raw_record.fields != ordered_group[0].raw_record.fields
                for item in ordered_group[1:]
            ):
                raise ValueError("DUPLICATE_IDENTICAL group must have identical rows")
            published = ordered_group[0].mapping_outcome.record
            assert published is not None
        else:
            if len(ordered_group) < 2 or all(
                item.raw_record.fields == ordered_group[0].raw_record.fields
                for item in ordered_group[1:]
            ):
                raise ValueError("DUPLICATE_CONFLICT group must contain different rows")
            published = None
            conflicts.append(
                ReferenceIdentityConflict(
                    case_id=grid_case.case_id,
                    source_entity_type=_SOURCE_TYPE_BY_FILE_TYPE[file_type],
                    source_id=source_id,
                    source_record_refs=tuple(
                        item.raw_record.source_record_ref for item in ordered_group
                    ),
                )
            )

        published_ref = _entity_ref(published) if published is not None else None
        if published is not None:
            assert published.source_record_ref is not None
            published_by_row[published.source_record_ref] = published
        for item in ordered_group:
            published_for_input_row[item.raw_record.source_record_ref] = published
            mapper_issues.extend(
                _retarget_mapper_issue(
                    issue,
                    dataset_id=dataset_id,
                    target_ref=published_ref,
                )
                for issue in item.mapping_outcome.issues
            )
            if status is IdentityStatus.UNIQUE:
                continue
            code = (
                QualityIssueCode.SOURCE_ID_DUPLICATE_IDENTICAL
                if status is IdentityStatus.DUPLICATE_IDENTICAL
                else QualityIssueCode.SOURCE_ID_DUPLICATE_CONFLICT
            )
            duplicate_issues.append(
                _make_issue(
                    dataset_id=dataset_id,
                    case_id=grid_case.case_id,
                    target_ref=published_ref,
                    field_path=_FIELD_PATH_BY_FILE_TYPE[file_type],
                    code=code,
                    source_record_ref=item.raw_record.source_record_ref,
                    occurrence_key="",
                    observed_value=source_id,
                    message=(
                        "source identity has identical duplicate rows"
                        if status is IdentityStatus.DUPLICATE_IDENTICAL
                        else "source identity has conflicting duplicate rows"
                    ),
                )
            )

    unmapped_records: list[UnmappedSourceRecord] = []
    for item in rows:
        if item.mapping_outcome.record is not None:
            continue
        mapper_issues.extend(item.mapping_outcome.issues)
        assert item.mapping_outcome.unmapped_record is not None
        unmapped_records.append(item.mapping_outcome.unmapped_record)
        published_for_input_row[item.raw_record.source_record_ref] = None

    published_records = tuple(published_by_row.values())
    index = build_nanjing_reference_candidate_index(
        published_records,
        identity_conflicts=conflicts,
    )
    raw_by_ref = {item.raw_record.source_record_ref: item.raw_record for item in rows}
    integrated_by_row = dict(published_by_row)
    resolutions: list[ReferenceResolutionResult] = []
    reference_issues: list[DataQualityIssue] = []
    for source_record_ref, record in published_by_row.items():
        if isinstance(record, Bus):
            integration = integrate_bus_station_reference(
                raw_by_ref[source_record_ref], record, index
            )
        elif isinstance(record, Feeder):
            integration = integrate_feeder_source_bus_reference(
                raw_by_ref[source_record_ref], record, index
            )
        else:
            continue
        integrated_by_row[source_record_ref] = integration.record
        resolutions.append(integration.resolution)
        reference_issues.extend(
            reference_issues_for_result(
                integration.resolution,
                dataset_id=dataset_id,
                target_ref=_entity_ref(integration.record),
            )
        )

    final_records = tuple(sorted(integrated_by_row.values(), key=_record_sort_key))
    feeder_rows = tuple(
        item
        for item in successful
        if item.raw_record.source_file_type is SourceFileType.FEEDER
    )
    has_duplicate_feeder = any(
        item.identity_status is not IdentityStatus.UNIQUE for item in feeder_rows
    )
    unique_feeders = tuple(
        record
        for record in final_records
        if isinstance(record, Feeder)
        and record.identity_status is IdentityStatus.UNIQUE
    )
    grid_case_ref = EntityRef(
        entity_type=Identifier("GRID_CASE"), entity_id=grid_case.case_id
    )
    feeder_issues: list[DataQualityIssue] = []
    if has_duplicate_feeder or len(unique_feeders) > 1:
        assembled_grid_case = replace(grid_case, feeder_ref=None)
        feeder_issues.append(
            _make_issue(
                dataset_id=dataset_id,
                case_id=grid_case.case_id,
                target_ref=grid_case_ref,
                field_path="grid_case.feeder_ref",
                code=QualityIssueCode.GRID_CASE_FEEDER_AMBIGUOUS,
                source_record_ref=None,
                occurrence_key="",
                observed_value=None,
                message="case does not have one unambiguous unique Feeder",
            )
        )
    elif len(unique_feeders) == 1:
        assembled_grid_case = replace(
            grid_case, feeder_ref=_entity_ref(unique_feeders[0])
        )
    else:
        assembled_grid_case = replace(grid_case, feeder_ref=None)
        feeder_issues.append(
            _make_issue(
                dataset_id=dataset_id,
                case_id=grid_case.case_id,
                target_ref=grid_case_ref,
                field_path="grid_case.feeder_ref",
                code=QualityIssueCode.GRID_CASE_FEEDER_MISSING,
                source_record_ref=None,
                occurrence_key="",
                observed_value=None,
                message="case has no successfully established Feeder",
            )
        )

    ordered_resolutions = tuple(sorted(resolutions, key=_resolution_sort_key))
    resolution_index_by_ref = {
        _entity_ref(record): index_position
        for index_position, result in enumerate(ordered_resolutions)
        for record in final_records
        if record.source_record_ref == result.request.owner_source_record_ref
    }
    issues = tuple(
        sorted(
            (
                *mapper_issues,
                *duplicate_issues,
                *reference_issues,
                *feeder_issues,
            ),
            key=_issue_sort_key,
        )
    )
    issue_ids_by_row: dict[str, list[CanonicalId]] = {}
    for issue in issues:
        if issue.source_record_ref is not None:
            issue_ids_by_row.setdefault(issue.source_record_ref, []).append(
                issue.issue_id
            )

    accounting: list[RowAccountability] = []
    for item in rows:
        locator = item.raw_record.source_record_ref
        published = published_for_input_row[locator]
        canonical_ref = _entity_ref(published) if published is not None else None
        resolution_indexes = (
            (resolution_index_by_ref[canonical_ref],)
            if canonical_ref in resolution_index_by_ref
            else ()
        )
        if item.mapping_outcome.record is None:
            category = RowTerminalCategory.REJECTED
        elif item.identity_status is not IdentityStatus.UNIQUE:
            category = RowTerminalCategory.DUPLICATE
        elif resolution_indexes and ordered_resolutions[
            resolution_indexes[0]
        ].resolution_status in {
            SourceReferenceStatus.AMBIGUOUS,
            SourceReferenceStatus.UNRESOLVED,
        }:
            category = RowTerminalCategory.UNRESOLVED
        else:
            category = RowTerminalCategory.MAPPED
        accounting.append(
            RowAccountability(
                raw_record=item.raw_record,
                terminal_category=category,
                identity_status=item.identity_status,
                canonical_ref=canonical_ref,
                issue_ids=tuple(issue_ids_by_row.get(locator, ())),
                resolution_indexes=resolution_indexes,
            )
        )

    return CaseAssemblyResult(
        grid_case=assembled_grid_case,
        records=final_records,
        issues=issues,
        unmapped_records=tuple(
            sorted(
                unmapped_records,
                key=lambda item: (
                    item.source_file_type.value,
                    item.source_record_ref,
                ),
            )
        ),
        resolutions=ordered_resolutions,
        accounting=tuple(
            sorted(
                accounting,
                key=lambda item: (
                    item.raw_record.source_file_type.value,
                    item.raw_record.source_record_ref,
                ),
            )
        ),
    )
