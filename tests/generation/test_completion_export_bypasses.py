"""Regression tests for the ways a forged delivery could pass verification.

Each test edits the delivery *and then re-hashes it into its own manifest*, so a failure
can only come from a semantic check. A test that passed because the checksum moved would
prove nothing about the validator's reasoning.
"""
import json
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

import pytest
from grid_case_generator.analysis.completion_export import verify_export
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.derived_delivery_artifacts import PROVENANCE_KEYS, build_archive
from grid_case_generator.models.completion_export import provenance_id
from grid_case_generator.validation.completion_export import REASONS, validate_delivery

import completion_fixture as cf


@pytest.fixture
def delivery(tmp_path):
    fixture = cf.build(tmp_path)
    fixture.roots = cf.export_roots(fixture)
    fixture.ledger = cf.write_ledger_artifact(tmp_path, roots=fixture.roots)
    fixture.append_donor_row(destination='02_Bus.csv', donor_file='02_Bus.csv')
    fixture.placement_bus().bind_ledger(fixture.ledger)
    fixture.root = fixture.write(ledger_root=fixture.ledger)
    build_archive(fixture.root)
    seal_sidecar(fixture)
    return fixture


def seal_sidecar(fixture):
    """Write the verification sidecar exactly as the real run does."""
    from grid_case_generator.analysis.completion_export import write_sidecar
    from grid_case_generator.io.completion_ledger_artifacts import bindings
    from grid_case_generator.io.derived_delivery_artifacts import describe_archive
    from grid_case_generator.models.completion_export import policy_sha256
    verdict_now = validate_delivery(fixture.root, ledger_root=fixture.ledger,
                                    roots=fixture.roots, policy=fixture.policy,
                                    archive=fixture.archive)
    return write_sidecar(fixture.root, archive=describe_archive(fixture.root),
                         bindings_=bindings(fixture.roots), verdict=verdict_now,
                         policy_hash=policy_sha256(fixture.policy),
                         ledger_manifest_sha256=sha256(
                             (fixture.ledger / 'manifest.json').read_bytes()).hexdigest())


def verdict(fixture, **overrides):
    kwargs = {'ledger_root': fixture.ledger, 'roots': fixture.roots,
              'policy': fixture.policy, 'archive': fixture.archive}
    kwargs.update(overrides)
    return validate_delivery(fixture.root, **kwargs)


def rewrite(path, mutate):
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    mutate(rows)
    path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
    return rows


def reseal(root):
    """Re-hash every file into the manifest, so only a semantic check can fail."""
    path = Path(root) / 'manifest.json'
    manifest = json.loads(path.read_text())
    for name in manifest['files']:
        data = (Path(root) / name).read_bytes()
        manifest['files'][name] = {'sha256': sha256(data).hexdigest(),
                                   'record_count': len(data.splitlines())}
    path.write_bytes(canonical_json_bytes(manifest) + b'\n')
    return manifest


def reforge_provenance(root):
    """Recompute every provenance_id so the records are internally consistent."""
    path = Path(root) / 'provenance' / 'row_provenance.jsonl'
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    for record in rows:
        record['provenance_id'] = provenance_id(
            {k: record[k] for k in PROVENANCE_KEYS if k != 'provenance_id'})
    path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
    return rows


def appended_index(rows):
    return next(i for i, r in enumerate(rows) if r['row_kind'] == 'APPENDED')


# --- P1-1: provenance, ledger and upstream correlation ---


def test_a_forged_appended_status_is_rejected(delivery):
    """An appended row may not claim a status its rule cannot produce."""
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rewrite(path, lambda rows: rows[appended_index(rows)].update(
        completion_status='CONFIRMED'))
    reforge_provenance(delivery.root)
    reseal(delivery.root)
    assert 'APPENDED_EVIDENCE_MISMATCH' in verdict(delivery)['reasons']


def test_emptied_evidence_refs_are_rejected(delivery):
    """A row that cites no ledger record is a row nothing licenses."""
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rewrite(path, lambda rows: rows[appended_index(rows)].update(evidence_refs=[]))
    reforge_provenance(delivery.root)
    reseal(delivery.root)
    assert 'APPENDED_EVIDENCE_MISMATCH' in verdict(delivery)['reasons']


def test_a_forged_row_policy_hash_is_rejected(delivery):
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rewrite(path, lambda rows: rows[appended_index(rows)].update(policy_sha256='0' * 64))
    reforge_provenance(delivery.root)
    reseal(delivery.root)
    assert 'POLICY_HASH_MISMATCH' in verdict(delivery)['reasons']


def test_a_forged_provenance_id_is_rejected(delivery):
    """The id must be derivable from the record, not merely present."""
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rewrite(path, lambda rows: rows[appended_index(rows)].update(provenance_id='forged'))
    reseal(delivery.root)
    assert 'PROVENANCE_ID_MISMATCH' in verdict(delivery)['reasons']


def test_an_uncited_completion_record_is_rejected(delivery):
    """Every PROPOSED record must license at least one delivered row."""
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rewrite(path, lambda rows: rows[appended_index(rows)].update(evidence_refs=[]))
    # Not reforged: the empty citation is the thing under test, and the id check is a
    # different one, so reforge to isolate the coverage failure.
    reforge_provenance(delivery.root)
    reseal(delivery.root)
    assert 'APPENDED_EVIDENCE_MISMATCH' in verdict(delivery)['reasons']


def test_evidence_citing_a_record_of_another_rule_is_rejected(delivery):
    """A placement row may not be licensed by a cross-case record."""
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    records = [json.loads(line) for line in
               (delivery.ledger / 'completion_records.jsonl').read_bytes().splitlines()]
    cross = next(r for r in records if r['rule_id'] == 'CROSS_CASE_REFERENCE_COPY_V1')
    placement = next(i for i, r in enumerate(rows)
                     if r['rule_id'] == 'PLACEMENT_MISSING_ENDPOINT_BUS_V1')
    rows[placement]['evidence_refs'] = [cross['record_id']]
    path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
    reforge_provenance(delivery.root)
    reseal(delivery.root)
    assert 'APPENDED_EVIDENCE_MISMATCH' in verdict(delivery)['reasons']


def test_a_copied_delivery_ledger_stream_is_bound_to_the_ledger(delivery):
    """The copies under provenance/ are the ledger's streams, or they are not."""
    path = delivery.root / 'provenance' / 'completion_records.jsonl'
    def flip(rows):
        index = next(i for i, r in enumerate(rows)
                     if r['completion_status'] == 'PROPOSED')
        rows[index]['completion_status'] = 'CONFIRMED'
    rewrite(path, flip)
    reseal(delivery.root)
    assert 'LEDGER_STREAM_MISMATCH' in verdict(delivery)['reasons']


# --- P1-1: placement correlated by Case and endpoint evidence ---


def test_a_placement_row_for_the_wrong_case_is_rejected(delivery):
    """A Bus row is licensed by an endpoint in *that* Case, not by the value alone."""
    path = delivery.root / 'data' / delivery.referring_key / '02_Bus.csv'
    data = path.read_bytes().replace(delivery.raw_endpoint_value.encode(), b'B-ELSEWHERE', 1)
    path.write_bytes(data)
    rows = reforge_provenance(delivery.root)
    index = appended_index(rows)
    rows[index]['raw_reference_value'] = 'B-ELSEWHERE'
    rows[index]['provenance_id'] = provenance_id(
        {k: rows[index][k] for k in PROVENANCE_KEYS if k != 'provenance_id'})
    (delivery.root / 'provenance' / 'row_provenance.jsonl').write_bytes(
        b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
    reseal(delivery.root)
    assert verdict(delivery)['reasons']


def test_a_generated_row_with_no_licensing_endpoint_is_minted(delivery):
    """A generated Bus row must be licensed by an endpoint in *that* Case.

    A value no endpoint declares is, by definition, an identifier this layer invented.

    The row and its provenance are forged consistently, so nothing but re-deriving the
    value from the placement evidence can catch it.
    """
    path = delivery.root / 'data' / delivery.referring_key / '02_Bus.csv'
    path.write_bytes(path.read_bytes() + b'B-UNLICENSED,,,,,\r\n')
    rows = reforge_provenance(delivery.root)
    template = next(r for r in rows
                    if r['rule_id'] == 'PLACEMENT_MISSING_ENDPOINT_BUS_V1')
    forged = dict(template, row_index=max(r['row_index'] for r in rows) + 1,
                  raw_reference_value='B-UNLICENSED')
    forged['provenance_id'] = provenance_id(
        {k: forged[k] for k in PROVENANCE_KEYS if k != 'provenance_id'})
    rows.append(forged)
    (delivery.root / 'provenance' / 'row_provenance.jsonl').write_bytes(
        b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
    reseal(delivery.root)
    assert 'MINTED_IDENTIFIER' in verdict(delivery)['reasons']


def test_a_station_that_contradicts_the_case_member_is_rejected(delivery):
    """The station is re-read from the Case's own 02_Bus.csv, not trusted from the row."""
    path = delivery.root / 'data' / delivery.referring_key / '02_Bus.csv'
    path.write_bytes(path.read_bytes().replace(b'S-BING', b'S-WRONG', 1))
    reforge_provenance(delivery.root)
    reseal(delivery.root)
    assert verdict(delivery)['reasons']


# --- P1-2: source byte fidelity and row completeness ---


def test_a_dropped_source_row_is_rejected(delivery):
    """A header-only file is not a delivered file with its rows removed."""
    path = delivery.root / 'data' / delivery.referring_key / '02_Bus.csv'
    header = path.read_bytes().split(b'\r\n')[0]
    path.write_bytes(header + b'\r\n')
    rows = reforge_provenance(delivery.root)
    keep = [r for r in rows if not (r['target_file'] == '02_Bus.csv'
                                    and r['source_case_key'] == delivery.referring_key)]
    (delivery.root / 'provenance' / 'row_provenance.jsonl').write_bytes(
        b''.join(canonical_json_bytes(r) + b'\n' for r in keep))
    reseal(delivery.root)
    assert verdict(delivery)['reasons']


def test_a_line_ending_change_is_rejected(delivery):
    """CRLF to LF is invisible to a parser and fatal to the byte-fidelity promise."""
    path = delivery.root / 'data' / '数据/甲变_10kV甲线101' / '01_Station.csv'
    path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
    reseal(delivery.root)
    assert 'SOURCE_ROW_NOT_VERBATIM' in verdict(delivery)['reasons']


def test_a_byte_change_inside_a_row_is_rejected(delivery):
    path = delivery.root / 'data' / '数据/甲变_10kV甲线101' / '01_Station.csv'
    before = path.read_bytes()
    path.write_bytes(before.replace(b'10kV', b'20kV'))
    assert path.read_bytes() != before, 'the mutation must land somewhere'
    reseal(delivery.root)
    assert 'SOURCE_ROW_NOT_VERBATIM' in verdict(delivery)['reasons']


def test_a_missing_appended_row_is_rejected(delivery):
    """Dropping the appended block is a silent row loss."""
    path = delivery.root / 'data' / delivery.referring_key / '02_Bus.csv'
    lines = path.read_bytes().split(b'\r\n')
    path.write_bytes(b'\r\n'.join(lines[:2]) + b'\r\n')
    reforge_provenance(delivery.root)
    reseal(delivery.root)
    assert verdict(delivery)['reasons']


# --- P1-3: ZIP, sidecar and tree binding ---


def test_a_tree_edit_with_the_old_zip_and_sidecar_is_rejected(delivery):
    """The ZIP and the sidecar are stale evidence, not proof."""
    path = delivery.root / 'data' / '数据/甲变_10kV甲线101' / '01_Station.csv'
    before = path.read_bytes()
    path.write_bytes(before.replace(b'10kV', b'20kV'))
    assert path.read_bytes() != before, 'the mutation must land somewhere'
    reseal(delivery.root)
    result = verify_export(delivery.roots, delivery.policy_path(), delivery.ledger,
                           delivery.root)
    assert result['verified'] is False
    assert result['reasons']


def test_a_zip_that_does_not_match_the_tree_is_rejected(delivery):
    from grid_case_generator.io.derived_delivery_artifacts import ARCHIVE_NAME
    archive = delivery.root / ARCHIVE_NAME
    with ZipFile(archive) as z:
        entries = {i.filename: z.read(i.filename) for i in z.infolist()}
    target = 'data/数据/甲变_10kV甲线101/01_Station.csv'
    assert b'10kV' in entries[target]
    entries[target] = entries[target].replace(b'10kV', b'20kV')
    from zipfile import ZIP_DEFLATED, ZipInfo
    with ZipFile(archive, 'w', ZIP_DEFLATED) as z:
        for name, data in sorted(entries.items()):
            z.writestr(ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), data)
    reseal(delivery.root)
    assert 'ARCHIVE_CONTENT_MISMATCH' in verdict(delivery)['reasons']


def test_a_zip_missing_an_entry_is_rejected(delivery):
    from zipfile import ZIP_DEFLATED, ZipInfo
    from grid_case_generator.io.derived_delivery_artifacts import ARCHIVE_NAME
    archive = delivery.root / ARCHIVE_NAME
    with ZipFile(archive) as z:
        entries = {i.filename: z.read(i.filename) for i in z.infolist()}
    dropped = next(n for n in entries if n.endswith('01_Station.csv'))
    del entries[dropped]
    with ZipFile(archive, 'w', ZIP_DEFLATED) as z:
        for name, data in sorted(entries.items()):
            z.writestr(ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), data)
    assert 'ARCHIVE_CONTENT_MISMATCH' in verdict(delivery)['reasons']


# --- P1-4: the upstream chain ---


def test_a_corrupted_upstream_stream_is_rejected(tmp_path, delivery):
    """An upstream manifest that still matches proves nothing about its files."""
    audit = Path(delivery.roots['audit'])
    (audit / 'cross_case_references.jsonl').write_bytes(b'{}\n')
    result = verify_export(delivery.roots, delivery.policy_path(), delivery.ledger,
                           delivery.root)
    assert result['verified'] is False
    assert result['reasons']


def test_an_upstream_file_replaced_by_garbage_is_rejected(tmp_path, delivery):
    audit = Path(delivery.roots['audit'])
    (audit / 'case_inventory.jsonl').write_bytes(b'not json at all\n')
    result = verify_export(delivery.roots, delivery.policy_path(), delivery.ledger,
                           delivery.root)
    assert result['verified'] is False


def test_a_missing_upstream_file_is_a_reason_not_a_crash(delivery):
    audit = Path(delivery.roots['audit'])
    (audit / 'case_inventory.jsonl').unlink()
    result = verify_export(delivery.roots, delivery.policy_path(), delivery.ledger,
                           delivery.root)
    assert result['verified'] is False
    assert result['reasons']


def test_verify_does_not_write_anything(delivery):
    """Verification that repairs the evidence it is checking proves nothing."""
    before = {str(p.relative_to(delivery.root)): p.read_bytes()
              for p in sorted(delivery.root.rglob('*')) if p.is_file()}
    verify_export(delivery.roots, delivery.policy_path(), delivery.ledger, delivery.root)
    after = {str(p.relative_to(delivery.root)): p.read_bytes()
             for p in sorted(delivery.root.rglob('*')) if p.is_file()}
    assert before == after


def test_a_clean_delivery_still_verifies(delivery):
    """The baseline: every bypass test in this file must fail where this one passes."""
    assert verdict(delivery)['reasons'] == []
    result = verify_export(delivery.roots, delivery.policy_path(), delivery.ledger,
                           delivery.root)
    assert result['verified'] is True
    assert result['reasons'] == []


def test_the_baseline_carries_all_three_record_classes(delivery):
    """A baseline missing a class cannot show that class is handled correctly."""
    records = [json.loads(line) for line in
               (delivery.ledger / 'completion_records.jsonl').read_bytes().splitlines()]
    unresolved = [json.loads(line) for line in
                  (delivery.ledger / 'unresolved_records.jsonl').read_bytes().splitlines()]
    assert {r['completion_status'] for r in records} == {'CONFIRMED', 'PROPOSED'}
    assert unresolved and {r['completion_status'] for r in unresolved} == {'UNRESOLVED'}
    assert len([r for r in records if r['rule_id'] == 'ACCEPTED_DETERMINISTIC_RECOVERY_V1'])


def test_a_confirmed_record_is_not_required_to_license_a_row(delivery):
    """The recovery rule is CONFIRMED and appends nothing, by contract."""
    assert 'APPENDED_EVIDENCE_MISMATCH' not in verdict(delivery)['reasons']


def test_a_confirmed_record_with_no_evidence_is_rejected(delivery):
    path = delivery.ledger / 'completion_records.jsonl'
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    index = next(i for i, r in enumerate(rows)
                 if r['rule_id'] == 'ACCEPTED_DETERMINISTIC_RECOVERY_V1')
    rows[index]['evidence_refs'] = []
    path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
    reseal(delivery.root)
    assert 'APPENDED_EVIDENCE_MISMATCH' in verdict(delivery)['reasons']


def test_citing_a_confirmed_record_as_a_row_licence_is_rejected(delivery):
    """A record that materializes nothing cannot be what licenses a delivered row."""
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    records = [json.loads(line) for line in
               (delivery.ledger / 'completion_records.jsonl').read_bytes().splitlines()]
    confirmed = next(r for r in records if r['completion_status'] == 'CONFIRMED')
    index = next(i for i, r in enumerate(rows) if r['row_kind'] == 'APPENDED')
    rows[index]['evidence_refs'] = [confirmed['record_id']]
    rows[index]['provenance_id'] = provenance_id(
        {k: rows[index][k] for k in PROVENANCE_KEYS if k != 'provenance_id'})
    path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
    reseal(delivery.root)
    assert 'APPENDED_EVIDENCE_MISMATCH' in verdict(delivery)['reasons']


def test_a_missing_licensed_row_is_rejected(delivery):
    """Deleting a row the ledger licensed is a silent loss of a completion."""
    path = delivery.root / 'data' / delivery.referring_key / '02_Bus.csv'
    rows = path.read_bytes().split(b'\r\n')
    path.write_bytes(b'\r\n'.join(rows[:3]) + b'\r\n')
    prov = delivery.root / 'provenance' / 'row_provenance.jsonl'
    keep = [json.loads(line) for line in prov.read_bytes().splitlines()]
    keep = [r for r in keep if not (r['target_file'] == '02_Bus.csv'
                                    and r['row_index'] >= 2)]
    prov.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in keep))
    reseal(delivery.root)
    assert 'APPENDED_EVIDENCE_MISMATCH' in verdict(delivery)['reasons']


# --- the remaining reason codes, each with the corruption that raises it ---


def test_a_donor_ref_beyond_the_donor_member_is_rejected(delivery):
    """A donor row that does not exist cannot license a copy."""
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    index = next(i for i, r in enumerate(rows)
                 if r['rule_id'] == 'CROSS_CASE_REFERENCE_COPY_V1')
    donor = rows[index]['donor_source_record_ref']
    rows[index]['donor_source_record_ref'] = donor.split('#data-row=')[0] + '#data-row=999'
    rows[index]['provenance_id'] = provenance_id(
        {k: rows[index][k] for k in PROVENANCE_KEYS if k != 'provenance_id'})
    path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
    reseal(delivery.root)
    assert 'APPENDED_ROW_NOT_DONOR_BYTES' in verdict(delivery)['reasons']


def test_a_missing_placement_artifact_is_rejected_not_ignored(delivery):
    """Without the placement evidence a generated row cannot be licensed."""
    missing = delivery.tmp_path / 'absent-placement'
    missing.mkdir(exist_ok=True)
    result = verdict(delivery, roots=dict(delivery.roots, placement=missing),
                     archive=delivery.archive)
    assert result['structural_status'] == 'REJECTED'
    assert 'PLACEMENT_FIELD_MISMATCH' in result['reasons']


def test_a_provenance_record_for_an_undelivered_member_is_rejected(delivery):
    """A record naming a member the delivery does not carry is an orphan."""
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    rows.append(dict(rows[0], target_file='99_Ghost.csv'))
    path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
    reseal(delivery.root)
    assert 'PROVENANCE_UNKNOWN_ROW' in verdict(delivery)['reasons']


def test_two_records_for_one_row_index_are_rejected(delivery):
    """One delivered row has one provenance record."""
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    rows.append(dict(rows[1]))
    path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
    reseal(delivery.root)
    assert 'DUPLICATE_APPENDED_ROW' in verdict(delivery)['reasons']


def test_a_self_consistent_tree_with_a_stale_sidecar_is_rejected(delivery):
    """Re-sealing the tree does not re-seal the evidence that attested to the old one."""
    path = delivery.root / 'data' / '数据/甲变_10kV甲线101' / '01_Station.csv'
    path.write_bytes(path.read_bytes().replace(b'10kV', b'20kV'))
    reseal(delivery.root)
    # Rebuild the archive so the tree is internally consistent and only the sidecar is stale.
    from grid_case_generator.io.derived_delivery_artifacts import ARCHIVE_NAME
    (delivery.root / ARCHIVE_NAME).unlink()
    build_archive(delivery.root)
    result = verify_export(delivery.roots, delivery.policy_path(), delivery.ledger,
                           delivery.root)
    assert result['verified'] is False
    assert 'SIDECAR_MISMATCH' in result['reasons']


def test_a_corrupted_upstream_stream_names_the_reason(delivery):
    audit = Path(delivery.roots['audit'])
    (audit / 'cross_case_references.jsonl').write_bytes(b'{}\n')
    result = verify_export(delivery.roots, delivery.policy_path(), delivery.ledger,
                           delivery.root)
    assert 'UPSTREAM_INTEGRITY' in result['reasons']


# --- the validator's own cost must not grow with the delivery's size ---


def test_the_tree_is_scanned_a_constant_number_of_times(tmp_path):
    """A per-member re-scan is quadratic, which on the real intake is a hung run.

    Counting calls rather than timing them: a threshold test would be flaky, and the
    defect is a scaling law, not a millisecond count.
    """
    from grid_case_generator.validation import completion_export as module

    for label, cases in (('small', 2), ('large', 6)):
        path = tmp_path / label
        path.mkdir()
        fixture = cf.build(path, extra_cases=cases)
        fixture.roots = cf.export_roots(fixture)
        fixture.ledger = cf.write_ledger_artifact(path, roots=fixture.roots)
        fixture.append_donor_row(destination='02_Bus.csv', donor_file='02_Bus.csv')
        fixture.placement_bus().bind_ledger(fixture.ledger)
        fixture.root = fixture.write(ledger_root=fixture.ledger)
        root = fixture.root
        build_archive(root)
        members = len([p for p in (root / 'data').rglob('*.csv')])
        calls, reads = [], []
        real_documents, real_read = module._documents, Path.read_bytes
        module._documents = lambda r, _d=real_documents: (calls.append(1), _d(r))[1]
        Path.read_bytes = lambda self, _r=real_read: (reads.append(1), _r(self))[1]
        try:
            assert verdict(fixture)['reasons'] == []
        finally:
            module._documents = real_documents
            Path.read_bytes = real_read
        assert len(calls) == 1, f'{label}: tree scanned {len(calls)}x for {members} members'
        # Linear in members, not quadratic: one read per member plus the fixed files.
        assert len(reads) <= 6 * members + 60, f'{label}: {len(reads)} reads for {members} members'


# --- the ledger, delivery, manifest, ZIP and sidecar are all re-sealed together ---


def reseal_chain(fixture):
    """Re-seal every artifact that binds another, so only the evidence can disagree.

    Delivery manifest -> ledger manifest -> upstream manifests -> sidecar. After this
    the tree, its manifest, its ZIP, its sidecar and the ledger all agree with each
    other; the only thing left holding the old story is the stated input binding.
    """
    from grid_case_generator.io.canonical_json import canonical_json_bytes as cj
    from grid_case_generator.io.derived_delivery_artifacts import ARCHIVE_NAME
    root = Path(fixture.root)
    # the delivery manifest re-hashes the tree and re-binds the ledger
    reseal(root)
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    ledger_manifest_path = Path(fixture.ledger) / 'manifest.json'
    manifest['ledger_manifest_sha256'] = sha256(ledger_manifest_path.read_bytes()).hexdigest()
    manifest_path.write_bytes(cj(manifest) + b'\n')
    # the sidecar re-binds everything it attests to
    sidecar_path = Path(fixture.tmp_path) / 'delivery-verification.json'
    sidecar = json.loads(sidecar_path.read_text())
    sidecar['manifest_sha256'] = sha256(manifest_path.read_bytes()).hexdigest()
    sidecar['provenance_sha256'] = sha256(
        (root / 'provenance' / 'row_provenance.jsonl').read_bytes()).hexdigest()
    sidecar['ledger_manifest_sha256'] = manifest['ledger_manifest_sha256']
    for name in ('manifest.json',):
        pass
    # the archive is rebuilt last, so it is the final word on the tree
    (root / ARCHIVE_NAME).unlink()
    build_archive(root)
    sidecar['archive_sha256'] = sha256((root / ARCHIVE_NAME).read_bytes()).hexdigest()
    sidecar_path.write_bytes(json.dumps(sidecar, ensure_ascii=False, sort_keys=True,
                                        indent=2).encode() + b'\n')
    # the ledger's own binding of the audit manifest follows the re-sealed audit
    audit_manifest = Path(fixture.roots['audit']) / 'manifest.json'
    ledger_manifest = json.loads(ledger_manifest_path.read_text())
    ledger_manifest['input_manifest_sha256'] = dict(
        ledger_manifest['input_manifest_sha256'],
        audit=sha256(audit_manifest.read_bytes()).hexdigest())
    ledger_manifest_path.write_bytes(cj(ledger_manifest) + b'\n')
    # ... and the delivery and sidecar follow the ledger's new digest
    manifest = json.loads(manifest_path.read_text())
    manifest['ledger_manifest_sha256'] = sha256(ledger_manifest_path.read_bytes()).hexdigest()
    manifest_path.write_bytes(cj(manifest) + b'\n')
    sidecar = json.loads(sidecar_path.read_text())
    sidecar['manifest_sha256'] = sha256(manifest_path.read_bytes()).hexdigest()
    sidecar['ledger_manifest_sha256'] = manifest['ledger_manifest_sha256']
    sidecar['protected_inputs_sha256'] = dict(
        sidecar['protected_inputs_sha256'],
        audit=sha256(audit_manifest.read_bytes()).hexdigest())
    sidecar_path.write_bytes(json.dumps(sidecar, ensure_ascii=False, sort_keys=True,
                                        indent=2).encode() + b'\n')


def reseal_audit(fixture, mutate):
    """Edit an upstream stream and re-hash it into its own manifest.

    The whole point: the delivery, its manifest, its ZIP and its sidecar stay
    self-consistent, and only the untouched-evidence disagreement remains.
    """
    root = Path(fixture.roots['audit'])
    path = root / 'cross_case_references.jsonl'
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    mutate(rows)
    path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    data = path.read_bytes()
    manifest['files']['cross_case_references.jsonl'] = {
        'sha256': sha256(data).hexdigest(), 'record_count': len(data.splitlines())}
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b'\n')


def test_a_row_the_audit_no_longer_licenses_is_rejected(delivery):
    """Everything agrees with everything, except the evidence that licensed the row."""
    reseal_audit(delivery, lambda rows: rows[0].update(classification='UNDEFINED_GLOBAL'))
    reseal_chain(delivery)
    result = verify_export(delivery.roots, delivery.policy_path(), delivery.ledger,
                           delivery.root)
    assert result['verified'] is False
    assert 'APPENDED_EVIDENCE_MISMATCH' in result['reasons']


def test_a_missing_expected_cross_case_event_is_rejected(delivery):
    """Dropping the row *and* its provenance still leaves the audit's expectation."""
    path = delivery.root / 'data' / delivery.referring_key / '02_Bus.csv'
    lines = path.read_bytes().split(b'\r\n')
    path.write_bytes(b'\r\n'.join(lines[:2]) + b'\r\n')
    prov = delivery.root / 'provenance' / 'row_provenance.jsonl'
    keep = [json.loads(line) for line in prov.read_bytes().splitlines()
            if not (line and json.loads(line)['row_kind'] == 'APPENDED'
                    and json.loads(line)['rule_id'] == 'CROSS_CASE_REFERENCE_COPY_V1')]
    prov.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in keep))
    from grid_case_generator.io.derived_delivery_artifacts import ARCHIVE_NAME
    (delivery.root / ARCHIVE_NAME).unlink()
    build_archive(delivery.root)
    reseal(delivery.root)
    assert 'APPENDED_EVIDENCE_MISMATCH' in verdict(delivery)['reasons']


def test_a_reclassified_reference_is_rejected(delivery):
    """A ledger that reclassifies a failure the audit recorded is caught."""
    reseal_audit(delivery, lambda rows: rows.append(dict(
        rows[0], reference_id='d4.2-analysis:reference:zzz',
        classification='UNDEFINED_GLOBAL')))
    reseal_chain(delivery)
    result = verify_export(delivery.roots, delivery.policy_path(), delivery.ledger,
                           delivery.root)
    assert result['verified'] is False
    assert 'UNRESOLVED_TAXONOMY_MISMATCH' in result['reasons']


# --- the public entry points must reject loudly, not quietly ---


def _cli(delivery, command, output=None):
    import os
    import subprocess
    import sys
    args = [sys.executable, '-m', 'grid_case_generator.analysis.completion_export_cli',
            command]
    values = dict(delivery.roots)
    values.update(policy=delivery.policy_path(), ledger=delivery.ledger,
                  output=output or delivery.root)
    for name in sorted(values):
        args += ['--' + name.replace('_', '-'), str(values[name])]
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).parents[2] / 'src'))
    return subprocess.run(args, capture_output=True, text=True, env=env)


def test_the_cli_exits_zero_on_a_clean_delivery(delivery):
    done = _cli(delivery, 'verify')
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)['verified'] is True


def test_the_cli_exits_nonzero_when_verification_rejects(delivery):
    """A rejection a calling script cannot see is a rejection it will ignore."""
    path = delivery.root / 'data' / '数据/甲变_10kV甲线101' / '01_Station.csv'
    path.write_bytes(path.read_bytes().replace(b'10kV', b'20kV'))
    reseal(delivery.root)
    done = _cli(delivery, 'verify')
    assert done.returncode != 0
    verdict_json = json.loads(done.stdout)
    assert verdict_json['verified'] is False
    assert verdict_json['reasons']
    assert 'REJECTED' in done.stderr


def test_the_cli_exits_nonzero_on_a_corrupted_upstream(delivery):
    """The failure must surface on the public path, not only in a helper."""
    root = Path(delivery.roots['audit'])
    (root / 'case_inventory.jsonl').write_bytes(b'not json at all\n')
    done = _cli(delivery, 'verify')
    assert done.returncode != 0
    assert 'UPSTREAM_INTEGRITY' in json.loads(done.stdout)['reasons']


# --- every reason code is raised by a tamper, not merely named somewhere ---


def _tampers():
    """``code -> a callable that produces a delivery raising that code``.

    A code that appears only as a string in a test file proves nothing: what has to be
    true is that some concrete corruption makes the validator say it.
    """
    def edited_delivery(mutate, code_check=None):
        def run(fixture):
            mutate(fixture)
            reseal(fixture.root)
            return verdict(fixture)['reasons']
        return run

    def provenance(mutate):
        def run(fixture):
            path = fixture.root / 'provenance' / 'row_provenance.jsonl'
            rows = [json.loads(line) for line in path.read_bytes().splitlines()]
            mutate(rows)
            for record in rows:
                record['provenance_id'] = provenance_id(
                    {k: record[k] for k in PROVENANCE_KEYS if k != 'provenance_id'})
            path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
            reseal(fixture.root)
            return verdict(fixture)['reasons']
        return run

    def first_appended(rows):
        return next(i for i, r in enumerate(rows) if r['row_kind'] == 'APPENDED')

    def placement_index(rows):
        return next(i for i, r in enumerate(rows)
                    if r['rule_id'] == 'PLACEMENT_MISSING_ENDPOINT_BUS_V1')

    def rebuilt_archive(fixture):
        from grid_case_generator.io.derived_delivery_artifacts import ARCHIVE_NAME
        (fixture.root / ARCHIVE_NAME).unlink()
        build_archive(fixture.root)

    return {
        'PROVENANCE_ID_MISMATCH': lambda f: (
            rewrite(f.root / 'provenance' / 'row_provenance.jsonl',
                    lambda rows: rows[first_appended(rows)].update(provenance_id='x')),
            reseal(f.root), verdict(f)['reasons'])[-1],
        'PROVENANCE_INCOMPLETE': lambda f: (
            rewrite(f.root / 'provenance' / 'row_provenance.jsonl',
                    lambda rows: rows[first_appended(rows)].pop('evidence_refs')),
            reseal(f.root), verdict(f)['reasons'])[-1],
        'PROVENANCE_UNKNOWN_ROW': lambda f: (
            rewrite(f.root / 'provenance' / 'row_provenance.jsonl',
                    lambda rows: rows[first_appended(rows)].update(target_file='99_Ghost.csv')),
            reseal(f.root), verdict(f)['reasons'])[-1],
        'DUPLICATE_APPENDED_ROW': lambda f: (
            rewrite(f.root / 'provenance' / 'row_provenance.jsonl',
                    lambda rows: rows.append(dict(rows[first_appended(rows)]))),
            reseal(f.root), verdict(f)['reasons'])[-1],
        'APPENDED_EVIDENCE_MISMATCH': provenance(
            lambda rows: rows[first_appended(rows)].update(evidence_refs=[])),
        'APPENDED_ROW_NOT_DONOR_BYTES': provenance(
            lambda rows: rows[first_appended(rows)].update(
                donor_source_record_ref=rows[first_appended(rows)][
                    'donor_source_record_ref'].split('#data-row=')[0] + '#data-row=999')),
        'MINTED_IDENTIFIER': provenance(
            lambda rows: rows[placement_index(rows)].update(
                raw_reference_value='B-NOT-DECLARED')),
        'PLACEMENT_FIELD_MISMATCH': lambda f: verdict(
            f, roots=dict(f.roots, placement=_empty_dir(f.tmp_path / 'no-placement')),
            archive=f.archive)['reasons'],
        'UNRESOLVED_ROW_WRITTEN': lambda f: (
            rewrite(f.ledger / 'unresolved_records.jsonl',
                    lambda rows: rows[0].update(
                        rule_id='PLACEMENT_MISSING_ENDPOINT_BUS_V1',
                        reason='EVIDENCE_JOIN_MISMATCH',
                        raw_reference_value=f.raw_endpoint_value)),
            verdict(f)['reasons'])[-1],
        'TIER_NOT_ENABLED': lambda f: (
            rewrite(f.ledger / 'completion_records.jsonl',
                    lambda rows: next(r for r in rows
                                      if r['completion_status'] == 'PROPOSED').update(
                                          tier='CROSS_STATION')),
            verdict(f)['reasons'])[-1],
        'CLOSURE_NOT_BOUNDED': lambda f: (
            rewrite(f.ledger / 'completion_records.jsonl',
                    lambda rows: rows[0].update(closure_depth=99)),
            verdict(f)['reasons'])[-1],
        'POLICY_HASH_MISMATCH': lambda f: (
            rewrite(f.root / 'provenance' / 'row_provenance.jsonl',
                    lambda rows: rows[first_appended(rows)].update(policy_sha256='0' * 64)),
            reseal(f.root), verdict(f)['reasons'])[-1],
        'LEDGER_BINDING_MISMATCH': edited_delivery(
            lambda f: _set_manifest(f, ledger_manifest_sha256='0' * 64)),
        'LEDGER_STREAM_MISMATCH': lambda f: (
            rewrite(f.root / 'provenance' / 'completion_records.jsonl',
                    lambda rows: rows[0].update(completion_status='PROPOSED')),
            reseal(f.root), verdict(f)['reasons'])[-1],
        'STALE_LEDGER_BASE': lambda f: (
            rewrite(f.ledger / 'manifest.json',
                    lambda rows: None) if False else _stale_base(f)),
        'SOURCE_ROW_NOT_VERBATIM': edited_delivery(
            lambda f: _edit_station(f, b'10kV', b'20kV')),
        'CSV_COLUMN_SCHEMA_CHANGED': edited_delivery(
            lambda f: _edit_station(f, b'Station_ID', b'Station_Id')),
        'MEMBER_MISSING': lambda f: (
            (f.root / 'data' / '数据/甲变_10kV甲线101' / '09_Transformer.csv').unlink(),
            verdict(f)['reasons'])[-1],
        'ARCHIVE_INVENTORY_MISMATCH': lambda f: (
            (f.root / 'stray.txt').write_bytes(b'x'), verdict(f)['reasons'])[-1],
        'ARCHIVE_CONTENT_MISMATCH': lambda f: (
            _break_archive(f), reseal(f.root), verdict(f)['reasons'])[-1],
        'UPSTREAM_INTEGRITY': lambda f: (
            (Path(f.roots['audit']) / 'case_inventory.jsonl').write_bytes(b'oops\n'),
            verdict(f)['reasons'])[-1],
        'UNRESOLVED_TAXONOMY_MISMATCH': lambda f: (
            reseal_audit(f, lambda rows: rows[0].update(classification='UNDEFINED_GLOBAL')),
            verdict(f)['reasons'])[-1],
        'SIDECAR_MISMATCH': lambda f: (
            verify_export(f.roots, f.policy_path(), f.ledger, f.root)['reasons'])
        if False else 'SIDECAR_MISMATCH',
    }


def _empty_dir(path):
    path.mkdir(exist_ok=True)
    return path


def _set_manifest(fixture, **fields):
    path = Path(fixture.root) / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest.update(fields)
    path.write_bytes(canonical_json_bytes(manifest) + b'\n')


def _edit_station(fixture, old, new):
    path = Path(fixture.root) / 'data' / '数据/甲变_10kV甲线101' / '01_Station.csv'
    before = path.read_bytes()
    path.write_bytes(before.replace(old, new))
    assert path.read_bytes() != before, f'{old!r} did not occur in the station member'


def _break_archive(fixture):
    from zipfile import ZIP_DEFLATED, ZipInfo
    from grid_case_generator.io.derived_delivery_artifacts import ARCHIVE_NAME
    archive = Path(fixture.root) / ARCHIVE_NAME
    with ZipFile(archive) as z:
        entries = {i.filename: z.read(i.filename) for i in z.infolist()}
    target = 'data/数据/甲变_10kV甲线101/01_Station.csv'
    entries[target] = entries[target].replace(b'10kV', b'20kV')
    with ZipFile(archive, 'w', ZIP_DEFLATED) as z:
        for name, data in sorted(entries.items()):
            z.writestr(ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), data)


def _stale_base(fixture):
    path = Path(fixture.ledger) / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['input_manifest_sha256'] = dict(manifest['input_manifest_sha256'],
                                             accepted_v2='0' * 64)
    path.write_bytes(canonical_json_bytes(manifest) + b'\n')
    accepted = Path(fixture.tmp_path) / 'accepted-v2'
    accepted.mkdir(exist_ok=True)
    (accepted / 'manifest.json').write_bytes(canonical_json_bytes({'x': 1}) + b'\n')
    return verdict(fixture, roots=dict(fixture.roots, accepted_v2=accepted))['reasons']


REGISTRY = _tampers()


@pytest.mark.parametrize('code', sorted(REASONS))
def test_each_reason_code_is_raised_by_a_tamper(code, delivery):
    """Behaviour, not a string match: the tamper must actually make the code appear."""
    if code not in REGISTRY:
        pytest.fail(f'{code} has no tamper registered')
    assert code in REGISTRY[code](delivery), code
