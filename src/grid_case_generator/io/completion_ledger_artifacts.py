"""Canonical v1 completion-ledger artifact, its replay and its binding checks.

The artifact is the persisted form of ``generation/completion_ledger.py`` output: the
three record streams, the policy verbatim as consumed, the aggregate and the human
report. It is write-once, canonical JSON/JSONL, and carries no timestamp, so the same
inputs and the same policy reproduce it byte for byte.

``verify_artifact`` re-derives the whole ledger from the same inputs and compares every
byte, so a tampered record survives neither the checksum nor the replay. The upstream
roots are checked at integrity level here — canonical manifest, inventory and per-file
digest — while each upstream's own semantic replay stays with its own CLI, because
re-running D4.2's 1.4 GB counterfactual build inside every ledger write would make the
export unusable and would verify nothing the upstream command does not.
"""
from collections import Counter
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

from grid_case_generator.generation.completion_ledger import (
    CompletionInputs, build_ledger)
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.deterministic_recovery_artifacts import (
    input_hashes as d3_hashes, read_json as read_artifact_json)
from grid_case_generator.io.source_artifacts import _artifact_member, _artifact_root
from grid_case_generator.io.source_bytes import raw_member_bytes
from grid_case_generator.io.switch_projection_artifacts import check_output
from grid_case_generator.models.completion_export import (
    VERSION, parse_policy, policy_bytes, policy_sha256)

SCOPE = 'COMPLETION_LEDGER'
STREAMS = ('completion_records', 'unresolved_records', 'case_summary')
FILES = tuple(name + '.jsonl' for name in STREAMS) + (
    'policy_snapshot.json', 'summary.json', 'report.md')
D3_ROOTS = frozenset({'source', 'baseline', 'projection', 'feeder', 'recovery', 'd1', 'd2',
                      'frozen'})
EXTRA_ROOTS = ('d3_analysis', 'accepted_v2', 'd4', 'placement', 'audit')
INPUTS = D3_ROOTS | frozenset(EXTRA_ROOTS)
BUS_MEMBER = '02_Bus.csv'
# The v1 pipeline's own code. A curated list, not every file under ``src``: a fingerprint
# over the whole tree would invalidate a published artifact the moment an unrelated
# module changed, and the semantic replay — not the hash — is what actually catches a
# tampered record.
CODE_FILES = ('generation/completion_ledger.py', 'io/completion_ledger_artifacts.py',
              'io/derived_delivery_artifacts.py', 'models/completion_export.py',
              'validation/completion_export.py', 'analysis/completion_export_cli.py')


def code_hash():
    root = Path(__file__).resolve().parents[1]
    entries = {name: sha256((root / name).read_bytes()).hexdigest() for name in CODE_FILES
               if (root / name).exists()}
    return sha256(canonical_json_bytes(entries)).hexdigest()


def read_lines(root, name):
    with _artifact_member(_artifact_root(root), name).open() as stream:
        yield from map(json.loads, stream)


def manifest_of(root):
    return read_artifact_json(root, 'manifest.json')


def verify_manifests(roots):
    """Integrity-check every root: canonical manifest, inventory, per-file digest.

    This is the binding level, not a semantic replay. Each upstream's own ``verify``
    command re-derives its stream from its inputs; running five of those inside a ledger
    write would cost hours and prove nothing the ledger itself depends on, because the
    ledger binds the upstream *manifest digests* and re-checks them before and after the
    run.
    """
    if set(roots) != INPUTS:
        raise ValueError('v1 ledger requires all thirteen roots')
    for name in sorted(roots):
        root = _artifact_root(roots[name])
        manifest = json.loads(_artifact_member(root, 'manifest.json').read_text())
        files = manifest.get('files')
        if not isinstance(files, dict) or not files:
            raise ValueError(f'v1 ledger upstream {name} has no file inventory')
        observed = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
        # Audit and D4.1 manifests also record the manifest itself; accept either form.
        if observed != set(files) | {'manifest.json'} and observed != set(files):
            raise ValueError(f'v1 ledger upstream {name} inventory mismatch')
        for relative, entry in sorted(files.items()):
            # Some manifests record themselves; a manifest cannot contain its own digest,
            # so that entry is an inventory statement, not a checksum claim.
            if relative == 'manifest.json':
                continue
            data = _artifact_member(root, relative).read_bytes()
            if sha256(data).hexdigest() != entry['sha256']:
                raise ValueError(f'v1 ledger upstream {name} checksum mismatch: {relative}')
            if len(data.splitlines()) != entry['record_count']:
                raise ValueError(f'v1 ledger upstream {name} count mismatch: {relative}')
    return True


def bindings(roots):
    """The thirteen upstream manifest digests the artifact binds."""
    if set(roots) != INPUTS:
        raise ValueError('v1 ledger requires all thirteen roots')
    hashes = d3_hashes({name: roots[name] for name in D3_ROOTS})
    hashes.update({name: sha256((Path(roots[name]) / 'manifest.json').read_bytes()).hexdigest()
                   for name in EXTRA_ROOTS})
    return hashes


# --- loading the thirteen roots ------------------------------------------------


def source_inventory(source_root):
    """``(case_id, source_case_key, members)`` triples, ascending by ``source_case_key``.

    ``inventory.json`` carries the members but not the ``case_id``; ``import_report.json``
    carries both and is written in the same order. The two are cross-checked rather than
    trusted, because a positional join that silently misaligns would deliver every Case's
    rows under its neighbour's key.
    """
    inventory = read_artifact_json(source_root, 'inventory.json')
    report = read_artifact_json(source_root, 'import_report.json')
    entries, identified = inventory['cases'], report['cases']
    if len(entries) != len(identified):
        raise ValueError('v1 ledger source inventory and import report disagree in length')
    cases = []
    for entry, identity in zip(entries, identified):
        if entry['source_case_key'] != identity['source_case_key']:
            raise ValueError('v1 ledger source inventory and import report disagree in order')
        members = tuple((file_type, member) for file_type, member in entry['members'])
        cases.append((identity['case_id'], entry['source_case_key'], members))
    keys = [case[1] for case in cases]
    if keys != sorted(keys) or len(set(keys)) != len(keys):
        raise ValueError('v1 ledger source inventory is not ordered by source_case_key')
    return tuple(cases)


def source_archive(source_root):
    """The raw ZIP the import artifact recorded, resolved and hash-checked.

    The artifact stores the archive's identity, not a usable path, so the path is derived
    from the recorded relative URI and then held to the recorded checksum. A mismatch is
    fatal: reading the wrong archive would deliver a complete and internally consistent
    tree for a different intake.
    """
    dataset = read_artifact_json(source_root, 'dataset.json')
    path = Path(dataset['source_uri'])
    if not path.is_file():
        raise ValueError(f'v1 ledger source archive absent: {dataset["source_uri"]}')
    digest = sha256(path.read_bytes()).hexdigest()
    expected = str(dataset['source_checksum']).split(':', 1)[-1]
    if digest != expected:
        raise ValueError('v1 ledger source archive checksum mismatch')
    return path


def _bus_member_bytes(cases, archive_path, wanted):
    """The referring Cases' ``02_Bus.csv`` bytes, the station join's only input.

    Only the Cases the placement rule actually proposes in are read, and a Case whose
    inventory carries no ``02_Bus.csv`` is simply absent — the rule reads that absence as
    "no unambiguous station evidence", which is what the contract measured for the 20
    Cases without one.
    """
    by_case = {case_id: (key, members) for case_id, key, members in cases}
    have = {}
    missing = []
    for case_id in sorted(wanted):
        if case_id not in by_case:
            raise ValueError(f'v1 ledger placement Case outside the source inventory: {case_id}')
        key, members = by_case[case_id]
        if any(member == f'{key}/{BUS_MEMBER}' for _file_type, member in members):
            have[case_id] = key
        else:
            missing.append(case_id)
    out = {}
    with ZipFile(archive_path, 'r') as archive:
        for case_id, key in sorted(have.items()):
            out[case_id] = raw_member_bytes(archive, f'{key}/{BUS_MEMBER}')
    return out, missing


def inputs_from_artifacts(roots, policy):
    """Assemble the engine's inputs from the thirteen verified roots.

    Every stream is read whole and in file order; the engine owns ordering, so nothing
    here sorts. ``source_case_key_by_case`` is cross-checked against the audit's own
    ``source_case_key`` because the engine raises on an unknown Case and a disagreement
    between the two artifacts would otherwise surface as a confusing unknown-Case error.
    """
    cases = source_inventory(roots['source'])
    archive = source_archive(roots['source'])
    case_keys = {case_id: key for case_id, key, _members in cases}

    audit_cases = tuple(read_lines(roots['audit'], 'case_inventory.jsonl'))
    for row in audit_cases:
        known = case_keys.get(row['case_id'])
        if known is not None and row.get('source_case_key') not in (None, known):
            raise ValueError('v1 ledger audit and source import disagree on a Case key')

    placement_proposals = tuple(read_lines(roots['placement'], 'line_component_proposals.jsonl'))
    endpoint_evidence = tuple(read_lines(roots['placement'], 'line_endpoint_evidence.jsonl'))
    placement_feeders = tuple(read_lines(roots['placement'], 'feeder_classification.jsonl'))
    bus_bytes, absent = _bus_member_bytes(
        cases, archive, {p['case_id'] for p in placement_proposals})

    return CompletionInputs(
        policy=policy,
        source_case_key_by_case=case_keys,
        audit_rows=tuple(read_lines(roots['audit'], 'cross_case_references.jsonl')),
        accepted_additions=tuple(read_lines(roots['d3_analysis'], 'accepted_connections.jsonl')),
        placement_proposals=placement_proposals,
        endpoint_evidence=endpoint_evidence,
        placement_feeders=placement_feeders,
        backbone_taxonomy=tuple(read_lines(roots['d4'], 'feeder_gap_taxonomy.jsonl')),
        # Nothing in the engine reads this stream; it is carried because the input
        # contract requires it, and left empty rather than re-projecting a stream that
        # would then look load-bearing.
        audit_classification=(),
        audit_cases=audit_cases,
        bus_member_bytes_by_case=bus_bytes)


# --- the artifact ---------------------------------------------------------------


def summarize(ledger):
    """The aggregate view: counts, per-rule, per-status and the UNRESOLVED taxonomy."""
    completion, unresolved = ledger.completion_records, ledger.unresolved_records
    return {
        'counts': dict(sorted(ledger.counts.items())),
        'case_count': len({r['case_id'] for r in (*completion, *unresolved)}),
        'status_counts': dict(sorted(Counter(
            r['completion_status'] for r in completion).items())),
        'rule_counts': dict(sorted(Counter(
            r['rule_id'] for r in completion).items())),
        'tier_counts': dict(sorted(Counter(
            r['tier'] for r in completion if r['tier']).items())),
        'unresolved_rule_counts': dict(sorted(Counter(
            r['rule_id'] for r in unresolved).items())),
        'reason_counts': dict(sorted(Counter(
            r['reason'] for r in unresolved).items())),
    }


def render_report(summary, policy, inputs, counts):
    """The human report: every count is one the run measured."""
    lines = [
        '# Nanjing v1 completion ledger',
        '',
        '**approved: false — applied: false.** This artifact authorizes nothing. Every',
        'record below is evidence about a proposal; no completion here has been approved,',
        'applied or promoted, and no canonical, accepted-v2 or source object was changed.',
        '',
        '## What this is',
        '',
        'A completion ledger over the frozen source intake. It states, per Case and per',
        'raw reference, which completions the enabled rules proposed, which they refused',
        'and why, and where every piece of supporting evidence lives. It is the evidence',
        'trail the delivery is built from; the delivery itself is a separate artifact.',
        '',
        f'- Cases in the source inventory: {len(inputs.source_case_key_by_case)}',
        f'- Cases represented in this ledger: {summary["case_count"]}',
        f'- Policy: `{policy.policy_version}` (sha256 `{policy_sha256(policy)}`)',
        f'- Enabled rules: {", ".join(policy.enabled_rules)}',
        f'- Materialized tiers: {", ".join(policy.materialize_tiers)}',
        f'- Reference closure bound: {policy.max_reference_closure_depth}',
        f'- Placement endpoint Bus rule: '
        f'{"on" if policy.placement_endpoint_bus else "off"}',
        '',
        '## Counts',
        '',
        '| Measure | Value |',
        '|---|---:|',
    ]
    for name, value in sorted(summary['counts'].items()):
        lines.append(f'| `{name}` | {value} |')
    lines += [
        '',
        f'`addition_count` counts the `PROPOSED` records the materializing rules',
        f'contributed; `appended_row_count` counts the rows those records actually write.',
        f'They differ whenever several references share one row, and neither is hardcoded.',
        '',
        '## Completion records by rule',
        '',
        '| Rule | Records |',
        '|---|---:|',
    ]
    for name, value in sorted(summary['rule_counts'].items()):
        lines.append(f'| `{name}` | {value} |')
    lines += [
        '',
        'Every one of them is `PROPOSED`. A `PROPOSED` record stays `PROPOSED` regardless',
        'of the upstream D2/D4/D4.1 lifecycle; only `SOURCE_PASSTHROUGH_V1` and the',
        'D3-accepted recovery rule reach `CONFIRMED`, and neither of those materializes a',
        'new object here.',
        '',
        '## UNRESOLVED taxonomy',
        '',
        'Nothing in this section is written to a delivered CSV. Every entry is one ledger',
        'record with its own reason.',
        '',
        '| Reason | Records |',
        '|---|---:|',
    ]
    for name, value in sorted(summary['reason_counts'].items()):
        lines.append(f'| `{name}` | {value} |')
    overlap = counts['cohort_overlap_members']
    lines += [
        '',
        f'The four cohort reasons are not mutually exclusive and',
        f'`counts["cohort_overlap_members"]` reports the overlap explicitly: **{overlap}**',
        'distinct `(case_id, feeder_id)` identities appear under more than one reason.',
        'Consumers must use that count rather than summing the per-reason populations.',
        '',
        '## Known limitations',
        '',
        '1. The D4.2 `voltage_relationship == "COMPATIBLE"` check on `SAME_STATION`',
        '   candidates rests on `voltage_basis == "SOURCE_HEAD_CONTEXT"`, comparing a',
        '   station-head context rather than terminal voltages. It is an evidence tier,',
        '   not a proven voltage equivalence.',
        '2. An appended row can introduce a reference that resolves neither in the',
        '   referring Case nor within the closure bound. Such references are recorded as',
        '   `UNRESOLVED` and are not resolved by this layer.',
        '3. `PLACEMENT_MISSING_ENDPOINT_BUS_V1` is the only rule that produces a row for an',
        '   entity with no source row of its own. A generated Bus row carries `Bus_ID` and',
        '   five null attributes, has no voltage evidence and no unambiguous station',
        '   evidence. These are **declaration completions**, not modelled buses; their',
        '   empty fields must not be read as zero, as a measured absence of the attribute,',
        '   or as an implication about the bus voltage or station.',
        '4. This ledger does not reduce the open question set. Q-CONN-001, Q-PHASE-001,',
        '   Q-TRANSFORMER-001, Q-SIMCONFIG-001 and Q-CASE-001 remain `OPEN`.',
        '',
        '## Boundaries honoured',
        '',
        '- `data/raw/` was opened read-only; no source byte, ID or reference was changed.',
        '- No canonical record, accepted topology v2 object or GridCase boundary was',
        '  created, edited or deleted.',
        '- No electrical parameter, Load row, DER row, Transformer, LV Bus or simulation',
        '  configuration was generated.',
        '- No candidate was selected by ordering, proximity or similarity; selection is',
        '  preconditions plus policy only.',
        '- No identifier was minted for any delivered row.',
        '',
    ]
    return '\n'.join(lines)


def ledger_events(inputs):
    """Yield ``(filename, row)`` for the whole artifact, in the artifact's own order.

    ``report.md`` yields ``str``; every other stream yields a canonical JSON value.
    """
    ledger = build_ledger(inputs)
    summary = summarize(ledger)
    for row in ledger.completion_records:
        yield 'completion_records.jsonl', row
    for row in ledger.unresolved_records:
        yield 'unresolved_records.jsonl', row
    for row in ledger.case_summary:
        yield 'case_summary.jsonl', row
    yield 'policy_snapshot.json', json.loads(policy_bytes(inputs.policy))
    yield 'summary.json', summary
    yield 'report.md', render_report(summary, inputs.policy, inputs, ledger.counts)


def payload(name, row):
    return row.encode('utf-8') if name == 'report.md' else canonical_json_bytes(row) + b'\n'


def write_artifact(inputs, output, input_bindings, protected=None):
    check_output(output, protected or {})
    output = Path(output).absolute()
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    hashes = {name: sha256() for name in FILES}
    counts = {name: 0 for name in FILES}
    with ExitStack() as stack:
        streams = {name: stack.enter_context((output / name).open('xb')) for name in FILES}
        for name, row in ledger_events(inputs):
            data = payload(name, row)
            streams[name].write(data)
            hashes[name].update(data)
            # The report is one document, not one record per line; its count is its
            # line count, which is what a reader reconciling the manifest would count.
            counts[name] = len(data.splitlines()) if name.endswith('.md') else counts[name] + 1
    manifest = {
        'artifact_kind': SCOPE, 'version': VERSION, 'rule_version': VERSION,
        'schema_version': VERSION, 'input_manifest_sha256': input_bindings,
        'policy_version': inputs.policy.policy_version,
        'policy_sha256': policy_sha256(inputs.policy), 'code_sha256': code_hash(),
        'approved': False, 'applied': False, 'canonical_changed': False,
        'accepted_v2_changed': False, 'source_changed': False, 'e3_ready': False,
        'opendss_ready': False,
        'files': {name: {'sha256': hashes[name].hexdigest(), 'record_count': counts[name]}
                  for name in sorted(FILES)},
    }
    (output / 'manifest.json').write_bytes(canonical_json_bytes(manifest) + b'\n')
    return {'written': True, 'output': str(output), 'policy_sha256': manifest['policy_sha256'],
            'manifest_sha256': sha256(canonical_json_bytes(manifest) + b'\n').hexdigest()}


def _check_manifest(manifest, expected_bindings):
    if manifest.get('artifact_kind') != SCOPE:
        raise ValueError('v1 ledger artifact kind mismatch')
    if manifest.get('version') != VERSION or manifest.get('schema_version') != VERSION:
        raise ValueError('v1 ledger version mismatch')
    for flag in ('approved', 'applied', 'canonical_changed', 'accepted_v2_changed',
                 'source_changed', 'e3_ready', 'opendss_ready'):
        if manifest.get(flag) is not False:
            raise ValueError(f'v1 ledger scope violation: {flag}')
    if expected_bindings is not None and manifest['input_manifest_sha256'] != expected_bindings:
        raise ValueError('v1 ledger input binding mismatch')


def verify_artifact(output, *, inputs=None, expected_bindings=None):
    """Check the artifact against its own manifest, and replay it when inputs are given.

    The replay is the load-bearing check: a record rewritten *with* a rehashed manifest
    still fails, because the ledger is re-derived from the inputs and compared byte for
    byte.
    """
    output = _artifact_root(output)
    manifest = json.loads((output / 'manifest.json').read_text())
    _check_manifest(manifest, expected_bindings)
    if manifest.get('code_sha256') != code_hash():
        raise ValueError('v1 ledger code hash mismatch')
    observed = {str(p.relative_to(output)) for p in output.rglob('*') if p.is_file()}
    if observed != set(FILES) | {'manifest.json'}:
        raise ValueError('v1 ledger inventory mismatch')
    if set(manifest['files']) != set(FILES):
        raise ValueError('v1 ledger manifest inventory mismatch')
    for name, entry in sorted(manifest['files'].items()):
        data = (output / name).read_bytes()
        if sha256(data).hexdigest() != entry['sha256']:
            raise ValueError(f'v1 ledger checksum mismatch: {name}')
        if len(data.splitlines()) != entry['record_count']:
            raise ValueError(f'v1 ledger count mismatch: {name}')
        if name.endswith(('.json', '.jsonl')):
            for line in data.splitlines():
                if canonical_json_bytes(json.loads(line)) != line:
                    raise ValueError(f'v1 ledger noncanonical stream: {name}')
    # The snapshot is the policy verbatim as consumed, so it and the manifest's digest
    # must agree with each other even when the caller supplies no policy to compare to.
    snapshot_raw = (output / 'policy_snapshot.json').read_bytes()
    if sha256(snapshot_raw).hexdigest() != manifest['policy_sha256']:
        raise ValueError('v1 ledger policy_sha256 does not match its own snapshot')
    if inputs is not None:
        snapshot = json.loads(snapshot_raw)
        if snapshot != json.loads(policy_bytes(inputs.policy)):
            raise ValueError('v1 ledger policy snapshot mismatch')
        # Replay record by record against a bounded read, so a 100k-record stream is
        # compared without holding either the whole artifact or the whole expectation.
        with ExitStack() as stack:
            streams = {name: stack.enter_context((output / name).open('rb')) for name in FILES}
            for name, row in ledger_events(inputs):
                expected = payload(name, row)
                if streams[name].read(len(expected)) != expected:
                    raise ValueError(f'v1 ledger replay mismatch: {name}')
            if any(stream.read(1) for stream in streams.values()):
                raise ValueError('v1 ledger replay left extra records')
    return {'verified': True, 'input_bound': expected_bindings is not None,
            'policy_sha256': manifest['policy_sha256'],
            'manifest_sha256': sha256((output / 'manifest.json').read_bytes()).hexdigest()}


def run(roots, output, policy_path=None, verify=False, *, policy=None):
    """Build or re-verify the ledger artifact from the thirteen roots."""
    policy = policy or parse_policy(policy_path)
    check_output(output, roots)
    before = bindings(roots)
    verify_manifests(roots)
    built = inputs_from_artifacts(roots, policy)
    if verify:
        result = verify_artifact(output, inputs=built, expected_bindings=before)
    else:
        result = write_artifact(built, output, before, protected=roots)
        verify_artifact(output, inputs=built, expected_bindings=before)
    if bindings(roots) != before:
        raise ValueError('v1 ledger inputs changed during run')
    return result
