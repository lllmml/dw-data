"""Read-only intake primitives for the Nanjing source archive."""

from .archive import inventory_archive
from .csv_reader import read_raw_csv_member
from .locator import (
    SourceRecordRef,
    UnsafeZipMemberPath,
    source_record_ref,
    validate_zip_member_path,
)
from .mapping import (
    CANONICAL_SPEC_VERSION,
    RecordMappingOutcome,
    UnmappedSourceRecord,
    map_dataset,
    map_feeder,
    map_grid_case,
    map_station,
)
from .models import (
    IntakeDiagnostic,
    IntakeDiagnosticCode,
    RawCsvRecord,
    RawSourceFile,
    SourceCaseInventory,
    SourceDatasetInventory,
)
from .schema import (
    NANJING_SOURCE_SCHEMA,
    SourceFileSchema,
    SourceFileType,
    SourceSchemaRegistry,
)

__all__ = [
    "IntakeDiagnostic",
    "IntakeDiagnosticCode",
    "NANJING_SOURCE_SCHEMA",
    "RecordMappingOutcome",
    "RawCsvRecord",
    "RawSourceFile",
    "SourceCaseInventory",
    "SourceDatasetInventory",
    "SourceFileSchema",
    "SourceFileType",
    "SourceSchemaRegistry",
    "SourceRecordRef",
    "UnmappedSourceRecord",
    "UnsafeZipMemberPath",
    "inventory_archive",
    "map_dataset",
    "map_feeder",
    "map_grid_case",
    "map_station",
    "read_raw_csv_member",
    "source_record_ref",
    "validate_zip_member_path",
    "CANONICAL_SPEC_VERSION",
]
