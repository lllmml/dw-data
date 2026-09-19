"""Byte-identical SOURCE_PASSTHROUGH_V1 delivery; the first slice that writes CSV.

The delivered ``data/`` tree streams each source ZIP member's raw bytes straight
to its destination path. No member is decoded and re-encoded — the ``csv`` module
never appears here, so quoting, newline convention and the UTF-8 BOM all survive
verbatim. One canonical provenance record is emitted per delivered source data
row into ``provenance/row_provenance.jsonl``.
"""
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.completion_ledger_artifacts import code_hash
from grid_case_generator.io.nanjing_source.locator import (
    SourceRecordRef, source_record_ref, validate_zip_member_path,
)
from grid_case_generator.io.source_bytes import (
    member_path_of, raw_member_bytes, split_raw_records,
)
from grid_case_generator.io.switch_projection_artifacts import check_output
from grid_case_generator.generation.completion_ledger import render_bus_row
from grid_case_generator.models.completion_export import (
    CROSS_CASE_RULE, CROSS_CASE_RULE_VERSION, PASSTHROUGH_RULE, PLACEMENT_BUS_RULE,
    PLACEMENT_BUS_RULE_VERSION, RULE_VERSION, VERSION, policy_sha256,
    provenance_id as provenance_id_of,
)

DELIVERY_DATA_DIR = 'data'
PROVENANCE_DIR = 'provenance'
ARCHIVE_NAME = 'nanjing-derived-v1.zip'
ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
DELIVERY_SCOPE = 'DERIVED_DELIVERY'
# Copied verbatim into the delivery's `provenance/` so the delivery is readable without
# the ledger artifact, as the contract requires.
LEDGER_COPIES = ('completion_records.jsonl', 'unresolved_records.jsonl')

PROVENANCE_KEYS = ('provenance_id', 'case_id', 'source_case_key', 'target_file',
    'row_index', 'row_kind', 'completion_status', 'confidence_class', 'tier', 'rule_id',
    'rule_version', 'source_record_ref', 'donor_source_record_ref', 'raw_field',
    'raw_reference_value', 'evidence_refs', 'policy_id', 'policy_sha256')


class _MemberCache:
    """Read each source member once and split it at most once, keyed by member path.

    Both memos are keyed by member path and share one read, so a member that is
    delivered *and* used as a donor row source is read and split exactly once. A
    content-keyed cache would not do: several Cases ship byte-identical members.

    The memos live for the whole run, because a donor member may be delivered before
    or after the Case that refers to it, so nothing may be evicted on delivery. The
    run's ceiling is therefore the uncompressed size of the archive — bounded, but
    linear in it, where an evicting cache would be bounded by the largest Case.
    """
    def __init__(self, archive):
        self._archive, self._bytes, self._records = archive, {}, {}

    def bytes(self, member_path):
        if member_path not in self._bytes:
            self._bytes[member_path] = raw_member_bytes(self._archive, member_path)
        return self._bytes[member_path]

    def records(self, member_path):
        if member_path not in self._records:
            self._records[member_path] = split_raw_records(self.bytes(member_path))
        return self._records[member_path]


def write_member(archive, member_path, destination, appended=(), *, data=None) -> bytes:
    """Stream one member's source bytes verbatim, then any appended donor rows.

    ``data`` lets a caller that has already read the member hand its bytes over
    rather than have them read a second time; when omitted the member is read here,
    so a standalone call still costs exactly one read.

    The ``endswith`` check is load-bearing: a member whose final record carries no
    terminator would otherwise have the appended block concatenated onto that record.
    The separator exists only to prevent two logical records from merging; it is not
    source normalization, so the source region stays verbatim and a member whose own
    terminators differ ends up mixed.
    """
    if data is None:
        data = raw_member_bytes(archive, member_path)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
        if appended:
            if not data.endswith((b'\r\n', b'\n', b'\r')):
                stream.write(b'\r\n')
            stream.write(b'\r\n'.join(appended) + b'\r\n')
    return data


def passthrough_member(archive, member_path, destination) -> bytes:
    """Stream one source member's raw bytes to ``destination``, verbatim."""
    return write_member(archive, member_path, destination)


def render_report(result, ledger_summary):
    """The delivery's human report, stating every fact the contract requires of it."""
    rules = ledger_summary.get('rule_counts', {})
    reasons = ledger_summary.get('reason_counts', {})
    lines = [
        '# Nanjing v1 completion delivery',
        '',
        '**approved: false — applied: false.** This delivery authorizes nothing and',
        'promotes nothing. It contains **PROPOSED** rows: completions the rules put',
        'forward and no one has approved. Every row\'s status is in',
        '`provenance/row_provenance.jsonl`, but a consumer that ignores the sidecar can',
        'still read a proposal as an assertion.',
        '',
        '## What was delivered',
        '',
        '| Measure | Value |',
        '|---|---:|',
        f'| Cases | {result["cases"]} |',
        f'| Delivered members | {result["members"]} |',
        f'| Source rows (verbatim) | {result["source_rows"]} |',
        f'| Appended rows | {result["appended_rows"]} |',
        f'| .. of which generated Bus declaration rows | {result["placement_rows"]} |',
        '',
        'Every member with no appended row is byte-identical to its source member: same',
        'BOM, same quoting, same line endings, same trailing terminator. `10_Load.csv`',
        'and `11_DER.csv` are delivered header-only, and `12_SimConfig.csv` is',
        'source-verbatim; no Load, DER, Transformer, LV Bus, profile or simulation',
        'parameter was generated.',
        '',
        '## Completion rules represented',
        '',
        '| Rule | Ledger records |',
        '|---|---:|',
    ]
    for name, value in sorted(rules.items()):
        lines.append(f'| `{name}` | {value} |')
    lines += [
        '',
        '`SOURCE_PASSTHROUGH_V1` contributes no ledger record by design: it is not a',
        'completion, and every source row\'s provenance is in the delivery sidecar.',
        '',
        '## What the appended rows rest on',
        '',
        '`CROSS_CASE_REFERENCE_COPY_V1` copies a donor Case\'s source row verbatim into a',
        'referring Case that names it. The `voltage_relationship == "COMPATIBLE"` check on',
        '`SAME_STATION` candidates rests on `voltage_basis == "SOURCE_HEAD_CONTEXT"`, which',
        'compares a station-head context rather than terminal voltages. It is an evidence',
        'tier, not a proven voltage equivalence. An appended row can also introduce a',
        'reference that resolves neither in the referring Case nor within the closure',
        'bound; those are recorded as `UNRESOLVED` and are not resolved by this delivery.',
        '',
        '## Generated Bus declaration rows',
        '',
        f'`PLACEMENT_MISSING_ENDPOINT_BUS_V1` wrote {result["placement_rows"]} Bus rows',
        'into `02_Bus.csv`. It is the only rule that produces a row for an entity with no',
        'source row of its own. Each carries `Bus_ID` — the source-declared endpoint text,',
        'verbatim, never minted — and five null attributes, because no consumed artifact',
        'carries voltage evidence or an unambiguous station for these endpoints.',
        '',
        '**These are declaration completions, not modelled buses**, and are the highest-',
        'scrutiny object in the delivery. Their empty fields must not be read as zero, as a',
        'measured absence of the attribute, or as an implication about the bus voltage or',
        'station. `08_Line.csv` receives no row: the proposal is a placement',
        'representation of a Line that already exists, carrying `NOT_A_NEW_LINE_DEVICE`.',
        '',
        '## UNRESOLVED taxonomy',
        '',
        'Nothing in this section is written to a delivered CSV.',
        '',
        '| Reason | Records |',
        '|---|---:|',
    ]
    for name, value in sorted(reasons.items()):
        lines.append(f'| `{name}` | {value} |')
    lines += [
        '',
        '## Open questions',
        '',
        'This delivery does not reduce the open question set. Q-CONN-001, Q-PHASE-001,',
        'Q-TRANSFORMER-001, Q-SIMCONFIG-001 and Q-CASE-001 remain `OPEN`.',
        '',
    ]
    return '\n'.join(lines)


def write_delivery(root, *, archive_path, cases, policy, roots, append_plan=(), bus_plan=(),
                   ledger_root=None, input_bindings=None, progress=None):
    """Write the v1 delivery tree: every source member byte-identical, plus provenance.

    ``cases`` is an iterable of ``(case_id, source_case_key, members)`` from a
    verified source-import artifact, so its ordering is already canonical; it is
    asserted here rather than re-derived. The inventory is ordered by
    ``source_case_key``; ``case_id`` is a sha256-derived hash and carries no
    ordering guarantee, so the assertion keys on ``source_case_key``.

    Two plans append rows to a member: ``append_plan`` copies a donor Case's source row
    verbatim, ``bus_plan`` renders a generated Bus row from the values the placement
    rule derived. Both produce ``APPENDED`` provenance, ordered by ``rule_id``.

    ``cases`` is materialized, because both the ordering assertion and the check that
    every plan destination is a member the inventory carries are whole-inventory
    questions, and both must be answered before the first byte is written. A plan
    entry naming an undelivered member would otherwise drop a row with nothing to
    show for it, and a partially written tree left by a late failure cannot be retried
    (the target is write-once).
    """
    root = Path(root)
    check_output(root, roots)
    resolved = root.resolve()
    if any(p.name == 'raw' and p.parent.name == 'data' for p in (resolved, *resolved.parents)):
        raise ValueError('v1 delivery output cannot be data/raw')
    if root.exists():
        raise FileExistsError(root)

    inventory = []
    previous = None
    for case_id, case_key, members in cases:
        if previous is not None and case_key <= previous:
            raise ValueError('v1 delivery case ordering')
        previous = case_key
        inventory.append((case_id, case_key, tuple(members)))

    append_by_member = {}
    for entry in append_plan:
        append_by_member.setdefault(entry['destination_member'], []).append(entry)
    bus_by_member = {}
    for entry in bus_plan:
        bus_by_member.setdefault(entry['destination_member'], []).append(entry)
    delivered = {member for _, _, members in inventory for _file_type, member in members}
    dropped = sorted((set(append_by_member) | set(bus_by_member)) - delivered)
    if dropped:
        raise ValueError('v1 delivery plan member outside the delivered inventory: '
                         + dropped[0])

    root.mkdir(parents=True)
    provenance_dir = root / PROVENANCE_DIR
    provenance_dir.mkdir(parents=True, exist_ok=True)
    provenance_path = provenance_dir / 'row_provenance.jsonl'

    policy_id = policy.policy_version
    policy_hash = policy_sha256(policy)

    case_count = 0
    member_count = 0
    source_rows = 0
    appended_rows = 0
    placement_rows = 0

    with ZipFile(archive_path, 'r') as archive, provenance_path.open('xb') as stream:
        cache = _MemberCache(archive)
        for case_index, (case_id, case_key, members) in enumerate(inventory, 1):
            case_count += 1
            for _file_type, member_path in members:
                validate_zip_member_path(member_path)
                if not member_path.startswith(case_key + '/'):
                    raise ValueError('v1 delivery member outside its case scope: ' + member_path)
                filename = member_path.rsplit('/', 1)[-1]
                planned = append_by_member.get(member_path, ())
                generated = bus_by_member.get(member_path, ())
                blocks = []
                for entry in planned:
                    ref = SourceRecordRef(entry['donor_source_record_ref'])
                    blocks.append((CROSS_CASE_RULE,
                                   cache.records(member_path_of(ref))[ref.data_row],
                                   {'completion_status': 'PROPOSED',
                                    'confidence_class': 'UNIQUE_EVIDENCE',
                                    'tier': entry['tier'],
                                    'rule_id': CROSS_CASE_RULE,
                                    'rule_version': CROSS_CASE_RULE_VERSION,
                                    'source_record_ref': entry['source_record_ref'],
                                    'donor_source_record_ref': entry['donor_source_record_ref'],
                                    'raw_field': None,
                                    'raw_reference_value': None,
                                    'evidence_refs': list(entry['record_ids'])}))
                for entry in generated:
                    # render_bus_row emits a terminated record line; the append block
                    # joins terminator-free records, exactly as a copied donor row is.
                    blocks.append((PLACEMENT_BUS_RULE,
                                   render_bus_row(entry['values']).removesuffix(b'\r\n'),
                                   {'completion_status': 'PROPOSED',
                                    'confidence_class': 'ENGINEERING_DEFAULT',
                                    'tier': entry['tier'],
                                    'rule_id': PLACEMENT_BUS_RULE,
                                    'rule_version': PLACEMENT_BUS_RULE_VERSION,
                                    'source_record_ref': entry['source_record_ref'],
                                    'donor_source_record_ref': None,
                                    'raw_field': entry['raw_field'],
                                    'raw_reference_value': entry['raw_reference_value'],
                                    'evidence_refs': list(entry['record_ids'])}))
                # A member's appended rows are ordered by ``rule_id``, as the contract
                # states. The sort is stable, so each rule keeps its own deterministic
                # plan order; the contract's secondary key, ``provenance_id``, hashes
                # ``row_index``, which this ordering itself determines, so it cannot be
                # a sort key.
                blocks = sorted(blocks, key=lambda block: block[0])
                appended = [block[1] for block in blocks]
                appended_provenance = [block[2] for block in blocks]
                data = cache.bytes(member_path)
                records = cache.records(member_path)
                write_member(archive, member_path,
                             root / DELIVERY_DATA_DIR / case_key / filename,
                             appended=appended, data=data)
                member_count += 1
                n_source = max(0, len(records) - 1)
                source_rows += n_source
                appended_rows += len(appended)
                placement_rows += len(generated)
                for n in range(1, len(records)):
                    record = {
                        'case_id': case_id,
                        'source_case_key': case_key,
                        'target_file': filename,
                        'row_index': n - 1,
                        'row_kind': 'SOURCE',
                        'completion_status': 'CONFIRMED',
                        'confidence_class': 'EXACT_STRUCTURAL',
                        'tier': None,
                        'rule_id': PASSTHROUGH_RULE,
                        'rule_version': RULE_VERSION,
                        'source_record_ref': source_record_ref(member_path, data_row=n),
                        'donor_source_record_ref': None,
                        'raw_field': None,
                        'raw_reference_value': None,
                        'evidence_refs': [],
                        'policy_id': policy_id,
                        'policy_sha256': policy_hash,
                    }
                    record['provenance_id'] = provenance_id_of(
                        {k: record[k] for k in PROVENANCE_KEYS if k != 'provenance_id'})
                    stream.write(canonical_json_bytes(record) + b'\n')
                for j, fields in enumerate(appended_provenance):
                    record = {
                        'case_id': case_id,
                        'source_case_key': case_key,
                        'target_file': filename,
                        'row_index': n_source + j,
                        'row_kind': 'APPENDED',
                        'policy_id': policy_id,
                        'policy_sha256': policy_hash,
                        **fields,
                    }
                    record['provenance_id'] = provenance_id_of(
                        {k: record[k] for k in PROVENANCE_KEYS if k != 'provenance_id'})
                    stream.write(canonical_json_bytes(record) + b'\n')
            if progress is not None:
                progress(case_index, case_id)

    # The plans are the row arithmetic's own statement of what should have been written,
    # so a plan entry lost inside the loops above cannot pass as a complete delivery.
    planned_rows = len(append_plan) + len(bus_plan)
    if appended_rows != planned_rows:
        raise ValueError(f'v1 delivery wrote {appended_rows} appended rows for '
                         f'{planned_rows} plan entries')

    result = {'cases': case_count, 'members': member_count, 'source_rows': source_rows,
              'appended_rows': appended_rows, 'placement_rows': placement_rows}
    result['ledger_manifest_sha256'] = _copy_ledger_streams(root, ledger_root)
    result['source_archive_sha256'] = sha256(Path(archive_path).read_bytes()).hexdigest()
    ledger_summary = _ledger_summary(ledger_root)
    (root / 'report.md').write_bytes(render_report(result, ledger_summary).encode('utf-8'))
    result['manifest_sha256'] = _write_manifest(
        root, policy, result, input_bindings, ledger_summary)
    return result


def _copy_ledger_streams(root, ledger_root):
    """Copy the ledger's two record streams in verbatim, and return its manifest hash.

    The copy is byte-for-byte, so a recipient can locate every gap and every inference
    from the delivery alone without re-running the pipeline or holding the ledger
    artifact, and the two copies can be diffed against their origin.
    """
    if ledger_root is None:
        return None
    ledger_root = Path(ledger_root)
    for name in LEDGER_COPIES:
        source = ledger_root / name
        if not source.is_file():
            raise ValueError(f'v1 delivery ledger artifact is missing {name}')
        (root / PROVENANCE_DIR / name).write_bytes(source.read_bytes())
    return sha256((ledger_root / 'manifest.json').read_bytes()).hexdigest()


def _ledger_summary(ledger_root):
    if ledger_root is None:
        return {}
    return json.loads((Path(ledger_root) / 'summary.json').read_text())


def _write_manifest(root, policy, result, input_bindings, ledger_summary):
    """Write ``manifest.json`` last, over the inventory it has just measured.

    The manifest inventories every delivered file **except itself and the archive**, so
    the archive's digest is stored outside it, in the verification sidecar and the CLI
    result. No recursive hashing is performed.
    """
    files = {}
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.name == 'manifest.json':
            continue
        data = path.read_bytes()
        files[str(path.relative_to(root))] = {
            'sha256': sha256(data).hexdigest(), 'record_count': len(data.splitlines())}
    manifest = {
        'artifact_kind': DELIVERY_SCOPE, 'version': VERSION, 'rule_version': VERSION,
        'schema_version': VERSION, 'policy_sha256': policy_sha256(policy),
        'code_sha256': code_hash(), 'input_manifest_sha256': input_bindings,
        'ledger_manifest_sha256': result['ledger_manifest_sha256'],
        'source_archive_sha256': result['source_archive_sha256'],
        'approved': False, 'applied': False, 'canonical_changed': False,
        'accepted_v2_changed': False, 'source_changed': False, 'e3_ready': False,
        'opendss_ready': False,
        'cases': result['cases'], 'members': result['members'],
        'source_rows': result['source_rows'], 'appended_rows': result['appended_rows'],
        'placement_rows': result['placement_rows'],
        'rules': {name: {'completion_records': count} for name, count
                  in sorted(ledger_summary.get('rule_counts', {}).items())},
        'files': files,
    }
    data = canonical_json_bytes(manifest) + b'\n'
    (root / 'manifest.json').write_bytes(data)
    return sha256(data).hexdigest()


def describe_archive(root, *, name=ARCHIVE_NAME):
    """The identity of an archive already on disk, without writing anything."""
    root = Path(root)
    data = (root / name).read_bytes()
    with ZipFile(root / name) as archive:
        entries = len(archive.namelist())
    return {'name': name, 'sha256': sha256(data).hexdigest(), 'entries': entries}


def build_archive(root, *, name=ARCHIVE_NAME, progress=None):
    """Write the deterministic delivery archive and return its identity.

    Every entry is a ``ZipInfo`` built here with a fixed timestamp and attributes: the
    ``ZipFile.write`` helper stamps the filesystem mtime, which would make the archive
    depend on when it was built. Entries are added in sorted path order, so two runs
    over identical inputs produce a byte-identical archive and one digest.

    The archive is excluded from its own entry list. ``ZipFile(..., 'w')`` truncates the
    target before the first write, so an archive that listed itself would be read back
    mid-write and embedded as a partial copy of itself — and the build would stop being
    idempotent, which is the whole point of it.
    """
    root = Path(root)
    names = sorted(str(p.relative_to(root)) for p in root.rglob('*')
                   if p.is_file() and str(p.relative_to(root)) != name)
    with ZipFile(root / name, 'w', ZIP_DEFLATED) as archive:
        for index, entry in enumerate(names, 1):
            info = ZipInfo(entry, date_time=ARCHIVE_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 0
            archive.writestr(info, (root / entry).read_bytes())
            if progress is not None:
                progress(index, entry)
    return describe_archive(root, name=name)
