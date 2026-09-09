import random

import pytest

from grid_case_generator.models.records import Bus
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
from grid_case_generator.validation.reference_resolution import (
    ReferenceCandidate,
    ReferenceResolutionRequest,
    build_reference_candidate_index,
    resolve_source_reference,
)


CASE_A = CanonicalId("case-a")
CASE_B = CanonicalId("case-b")


def _entity_type(source_entity_type: SourceEntityType) -> Identifier:
    if source_entity_type in {
        SourceEntityType.STATION,
        SourceEntityType.FEEDER,
        SourceEntityType.BUS,
    }:
        return Identifier(source_entity_type.value)
    return Identifier("EQUIPMENT")


def _candidate(
    source_id: str,
    *,
    source_entity_type: SourceEntityType = SourceEntityType.BUS,
    case_id: CanonicalId = CASE_A,
    identity_status: IdentityStatus = IdentityStatus.UNIQUE,
    row: int = 1,
) -> ReferenceCandidate:
    entity_ref = EntityRef(
        entity_type=_entity_type(source_entity_type),
        entity_id=CanonicalId(
            f"{source_entity_type.value.lower()}:{case_id}:{source_id}:{row}"
        ),
    )
    return ReferenceCandidate(
        case_id=case_id,
        candidate_source_entity_type=source_entity_type,
        source_id=SourceId(source_id),
        source_record_ref=(
            f"zip-member:case/{source_entity_type.value}.csv#data-row={row}"
        ),
        identity_status=identity_status,
        entity_ref=entity_ref,
    )


def _request(
    raw_reference_value: str,
    *,
    case_id: CanonicalId = CASE_A,
    allowed_types: tuple[SourceEntityType, ...] = (SourceEntityType.BUS,),
) -> ReferenceResolutionRequest:
    return ReferenceResolutionRequest(
        case_id=case_id,
        owner_source_entity_type=Identifier("FEEDER"),
        owner_source_id=SourceId("owner-1"),
        owner_source_record_ref="zip-member:case/05_Feeder.csv#data-row=1",
        reference_field_path="feeder.source_bus_source_ref",
        raw_reference_value=raw_reference_value,
        allowed_candidate_source_entity_types=allowed_types,
    )


def test_empty_reference_is_missing_without_candidates_or_issue() -> None:
    candidate = _candidate("bus-1")
    result = resolve_source_reference(
        build_reference_candidate_index((candidate,)),
        _request(""),
    )

    assert result.resolution_status is SourceReferenceStatus.MISSING
    assert result.candidates == ()
    assert result.resolved_ref is None
    assert not hasattr(result, "issue")


def test_unique_candidate_is_exact_and_reuses_existing_entity_ref() -> None:
    candidate = _candidate("bus-1")
    result = resolve_source_reference(
        build_reference_candidate_index((candidate,)),
        _request("bus-1"),
    )

    assert result.resolution_status is SourceReferenceStatus.EXACT
    assert result.candidates == (candidate,)
    assert result.resolved_ref is candidate.entity_ref


def test_nonempty_reference_without_candidate_is_unresolved() -> None:
    result = resolve_source_reference(
        build_reference_candidate_index(()),
        _request("missing-bus"),
    )

    assert result.resolution_status is SourceReferenceStatus.UNRESOLVED
    assert result.candidates == ()
    assert result.resolved_ref is None


def test_multiple_candidates_are_ambiguous_and_none_is_selected() -> None:
    first = _candidate("bus-1", row=2)
    second = _candidate("bus-1", row=1)
    result = resolve_source_reference(
        build_reference_candidate_index((first, second)),
        _request("bus-1"),
    )

    assert result.resolution_status is SourceReferenceStatus.AMBIGUOUS
    assert result.candidates == (second, first)
    assert result.resolved_ref is None


def test_single_duplicate_identical_candidate_is_ambiguous() -> None:
    candidate = _candidate(
        "bus-1", identity_status=IdentityStatus.DUPLICATE_IDENTICAL
    )
    result = resolve_source_reference(
        build_reference_candidate_index((candidate,)),
        _request("bus-1"),
    )

    assert result.resolution_status is SourceReferenceStatus.AMBIGUOUS
    assert result.candidates == (candidate,)
    assert result.resolved_ref is None


def test_single_duplicate_conflict_candidate_is_ambiguous() -> None:
    candidate = _candidate(
        "bus-1", identity_status=IdentityStatus.DUPLICATE_CONFLICT
    )
    result = resolve_source_reference(
        build_reference_candidate_index((candidate,)),
        _request("bus-1"),
    )

    assert result.resolution_status is SourceReferenceStatus.AMBIGUOUS
    assert result.candidates == (candidate,)
    assert result.resolved_ref is None


def test_candidate_lookup_is_isolated_by_case() -> None:
    other_case_candidate = _candidate("bus-1", case_id=CASE_B)
    result = resolve_source_reference(
        build_reference_candidate_index((other_case_candidate,)),
        _request("bus-1", case_id=CASE_A),
    )

    assert result.resolution_status is SourceReferenceStatus.UNRESOLVED
    assert result.candidates == ()


def test_candidate_lookup_is_isolated_by_concrete_source_entity_type() -> None:
    station = _candidate("shared", source_entity_type=SourceEntityType.STATION)
    line = _candidate("shared", source_entity_type=SourceEntityType.LINE)
    result = resolve_source_reference(
        build_reference_candidate_index((station, line)),
        _request("shared", allowed_types=(SourceEntityType.SWITCH,)),
    )

    assert result.resolution_status is SourceReferenceStatus.UNRESOLVED
    assert result.candidates == ()


def test_reference_strings_are_not_normalized() -> None:
    candidates = tuple(
        _candidate(value, row=row)
        for row, value in enumerate(("001", "1", "1e0"), start=1)
    )
    index = build_reference_candidate_index(candidates)

    results = tuple(
        resolve_source_reference(index, _request(value))
        for value in ("001", "1", "1e0")
    )

    assert tuple(result.resolved_ref for result in results) == tuple(
        candidate.entity_ref for candidate in candidates
    )


def test_candidate_and_allowed_type_order_do_not_change_resolution() -> None:
    bus = _candidate("shared", source_entity_type=SourceEntityType.BUS, row=2)
    station = _candidate(
        "shared", source_entity_type=SourceEntityType.STATION, row=1
    )
    forward = resolve_source_reference(
        build_reference_candidate_index((bus, station)),
        _request(
            "shared",
            allowed_types=(SourceEntityType.BUS, SourceEntityType.STATION),
        ),
    )
    reverse = resolve_source_reference(
        build_reference_candidate_index((station, bus)),
        _request(
            "shared",
            allowed_types=(SourceEntityType.STATION, SourceEntityType.BUS),
        ),
    )

    assert forward.resolution_status is reverse.resolution_status
    assert forward.candidates == reverse.candidates
    assert forward.resolved_ref == reverse.resolved_ref


def test_mixed_source_type_index_order_is_deterministic() -> None:
    candidates = (
        _candidate(
            "transformer-1",
            source_entity_type=SourceEntityType.TRANSFORMER,
            case_id=CASE_B,
            row=2,
        ),
        _candidate("station-1", source_entity_type=SourceEntityType.STATION),
        _candidate("line-1", source_entity_type=SourceEntityType.LINE),
        _candidate("bus-1", source_entity_type=SourceEntityType.BUS),
        _candidate("switch-1", source_entity_type=SourceEntityType.SWITCH),
        _candidate(
            "access-point-1",
            source_entity_type=SourceEntityType.ACCESS_POINT,
        ),
    )
    expected_keys = tuple(
        sorted(
            (
                (
                    candidate.case_id,
                    candidate.candidate_source_entity_type,
                    candidate.source_id,
                )
                for candidate in candidates
            ),
            key=lambda key: (key[0], key[1].value, key[2]),
        )
    )

    indexes = []
    for seed in range(10):
        shuffled = list(candidates)
        random.Random(seed).shuffle(shuffled)
        indexes.append(build_reference_candidate_index(shuffled))

    assert all(index.entries == indexes[0].entries for index in indexes)
    assert tuple(key for key, _ in indexes[0].entries) == expected_keys


def test_reference_candidate_rejects_empty_source_id() -> None:
    empty_source_id = str.__new__(SourceId, "")

    with pytest.raises(ValueError, match="source_id must be non-empty"):
        ReferenceCandidate(
            case_id=CASE_A,
            candidate_source_entity_type=SourceEntityType.BUS,
            source_id=empty_source_id,
            source_record_ref="zip-member:case/02_Bus.csv#data-row=1",
            identity_status=IdentityStatus.UNIQUE,
            entity_ref=EntityRef(
                entity_type=Identifier("BUS"),
                entity_id=CanonicalId("bus:existing"),
            ),
        )


def test_resolver_is_pure_and_returns_no_issue_or_connectivity() -> None:
    bus = Bus(
        record_origin=RecordOrigin.SOURCE,
        source_record_ref="zip-member:case/02_Bus.csv#data-row=1",
        source_mapping_id="nanjing_csv",
        source_mapping_version="0.2.0",
        bus_id=CanonicalId("bus:existing"),
        case_id=CASE_A,
        source_id=SourceId("bus-1"),
        identity_status=IdentityStatus.UNIQUE,
        name=None,
        base_voltage_kv=None,
        phases=None,
        station_source_ref=None,
        is_source=None,
    )
    candidate = ReferenceCandidate(
        case_id=bus.case_id,
        candidate_source_entity_type=SourceEntityType.BUS,
        source_id=bus.source_id,
        source_record_ref=bus.source_record_ref,
        identity_status=bus.identity_status,
        entity_ref=EntityRef(
            entity_type=Identifier("BUS"), entity_id=bus.bus_id
        ),
    )
    request = _request("bus-1")
    index = build_reference_candidate_index((candidate,))
    before = (bus, candidate, request, index)

    result = resolve_source_reference(index, request)

    assert (bus, candidate, request, index) == before
    assert result.resolved_ref is candidate.entity_ref
    assert not hasattr(result, "issue")
    assert not hasattr(result, "connectivity_status")
    assert not hasattr(result, "topology")
