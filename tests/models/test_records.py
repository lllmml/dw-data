from dataclasses import FrozenInstanceError, fields
from decimal import Decimal

import pytest

from grid_case_generator.models.records import (
    AccessPoint,
    Bus,
    DER,
    DataQualityIssue,
    Dataset,
    Equipment,
    Feeder,
    FieldProvenance,
    GridCase,
    Line,
    Load,
    OperationalSeries,
    OperationalValue,
    SimulationProfile,
    Station,
    SwitchingDevice,
    Terminal,
    Transformer,
    TransformerWinding,
)
from grid_case_generator.models.types import (
    CanonicalId,
    ConnectivityStatus,
    DataQuality,
    EntityRef,
    EquipmentType,
    Identifier,
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
from grid_case_generator.validation.quality import QualityIssueCode


TRACE = {
    "record_origin": RecordOrigin.SOURCE,
    "source_record_ref": "zip-member:data/01.csv#data-row=1",
    "source_mapping_id": "test_mapping",
    "source_mapping_version": "1.0.0",
}
CASE_ID = CanonicalId("case:one")
EQUIPMENT_ID = CanonicalId("equipment:one")
TERMINAL_ID = CanonicalId("terminal:one")
BUS_REF = EntityRef(entity_type=Identifier("BUS"), entity_id=CanonicalId("bus:one"))
MISSING_REF = SourceReference(
    raw_ref=None,
    resolved_source_ref=None,
    resolution_status=SourceReferenceStatus.MISSING,
)


def test_source_import_record_types_can_represent_explicit_nulls() -> None:
    records = [
        Dataset(
            **TRACE,
            dataset_id=CanonicalId("dataset:one"),
            name="dataset",
            source_uri=None,
            source_checksum=None,
            canonical_spec_version="0.3.0",
            imported_at="2026-09-08T00:00:00+00:00",
            import_status=ImportStatus.COMPLETE,
        ),
        GridCase(
            **TRACE,
            case_id=CASE_ID,
            dataset_id=CanonicalId("dataset:one"),
            source_case_key="case/path",
            feeder_ref=None,
        ),
        Station(
            **TRACE,
            station_id=CanonicalId("station:one"),
            case_id=CASE_ID,
            source_id=SourceId("station-source"),
            identity_status=IdentityStatus.UNIQUE,
            station_type=None,
            name=None,
            nominal_voltage_kv=None,
            longitude=None,
            latitude=None,
            coordinate_crs=None,
        ),
        Feeder(
            **TRACE,
            feeder_id=CanonicalId("feeder:one"),
            case_id=CASE_ID,
            source_id=SourceId("feeder-source"),
            identity_status=IdentityStatus.UNIQUE,
            name=None,
            source_bus_source_ref=MISSING_REF,
        ),
        Bus(
            **TRACE,
            bus_id=CanonicalId("bus:one"),
            case_id=CASE_ID,
            source_id=SourceId("001_bs"),
            identity_status=IdentityStatus.UNIQUE,
            name=None,
            base_voltage_kv=Decimal("10.5"),
            phases=None,
            station_source_ref=MISSING_REF,
            is_source=None,
        ),
        Equipment(
            **TRACE,
            equipment_id=EQUIPMENT_ID,
            case_id=CASE_ID,
            source_id=SourceId("equipment-source"),
            equipment_type=EquipmentType.SWITCH,
            name=None,
            phases=None,
            in_service=None,
            identity_status=IdentityStatus.UNIQUE,
        ),
        Terminal(
            **TRACE,
            terminal_id=TERMINAL_ID,
            case_id=CASE_ID,
            equipment_id=EQUIPMENT_ID,
            terminal_no=1,
            raw_connected_ref=None,
            resolved_source_ref=None,
            source_ref_status=SourceReferenceStatus.MISSING,
            connectivity_node_ref=None,
            connectivity_status=ConnectivityStatus.NOT_ASSESSED,
            phases=None,
        ),
        Line(
            **TRACE,
            equipment_id=EQUIPMENT_ID,
            line_type=None,
            model=None,
            length_km=None,
            r1_ohm_per_km=None,
            x1_ohm_per_km=None,
            r0_ohm_per_km=None,
            x0_ohm_per_km=None,
            c1_nf_per_km=None,
            c0_nf_per_km=None,
            rated_current_a=None,
            number_of_circuits=None,
            parameter_set_ref=None,
        ),
        SwitchingDevice(
            **TRACE,
            equipment_id=EQUIPMENT_ID,
            switch_kind=SwitchKind.SWITCH,
            normal_state=SwitchState.CLOSED,
            observed_state=None,
            is_tie=None,
            rated_current_a=None,
            measurement_capable=None,
        ),
        Transformer(
            **TRACE,
            equipment_id=EQUIPMENT_ID,
            rated_capacity_kva=Decimal("0"),
            r_pct=None,
            x_pct=None,
            number_of_taps=None,
            tap_min_pu=None,
            tap_max_pu=None,
            tap_range_raw=None,
        ),
        TransformerWinding(
            **TRACE,
            winding_id=CanonicalId("winding:one"),
            equipment_id=EQUIPMENT_ID,
            winding_no=1,
            terminal_id=TERMINAL_ID,
            rated_voltage_kv=None,
            connection=None,
            rated_capacity_kva=None,
        ),
        AccessPoint(
            **TRACE,
            equipment_id=EQUIPMENT_ID,
            user_type=None,
            contract_capacity_kva=None,
        ),
        Load(
            **TRACE,
            equipment_id=EQUIPMENT_ID,
            active_power_kw=None,
            reactive_power_kvar=None,
            power_factor=None,
            power_factor_mode=PowerFactorMode.UNKNOWN,
            connection=None,
            load_model=None,
            nominal_voltage_kv=None,
        ),
        DER(
            **TRACE,
            equipment_id=EQUIPMENT_ID,
            der_type=None,
            rated_capacity_kva=None,
            rated_power_kw=None,
            power_factor=None,
            connection=None,
            control_mode=None,
            nominal_voltage_kv=None,
        ),
        OperationalSeries(
            **TRACE,
            series_id=CanonicalId("operational-series:one"),
            scenario_id=None,
            target_ref=BUS_REF,
            metric="current",
            unit="A",
            phase=None,
            series_kind=SeriesKind.SNAPSHOT,
            value_type=ValueType.DECIMAL,
            interval_seconds=None,
            quality=DataQuality.TIME_UNKNOWN,
        ),
        OperationalValue(
            **TRACE,
            series_id=CanonicalId("operational-series:one"),
            timestamp=None,
            offset_seconds=None,
            sequence_no=0,
            decimal_value=Decimal("1.25"),
            boolean_value=None,
            category_value=None,
            quality=DataQuality.TIME_UNKNOWN,
        ),
        SimulationProfile(
            record_origin=RecordOrigin.SOURCE,
            source_record_ref=None,
            source_mapping_id="test_mapping",
            source_mapping_version="1.0.0",
            simulation_profile_id=CanonicalId("simulation-profile:one"),
            case_id=CASE_ID,
            scenario_id=None,
            mode=None,
            solver=None,
            frequency_hz=None,
            source_voltage_kv=None,
            source_bus_source_ref=MISSING_REF,
            output_voltage_bus_source_ref=MISSING_REF,
            max_iterations=None,
            tolerance=None,
            mva_sc3=None,
            mva_sc1=None,
            unit_system=None,
            extensions=None,
        ),
        DataQualityIssue(
            **TRACE,
            issue_id=CanonicalId("quality-issue:one"),
            case_id=CASE_ID,
            target_ref=None,
            field_path="station.nominal_voltage_kv",
            code=QualityIssueCode.SOURCE_VALUE_PARSE_FAILED,
            severity=Severity.WARNING,
            observed_value="not-a-number",
            message="unable to parse optional numeric value",
        ),
        FieldProvenance(
            **TRACE,
            provenance_id=CanonicalId("field-provenance:one"),
            case_id=CASE_ID,
            target_ref=BUS_REF,
            field_path="simulation_profile.frequency_hz",
            origin=RecordOrigin.SOURCE,
            source_field="Config_Value",
            rule_id=None,
            rule_version=None,
            config_ref=None,
            random_seed=None,
            assumption=None,
            changed_by=None,
        ),
    ]

    assert len(records) == 19
    assert records[2].name is None
    with pytest.raises(FrozenInstanceError):
        records[2].name = "changed"  # type: ignore[misc]


def test_records_reject_float_for_decimal_fields() -> None:
    with pytest.raises(TypeError):
        Station(
            **TRACE,
            station_id=CanonicalId("station:one"),
            case_id=CASE_ID,
            source_id=SourceId("station-source"),
            identity_status=IdentityStatus.UNIQUE,
            station_type=None,
            name=None,
            nominal_voltage_kv=10.5,  # type: ignore[arg-type]
            longitude=None,
            latitude=None,
            coordinate_crs=None,
        )


def test_source_record_requires_mapping_identity_and_version() -> None:
    with pytest.raises(
        ValueError,
        match="SOURCE records require source_mapping_id and source_mapping_version",
    ):
        Dataset(
            record_origin=RecordOrigin.SOURCE,
            source_record_ref=None,
            source_mapping_id=None,
            source_mapping_version=None,
            dataset_id=CanonicalId("dataset:one"),
            name="dataset",
            source_uri=None,
            source_checksum=None,
            canonical_spec_version="0.3.0",
            imported_at="2026-09-08T00:00:00+00:00",
            import_status=ImportStatus.COMPLETE,
        )


def test_non_source_record_may_omit_mapping_identity_and_version() -> None:
    record = Dataset(
        record_origin=RecordOrigin.DERIVED,
        source_record_ref=None,
        source_mapping_id=None,
        source_mapping_version=None,
        dataset_id=CanonicalId("dataset:one"),
        name="dataset",
        source_uri=None,
        source_checksum=None,
        canonical_spec_version="0.3.0",
        imported_at="2026-09-08T00:00:00+00:00",
        import_status=ImportStatus.COMPLETE,
    )

    assert record.source_mapping_id is None
    assert record.source_mapping_version is None


def test_aggregate_source_record_may_omit_source_record_ref() -> None:
    profile = SimulationProfile(
        record_origin=RecordOrigin.SOURCE,
        source_record_ref=None,
        source_mapping_id="test_mapping",
        source_mapping_version="1.0.0",
        simulation_profile_id=CanonicalId("simulation-profile:one"),
        case_id=CASE_ID,
        scenario_id=None,
        mode=None,
        solver=None,
        frequency_hz=None,
        source_voltage_kv=None,
        source_bus_source_ref=MISSING_REF,
        output_voltage_bus_source_ref=MISSING_REF,
        max_iterations=None,
        tolerance=None,
        mva_sc3=None,
        mva_sc1=None,
        unit_system=None,
        extensions=None,
    )

    assert profile.source_record_ref is None


def test_exact_source_reference_does_not_require_confirmed_connectivity() -> None:
    terminal = Terminal(
        **TRACE,
        terminal_id=TERMINAL_ID,
        case_id=CASE_ID,
        equipment_id=EQUIPMENT_ID,
        terminal_no=1,
        raw_connected_ref=SourceId("bus-source"),
        resolved_source_ref=BUS_REF,
        source_ref_status=SourceReferenceStatus.EXACT,
        connectivity_node_ref=None,
        connectivity_status=ConnectivityStatus.NOT_ASSESSED,
        phases=None,
    )

    assert terminal.source_ref_status is SourceReferenceStatus.EXACT
    assert terminal.connectivity_status is ConnectivityStatus.NOT_ASSESSED
    assert terminal.connectivity_node_ref is None


def test_operational_value_requires_exactly_one_value_field() -> None:
    with pytest.raises(ValueError):
        OperationalValue(
            **TRACE,
            series_id=CanonicalId("operational-series:one"),
            timestamp=None,
            offset_seconds=None,
            sequence_no=None,
            decimal_value=None,
            boolean_value=None,
            category_value=None,
            quality=DataQuality.TIME_UNKNOWN,
        )


def test_record_field_sets_match_canonical_spec() -> None:
    trace = {
        "record_origin",
        "source_record_ref",
        "source_mapping_id",
        "source_mapping_version",
    }
    expected_fields = {
        Dataset: trace
        | {
            "dataset_id",
            "name",
            "source_uri",
            "source_checksum",
            "canonical_spec_version",
            "imported_at",
            "import_status",
        },
        GridCase: trace | {"case_id", "dataset_id", "source_case_key", "feeder_ref"},
        Station: trace
        | {
            "station_id",
            "case_id",
            "source_id",
            "identity_status",
            "station_type",
            "name",
            "nominal_voltage_kv",
            "longitude",
            "latitude",
            "coordinate_crs",
        },
        Feeder: trace
        | {
            "feeder_id",
            "case_id",
            "source_id",
            "identity_status",
            "name",
            "source_bus_source_ref",
        },
        Bus: trace
        | {
            "bus_id",
            "case_id",
            "source_id",
            "identity_status",
            "name",
            "base_voltage_kv",
            "phases",
            "station_source_ref",
            "is_source",
        },
        Equipment: trace
        | {
            "equipment_id",
            "case_id",
            "source_id",
            "equipment_type",
            "name",
            "phases",
            "in_service",
            "identity_status",
        },
        Terminal: trace
        | {
            "terminal_id",
            "case_id",
            "equipment_id",
            "terminal_no",
            "raw_connected_ref",
            "resolved_source_ref",
            "source_ref_status",
            "connectivity_node_ref",
            "connectivity_status",
            "phases",
        },
        Line: trace
        | {
            "equipment_id",
            "line_type",
            "model",
            "length_km",
            "r1_ohm_per_km",
            "x1_ohm_per_km",
            "r0_ohm_per_km",
            "x0_ohm_per_km",
            "c1_nf_per_km",
            "c0_nf_per_km",
            "rated_current_a",
            "number_of_circuits",
            "parameter_set_ref",
        },
        SwitchingDevice: trace
        | {
            "equipment_id",
            "switch_kind",
            "normal_state",
            "observed_state",
            "is_tie",
            "rated_current_a",
            "measurement_capable",
        },
        Transformer: trace
        | {
            "equipment_id",
            "rated_capacity_kva",
            "r_pct",
            "x_pct",
            "number_of_taps",
            "tap_min_pu",
            "tap_max_pu",
            "tap_range_raw",
        },
        TransformerWinding: trace
        | {
            "winding_id",
            "equipment_id",
            "winding_no",
            "terminal_id",
            "rated_voltage_kv",
            "connection",
            "rated_capacity_kva",
        },
        AccessPoint: trace | {"equipment_id", "user_type", "contract_capacity_kva"},
        Load: trace
        | {
            "equipment_id",
            "active_power_kw",
            "reactive_power_kvar",
            "power_factor",
            "power_factor_mode",
            "connection",
            "load_model",
            "nominal_voltage_kv",
        },
        DER: trace
        | {
            "equipment_id",
            "der_type",
            "rated_capacity_kva",
            "rated_power_kw",
            "power_factor",
            "connection",
            "control_mode",
            "nominal_voltage_kv",
        },
        OperationalSeries: trace
        | {
            "series_id",
            "scenario_id",
            "target_ref",
            "metric",
            "unit",
            "phase",
            "series_kind",
            "value_type",
            "interval_seconds",
            "quality",
        },
        OperationalValue: trace
        | {
            "series_id",
            "timestamp",
            "offset_seconds",
            "sequence_no",
            "decimal_value",
            "boolean_value",
            "category_value",
            "quality",
        },
        SimulationProfile: trace
        | {
            "simulation_profile_id",
            "case_id",
            "scenario_id",
            "mode",
            "solver",
            "frequency_hz",
            "source_voltage_kv",
            "source_bus_source_ref",
            "output_voltage_bus_source_ref",
            "max_iterations",
            "tolerance",
            "mva_sc3",
            "mva_sc1",
            "unit_system",
            "extensions",
        },
        DataQualityIssue: trace
        | {
            "issue_id",
            "case_id",
            "target_ref",
            "field_path",
            "code",
            "severity",
            "observed_value",
            "message",
        },
        FieldProvenance: trace
        | {
            "provenance_id",
            "case_id",
            "target_ref",
            "field_path",
            "origin",
            "source_field",
            "rule_id",
            "rule_version",
            "config_ref",
            "random_seed",
            "assumption",
            "changed_by",
        },
    }

    assert {
        record_type: {field.name for field in fields(record_type)}
        for record_type in expected_fields
    } == expected_fields
