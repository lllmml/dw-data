import json
from decimal import Decimal

import pytest

from grid_case_generator.io.canonical_json import canonical_json_bytes, to_canonical_data
from grid_case_generator.models.records import Station
from grid_case_generator.models.types import (
    CanonicalId,
    EntityRef,
    Identifier,
    IdentityStatus,
    RecordOrigin,
    SourceId,
    SourceReference,
    SourceReferenceStatus,
)


def test_canonical_json_serializes_dataclass_enum_decimal_reference_and_null() -> None:
    station = Station(
        record_origin=RecordOrigin.SOURCE,
        source_record_ref="zip-member:%E6%95%B0%E6%8D%AE/01_Station.csv#data-row=1",
        source_mapping_id="nanjing_csv",
        source_mapping_version="0.2.0",
        station_id=CanonicalId("station:one"),
        case_id=CanonicalId("case:one"),
        source_id=SourceId("001"),
        identity_status=IdentityStatus.UNIQUE,
        station_type=None,
        name="南京站",
        nominal_voltage_kv=Decimal("10.500000000000000001"),
        longitude=None,
        latitude=None,
        coordinate_crs=None,
    )

    encoded = canonical_json_bytes(station)
    decoded = json.loads(encoded)

    assert decoded["station_id"] == "station:one"
    assert decoded["source_id"] == "001"
    assert decoded["identity_status"] == "UNIQUE"
    assert decoded["nominal_voltage_kv"] == "10.500000000000000001"
    assert decoded["longitude"] is None
    assert "南京站".encode() in encoded
    assert canonical_json_bytes(station) == encoded


def test_nested_source_reference_is_serialized_as_an_object() -> None:
    reference = SourceReference(
        raw_ref=SourceId("bus_01_bs"),
        resolved_source_ref=EntityRef(
            entity_type=Identifier("BUS"), entity_id=CanonicalId("bus:one")
        ),
        resolution_status=SourceReferenceStatus.EXACT,
    )

    assert to_canonical_data(reference) == {
        "raw_ref": "bus_01_bs",
        "resolved_source_ref": {"entity_type": "BUS", "entity_id": "bus:one"},
        "resolution_status": "EXACT",
    }


def test_canonical_json_has_deterministic_key_order() -> None:
    left = {"z": Decimal("2.0"), "a": SourceId("001")}
    right = {"a": SourceId("001"), "z": Decimal("2.0")}

    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert canonical_json_bytes(left) == b'{"a":"001","z":"2.0"}'


@pytest.mark.parametrize("value", [1.0, float("nan"), float("inf"), float("-inf")])
def test_canonical_json_rejects_all_floats(value: float) -> None:
    with pytest.raises(TypeError):
        canonical_json_bytes({"value": value})


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_canonical_json_rejects_non_finite_decimals(value: Decimal) -> None:
    with pytest.raises(TypeError):
        canonical_json_bytes({"value": value})
