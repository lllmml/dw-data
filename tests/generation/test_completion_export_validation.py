import json
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

import pytest
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.derived_delivery_artifacts import build_archive
from grid_case_generator.validation.completion_export import (
    PROVENANCE_KEYS, REASONS, validate_delivery)

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
    return fixture


def verdict(fixture, **overrides):
    kwargs = {'ledger_root': fixture.ledger, 'roots': fixture.roots,
              'policy': fixture.policy, 'archive': fixture.archive}
    kwargs.update(overrides)
    return validate_delivery(fixture.root, **kwargs)


def rewrite(path, mutate):
    records = [json.loads(line) for line in path.read_bytes().splitlines()]
    mutate(records)
    path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in records))


def reseal(fixture):
    """Re-hash the tampered tree into the manifest, so only a semantic check can catch it."""
    manifest_path = fixture.root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    for name in manifest['files']:
        data = (fixture.root / name).read_bytes()
        manifest['files'][name] = {'sha256': sha256(data).hexdigest(),
                                   'record_count': len(data.splitlines())}
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b'\n')


def test_clean_delivery_passes(delivery):
    assert verdict(delivery)['reasons'] == []
    assert verdict(delivery)['structural_status'] == 'PASS'




def test_semantics_are_checked_even_when_the_tree_is_resealed(delivery):
    """The clean run is not passing because the walk found nothing to look at."""
    assert verdict(delivery)['measured']['appended_rows'] > 0
    assert verdict(delivery)['measured']['delivered_rows'] > 0
    assert verdict(delivery)['measured']['provenance_records'] > 0


def test_a_missing_ledger_binding_is_rejected(delivery):
    manifest_path = delivery.root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['ledger_manifest_sha256'] = '0' * 64
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b'\n')
    assert 'LEDGER_BINDING_MISMATCH' in verdict(delivery)['reasons']


def test_a_policy_hash_mismatch_is_rejected(delivery):
    manifest_path = delivery.root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['policy_sha256'] = '0' * 64
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b'\n')
    assert 'POLICY_HASH_MISMATCH' in verdict(delivery)['reasons']


def test_a_stale_ledger_base_is_rejected(delivery):
    """A ledger built against a superseded accepted v2 may not back this delivery."""
    path = delivery.ledger / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['input_manifest_sha256'] = dict(manifest['input_manifest_sha256'],
                                             accepted_v2='0' * 64)
    path.write_bytes(canonical_json_bytes(manifest) + b'\n')
    # Re-binding the tampered manifest keeps LEDGER_BINDING_MISMATCH out of the way, so
    # this asserts the stale-base check itself and not the checksum that guards it.
    outer = delivery.root / 'manifest.json'
    rebound = json.loads(outer.read_text())
    rebound['ledger_manifest_sha256'] = sha256(path.read_bytes()).hexdigest()
    outer.write_bytes(canonical_json_bytes(rebound) + b'\n')
    accepted = delivery.tmp_path / 'accepted-v2'
    accepted.mkdir(exist_ok=True)
    (accepted / 'manifest.json').write_bytes(canonical_json_bytes({'rebuilt': True}) + b'\n')
    assert 'STALE_LEDGER_BASE' in verdict(
        delivery, roots=dict(delivery.roots, accepted_v2=accepted))['reasons']


def test_a_missing_member_is_rejected(delivery):
    (delivery.root / 'data' / delivery.referring_key / '09_Transformer.csv').unlink()
    assert 'MEMBER_MISSING' in verdict(delivery)['reasons']


def test_a_renamed_column_is_rejected(delivery):
    path = delivery.root / 'data' / delivery.referring_key / '01_Station.csv'
    data = path.read_bytes().replace(b'Station_ID', b'Station_Id', 1)
    path.write_bytes(data)
    assert 'CSV_COLUMN_SCHEMA_CHANGED' in verdict(delivery)['reasons']


def test_a_tampered_source_row_is_rejected(delivery):
    path = delivery.root / 'data' / delivery.referring_key / '02_Bus.csv'
    data = path.read_bytes().replace(b'B-BING-0', b'B-BING-X', 1)
    path.write_bytes(data)
    assert 'SOURCE_ROW_NOT_VERBATIM' in verdict(delivery)['reasons']


def test_a_tampered_appended_row_is_rejected(delivery):
    path = delivery.root / 'data' / delivery.referring_key / '02_Bus.csv'
    data = path.read_bytes().replace(b'B-DING-1', b'B-DING-9', 1)
    path.write_bytes(data)
    assert verdict(delivery)['structural_status'] == 'REJECTED'


def test_a_minted_bus_id_is_rejected(delivery):
    """A generated row may only carry an identity the source itself declared."""
    path = delivery.root / 'data' / delivery.referring_key / '02_Bus.csv'
    path.write_bytes(path.read_bytes().replace(
        delivery.raw_endpoint_value.encode(), b'MINTED-1', 1))
    assert verdict(delivery)['structural_status'] == 'REJECTED'


def test_a_dropped_provenance_row_is_rejected(delivery):
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rewrite(path, lambda rows: rows.pop(0))
    reseal(delivery)
    # Rebuild the archive too, so the tree is self-consistent and only the semantic
    # checks can object.
    from grid_case_generator.io.derived_delivery_artifacts import ARCHIVE_NAME, build_archive
    (delivery.root / ARCHIVE_NAME).unlink()
    build_archive(delivery.root)
    assert 'PROVENANCE_INCOMPLETE' in verdict(delivery)['reasons']
    assert verdict(delivery)['structural_status'] == 'REJECTED'


def test_a_provenance_row_for_a_nonexistent_row_is_rejected(delivery):
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rewrite(path, lambda rows: rows[0].update(row_index=9999))
    reseal(delivery)
    assert verdict(delivery)['structural_status'] == 'REJECTED'


def test_a_provenance_row_missing_a_key_is_rejected(delivery):
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rewrite(path, lambda rows: rows[0].pop('evidence_refs'))
    reseal(delivery)
    assert 'PROVENANCE_INCOMPLETE' in verdict(delivery)['reasons']


def test_a_duplicated_appended_row_is_rejected(delivery):
    path = delivery.root / 'data' / delivery.referring_key / '02_Bus.csv'
    data = path.read_bytes()
    last = data.split(b'\r\n')[-2]
    path.write_bytes(data + last + b'\r\n')
    assert verdict(delivery)['structural_status'] == 'REJECTED'


def test_an_unresolved_bus_value_written_as_a_row_is_rejected(delivery):
    """A row the ledger withheld must not appear in the delivery.

    The ledger is edited to claim the delivered Bus value was withheld for a join
    mismatch, which is exactly the disagreement a consumer would otherwise never see.
    """
    path = delivery.ledger / 'unresolved_records.jsonl'
    rewrite(path, lambda rows: rows[0].update(
        rule_id='PLACEMENT_MISSING_ENDPOINT_BUS_V1', reason='EVIDENCE_JOIN_MISMATCH',
        raw_reference_value=delivery.raw_endpoint_value))
    assert 'UNRESOLVED_ROW_WRITTEN' in verdict(delivery)['reasons']


def test_a_nulled_field_reason_is_not_mistaken_for_a_withheld_row(delivery):
    """A degradation record shares its value with the row it degraded."""
    path = delivery.ledger / 'unresolved_records.jsonl'
    rewrite(path, lambda rows: rows[0].update(
        rule_id='PLACEMENT_MISSING_ENDPOINT_BUS_V1', reason='VOLTAGE_EVIDENCE_ABSENT',
        raw_reference_value=delivery.raw_endpoint_value))
    assert 'UNRESOLVED_ROW_WRITTEN' not in verdict(delivery)['reasons']


def test_a_foreign_tier_in_the_ledger_is_rejected(delivery):
    path = delivery.ledger / 'completion_records.jsonl'
    rewrite(path, lambda rows: rows[0].update(tier='CROSS_STATION'))
    assert 'TIER_NOT_ENABLED' in verdict(delivery)['reasons']


def test_an_over_deep_ledger_record_is_rejected(delivery):
    path = delivery.ledger / 'completion_records.jsonl'
    rewrite(path, lambda rows: rows[0].update(closure_depth=99))
    assert 'CLOSURE_NOT_BOUNDED' in verdict(delivery)['reasons']


def test_the_archive_is_not_inventoried_in_the_manifest(delivery):
    assert 'ARCHIVE_INVENTORY_MISMATCH' not in verdict(delivery)['reasons']
    manifest_path = delivery.root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['files']['nanjing-derived-v1.zip'] = {'sha256': '0' * 64, 'record_count': 1}
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b'\n')
    assert 'ARCHIVE_INVENTORY_MISMATCH' in verdict(delivery)['reasons']


def test_an_extra_file_is_rejected(delivery):
    (delivery.root / 'stray.txt').write_bytes(b'x')
    assert 'ARCHIVE_INVENTORY_MISMATCH' in verdict(delivery)['reasons']


def test_skipped_checks_are_named_not_silently_passed(delivery):
    """Without roots the byte checks cannot run, and the verdict must say so."""
    result = validate_delivery(delivery.root)
    assert result['reasons'] == []
    assert 'SOURCE_ROW_NOT_VERBATIM' in result['measured']['checks_skipped']
    assert 'TIER_NOT_ENABLED' in result['measured']['checks_skipped']
    assert 'STALE_LEDGER_BASE' in result['measured']['checks_skipped']


def test_a_delivery_without_a_manifest_is_rejected(tmp_path):
    empty = tmp_path / 'empty'
    empty.mkdir()
    assert validate_delivery(empty)['structural_status'] == 'REJECTED'


def test_provenance_key_set_matches_the_writer(delivery):
    from grid_case_generator.io.derived_delivery_artifacts import PROVENANCE_KEYS as writer_keys
    assert set(PROVENANCE_KEYS) == set(writer_keys)
    rows = [json.loads(line) for line in
            (delivery.root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()]
    assert all(set(r) == set(PROVENANCE_KEYS) for r in rows)


def test_a_tier_not_materialized_record_is_not_a_tier_violation(delivery):
    """An UNRESOLVED record names the tier it was refused for; that is its job.

    `TIER_NOT_MATERIALIZED` carries `CROSS_STATION` whenever that tier is switched off,
    so a check that held every record to `materialize_tiers` would reject every real
    delivery that has one.
    """
    path = delivery.ledger / 'unresolved_records.jsonl'
    rewrite(path, lambda rows: rows[0].update(
        rule_id='COHORT_TAXONOMY_V1', reason='TIER_NOT_MATERIALIZED',
        completion_status='UNRESOLVED', tier='CROSS_STATION'))
    assert 'TIER_NOT_ENABLED' not in verdict(delivery)['reasons']


def test_a_materialized_cross_station_row_is_still_a_violation(delivery):
    path = delivery.ledger / 'completion_records.jsonl'
    rewrite(path, lambda rows: rows[0].update(
        completion_status='PROPOSED', tier='CROSS_STATION'))
    assert 'TIER_NOT_ENABLED' in verdict(delivery)['reasons']


# --- the checks a forged provenance record would otherwise choose for itself ---


def _first_appended(rows):
    return next(i for i, r in enumerate(rows) if r['row_kind'] == 'APPENDED')


def test_an_appended_row_cannot_claim_the_source_rule(delivery):
    """A row that calls itself SOURCE must not pick the cheapest byte test."""
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rewrite(path, lambda rows: rows[_first_appended(rows)].update(
        row_kind='SOURCE', rule_id='SOURCE_PASSTHROUGH_V1', donor_source_record_ref=None))
    assert verdict(delivery)['structural_status'] == 'REJECTED'


def test_a_source_row_must_mirror_its_own_position(delivery):
    """A SOURCE row that points at another member's row is not a passthrough."""
    from grid_case_generator.io.nanjing_source.locator import source_record_ref
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    elsewhere = str(source_record_ref(f'{delivery.referring_key}/03_Switch.csv', data_row=1))
    rewrite(path, lambda rows: rows[0].update(source_record_ref=elsewhere))
    assert 'SOURCE_ROW_NOT_VERBATIM' in verdict(delivery)['reasons']


def test_an_appended_row_cannot_claim_an_unknown_rule(delivery):
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rewrite(path, lambda rows: rows[_first_appended(rows)].update(rule_id='NOT_A_RULE'))
    assert 'APPENDED_EVIDENCE_MISMATCH' in verdict(delivery)['reasons']
    assert verdict(delivery)['structural_status'] == 'REJECTED'


def test_a_cross_case_row_without_a_donor_cannot_skip_the_byte_test(delivery):
    """The donor comparison is what makes a copied row a copy; nulling it must not hide it."""
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    cross = next(i for i, r in enumerate(rows) if r['rule_id'] == 'CROSS_CASE_REFERENCE_COPY_V1')
    rows[cross]['donor_source_record_ref'] = None
    path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
    assert 'PROVENANCE_INCOMPLETE' in verdict(delivery)['reasons']


def test_a_fabricated_row_with_a_forged_record_is_still_rejected(delivery):
    """The end-to-end bypass: a new row plus a record that dodges every byte test."""
    bus = delivery.root / 'data' / delivery.referring_key / '02_Bus.csv'
    bus.write_bytes(bus.read_bytes() + b'FABRICATED-BUS-1,,,,,\r\n')
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    forged = dict(rows[-1], row_kind='APPENDED', rule_id='SOURCE_PASSTHROUGH_V1',
                  donor_source_record_ref=None, row_index=rows[-1]['row_index'] + 1)
    rows.append(forged)
    path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
    assert verdict(delivery)['reasons']


def test_an_edited_delivered_file_is_caught_by_the_manifest(delivery):
    """Without re-hashing the manifest is an unchecked claim."""
    path = delivery.root / 'data' / delivery.referring_key / '01_Station.csv'
    path.write_bytes(path.read_bytes() + b'S-X,,,,,\r\n')
    assert 'ARCHIVE_INVENTORY_MISMATCH' in verdict(delivery)['reasons']


def test_a_flipped_delivery_boundary_flag_is_rejected(delivery):
    """A manifest claiming approval is exactly what the sidecar exists to prevent."""
    path = delivery.root / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['approved'] = True
    manifest['e3_ready'] = True
    path.write_bytes(canonical_json_bytes(manifest) + b'\n')
    assert 'LEDGER_BINDING_MISMATCH' in verdict(delivery)['reasons']


def test_a_source_ref_to_an_absent_member_is_a_reason_not_a_crash(delivery):
    """A verifier that raises on a tampered tree is one a caller cannot use.

    A provenance record can name a source row the archive does not carry; the finding is
    the missing member, so it must arrive as a reason rather than as a traceback.
    """
    from grid_case_generator.io.nanjing_source.locator import source_record_ref
    path = delivery.root / 'provenance' / 'row_provenance.jsonl'
    ghost = str(source_record_ref(f'{delivery.referring_key}/99_Ghost.csv', data_row=1))
    rewrite(path, lambda rows: rows[0].update(source_record_ref=ghost))
    result = verdict(delivery)
    assert result['structural_status'] == 'REJECTED'
    assert 'MEMBER_MISSING' in result['reasons'] or 'SOURCE_ROW_NOT_VERBATIM' in result['reasons']
