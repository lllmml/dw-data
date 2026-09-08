from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from grid_case_generator.io.nanjing_source.archive import inventory_archive
from grid_case_generator.io.nanjing_source.locator import UnsafeZipMemberPath
from grid_case_generator.io.nanjing_source.models import IntakeDiagnosticCode
from grid_case_generator.io.nanjing_source.schema import NANJING_SOURCE_SCHEMA


def _write_case(
    archive_path: Path, source_case_key: str, *, omit_filename: str | None = None
) -> None:
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for schema in NANJING_SOURCE_SCHEMA.files:
            if schema.filename == omit_filename:
                continue
            archive.writestr(
                f"{source_case_key}/{schema.filename}",
                "\ufeff" + ",".join(schema.header) + "\r\n",
            )


def test_inventory_discovers_case_from_exact_expected_file_positions(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "source.zip"
    source_case_key = "数据/001 馈线%#?"
    _write_case(archive_path, source_case_key)

    inventory = inventory_archive(archive_path)

    assert inventory.csv_member_count == 12
    assert inventory.member_count == 12
    assert len(inventory.cases) == 1
    case = inventory.cases[0]
    assert case.source_case_key == source_case_key
    assert case.is_complete
    assert case.missing_file_types == ()
    assert case.member_for(NANJING_SOURCE_SCHEMA.files[0].file_type) == (
        f"{source_case_key}/01_Station.csv"
    )
    assert inventory.diagnostics == ()


def test_inventory_reports_missing_expected_file(tmp_path: Path) -> None:
    archive_path = tmp_path / "source.zip"
    _write_case(archive_path, "data/case", omit_filename="05_Feeder.csv")

    inventory = inventory_archive(archive_path)

    case = inventory.cases[0]
    assert not case.is_complete
    assert tuple(file_type.value for file_type in case.missing_file_types) == (
        "FEEDER",
    )
    assert len(inventory.diagnostics) == 1
    diagnostic = inventory.diagnostics[0]
    assert diagnostic.code is IntakeDiagnosticCode.SOURCE_FILE_MISSING
    assert diagnostic.source_case_key == "data/case"
    assert diagnostic.member_path == "data/case/05_Feeder.csv"
    assert diagnostic.source_record_ref is None


@pytest.mark.parametrize(
    "unsafe_name", ["/data/01_Station.csv", "data/../01_Station.csv"]
)
def test_inventory_rejects_unsafe_member_before_discovery(
    tmp_path: Path, unsafe_name: str
) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(unsafe_name, "value")

    with pytest.raises(UnsafeZipMemberPath):
        inventory_archive(archive_path)
