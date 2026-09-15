"""Small source fixtures exercise E2 through the frozen E1 mapper."""
from grid_case_generator.io.nanjing_source.schema import NANJING_SOURCE_SCHEMA as SCHEMA
from grid_case_generator.io.nanjing_source.models import RawCsvRecord, RawSourceFile, SourceCaseInventory
from grid_case_generator.io.nanjing_source.locator import source_record_ref
from grid_case_generator.models.identifiers import SourceImportIdFactory as IDs
from grid_case_generator.io.nanjing_source.import_pipeline import map_source_case

DATASET = IDs.dataset_id('a' * 64)


def source_files(rows, case='case'):
    files = []
    for schema in SCHEMA.files:
        member = f'{case}/{schema.filename}'
        records = []
        for n, row in enumerate(rows.get(schema.file_type.value, []), 1):
            values = tuple(row.get(k, '') for k in schema.header)
            records.append(RawCsvRecord(source_case_key=case, source_file_type=schema.file_type,
                header=schema.header, data_row=n, source_record_ref=source_record_ref(member, data_row=n),
                values=values, fields=tuple(zip(schema.header, values))))
        files.append(RawSourceFile(source_case_key=case, source_file_type=schema.file_type,
            member_path=member, header=schema.header, records=tuple(records), diagnostics=()))
    inventory = SourceCaseInventory(source_case_key=case,
        members=tuple((s.file_type, f'{case}/{s.filename}') for s in SCHEMA.files))
    return inventory, tuple(files)


def mapped(rows):
    inventory, files = source_files(rows)
    return map_source_case(inventory, files, dataset_id=DATASET)
