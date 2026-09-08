from grid_case_generator.models.types import (
    CanonicalId,
    IdentityStatus,
    SourceId,
)
from grid_case_generator.validation.identity import (
    SourceEntityType,
    SourceIdentityRecord,
    classify_source_identities,
)


CASE_ID = CanonicalId("case-1")
OTHER_CASE_ID = CanonicalId("case-2")


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
    return classify_source_identities(records)


def test_identical_duplicates_keep_every_record() -> None:
    fields = (("Station_ID", "001"), ("Station_Name", "原名"))
    first = _record(source_id="001", data_row=1, decoded_fields=fields)
    second = _record(source_id="001", data_row=2, decoded_fields=fields)

    results = _classify(first, second)

    assert len(results) == 2
    assert tuple(result.record for result in results) == (first, second)
    assert {result.identity_status for result in results} == {
        IdentityStatus.DUPLICATE_IDENTICAL
    }
    assert all(not hasattr(result, "issue") for result in results)


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


def test_classification_is_independent_of_input_order() -> None:
    fields = (("Station_ID", "station-1"), ("Station_Name", "name"))
    first = _record(source_id="station-1", data_row=2, decoded_fields=fields)
    second = _record(source_id="station-1", data_row=1, decoded_fields=fields)

    forward = _classify(first, second)
    reverse = _classify(second, first)

    assert forward == reverse
    assert [result.record.source_record_ref for result in forward] == sorted(
        [first.source_record_ref, second.source_record_ref]
    )


def test_repeated_locator_is_not_rejected_or_used_for_classification() -> None:
    first = _record(
        source_id="line-01",
        data_row=1,
        decoded_fields=(("Line_ID", "line-01"), ("Line_Length_km", "1")),
        source_entity_type=SourceEntityType.LINE,
        member="data/case/08_Line.csv",
    )
    second = _record(
        source_id="line-01",
        data_row=1,
        decoded_fields=(("Line_ID", "line-01"), ("Line_Length_km", "2")),
        source_entity_type=SourceEntityType.LINE,
        member="data/case/08_Line.csv",
    )

    forward = _classify(first, second)
    reverse = _classify(second, first)

    assert len(forward) == 2
    assert forward == reverse
    assert all(
        result.identity_status is IdentityStatus.DUPLICATE_CONFLICT
        for result in forward
    )
