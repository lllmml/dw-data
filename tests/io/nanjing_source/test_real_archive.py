from hashlib import sha256
from pathlib import Path

import pytest

from grid_case_generator.io.nanjing_source.archive import inventory_archive


EXPECTED_SHA256 = "7ae1e246e5ac8073053d280cd64e66cdc491d5303dc2c15aa74f823be202de25"
ARCHIVE_PATH = Path(__file__).parents[3] / "data" / "raw" / "南京数据.zip"


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@pytest.mark.skipif(
    not ARCHIVE_PATH.is_file(), reason="real Nanjing archive unavailable"
)
def test_real_nanjing_archive_inventory_is_complete_and_read_only() -> None:
    before_stat = ARCHIVE_PATH.stat()
    before_digest = _sha256(ARCHIVE_PATH)

    assert before_digest == EXPECTED_SHA256
    inventory = inventory_archive(ARCHIVE_PATH)

    assert len(inventory.cases) == 5_159
    assert inventory.csv_member_count == 61_908
    assert all(case.is_complete for case in inventory.cases)
    assert inventory.diagnostics == ()

    after_stat = ARCHIVE_PATH.stat()
    assert (after_stat.st_size, after_stat.st_mtime_ns) == (
        before_stat.st_size,
        before_stat.st_mtime_ns,
    )
    assert _sha256(ARCHIVE_PATH) == before_digest
