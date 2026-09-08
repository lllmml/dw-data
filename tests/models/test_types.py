from decimal import Decimal

import pytest

from grid_case_generator.models.types import (
    CanonicalId,
    ConnectivityStatus,
    DataQuality,
    EntityRef,
    Identifier,
    IdentityStatus,
    ImportStatus,
    Severity,
    SourceId,
    SourceReference,
    SourceReferenceStatus,
)


@pytest.mark.parametrize(
    "value",
    [
        "00123",
        "1234567890123456789",
        "bus_01_bs",
        "1.13997365584593e+17",
        "南京母线",
        "  source-id  ",
    ],
)
def test_identifier_types_preserve_source_text(value: str) -> None:
    assert Identifier(value) == value
    assert CanonicalId(value) == value
    assert SourceId(value) == value
    assert isinstance(SourceId(value), str)


@pytest.mark.parametrize("identifier_type", [Identifier, CanonicalId, SourceId])
def test_identifier_types_reject_empty_and_non_string_values(identifier_type: type[str]) -> None:
    with pytest.raises(ValueError):
        identifier_type("")
    with pytest.raises(TypeError):
        identifier_type(123)  # type: ignore[arg-type]


def test_entity_ref_is_typed_and_immutable() -> None:
    ref = EntityRef(entity_type=Identifier("BUS"), entity_id=CanonicalId("bus:abc"))

    assert ref.entity_type == "BUS"
    assert ref.entity_id == "bus:abc"
    with pytest.raises(AttributeError):
        ref.entity_id = CanonicalId("bus:def")  # type: ignore[misc]


def test_entity_ref_rejects_untyped_values() -> None:
    with pytest.raises(TypeError):
        EntityRef(entity_type="BUS", entity_id=CanonicalId("bus:abc"))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        EntityRef(entity_type=Identifier("BUS"), entity_id="bus:abc")  # type: ignore[arg-type]


def test_source_reference_null_and_resolution_invariants() -> None:
    missing = SourceReference(
        raw_ref=None,
        resolved_source_ref=None,
        resolution_status=SourceReferenceStatus.MISSING,
    )
    exact = SourceReference(
        raw_ref=SourceId("001"),
        resolved_source_ref=EntityRef(
            entity_type=Identifier("BUS"), entity_id=CanonicalId("bus:one")
        ),
        resolution_status=SourceReferenceStatus.EXACT,
    )
    unresolved = SourceReference(
        raw_ref=SourceId("1.13997365584593e+17"),
        resolved_source_ref=None,
        resolution_status=SourceReferenceStatus.UNRESOLVED,
    )

    assert missing.raw_ref is None
    assert exact.resolved_source_ref is not None
    assert unresolved.raw_ref == "1.13997365584593e+17"

    with pytest.raises(ValueError):
        SourceReference(
            raw_ref=None,
            resolved_source_ref=None,
            resolution_status=SourceReferenceStatus.EXACT,
        )
    with pytest.raises(ValueError):
        SourceReference(
            raw_ref=SourceId("bus-1"),
            resolved_source_ref=exact.resolved_source_ref,
            resolution_status=SourceReferenceStatus.UNRESOLVED,
        )


def test_decimal_remains_decimal_and_not_float() -> None:
    value = Decimal("10.500000000000000001")

    assert isinstance(value, Decimal)
    assert str(value) == "10.500000000000000001"


def test_frozen_enum_contract_values() -> None:
    assert set(IdentityStatus) == {
        IdentityStatus.UNIQUE,
        IdentityStatus.DUPLICATE_IDENTICAL,
        IdentityStatus.DUPLICATE_CONFLICT,
    }
    assert SourceReferenceStatus.EXACT.value == "EXACT"
    assert ConnectivityStatus.NOT_ASSESSED.value == "NOT_ASSESSED"
    assert DataQuality.TIME_UNKNOWN.value == "TIME_UNKNOWN"
    assert set(Severity) == {Severity.INFO, Severity.WARNING, Severity.ERROR}
    assert set(ImportStatus) == {
        ImportStatus.COMPLETE,
        ImportStatus.INCOMPLETE,
        ImportStatus.FAILED,
    }
