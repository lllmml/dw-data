from grid_case_generator.models.identifiers import SourceImportIdFactory
from grid_case_generator.models.quality import QualityIssueCode
from grid_case_generator.models.types import (
    CanonicalId,
    EntityRef,
    EquipmentType,
    Identifier,
    IdentityStatus,
    Severity,
    SourceId,
)
from grid_case_generator.validation.identity import (
    SourceEntityType,
    SourceIdentityRecord,
    classify_source_identities,
)


DATASET_ID = SourceImportIdFactory.dataset_id("a" * 64)
CASE_ID = SourceImportIdFactory.case_id(DATASET_ID, "data/case")
OTHER_CASE_ID = SourceImportIdFactory.case_id(DATASET_ID, "data/other-case")


def _record(
    *,
    source_id: str,
    data_row: int,
    decoded_fields: tuple[tuple[str, str], ...],
    source_entity_type: SourceEntityType = SourceEntityType.STATION,
    case_id: CanonicalId = CASE_ID,
    member: str = "data/case/01_Station.csv",
) -> SourceIdentityRecord:
    return SourceIdentityRecord(
        case_id=case_id,
        source_entity_type=source_entity_type,
        source_id=SourceId(source_id),
        source_record_ref=f"zip-member:{member}#data-row={data_row}",
        decoded_fields=decoded_fields,
    )


def _classify(*records: SourceIdentityRecord):
    return classify_source_identities(
        records,
        dataset_id=DATASET_ID,
        source_mapping_id="nanjing_csv",
        source_mapping_version="0.2.0",
    )


def test_identical_duplicates_keep_every_record_and_create_warning_issues() -> None:
    fields = (("Station_ID", "001"), ("Station_Name", "原名"))
    first = _record(source_id="001", data_row=1, decoded_fields=fields)
    second = _record(source_id="001", data_row=2, decoded_fields=fields)

    results = _classify(first, second)

    assert len(results) == 2
    assert tuple(result.record for result in results) == (first, second)
    assert {result.identity_status for result in results} == {
        IdentityStatus.DUPLICATE_IDENTICAL
    }
    assert all(result.issue is not None for result in results)
    assert {result.issue.code for result in results if result.issue} == {
        QualityIssueCode.SOURCE_ID_DUPLICATE_IDENTICAL
    }
    assert {result.issue.severity for result in results if result.issue} == {
        Severity.WARNING
    }
    assert len({result.issue.issue_id for result in results if result.issue}) == 2


def test_any_field_difference_marks_the_entire_group_conflicting() -> None:
    first = _record(
        source_id="switch-1",
        data_row=1,
        source_entity_type=SourceEntityType.SWITCH,
        decoded_fields=(("Switch_ID", "switch-1"), ("Switch_ToBus", "bus-1")),
        member="data/case/03_Switch.csv",
    )
    second = _record(
        source_id="switch-1",
        data_row=2,
        source_entity_type=SourceEntityType.SWITCH,
        decoded_fields=(("Switch_ID", "switch-1"), ("Switch_ToBus", "bus-2")),
        member="data/case/03_Switch.csv",
    )

    results = _classify(first, second)

    assert len(results) == 2
    assert {result.identity_status for result in results} == {
        IdentityStatus.DUPLICATE_CONFLICT
    }
    assert {result.issue.code for result in results if result.issue} == {
        QualityIssueCode.SOURCE_ID_DUPLICATE_CONFLICT
    }
    assert {result.issue.severity for result in results if result.issue} == {
        Severity.ERROR
    }


def test_locator_path_and_row_do_not_affect_duplicate_comparison() -> None:
    fields = (("Feeder_ID", "0007"), ("Feeder_Name", "A"))
    first = _record(
        source_id="0007",
        data_row=1,
        decoded_fields=fields,
        source_entity_type=SourceEntityType.FEEDER,
        member="data/case/05_Feeder.csv",
    )
    second = _record(
        source_id="0007",
        data_row=99,
        decoded_fields=fields,
        source_entity_type=SourceEntityType.FEEDER,
        member="data/case/copy/05_Feeder.csv",
    )

    results = _classify(first, second)

    assert all(
        result.identity_status is IdentityStatus.DUPLICATE_IDENTICAL
        for result in results
    )


def test_source_ids_keep_leading_zero_and_large_identifier_semantics() -> None:
    records = (
        _record(
            source_id="001",
            data_row=1,
            decoded_fields=(("Bus_ID", "001"),),
            source_entity_type=SourceEntityType.BUS,
            member="data/case/02_Bus.csv",
        ),
        _record(
            source_id="1",
            data_row=2,
            decoded_fields=(("Bus_ID", "1"),),
            source_entity_type=SourceEntityType.BUS,
            member="data/case/02_Bus.csv",
        ),
        _record(
            source_id="1234567890123456789",
            data_row=3,
            decoded_fields=(("Bus_ID", "1234567890123456789"),),
            source_entity_type=SourceEntityType.BUS,
            member="data/case/02_Bus.csv",
        ),
    )

    results = _classify(*records)

    assert tuple(result.record.source_id for result in results) == (
        SourceId("001"),
        SourceId("1"),
        SourceId("1234567890123456789"),
    )
    assert all(result.identity_status is IdentityStatus.UNIQUE for result in results)
    assert all(result.issue is None for result in results)


def test_case_and_concrete_source_entity_type_are_part_of_group_key() -> None:
    fields = (("ID", "same-id"),)
    records = (
        _record(source_id="same-id", data_row=1, decoded_fields=fields),
        _record(
            source_id="same-id",
            data_row=1,
            decoded_fields=fields,
            case_id=OTHER_CASE_ID,
            member="data/other-case/01_Station.csv",
        ),
        _record(
            source_id="same-id",
            data_row=1,
            decoded_fields=fields,
            source_entity_type=SourceEntityType.LINE,
            member="data/case/08_Line.csv",
        ),
        _record(
            source_id="same-id",
            data_row=1,
            decoded_fields=fields,
            source_entity_type=SourceEntityType.SWITCH,
            member="data/case/03_Switch.csv",
        ),
    )

    results = _classify(*records)

    assert len(results) == 4
    assert all(result.identity_status is IdentityStatus.UNIQUE for result in results)


def test_classification_and_issue_ids_are_independent_of_input_order() -> None:
    fields = (("Station_ID", "station-1"), ("Station_Name", "name"))
    first = _record(source_id="station-1", data_row=2, decoded_fields=fields)
    second = _record(source_id="station-1", data_row=1, decoded_fields=fields)

    forward = _classify(first, second)
    reverse = _classify(second, first)

    assert forward == reverse
    assert [result.record.source_record_ref for result in forward] == sorted(
        [first.source_record_ref, second.source_record_ref]
    )


def test_duplicate_issue_uses_existing_id_factory_for_canonical_target_and_issue(
) -> None:
    fields = (("Line_ID", "line-01"), ("Line_Length_km", ""))
    first = _record(
        source_id="line-01",
        data_row=1,
        decoded_fields=fields,
        source_entity_type=SourceEntityType.LINE,
        member="data/case/08_Line.csv",
    )
    second = _record(
        source_id="line-01",
        data_row=2,
        decoded_fields=fields,
        source_entity_type=SourceEntityType.LINE,
        member="data/case/08_Line.csv",
    )

    result = _classify(first, second)[0]
    expected_equipment_id = SourceImportIdFactory.equipment_id(
        CASE_ID,
        EquipmentType.LINE,
        SourceId("line-01"),
        result.record.source_record_ref,
    )
    expected_target = EntityRef(
        entity_type=Identifier("EQUIPMENT"),
        entity_id=expected_equipment_id,
    )
    expected_issue_id = SourceImportIdFactory.quality_issue_id(
        DATASET_ID,
        CASE_ID,
        expected_target,
        "identity_status",
        QualityIssueCode.SOURCE_ID_DUPLICATE_IDENTICAL,
        result.record.source_record_ref,
        "",
    )

    assert result.issue is not None
    assert result.issue.target_ref == expected_target
    assert result.issue.issue_id == expected_issue_id
    assert result.issue.source_mapping_id == "nanjing_csv"
    assert result.issue.source_mapping_version == "0.2.0"


def test_bus_duplicate_issue_targets_factory_generated_bus_id() -> None:
    fields = (("Bus_ID", "bus-01"), ("Bus_Name", ""))
    first = _record(
        source_id="bus-01",
        data_row=1,
        decoded_fields=fields,
        source_entity_type=SourceEntityType.BUS,
        member="data/case/02_Bus.csv",
    )
    second = _record(
        source_id="bus-01",
        data_row=2,
        decoded_fields=fields,
        source_entity_type=SourceEntityType.BUS,
        member="data/case/02_Bus.csv",
    )

    result = _classify(first, second)[0]
    expected_target = EntityRef(
        entity_type=Identifier("BUS"),
        entity_id=SourceImportIdFactory.bus_id(
            CASE_ID,
            SourceId("bus-01"),
            result.record.source_record_ref,
        ),
    )

    assert result.issue is not None
    assert result.issue.target_ref == expected_target
