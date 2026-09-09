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
from .reference_integration import (
    ReferenceIntegrationOutcome,
    build_nanjing_reference_candidate_index,
    integrate_bus_station_reference,
    integrate_feeder_source_bus_reference,
    reference_candidate_from_mapped_record,
)
from .reference_issue_policy import reference_issues_for_result
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
    "ReferenceIntegrationOutcome",
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
    "build_nanjing_reference_candidate_index",
    "inventory_archive",
    "integrate_bus_station_reference",
    "integrate_feeder_source_bus_reference",
    "map_dataset",
    "map_feeder",
    "map_grid_case",
    "map_station",
    "read_raw_csv_member",
    "reference_candidate_from_mapped_record",
    "reference_issues_for_result",
    "source_record_ref",
    "validate_zip_member_path",
    "CANONICAL_SPEC_VERSION",
]
