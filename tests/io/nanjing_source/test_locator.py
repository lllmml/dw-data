import pytest

from grid_case_generator.io.nanjing_source.locator import (
    UnsafeZipMemberPath,
    source_record_ref,
    validate_zip_member_path,
)


@pytest.mark.parametrize(
    "member_path",
    [
        "/absolute/01_Station.csv",
        "\\absolute\\01_Station.csv",
        "C:/absolute/01_Station.csv",
        "../01_Station.csv",
        "case/../01_Station.csv",
        "case\\..\\01_Station.csv",
    ],
)
def test_unsafe_archive_member_paths_are_rejected(member_path: str) -> None:
    with pytest.raises(UnsafeZipMemberPath):
        validate_zip_member_path(member_path)


def test_parent_like_but_non_parent_segment_is_allowed() -> None:
    assert validate_zip_member_path("data/case..name/01_Station.csv") is None


def test_locator_uses_exact_rfc3986_percent_encoding() -> None:
    locator = source_record_ref("数据/馈线 space/%#?/01_Station.csv", data_row=2)

    assert locator == (
        "zip-member:%E6%95%B0%E6%8D%AE/"
        "%E9%A6%88%E7%BA%BF%20space/%25%23%3F/01_Station.csv#data-row=2"
    )


@pytest.mark.parametrize("data_row", [0, -1, True])
def test_locator_requires_positive_integer_logical_data_row(data_row: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        source_record_ref("data/case/01_Station.csv", data_row=data_row)
