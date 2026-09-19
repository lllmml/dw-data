import csv
import io
import json
from zipfile import ZipFile

import pytest
from grid_case_generator.io.derived_delivery_artifacts import build_archive, write_delivery
from hashlib import sha256
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
    delivery_fixture.append_donor_row().placement_bus()
    root = delivery_fixture.write()
    rows = [json.loads(line) for line in
            (root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()]
    keys = [(r['source_case_key'], r['target_file'], r['row_index']) for r in rows]
    assert keys == sorted(keys)


def test_source_record_ref_points_at_the_row_it_describes(delivery_fixture):
    """A SOURCE row, and a copied APPENDED row, each name the source row they mirror.

    A generated placement Bus row is exempt, and is checked by
    ``test_generated_bus_row_cites_the_line_that_declared_it`` instead: no source Bus
    row exists for it to mirror, so its ref names the source *Line* row that declared
    the endpoint, in a different member and at an unrelated row index.
    """
    from grid_case_generator.io.nanjing_source.locator import SourceRecordRef
    from grid_case_generator.io.source_bytes import member_path_of
    delivery_fixture.placement_bus()
    root = delivery_fixture.write()
    rows = [json.loads(line) for line in
            (root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()]
    checked = [r for r in rows if r['rule_id'] != 'PLACEMENT_MISSING_ENDPOINT_BUS_V1']
    assert len(checked) == len(rows) - len(delivery_fixture.bus_plan)
    for row in checked:
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


def test_member_outside_its_case_scope_is_rejected(delivery_fixture):
    cases = list(delivery_fixture.cases)
    case_id, case_key, members = cases[0]
    foreign = ('数据/别的变_10kV别线999/01_Station.csv',)
    cases[0] = (case_id, case_key, (members[0], (members[0][0], foreign[0])))
    args = delivery_fixture.write_args()
    args['cases'] = tuple(cases)
    with pytest.raises(ValueError, match='case scope'):
        write_delivery(delivery_fixture.tmp_path / 'scoped', **args)


def test_delivery_summary_matches_the_inputs_and_the_disk(delivery_fixture):
    root = delivery_fixture.write()
    result = delivery_fixture.result
    assert result['cases'] == len(delivery_fixture.cases)
    assert result['members'] == len(delivery_fixture.members)
    assert result['source_rows'] == delivery_fixture.source_row_count
    provenance = (root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()
    assert result['source_rows'] == len(provenance)


def test_output_under_data_raw_is_rejected(delivery_fixture):
    # check_output passes here (the target nests inside no input root), so this
    # exercises the inline data/raw predicate specifically.
    target = delivery_fixture.tmp_path / 'data' / 'raw' / 'delivery'
    with pytest.raises(ValueError, match='data/raw'):
        write_delivery(target, **delivery_fixture.write_args())


# --- CROSS_CASE_REFERENCE_COPY_V1 append path ---


def test_crlf_source_appends_with_one_separator_and_stays_verbatim(delivery_fixture):
    delivery_fixture.append_donor_row()
    root = delivery_fixture.write()
    target = root / 'data' / delivery_fixture.referring_key / '03_Switch.csv'
    delivered = target.read_bytes()
    with ZipFile(delivery_fixture.archive) as archive:
        source = archive.read(f'{delivery_fixture.referring_key}/03_Switch.csv')
        donor = archive.read(delivery_fixture.donor_member('03_Switch.csv')).split(b'\r\n')
    assert delivered.startswith(source), 'the source prefix must be byte-identical'
    appended = delivered[len(source):]
    assert appended == donor[1] + b'\r\n'
    assert b'\r\n\r\n' not in appended, 'exactly one separator, not two'


def test_lf_only_source_keeps_its_own_terminators_in_the_source_region(delivery_fixture):
    delivery_fixture.append_donor_row(destination='04_Disconnector.csv',
                                      donor_file='03_Switch.csv')
    root = delivery_fixture.write()
    delivered = (root / 'data' / delivery_fixture.referring_key / '04_Disconnector.csv').read_bytes()
    with ZipFile(delivery_fixture.archive) as archive:
        source = archive.read(f'{delivery_fixture.referring_key}/04_Disconnector.csv')
    assert delivered.startswith(source)
    assert source.count(b'\r\n') == 0, 'the fixture edge member is LF-only'
    # The appended block is CRLF by contract; the source region is untouched.
    assert delivered[len(source):].endswith(b'\r\n')
    assert delivered[len(source):].count(b'\r\n') == 1


def test_missing_trailing_terminator_gets_exactly_one_separator(delivery_fixture):
    delivery_fixture.append_donor_row(destination='06_EarthingSwitch.csv',
                                      donor_file='03_Switch.csv')
    root = delivery_fixture.write()
    delivered = (root / 'data' / delivery_fixture.referring_key / '06_EarthingSwitch.csv').read_bytes()
    with ZipFile(delivery_fixture.archive) as archive:
        source = archive.read(f'{delivery_fixture.referring_key}/06_EarthingSwitch.csv')
        donor = archive.read(delivery_fixture.donor_member('03_Switch.csv')).split(b'\r\n')
    assert not source.endswith(b'\r\n'), 'this edge member has no trailing terminator'
    assert delivered == source + b'\r\n' + donor[1] + b'\r\n'
    # Two logical records, not one: the last source row did not absorb the donor row.
    rows = list(csv.reader(io.StringIO(delivered.decode('utf-8-sig'), newline='')))
    assert rows[-1][0] == donor[1].split(b',')[0].decode()


def test_unappended_member_source_prefix_is_byte_identical(delivery_fixture):
    delivery_fixture.append_donor_row(destination='03_Switch.csv', donor_file='03_Switch.csv')
    root = delivery_fixture.write()
    with ZipFile(delivery_fixture.archive) as archive:
        for _, member_path in delivery_fixture.members:
            delivered = (root / 'data' / member_path).read_bytes()
            source = archive.read(member_path)
            if member_path.endswith(f'{delivery_fixture.referring_key}/03_Switch.csv'):
                assert delivered.startswith(source)
                assert delivered != source
            else:
                assert delivered == source, member_path


def test_appended_provenance_rows_align_with_the_delivered_csv(delivery_fixture):
    delivery_fixture.append_donor_row()
    root = delivery_fixture.write()
    rows = [json.loads(line) for line in
            (root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()]
    appended = [r for r in rows if r['row_kind'] == 'APPENDED']
    assert len(appended) == delivery_fixture.result['appended_rows'] == 1
    record, = appended
    assert record['rule_id'] == 'CROSS_CASE_REFERENCE_COPY_V1'
    assert record['rule_version'] == '1.1.0'
    assert record['completion_status'] == 'PROPOSED'
    assert record['tier'] == 'SAME_STATION'
    assert record['donor_source_record_ref'] is not None
    assert record['evidence_refs']
    target = root / 'data' / record['source_case_key'] / record['target_file']
    parsed = list(csv.reader(io.StringIO(target.read_bytes().decode('utf-8-sig'), newline='')))
    assert 1 + record['row_index'] == len(parsed) - 1, 'row_index must name the last row'
    appended_row = parsed[record['row_index'] + 1]
    with ZipFile(delivery_fixture.archive) as archive:
        donor_rows = list(csv.reader(io.StringIO(
            archive.read(delivery_fixture.donor_member('03_Switch.csv')).decode('utf-8-sig'),
            newline='')))
    assert appended_row == donor_rows[1], 'the appended row must be the donor row verbatim'


def test_no_source_member_is_read_or_split_twice(delivery_fixture, monkeypatch):
    """The split-once invariant: a donor member is not re-split when it is also delivered.

    Counting is keyed on the member path, not on content: several Cases ship
    byte-identical empty members, so a content-keyed count would over-report two splits
    where only one member was actually processed twice.
    """
    from grid_case_generator.io import derived_delivery_artifacts as dda
    reads, splits = [], []
    real_read, real_split = dda.raw_member_bytes, dda.split_raw_records

    def counted_read(archive, member_path):
        reads.append(member_path)
        return real_read(archive, member_path)

    def counted_split(member_bytes):
        splits.append(member_bytes)
        return real_split(member_bytes)

    monkeypatch.setattr(dda, 'raw_member_bytes', counted_read)
    monkeypatch.setattr(dda, 'split_raw_records', counted_split)
    delivery_fixture.append_donor_row()
    delivery_fixture.write()

    members = [member for _, member in delivery_fixture.members]
    assert sorted(reads) == sorted(members), 'every member read exactly once'
    assert len(splits) == len(members), 'one split per read, so at most one per member'


def test_passthrough_member_is_the_no_append_entry_point(delivery_fixture):
    from grid_case_generator.io.derived_delivery_artifacts import passthrough_member
    destination = delivery_fixture.tmp_path / 'single.csv'
    with ZipFile(delivery_fixture.archive) as archive:
        member = f'{delivery_fixture.referring_key}/01_Station.csv'
        written = passthrough_member(archive, member, destination)
        assert written == archive.read(member)
    assert destination.read_bytes() == written
    with pytest.raises(FileExistsError):
        with ZipFile(delivery_fixture.archive) as archive:
            passthrough_member(archive, member, destination)


# --- PLACEMENT_MISSING_ENDPOINT_BUS_V1 materialization ---


def test_generated_row_reparses_to_the_intended_values(delivery_fixture):
    delivery_fixture.placement_bus()
    delivery_fixture.write()
    row = delivery_fixture.reparsed_last_bus_row()
    assert row['Bus_ID'] == delivery_fixture.raw_endpoint_value
    assert row['Bus_Name'] == '' and row['Bus_Phase'] == '' and row['Bus_IsSource'] == ''
    assert row['Bus_Station_ID'] == 'S-BING', 'the single Case-local station, verbatim'
    assert list(row) == list(delivery_fixture.bus_header)


def test_bus_header_is_never_rewritten(delivery_fixture):
    delivery_fixture.placement_bus()
    root = delivery_fixture.write()
    target = (root / 'data' / delivery_fixture.bus_member).read_bytes()
    assert target.startswith(delivery_fixture.bus_member_bytes.split(b'\r\n')[0])
    assert target.startswith(delivery_fixture.bus_member_bytes), 'the source region is verbatim'


def test_line_csv_receives_no_new_row(delivery_fixture):
    delivery_fixture.placement_bus()
    root = delivery_fixture.write()
    after = (root / 'data' / delivery_fixture.referring_key / '08_Line.csv').read_bytes()
    with ZipFile(delivery_fixture.archive) as archive:
        assert after == archive.read(f'{delivery_fixture.referring_key}/08_Line.csv')


def test_both_plans_onto_one_member_are_ordered_by_rule_id(delivery_fixture):
    """Both plans target 02_Bus.csv, so this member really does carry both.

    The contract orders a member's appended rows by ``rule_id``, which puts the copied
    ``CROSS_CASE_REFERENCE_COPY_V1`` row before the generated
    ``PLACEMENT_MISSING_ENDPOINT_BUS_V1`` row. Appending the plans in the other order
    would still pass every test that gives each plan its own member.
    """
    delivery_fixture.append_donor_row(destination='02_Bus.csv', donor_file='02_Bus.csv')
    delivery_fixture.placement_bus()
    root = delivery_fixture.write()
    rows = [json.loads(line) for line in
            (root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()]
    target = root / 'data' / delivery_fixture.bus_member
    parsed = list(csv.reader(io.StringIO(target.read_bytes().decode('utf-8-sig'), newline='')))
    appended = [r for r in rows if r['target_file'] == '02_Bus.csv' and r['row_kind'] == 'APPENDED']
    assert len(appended) == 2
    assert [r['rule_id'] for r in appended] == [
        'CROSS_CASE_REFERENCE_COPY_V1', 'PLACEMENT_MISSING_ENDPOINT_BUS_V1']
    assert [r['row_index'] for r in appended] == [1, 2]
    assert [r['source_case_key'] for r in appended] == [delivery_fixture.referring_key] * 2
    bus = appended[-1]
    assert delivery_fixture.result['placement_rows'] == len(delivery_fixture.bus_plan)
    assert parsed[-1][0] == delivery_fixture.raw_endpoint_value
    assert parsed[1 + bus['row_index']] == parsed[-1], 'row_index names the delivered row'


def test_generated_bus_row_cites_the_line_that_declared_it(delivery_fixture):
    from grid_case_generator.io.nanjing_source.locator import SourceRecordRef
    from grid_case_generator.io.source_bytes import member_path_of
    delivery_fixture.placement_bus()
    root = delivery_fixture.write()
    rows = [json.loads(line) for line in
            (root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()]
    record, = [r for r in rows if r['rule_id'] == 'PLACEMENT_MISSING_ENDPOINT_BUS_V1']
    ref = SourceRecordRef(record['source_record_ref'])
    assert record['source_case_key'] == delivery_fixture.referring_key
    assert member_path_of(ref) == f'{delivery_fixture.referring_key}/08_Line.csv'
    assert record['raw_field'] in ('Line_FromBus', 'Line_ToBus')
    assert record['raw_reference_value'] == delivery_fixture.raw_endpoint_value


def test_generated_bus_row_provenance_is_engineering_default(delivery_fixture):
    delivery_fixture.placement_bus()
    root = delivery_fixture.write()
    rows = [json.loads(line) for line in
            (root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()]
    record, = [r for r in rows if r['rule_id'] == 'PLACEMENT_MISSING_ENDPOINT_BUS_V1']
    assert record['rule_version'] == '1.1.0'
    assert record['completion_status'] == 'PROPOSED'
    assert record['confidence_class'] == 'ENGINEERING_DEFAULT'
    assert record['tier'] is None
    assert record['donor_source_record_ref'] is None
    assert record['evidence_refs'] == list(delivery_fixture.bus_plan[0]['record_ids'])


def test_no_placement_rows_are_written_without_a_bus_plan(delivery_fixture):
    root = delivery_fixture.write()
    rows = [json.loads(line) for line in
            (root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()]
    assert delivery_fixture.result['placement_rows'] == 0
    assert not [r for r in rows if r['rule_id'] == 'PLACEMENT_MISSING_ENDPOINT_BUS_V1']




def test_a_cross_station_row_reports_its_own_tier(delivery_fixture):
    """The writer must not assert a tier the plan did not carry.

    ``materialize_tiers`` is a policy lever, so the same rule can emit both tiers. A
    literal ``SAME_STATION`` in the writer would then misreport a delivered row.
    """
    delivery_fixture.append_donor_row(tier='CROSS_STATION')
    root = delivery_fixture.write()
    rows = [json.loads(line) for line in
            (root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()]
    record, = [r for r in rows if r['row_kind'] == 'APPENDED']
    assert record['tier'] == 'CROSS_STATION'


def test_a_plan_entry_for_an_undelivered_member_writes_nothing(delivery_fixture):
    """The check must run before the first write, because the target is write-once.

    A late failure would leave a partial tree that no retry can replace and that is
    indistinguishable from a complete delivery.
    """
    delivery_fixture.placement_bus()
    plan = [dict(entry, destination_member='数据/无此变_10kV无此线000/02_Bus.csv')
            for entry in delivery_fixture.bus_plan]
    target = delivery_fixture.tmp_path / 'delivery'
    with pytest.raises(ValueError, match='outside the delivered inventory'):
        delivery_fixture.write(bus_plan=tuple(plan))
    assert not target.exists()


# --- delivery manifest, report and archive ---


def test_manifest_inventories_every_file_except_itself_and_the_archive(delivery_fixture):
    from grid_case_generator.io.derived_delivery_artifacts import ARCHIVE_NAME
    ledger = cf.write_ledger_artifact(delivery_fixture.tmp_path)
    root = delivery_fixture.write(ledger_root=ledger)
    build_archive(root)
    manifest = json.loads((root / 'manifest.json').read_text())
    on_disk = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    assert on_disk == set(manifest['files']) | {'manifest.json', ARCHIVE_NAME}
    assert ARCHIVE_NAME not in manifest['files']


def test_manifest_states_the_boundary_and_binds_its_ledger(delivery_fixture):
    ledger = cf.write_ledger_artifact(delivery_fixture.tmp_path)
    root = delivery_fixture.write(ledger_root=ledger)
    manifest = json.loads((root / 'manifest.json').read_text())
    for flag in ('approved', 'applied', 'canonical_changed', 'accepted_v2_changed',
                 'source_changed', 'e3_ready', 'opendss_ready'):
        assert manifest[flag] is False, flag
    assert manifest['artifact_kind'] == 'DERIVED_DELIVERY'
    assert manifest['ledger_manifest_sha256'] == sha256(
        (ledger / 'manifest.json').read_bytes()).hexdigest()
    assert manifest['cases'] == delivery_fixture.result['cases']
    assert manifest['members'] == delivery_fixture.result['members']
    assert manifest['appended_rows'] == delivery_fixture.result['appended_rows']
    assert manifest['rules'], 'a rule summary is required'


def test_delivery_carries_the_ledger_streams_verbatim(delivery_fixture):
    ledger = cf.write_ledger_artifact(delivery_fixture.tmp_path)
    root = delivery_fixture.write(ledger_root=ledger)
    for name in ('completion_records.jsonl', 'unresolved_records.jsonl'):
        assert (root / 'provenance' / name).read_bytes() == (ledger / name).read_bytes(), name


def test_a_delivery_without_a_ledger_says_so(delivery_fixture):
    """Silence would let an unbound delivery pass as a complete one."""
    root = delivery_fixture.write()
    manifest = json.loads((root / 'manifest.json').read_text())
    assert manifest['ledger_manifest_sha256'] is None
    assert not (root / 'provenance' / 'completion_records.jsonl').exists()


def test_report_states_every_required_fact(delivery_fixture):
    delivery_fixture.placement_bus()
    root = delivery_fixture.write()
    text = (root / 'report.md').read_text()
    for phrase in ('approved: false', 'PROPOSED', 'SOURCE_HEAD_CONTEXT',
                   'declaration completions', 'Q-CASE-001', 'UNRESOLVED taxonomy'):
        assert phrase in text, phrase


def test_archive_is_deterministic_and_sorted(delivery_fixture):
    from grid_case_generator.io.derived_delivery_artifacts import ARCHIVE_NAME
    root = delivery_fixture.write()
    first = build_archive(root)
    digest = (root / ARCHIVE_NAME).read_bytes()
    assert first['sha256'] == sha256(digest).hexdigest()
    assert first['entries'] == len(digest and ZipFile(root / ARCHIVE_NAME).namelist())
    names = ZipFile(root / ARCHIVE_NAME).namelist()
    assert sorted(names) == names
    assert 'manifest.json' in names and 'report.md' in names
    assert not any(n.endswith(ARCHIVE_NAME) for n in names)


def test_archive_timestamps_are_fixed_and_csvs_match_the_tree(delivery_fixture):
    from grid_case_generator.io.derived_delivery_artifacts import ARCHIVE_NAME
    root = delivery_fixture.write()
    build_archive(root)
    with ZipFile(root / ARCHIVE_NAME) as archive:
        assert {i.date_time for i in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}
        names = set(archive.namelist())
        for member in sorted(names):
            assert archive.read(member) == (root / member).read_bytes(), member
    on_disk = {str(p.relative_to(root)) for p in (root / 'data').rglob('*.csv')}
    assert {n for n in names if n.endswith('.csv')} == on_disk


def test_archive_is_byte_identical_across_a_repeat_build(delivery_fixture):
    from grid_case_generator.io.derived_delivery_artifacts import ARCHIVE_NAME
    root = delivery_fixture.write()
    build_archive(root)
    first = (root / ARCHIVE_NAME).read_bytes()
    (root / ARCHIVE_NAME).unlink()
    build_archive(root)
    assert (root / ARCHIVE_NAME).read_bytes() == first


def test_archive_hash_is_reported_not_manifested(delivery_fixture):
    from grid_case_generator.io.derived_delivery_artifacts import ARCHIVE_NAME
    root = delivery_fixture.write()
    archive = build_archive(root)
    manifest = json.loads((root / 'manifest.json').read_text())
    assert archive['sha256'] == sha256((root / ARCHIVE_NAME).read_bytes()).hexdigest()
    assert ARCHIVE_NAME not in manifest['files']
    assert manifest['source_archive_sha256'] == sha256(
        delivery_fixture.archive.read_bytes()).hexdigest()
