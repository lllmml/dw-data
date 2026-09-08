"""Canonical records used by the Source Import MVP."""

from __future__ import annotations

import types
from dataclasses import dataclass, fields
from decimal import Decimal
from functools import lru_cache
from typing import Any, Union, get_args, get_origin, get_type_hints

from .quality import DEFAULT_SEVERITY_BY_CODE, QualityIssueCode
from .types import (
    CanonicalId,
    ConnectivityStatus,
    DataQuality,
    EntityRef,
    EquipmentType,
    IdentityStatus,
    ImportStatus,
    PowerFactorMode,
    RecordOrigin,
    SeriesKind,
    Severity,
    SourceId,
    SourceReference,
    SourceReferenceStatus,
    SwitchKind,
    SwitchState,
    ValueType,
)


def _matches_type(value: object, annotation: object) -> bool:
    if annotation is Any:
        return True

    origin = get_origin(annotation)
    if origin in (types.UnionType, Union):
        return any(_matches_type(value, member) for member in get_args(annotation))
    if origin is tuple:
        if not isinstance(value, tuple):
            return False
        item_types = get_args(annotation)
        if len(item_types) == 2 and item_types[1] is Ellipsis:
            return all(_matches_type(item, item_types[0]) for item in value)
        return len(value) == len(item_types) and all(
            _matches_type(item, item_type)
            for item, item_type in zip(value, item_types, strict=True)
        )
    if origin is dict:
        if not isinstance(value, dict):
            return False
        key_type, value_type = get_args(annotation)
        return all(
            _matches_type(key, key_type) and _matches_type(item, value_type)
            for key, item in value.items()
        )
    if annotation is bool:
        return type(value) is bool
    if annotation is int:
        return type(value) is int
    if isinstance(annotation, type):
        return isinstance(value, annotation)
    return False


@lru_cache(maxsize=None)
def _record_type_hints(record_type: type[object]) -> dict[str, object]:
    return get_type_hints(record_type)


def _validate_field_types(record: object) -> None:
    hints = _record_type_hints(type(record))
    for field in fields(record):
        value = getattr(record, field.name)
        annotation = hints[field.name]
        if not _matches_type(value, annotation):
            raise TypeError(
                f"{type(record).__name__}.{field.name} does not match {annotation!r}: "
                f"got {type(value).__name__}"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class TraceableRecord:
    record_origin: RecordOrigin
    source_record_ref: str | None
    source_mapping_id: str | None
    source_mapping_version: str | None

    def __post_init__(self) -> None:
        _validate_field_types(self)
        for field_name in (
            "source_record_ref",
            "source_mapping_id",
            "source_mapping_version",
        ):
            value = getattr(self, field_name)
            if value == "":
                raise ValueError(f"{field_name} must be non-empty when present")
        if (self.source_mapping_id is None) != (self.source_mapping_version is None):
            raise ValueError(
                "source_mapping_id and source_mapping_version must be present together"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class Dataset(TraceableRecord):
    dataset_id: CanonicalId
    name: str
    source_uri: str | None
    source_checksum: str | None
    canonical_spec_version: str
    imported_at: str
    import_status: ImportStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class GridCase(TraceableRecord):
    case_id: CanonicalId
    dataset_id: CanonicalId
    source_case_key: str | None
    feeder_ref: EntityRef | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Station(TraceableRecord):
    station_id: CanonicalId
    case_id: CanonicalId
    source_id: SourceId | None
    identity_status: IdentityStatus
    station_type: str | None
    name: str | None
    nominal_voltage_kv: Decimal | None
    longitude: Decimal | None
    latitude: Decimal | None
    coordinate_crs: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Feeder(TraceableRecord):
    feeder_id: CanonicalId
    case_id: CanonicalId
    source_id: SourceId | None
    identity_status: IdentityStatus
    name: str | None
    source_bus_source_ref: SourceReference | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Bus(TraceableRecord):
    bus_id: CanonicalId
    case_id: CanonicalId
    source_id: SourceId | None
    identity_status: IdentityStatus
    name: str | None
    base_voltage_kv: Decimal | None
    phases: tuple[str, ...] | None
    station_source_ref: SourceReference | None
    is_source: bool | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Equipment(TraceableRecord):
    equipment_id: CanonicalId
    case_id: CanonicalId
    source_id: SourceId | None
    equipment_type: EquipmentType
    name: str | None
    phases: tuple[str, ...] | None
    in_service: bool | None
    identity_status: IdentityStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class Terminal(TraceableRecord):
    terminal_id: CanonicalId
    case_id: CanonicalId
    equipment_id: CanonicalId
    terminal_no: int
    raw_connected_ref: SourceId | None
    resolved_source_ref: EntityRef | None
    source_ref_status: SourceReferenceStatus
    connectivity_node_ref: EntityRef | None
    connectivity_status: ConnectivityStatus
    phases: tuple[str, ...] | None

    def __post_init__(self) -> None:
        TraceableRecord.__post_init__(self)
        if self.terminal_no < 1:
            raise ValueError("terminal_no must start at 1")
        SourceReference(
            raw_ref=self.raw_connected_ref,
            resolved_source_ref=self.resolved_source_ref,
            resolution_status=self.source_ref_status,
        )
        if self.connectivity_status is ConnectivityStatus.CONFIRMED:
            if self.connectivity_node_ref is None:
                raise ValueError("CONFIRMED connectivity requires connectivity_node_ref")
        elif self.connectivity_node_ref is not None:
            raise ValueError(
                f"{self.connectivity_status} connectivity must not contain a node ref"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class Line(TraceableRecord):
    equipment_id: CanonicalId
    line_type: str | None
    model: str | None
    length_km: Decimal | None
    r1_ohm_per_km: Decimal | None
    x1_ohm_per_km: Decimal | None
    r0_ohm_per_km: Decimal | None
    x0_ohm_per_km: Decimal | None
    c1_nf_per_km: Decimal | None
    c0_nf_per_km: Decimal | None
    rated_current_a: Decimal | None
    number_of_circuits: int | None
    parameter_set_ref: EntityRef | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SwitchingDevice(TraceableRecord):
    equipment_id: CanonicalId
    switch_kind: SwitchKind
    normal_state: SwitchState | None
    observed_state: SwitchState | None
    is_tie: bool | None
    rated_current_a: Decimal | None
    measurement_capable: bool | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Transformer(TraceableRecord):
    equipment_id: CanonicalId
    rated_capacity_kva: Decimal | None
    r_pct: Decimal | None
    x_pct: Decimal | None
    number_of_taps: int | None
    tap_min_pu: Decimal | None
    tap_max_pu: Decimal | None
    tap_range_raw: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformerWinding(TraceableRecord):
    winding_id: CanonicalId
    equipment_id: CanonicalId
    winding_no: int
    terminal_id: CanonicalId
    rated_voltage_kv: Decimal | None
    connection: str | None
    rated_capacity_kva: Decimal | None

    def __post_init__(self) -> None:
        TraceableRecord.__post_init__(self)
        if self.winding_no < 1:
            raise ValueError("winding_no must start at 1")


@dataclass(frozen=True, slots=True, kw_only=True)
class AccessPoint(TraceableRecord):
    equipment_id: CanonicalId
    user_type: str | None
    contract_capacity_kva: Decimal | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Load(TraceableRecord):
    equipment_id: CanonicalId
    active_power_kw: Decimal | None
    reactive_power_kvar: Decimal | None
    power_factor: Decimal | None
    power_factor_mode: PowerFactorMode | None
    connection: str | None
    load_model: str | None
    nominal_voltage_kv: Decimal | None


@dataclass(frozen=True, slots=True, kw_only=True)
class DER(TraceableRecord):
    equipment_id: CanonicalId
    der_type: str | None
    rated_capacity_kva: Decimal | None
    rated_power_kw: Decimal | None
    power_factor: Decimal | None
    connection: str | None
    control_mode: str | None
    nominal_voltage_kv: Decimal | None


@dataclass(frozen=True, slots=True, kw_only=True)
class OperationalSeries(TraceableRecord):
    series_id: CanonicalId
    scenario_id: CanonicalId | None
    target_ref: EntityRef
    metric: str
    unit: str | None
    phase: str | None
    series_kind: SeriesKind
    value_type: ValueType
    interval_seconds: Decimal | None
    quality: DataQuality


@dataclass(frozen=True, slots=True, kw_only=True)
class OperationalValue(TraceableRecord):
    series_id: CanonicalId
    timestamp: str | None
    offset_seconds: Decimal | None
    sequence_no: int | None
    decimal_value: Decimal | None
    boolean_value: bool | None
    category_value: str | None
    quality: DataQuality

    def __post_init__(self) -> None:
        TraceableRecord.__post_init__(self)
        values = (self.decimal_value, self.boolean_value, self.category_value)
        if sum(value is not None for value in values) != 1:
            raise ValueError("exactly one OperationalValue value field must be set")


@dataclass(frozen=True, slots=True, kw_only=True)
class SimulationProfile(TraceableRecord):
    simulation_profile_id: CanonicalId
    case_id: CanonicalId
    scenario_id: CanonicalId | None
    mode: str | None
    solver: str | None
    frequency_hz: Decimal | None
    source_voltage_kv: Decimal | None
    source_bus_source_ref: SourceReference | None
    output_voltage_bus_source_ref: SourceReference | None
    max_iterations: int | None
    tolerance: Decimal | None
    mva_sc3: Decimal | None
    mva_sc1: Decimal | None
    unit_system: str | None
    extensions: dict[str, str] | None


@dataclass(frozen=True, slots=True, kw_only=True)
class DataQualityIssue(TraceableRecord):
    issue_id: CanonicalId
    case_id: CanonicalId | None
    target_ref: EntityRef | None
    field_path: str | None
    code: QualityIssueCode
    severity: Severity
    observed_value: str | None
    message: str

    def __post_init__(self) -> None:
        TraceableRecord.__post_init__(self)
        expected = DEFAULT_SEVERITY_BY_CODE[self.code]
        if self.severity is not expected:
            raise ValueError(
                f"{self.code} requires default severity {expected}, got {self.severity}"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class FieldProvenance(TraceableRecord):
    provenance_id: CanonicalId
    case_id: CanonicalId | None
    target_ref: EntityRef
    field_path: str
    origin: RecordOrigin
    source_field: str | None
    rule_id: str | None
    rule_version: str | None
    config_ref: str | None
    random_seed: int | str | None
    assumption: str | None
    changed_by: str | None
