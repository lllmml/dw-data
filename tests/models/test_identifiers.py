import hashlib
import json
import unicodedata

import pytest

from grid_case_generator.models.identifiers import SourceImportIdFactory
from grid_case_generator.models.records import DataQualityIssue, Dataset, Station
from grid_case_generator.models.types import (
    CanonicalId,
    EntityRef,
    EquipmentType,
    Identifier,
    IdentityStatus,
    ImportStatus,
    RecordOrigin,
    Severity,
    SourceId,
)
from grid_case_generator.validation.quality import QualityIssueCode


CHECKSUM = "a" * 64
DATASET_ID = SourceImportIdFactory.dataset_id(CHECKSUM)
CASE_ID = SourceImportIdFactory.case_id(DATASET_ID, "数据/馈线-001")
SOURCE_REF = "zip-member:%E6%95%B0%E6%8D%AE/03_Switch.csv#data-row=1"
TARGET_REF = EntityRef(entity_type=Identifier("EQUIPMENT"), entity_id=CanonicalId("equipment:x"))


def expected_id(kind: str, *parts: object) -> str:
    payload = json.dumps(
        ["source-import-id-v1", kind, *parts],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{kind}:{hashlib.sha256(payload).hexdigest()}"


def test_dataset_id_uses_only_lowercase_source_artifact_checksum() -> None:
    assert DATASET_ID == expected_id("dataset", f"sha256:{CHECKSUM}")
    assert SourceImportIdFactory.dataset_id(CHECKSUM.upper()) == DATASET_ID


def test_case_id_matches_contract() -> None:
    assert CASE_ID == expected_id("case", DATASET_ID, "数据/馈线-001")


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        (
            SourceImportIdFactory.station_id(
                CASE_ID, SourceId("001"), SOURCE_REF
            ),
            expected_id("station", CASE_ID, "STATION", "001", SOURCE_REF),
        ),
        (
            SourceImportIdFactory.feeder_id(
                CASE_ID, SourceId("1234567890123456789"), SOURCE_REF
            ),
            expected_id(
                "feeder", CASE_ID, "FEEDER", "1234567890123456789", SOURCE_REF
            ),
        ),
        (
            SourceImportIdFactory.bus_id(
                CASE_ID, SourceId("bus_01_bs"), SOURCE_REF
            ),
            expected_id("bus", CASE_ID, "BUS", "bus_01_bs", SOURCE_REF),
        ),
        (
            SourceImportIdFactory.equipment_id(
                CASE_ID,
                EquipmentType.SWITCH,
                SourceId("1.13997365584593e+17"),
                SOURCE_REF,
            ),
            expected_id(
                "equipment",
                CASE_ID,
                "SWITCH",
                "1.13997365584593e+17",
                SOURCE_REF,
            ),
        ),
        (
            SourceImportIdFactory.terminal_id(CanonicalId("equipment:x"), 2),
            expected_id("terminal", "equipment:x", 2),
        ),
        (
            SourceImportIdFactory.winding_id(CanonicalId("equipment:x"), 1),
            expected_id("winding", "equipment:x", 1),
        ),
        (
            SourceImportIdFactory.simulation_profile_id(CASE_ID),
            expected_id("simulation-profile", CASE_ID, "source_sim_config"),
        ),
        (
            SourceImportIdFactory.operational_series_id(
                CASE_ID, TARGET_REF, SOURCE_REF, "Switch_Meas_I_A"
            ),
            expected_id(
                "operational-series",
                CASE_ID,
                "EQUIPMENT",
                "equipment:x",
                SOURCE_REF,
                "Switch_Meas_I_A",
            ),
        ),
        (
            SourceImportIdFactory.field_provenance_id(
                TARGET_REF,
                "simulation_profile.frequency_hz",
                RecordOrigin.SOURCE,
                SOURCE_REF,
                "Config_Value",
                "nanjing_csv",
                "0.2.0",
            ),
            expected_id(
                "field-provenance",
                "EQUIPMENT",
                "equipment:x",
                "simulation_profile.frequency_hz",
                "SOURCE",
                SOURCE_REF,
                "Config_Value",
                "nanjing_csv",
                "0.2.0",
            ),
        ),
        (
            SourceImportIdFactory.quality_issue_id(
                DATASET_ID,
                CASE_ID,
                TARGET_REF,
                "equipment.source_id",
                QualityIssueCode.SOURCE_IDENTIFIER_SUSPICIOUS_FORMAT,
                SOURCE_REF,
                "",
            ),
            expected_id(
                "quality-issue",
                DATASET_ID,
                CASE_ID,
                "EQUIPMENT",
                "equipment:x",
                "equipment.source_id",
                "SOURCE_IDENTIFIER_SUSPICIOUS_FORMAT",
                SOURCE_REF,
                "",
            ),
        ),
    ],
)
def test_every_source_import_id_matches_the_frozen_contract(actual: str, expected: str) -> None:
    assert actual == expected


def test_each_factory_is_repeatable_and_changes_when_an_identity_input_changes() -> None:
    first = SourceImportIdFactory.station_id(CASE_ID, SourceId("001"), SOURCE_REF)
    repeated = SourceImportIdFactory.station_id(CASE_ID, SourceId("001"), SOURCE_REF)
    changed_source = SourceImportIdFactory.station_id(CASE_ID, SourceId("002"), SOURCE_REF)
    changed_record = SourceImportIdFactory.station_id(
        CASE_ID, SourceId("001"), SOURCE_REF.replace("data-row=1", "data-row=2")
    )

    assert first == repeated
    assert len({first, changed_source, changed_record}) == 3


@pytest.mark.parametrize(
    ("factory", "changed_factory"),
    [
        (
            lambda: SourceImportIdFactory.dataset_id("a" * 64),
            lambda: SourceImportIdFactory.dataset_id("b" * 64),
        ),
        (
            lambda: SourceImportIdFactory.case_id(DATASET_ID, "case-a"),
            lambda: SourceImportIdFactory.case_id(DATASET_ID, "case-b"),
        ),
        (
            lambda: SourceImportIdFactory.station_id(
                CASE_ID, SourceId("001"), SOURCE_REF
            ),
            lambda: SourceImportIdFactory.station_id(
                CASE_ID, SourceId("002"), SOURCE_REF
            ),
        ),
        (
            lambda: SourceImportIdFactory.feeder_id(
                CASE_ID, SourceId("001"), SOURCE_REF
            ),
            lambda: SourceImportIdFactory.feeder_id(
                CASE_ID, SourceId("002"), SOURCE_REF
            ),
        ),
        (
            lambda: SourceImportIdFactory.bus_id(CASE_ID, SourceId("001"), SOURCE_REF),
            lambda: SourceImportIdFactory.bus_id(CASE_ID, SourceId("002"), SOURCE_REF),
        ),
        (
            lambda: SourceImportIdFactory.equipment_id(
                CASE_ID, EquipmentType.SWITCH, SourceId("001"), SOURCE_REF
            ),
            lambda: SourceImportIdFactory.equipment_id(
                CASE_ID, EquipmentType.LINE, SourceId("001"), SOURCE_REF
            ),
        ),
        (
            lambda: SourceImportIdFactory.terminal_id(CanonicalId("equipment:x"), 1),
            lambda: SourceImportIdFactory.terminal_id(CanonicalId("equipment:x"), 2),
        ),
        (
            lambda: SourceImportIdFactory.winding_id(CanonicalId("equipment:x"), 1),
            lambda: SourceImportIdFactory.winding_id(CanonicalId("equipment:x"), 2),
        ),
        (
            lambda: SourceImportIdFactory.simulation_profile_id(CASE_ID),
            lambda: SourceImportIdFactory.simulation_profile_id(CanonicalId("case:two")),
        ),
        (
            lambda: SourceImportIdFactory.operational_series_id(
                CASE_ID, TARGET_REF, SOURCE_REF, "Switch_Meas_I_A"
            ),
            lambda: SourceImportIdFactory.operational_series_id(
                CASE_ID, TARGET_REF, SOURCE_REF, "Switch_Meas_P_kW"
            ),
        ),
        (
            lambda: SourceImportIdFactory.field_provenance_id(
                TARGET_REF,
                "field",
                RecordOrigin.SOURCE,
                SOURCE_REF,
                "Config_Value",
                "nanjing_csv",
                "0.1.0",
            ),
            lambda: SourceImportIdFactory.field_provenance_id(
                TARGET_REF,
                "field",
                RecordOrigin.SOURCE,
                SOURCE_REF,
                "Config_Value",
                "nanjing_csv",
                "0.2.0",
            ),
        ),
        (
            lambda: SourceImportIdFactory.quality_issue_id(
                DATASET_ID,
                CASE_ID,
                TARGET_REF,
                "field",
                QualityIssueCode.SOURCE_VALUE_PARSE_FAILED,
                SOURCE_REF,
                "",
            ),
            lambda: SourceImportIdFactory.quality_issue_id(
                DATASET_ID,
                CASE_ID,
                TARGET_REF,
                "field",
                QualityIssueCode.SOURCE_VALUE_PARSE_FAILED,
                SOURCE_REF,
                "second-check",
            ),
        ),
    ],
)
def test_each_id_factory_is_repeatable_and_sensitive_to_its_identity_inputs(
    factory: object, changed_factory: object
) -> None:
    build = factory  # keep parametrized callables readable in failure output
    build_changed = changed_factory
    assert callable(build)
    assert callable(build_changed)
    assert build() == build()
    assert build() != build_changed()


def test_source_text_is_not_normalized_before_hashing() -> None:
    values = [
        "001",
        "1",
        "1234567890123456789",
        "bus_01_bs",
        "1.13997365584593e+17",
        "南京",
        unicodedata.normalize("NFD", "南京é"),
        unicodedata.normalize("NFC", "南京é"),
    ]

    ids = {
        SourceImportIdFactory.bus_id(CASE_ID, SourceId(value), SOURCE_REF)
        for value in values
    }
    assert len(ids) == len(values)


def test_source_entity_id_always_includes_source_record_ref() -> None:
    row_one = SourceImportIdFactory.equipment_id(
        CASE_ID, EquipmentType.SWITCH, SourceId("duplicate"), SOURCE_REF
    )
    row_two = SourceImportIdFactory.equipment_id(
        CASE_ID,
        EquipmentType.SWITCH,
        SourceId("duplicate"),
        SOURCE_REF.replace("data-row=1", "data-row=2"),
    )

    assert row_one != row_two


def test_mapping_metadata_does_not_affect_source_identity_but_changes_provenance_id() -> None:
    station_id = SourceImportIdFactory.station_id(
        CASE_ID, SourceId("001"), SOURCE_REF
    )

    def station(mapping_version: str) -> Station:
        return Station(
            record_origin=RecordOrigin.SOURCE,
            source_record_ref=SOURCE_REF,
            source_mapping_id="nanjing_csv",
            source_mapping_version=mapping_version,
            station_id=station_id,
            case_id=CASE_ID,
            source_id=SourceId("001"),
            identity_status=IdentityStatus.UNIQUE,
            station_type=None,
            name=None,
            nominal_voltage_kv=None,
            longitude=None,
            latitude=None,
            coordinate_crs=None,
        )

    assert station("0.1.0").station_id == station("0.2.0").station_id

    version_one = SourceImportIdFactory.field_provenance_id(
        TARGET_REF,
        "field",
        RecordOrigin.SOURCE,
        SOURCE_REF,
        "source_field",
        "nanjing_csv",
        "0.1.0",
    )
    version_two = SourceImportIdFactory.field_provenance_id(
        TARGET_REF,
        "field",
        RecordOrigin.SOURCE,
        SOURCE_REF,
        "source_field",
        "nanjing_csv",
        "0.2.0",
    )

    assert version_one != version_two


def test_message_import_time_and_absolute_path_are_not_factory_inputs() -> None:
    datasets = [
        Dataset(
            record_origin=RecordOrigin.SOURCE,
            source_record_ref=None,
            source_mapping_id="nanjing_csv",
            source_mapping_version=mapping_version,
            dataset_id=DATASET_ID,
            name="dataset",
            source_uri=source_uri,
            source_checksum=f"sha256:{CHECKSUM}",
            canonical_spec_version="0.3.0",
            imported_at=imported_at,
            import_status=ImportStatus.COMPLETE,
        )
        for mapping_version, source_uri, imported_at in [
            ("0.1.0", "/first/absolute/path.zip", "2026-01-01T00:00:00+00:00"),
            ("0.2.0", "/other/absolute/path.zip", "2026-09-08T00:00:00+00:00"),
        ]
    ]
    issue_id = SourceImportIdFactory.quality_issue_id(
        DATASET_ID,
        CASE_ID,
        None,
        None,
        QualityIssueCode.SOURCE_FILE_MISSING,
        None,
        "01_Station.csv",
    )
    issues = [
        DataQualityIssue(
            record_origin=RecordOrigin.DERIVED,
            source_record_ref=None,
            source_mapping_id=None,
            source_mapping_version=None,
            issue_id=issue_id,
            case_id=CASE_ID,
            target_ref=None,
            field_path=None,
            code=QualityIssueCode.SOURCE_FILE_MISSING,
            severity=Severity.ERROR,
            observed_value=None,
            message=message,
        )
        for message in ["first wording", "revised readable wording"]
    ]

    assert datasets[0].dataset_id == datasets[1].dataset_id
    assert issues[0].issue_id == issues[1].issue_id
