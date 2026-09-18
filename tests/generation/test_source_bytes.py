import csv
import io
from pathlib import Path
from zipfile import ZipFile

import pytest
from grid_case_generator.io.nanjing_source.csv_reader import read_raw_csv_member
from grid_case_generator.io.nanjing_source.locator import source_record_ref
from grid_case_generator.io.nanjing_source.schema import NANJING_SOURCE_SCHEMA
from grid_case_generator.io.source_bytes import (
    member_path_of, raw_member_bytes, raw_record_bytes, split_raw_records,
)

REAL = Path(__file__).parents[2] / 'data' / 'raw' / '南京数据.zip'
BOM = b'\xef\xbb\xbf'


def fixture_member():
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['Switch_ID', 'Switch_FromBus', 'Switch_Note'])
    writer.writerow(['S1', 'B1', 'plain'])
    writer.writerow(['S2', 'B2', 'has, comma'])
    writer.writerow(['S3', 'B3', 'has "quote"'])
    writer.writerow(['S4', 'B4', 'has\nnewline'])
    return BOM + stream.getvalue().encode()


def test_member_path_round_trips_the_locator():
    ref = source_record_ref('数据/甲变_10kV甲线101/03_Switch.csv', data_row=7)
    assert member_path_of(ref) == '数据/甲变_10kV甲线101/03_Switch.csv'


@pytest.mark.parametrize('bad', ['not-a-ref', 'zip-member:x.csv', 'file:x.csv#data-row=1'])
def test_member_path_rejects_a_non_locator(bad):
    with pytest.raises(ValueError, match='not a source record ref'):
        member_path_of(bad)


def test_member_path_round_trips_a_non_ascii_path():
    path = '数据/沙洲变_10kV新安江路#1线119/03_Switch.csv'
    ref = source_record_ref(path, data_row=1)
    assert member_path_of(ref) == path


def test_split_strips_terminators_but_alters_no_content():
    raw = split_raw_records(fixture_member())
    assert len(raw) == 5
    # The BOM is retained in the header slice; these are verbatim partitions.
    assert raw[0] == BOM + b'Switch_ID,Switch_FromBus,Switch_Note'
    assert raw[1] == b'S1,B1,plain'
    assert raw[2] == b'S2,B2,"has, comma"'
    assert raw[3] == b'S3,B3,"has ""quote"""'
    assert raw[4] == b'S4,B4,"has\nnewline"'
    assert not any(b'\r' in r for r in raw)


def test_raw_record_index_is_one_based_over_data_rows():
    member = fixture_member()
    assert raw_record_bytes(member, 1) == b'S1,B1,plain'
    assert raw_record_bytes(member, 4) == b'S4,B4,"has\nnewline"'
    with pytest.raises(IndexError):
        raw_record_bytes(member, 5)


def test_terminator_variants():
    assert split_raw_records(BOM + b'A,B\r\n') == (BOM + b'A,B',)
    assert split_raw_records(BOM + b'A,B\r\n1,2\r\n')[-1] == b'1,2'
    assert split_raw_records(BOM + b'A,B\r\n1,2')[-1] == b'1,2'
    assert split_raw_records(BOM + b'A,B\n1,2\n')[-1] == b'1,2'
    assert split_raw_records(BOM + b'A,B\r1,2\r')[-1] == b'1,2'
    assert split_raw_records(b'') == ()


def test_a_quoted_field_may_contain_either_terminator():
    assert split_raw_records(b'A\r\n"x\r\ny"\r\n') == (b'A', b'"x\r\ny"')
    assert split_raw_records(b'A\r\n"x\ny"\r\n') == (b'A', b'"x\ny"')
    assert split_raw_records(b'A\r\n"x\ry"\r\n') == (b'A', b'"x\ry"')


def test_an_escaped_quote_does_not_close_a_field():
    raw = split_raw_records(b'A\r\n"a""b\r\nc"\r\n')
    assert raw == (b'A', b'"a""b\r\nc"')


def test_an_unterminated_quoted_field_is_rejected():
    with pytest.raises(ValueError, match='unterminated quoted field'):
        split_raw_records(b'A\r\n"never closed')


def test_records_are_verbatim_partitions_of_a_uniform_member():
    member = fixture_member()
    assert b'\r\n'.join(split_raw_records(member)) + b'\r\n' == member


@pytest.mark.skipif(not REAL.exists(), reason='raw archive not present')
def test_split_agrees_with_the_parser_on_real_members():
    schema = NANJING_SOURCE_SCHEMA.for_filename('03_Switch.csv')
    assert schema is not None
    with ZipFile(REAL, 'r') as archive:
        names = [n for n in archive.namelist() if n.endswith('/03_Switch.csv')][:200]
        assert names
        for name in names:
            member = raw_member_bytes(archive, name)
            parsed = read_raw_csv_member(
                archive, source_case_key=name.rpartition('/')[0],
                member_path=name, file_schema=schema)
            assert len(split_raw_records(member)) == len(parsed.records) + 1, name


@pytest.mark.skipif(not REAL.exists(), reason='raw archive not present')
def test_real_members_are_verbatim_partitions():
    with ZipFile(REAL, 'r') as archive:
        names = [n for n in archive.namelist() if n.endswith('/02_Bus.csv')][:50]
        for name in names:
            member = raw_member_bytes(archive, name)
            assert b'\r\n'.join(split_raw_records(member)) + b'\r\n' == member, name


@pytest.mark.skipif(not REAL.exists(), reason='raw archive not present')
def test_raw_member_bytes_matches_a_direct_read():
    with ZipFile(REAL, 'r') as archive:
        name = next(n for n in archive.namelist() if n.endswith('/03_Switch.csv'))
        assert raw_member_bytes(archive, name) == archive.read(name)


def test_member_path_is_validated_before_reading():
    archive = ZipFile(io.BytesIO(b'PK\x05\x06' + b'\x00' * 18), 'r')
    with pytest.raises(ValueError):
        raw_member_bytes(archive, '../escape/01_Station.csv')


def test_the_module_never_opens_the_archive_or_parses_csv():
    import ast
    from pathlib import Path as _Path
    source = (_Path(__file__).parents[2] / 'src' / 'grid_case_generator' / 'io'
              / 'source_bytes.py').read_text()
    tree = ast.parse(source)
    called = set()
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
        elif isinstance(node, ast.Import):
            imported.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split('.')[0])
    # It must never open or construct an archive: the handle is caller-owned.
    assert not (called & {'ZipFile', 'open'}), called & {'ZipFile', 'open'}
    # It must never parse CSV: that is csv_reader's job.
    assert 'csv' not in imported
    assert not (called & {'reader', 'DictReader'}), called & {'reader', 'DictReader'}
    # Reading a member is the one filesystem-ish call it is allowed to make.
    assert 'read' in called
