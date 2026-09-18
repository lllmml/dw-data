import csv
import io
import json
from zipfile import ZipFile

import pytest
from grid_case_generator.io.derived_delivery_artifacts import write_delivery
import completion_fixture as cf


@pytest.fixture
def delivery_fixture(tmp_path):
    return cf.build(tmp_path)


def test_untouched_case_is_byte_identical(delivery_fixture):
    root = delivery_fixture.write()
    with ZipFile(delivery_fixture.archive, 'r') as archive:
        for _, member_path in delivery_fixture.members:
            assert (root / 'data' / member_path).read_bytes() == archive.read(member_path)


def test_every_member_is_delivered(delivery_fixture):
    root = delivery_fixture.write()
    delivered = {str(p.relative_to(root / 'data')) for p in (root / 'data').rglob('*.csv')}
    assert delivered == {member for _, member in delivery_fixture.members}
    for _, member_path in delivery_fixture.members:
        assert len(list((root / 'data' / member_path).parent.iterdir())) >= 1


def test_byte_fidelity_is_discriminating_not_parsed_equality(delivery_fixture):
    """The delivered LF-only member must keep LF, which a re-serializing writer would not.

    Parsed records are identical either way, so record-level equality would not catch it.
    """
    root = delivery_fixture.write()
    member = delivery_fixture.lf_member
    delivered = (root / 'data' / member).read_bytes()
    with ZipFile(delivery_fixture.archive, 'r') as archive:
        source = archive.read(member)
    assert delivered == source
    assert b'\r\n' not in delivered, 'a csv.writer-based writer would have emitted CRLF'
    decode = lambda b: list(csv.reader(io.StringIO(b.decode('utf-8-sig'), newline='')))
    assert decode(delivered) == decode(source), 'records are equal; only the bytes differ'


def test_a_missing_trailing_terminator_is_preserved(delivery_fixture):
    root = delivery_fixture.write()
    member = delivery_fixture.no_trailing_member
    with ZipFile(delivery_fixture.archive, 'r') as archive:
        source = archive.read(member)
    delivered = (root / 'data' / member).read_bytes()
    assert delivered == source
    assert not delivered.endswith(b'\r\n')


def test_quoted_fields_survive_verbatim(delivery_fixture):
    root = delivery_fixture.write()
    member = delivery_fixture.quoted_member
    with ZipFile(delivery_fixture.archive, 'r') as archive:
        source = archive.read(member)
    assert (root / 'data' / member).read_bytes() == source
    assert b'"' in source


def test_output_is_write_once(delivery_fixture):
    delivery_fixture.write()
    with pytest.raises(FileExistsError):
        delivery_fixture.write()


def test_output_may_not_nest_inside_an_input_root(delivery_fixture):
    with pytest.raises(ValueError, match='separate from every input'):
        write_delivery(delivery_fixture.roots['source'] / 'delivery',
                       **delivery_fixture.write_args())


def test_every_source_row_gets_a_provenance_record(delivery_fixture):
    root = delivery_fixture.write()
    rows = [json.loads(line) for line in
            (root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()]
    source = [r for r in rows if r['row_kind'] == 'SOURCE']
    assert len(source) == delivery_fixture.source_row_count
    assert {r['rule_id'] for r in source} == {'SOURCE_PASSTHROUGH_V1'}
    assert {r['completion_status'] for r in source} == {'CONFIRMED'}
    assert {r['confidence_class'] for r in source} == {'EXACT_STRUCTURAL'}
    assert all(r['donor_source_record_ref'] is None for r in source)
    assert all(r['tier'] is None for r in source)
    assert all(r['evidence_refs'] == [] for r in source)


def test_provenance_keys_are_exact(delivery_fixture):
    from grid_case_generator.io.derived_delivery_artifacts import PROVENANCE_KEYS
    root = delivery_fixture.write()
    rows = [json.loads(line) for line in
            (root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()]
    assert rows
    for row in rows:
        assert set(row) == set(PROVENANCE_KEYS)


def test_provenance_row_index_aligns_with_the_delivered_csv(delivery_fixture):
    root = delivery_fixture.write()
    rows = [json.loads(line) for line in
            (root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()]
    for row in rows:
        path = root / 'data' / row['source_case_key'] / row['target_file']
        text = path.read_bytes().decode('utf-8-sig')
        parsed = list(csv.reader(io.StringIO(text, newline='')))
        assert 1 + row['row_index'] < len(parsed)


def test_provenance_is_ordered_by_case_file_and_row(delivery_fixture):
    root = delivery_fixture.write()
    rows = [json.loads(line) for line in
            (root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()]
    keys = [(r['source_case_key'], r['target_file'], r['row_index']) for r in rows]
    assert keys == sorted(keys)


def test_source_record_ref_points_at_the_row_it_describes(delivery_fixture):
    from grid_case_generator.io.nanjing_source.locator import SourceRecordRef
    from grid_case_generator.io.source_bytes import member_path_of
    root = delivery_fixture.write()
    rows = [json.loads(line) for line in
            (root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()]
    for row in rows:
        ref = SourceRecordRef(row['source_record_ref'])
        assert member_path_of(ref) == f"{row['source_case_key']}/{row['target_file']}"
        assert ref.data_row == row['row_index'] + 1


def test_a_feederless_case_still_delivers_twelve_members(delivery_fixture):
    root = delivery_fixture.write()
    delivered = sorted(p.name for p in (root / 'data' / delivery_fixture.feederless_key).iterdir())
    assert len(delivered) == 12


def test_case_ordering_is_enforced(delivery_fixture):
    args = delivery_fixture.write_args()
    args['cases'] = tuple(reversed(tuple(args['cases'])))
    with pytest.raises(ValueError, match='ordering'):
        write_delivery(delivery_fixture.tmp_path / 'other', **args)


def test_case_ordering_is_by_source_case_key_not_by_case_id(delivery_fixture):
    # The inventory orders Cases by source_case_key; case_id is a hash and carries
    # no ordering guarantee, so an assertion on case_id would reject real input.
    keys = [c[1] for c in delivery_fixture.cases]
    ids = [c[0] for c in delivery_fixture.cases]
    assert keys == sorted(keys)
    assert ids != sorted(ids) or len(ids) < 3


def test_the_writer_never_uses_csv_writer():
    import ast
    from pathlib import Path as _Path
    source = (_Path(__file__).parents[2] / 'src' / 'grid_case_generator' / 'io'
              / 'derived_delivery_artifacts.py').read_text()
    tree = ast.parse(source)
    imported = set()
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split('.')[0])
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    assert 'csv' not in imported, 'the delivery writer must not parse or emit CSV'
    assert not (called & {'writer', 'DictWriter'}), called & {'writer', 'DictWriter'}


def test_provenance_records_are_canonical_json(delivery_fixture):
    from grid_case_generator.io.canonical_json import canonical_json_bytes
    root = delivery_fixture.write()
    raw = (root / 'provenance' / 'row_provenance.jsonl').read_bytes()
    for line in raw.splitlines():
        assert line == canonical_json_bytes(json.loads(line))
