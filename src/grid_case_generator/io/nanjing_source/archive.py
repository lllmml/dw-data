"""Read-only Nanjing ZIP inventory."""

from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

from .locator import validate_zip_member_path
from .models import (
    IntakeDiagnostic,
    IntakeDiagnosticCode,
    SourceCaseInventory,
    SourceDatasetInventory,
)
from .schema import NANJING_SOURCE_SCHEMA, SourceFileType, SourceSchemaRegistry


def _member_path(source_case_key: str, filename: str) -> str:
    return f"{source_case_key}/{filename}" if source_case_key else filename


def inventory_archive(
    archive_path: str | Path,
    *,
    registry: SourceSchemaRegistry = NANJING_SOURCE_SCHEMA,
) -> SourceDatasetInventory:
    """Inventory a ZIP without extracting or changing it."""

    source_path = Path(archive_path)
    digest = sha256()
    with source_path.open("rb") as source_stream:
        for block in iter(lambda: source_stream.read(1024 * 1024), b""):
            digest.update(block)
    with ZipFile(source_path, mode="r") as archive:
        infos = archive.infolist()

    paths_by_name: dict[str, int] = {}
    case_keys: set[str] = set()
    csv_member_count = 0
    for info in infos:
        validate_zip_member_path(info.filename)
        if info.is_dir():
            continue
        paths_by_name[info.filename] = paths_by_name.get(info.filename, 0) + 1
        if info.filename.endswith(".csv"):
            csv_member_count += 1

        source_case_key, separator, filename = info.filename.rpartition("/")
        if not separator:
            filename = info.filename
            source_case_key = ""
        if registry.for_filename(filename) is not None:
            case_keys.add(source_case_key)

    cases: list[SourceCaseInventory] = []
    diagnostics: list[IntakeDiagnostic] = []
    for source_case_key in sorted(case_keys):
        members: list[tuple[SourceFileType, str | None]] = []
        for file_schema in registry.files:
            expected_path = _member_path(source_case_key, file_schema.filename)
            occurrence_count = paths_by_name.get(expected_path, 0)
            member_path = expected_path if occurrence_count == 1 else None
            members.append((file_schema.file_type, member_path))
            if occurrence_count != 1:
                detail = "missing" if occurrence_count == 0 else "duplicated"
                diagnostics.append(
                    IntakeDiagnostic(
                        code=(
                            IntakeDiagnosticCode.SOURCE_FILE_MISSING
                            if occurrence_count == 0
                            else IntakeDiagnosticCode.SOURCE_FILE_READ_FAILED
                        ),
                        message=f"expected source file is {detail}",
                        source_case_key=source_case_key,
                        member_path=expected_path,
                        source_record_ref=None,
                    )
                )
        cases.append(
            SourceCaseInventory(
                source_case_key=source_case_key,
                members=tuple(members),
            )
        )

    return SourceDatasetInventory(
        source_uri=str(source_path),
        source_checksum=f"sha256:{digest.hexdigest()}",
        member_count=len(infos),
        csv_member_count=csv_member_count,
        cases=tuple(cases),
        diagnostics=tuple(diagnostics),
    )
