"""Deterministic completion ledger, bounded closure walker, and rule bodies.

Implemented rule families: ``ACCEPTED_DETERMINISTIC_RECOVERY_V1`` emits one
``CONFIRMED`` record per accepted addition and appends no CSV row;
``COHORT_TAXONOMY_V1`` is classification-only, emitting ``UNRESOLVED`` records
that never materialize a row; ``CROSS_CASE_REFERENCE_COPY_V1`` copies a donor
Case's source row into the referring Case under its nine preconditions, emitting
``PROPOSED``/``UNIQUE_EVIDENCE`` records plus a de-duplicated append plan;
``PLACEMENT_MISSING_ENDPOINT_BUS_V1`` declares one ``PROPOSED``/
``ENGINEERING_DEFAULT`` Bus row per distinct unresolved endpoint value, emitting
a bus plan the delivery writer renders. The module performs no filesystem or
network IO: ``build_ledger`` receives already-loaded rows, and the referring
Case's ``02_Bus.csv`` bytes, and returns the assembled ledger.

Forward constraint for Slices 4-7: ``record_id`` hashes ``evidence_refs`` in
list order, so any rule assembling ``evidence_refs`` from a set or dict must
sort it first, or record identity will churn between runs.
"""
import csv
import io
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.source_bytes import member_path_of
from grid_case_generator.models.completion_export import (
    CROSS_CASE_RULE, CROSS_CASE_RULE_VERSION, PLACEMENT_BUS_RULE,
    PLACEMENT_BUS_RULE_VERSION, RECOVERY_RULE, CompletionPolicy, ledger_id,
    policy_sha256)

RECORD_KEYS = ('record_id', 'completion_status', 'confidence_class', 'tier', 'rule_id',
    'rule_version', 'case_id', 'source_case_key', 'source_entity_type',
    'donor_source_entity_type', 'source_record_ref', 'donor_source_record_ref',
    'raw_field', 'raw_reference_value', 'evidence_refs', 'closure_depth',
    'policy_version', 'policy_sha256', 'reason')

COUNTS_KEYS = ('completion_records', 'unresolved_records', 'addition_count',
               'appended_row_count', 'cohort_overlap_members')

RECOVERY_RULE_VERSION = '1.0.0'
COHORT_RULE = 'COHORT_TAXONOMY_V1'
COHORT_RULE_VERSION = '1.0.0'
PLACEMENT_COHORT_REASONS = ('INSUFFICIENT_PLACEMENT_EVIDENCE', 'NON_UNIQUE_PLACEMENT')
BACKBONE_COHORT_REASONS = ('MANUAL_LAYOUT_REQUIRED', 'NO_SOURCE_LINE_LAYOUT_BASIS')
COHORT_REASONS = PLACEMENT_COHORT_REASONS + BACKBONE_COHORT_REASONS

# ``PLACEMENT_MISSING_ENDPOINT_BUS_V1``. The generated row's column order is the
# source ``02_Bus.csv`` header's own order, so the delivery renders a row the source
# format would have accepted.
PLACEMENT_BUS_COLUMNS = ('Bus_ID', 'Bus_Name', 'Bus_BaseKV', 'Bus_Phase',
                         'Bus_Station_ID', 'Bus_IsSource')
PLACEMENT_ASSUMPTIONS = ('NOT_A_NEW_LINE_DEVICE',)
LINE_ENDPOINT_FIELDS = ('Line_FromBus', 'Line_ToBus')
PLACEMENT_BUS_FILE = '02_Bus.csv'
VOLTAGE_ABSENT = 'VOLTAGE_EVIDENCE_ABSENT'
VOLTAGE_CONFLICT = 'VOLTAGE_EVIDENCE_CONFLICT'
STATION_NOT_UNIQUE = 'STATION_EVIDENCE_NOT_UNIQUE'
EVIDENCE_JOIN_MISMATCH = 'EVIDENCE_JOIN_MISMATCH'
ACCEPTED_NODE = 'ACCEPTED_NODE'


@dataclass(frozen=True, slots=True, kw_only=True)
class CompletionInputs:
    policy: CompletionPolicy
    source_case_key_by_case: Mapping[str, str]
    audit_rows: tuple[dict, ...]
    accepted_additions: tuple[dict, ...]
    placement_proposals: tuple[dict, ...]
    endpoint_evidence: tuple[dict, ...]
    placement_feeders: tuple[dict, ...]
    backbone_taxonomy: tuple[dict, ...]
    audit_classification: tuple[dict, ...]
    audit_cases: tuple[dict, ...]
    bus_member_bytes_by_case: Mapping[str, bytes] = field(
        default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True, kw_only=True)
class Ledger:
    completion_records: tuple[dict, ...]
    unresolved_records: tuple[dict, ...]
    case_summary: tuple[dict, ...]
    counts: dict
    append_plan: tuple[dict, ...]
    bus_plan: tuple[dict, ...] = ()


def record(**fields) -> dict:
    """Build a plain-dict ledger record with an exact RECORD_KEYS key set.

    ``record_id`` is computed from every key except ``reason``; a caller must
    never supply it. Unknown keys raise ``ValueError`` rather than leaking a
    stray key into the record.
    """
    if 'record_id' in fields:
        raise ValueError("'record_id' is caller-supplied and must not be set")
    unknown = [name for name in fields if name not in RECORD_KEYS]
    if unknown:
        raise ValueError(f"unknown ledger record field {unknown[0]!r}")
    r = {name: fields.get(name) for name in RECORD_KEYS}
    r['record_id'] = ledger_id(
        {name: r[name] for name in RECORD_KEYS if name not in ('record_id', 'reason')})
    return r


def closure_key(case_id, source_entity_type, source_id) -> tuple:
    """Return the plain 3-tuple key for a closure visited-set."""
    return (case_id, source_entity_type, source_id)


def walk_closure(seed, lookup, *, max_depth):
    """Deterministic breadth-first walk yielding ``(key, meta)`` pairs.

    ``seed`` is visited but never yielded. Each level's frontier is sorted by
    ``closure_key`` before processing. A node whose depth exceeds ``max_depth``
    is reported with ``depth_exceeded`` True but never expanded.

    ``lookup(key)`` must return a finite iterable of 3-tuples. Exceptions
    raised by ``lookup`` propagate lazily during iteration, not at call time.
    The ``max_depth`` guard likewise raises on the first iteration of the
    generator, not at call time, consistent with that lazy-exception note.
    ``meta['reference']`` repeats the key today, since ``closure_key`` is
    currently the identity function. It is carried so callers need not
    re-derive the ref if the projection ever drops a field.
    """
    if type(max_depth) is not int or max_depth < 0:
        raise ValueError(f'v1 ledger closure depth bound: {max_depth!r} (int >= 0)')
    visited = {seed}
    frontier = sorted(lookup(seed), key=lambda ref: closure_key(*ref))
    depth = 1
    while frontier:
        next_frontier = []
        for ref in frontier:
            key = closure_key(*ref)
            if key in visited:
                continue
            visited.add(key)
            exceeded = depth > max_depth
            yield key, {'depth': depth, 'depth_exceeded': exceeded, 'reference': ref}
            if not exceeded:
                next_frontier.extend(lookup(key))
        frontier = sorted(next_frontier, key=lambda ref: closure_key(*ref))
        depth += 1


def order_records(records) -> tuple:
    return tuple(sorted(records, key=lambda r: (
        r['rule_id'] or '', r['case_id'] or '', r['record_id'] or '',
        r['reason'] or '', canonical_json_bytes(r))))


def order_unresolved(records) -> tuple:
    return tuple(sorted(records, key=lambda r: (
        r['reason'] or '', r['case_id'] or '', r['record_id'] or '',
        canonical_json_bytes(r))))


def recovery_records(inputs: CompletionInputs) -> tuple[dict, ...]:
    """Emit one CONFIRMED/EXACT_STRUCTURAL record per accepted addition.

    Gated by ``RECOVERY_RULE`` in ``policy.enabled_rules``. Ledger-only: this
    rule appends no CSV row.
    """
    if RECOVERY_RULE not in inputs.policy.enabled_rules:
        return ()
    policy_fields = {'policy_version': inputs.policy.policy_version,
                     'policy_sha256': policy_sha256(inputs.policy)}
    records = []
    for addition in inputs.accepted_additions:
        case_id = addition['case_id']
        source_case_key = inputs.source_case_key_by_case.get(case_id)
        if source_case_key is None:
            raise ValueError(f'v1 ledger unknown case {case_id!r} in accepted additions')
        supporting_ref = min(addition['supporting_source_refs'])
        records.append(record(
            completion_status='CONFIRMED', confidence_class='EXACT_STRUCTURAL',
            tier=None, rule_id=RECOVERY_RULE, rule_version=RECOVERY_RULE_VERSION,
            case_id=case_id, source_case_key=source_case_key,
            source_entity_type='EQUIPMENT',
            donor_source_entity_type=None, source_record_ref=supporting_ref,
            donor_source_record_ref=None, raw_field=None, raw_reference_value=None,
            evidence_refs=[addition['edge_id'],
                           addition['rule_id'] + '/' + addition['rule_version']],
            closure_depth=0, reason=None, **policy_fields))
    return tuple(records)


def _cohort_source_record_ref(row, reason) -> str:
    return f'cohort:{reason}:{row["case_id"]}:{row["feeder_id"]}'


def _emit_cohort(records, seen, reasons_by_feeder, row, reason, evidence_refs,
                 policy_fields) -> None:
    source_record_ref = _cohort_source_record_ref(row, reason)
    key = (reason, row['case_id'], source_record_ref)
    if key in seen:
        return
    seen.add(key)
    feeder_key = (row['case_id'], row['feeder_id'])
    reasons_by_feeder.setdefault(feeder_key, set()).add(reason)
    records.append(record(
        completion_status='UNRESOLVED', confidence_class='NONE',
        tier=None, rule_id=COHORT_RULE, rule_version=COHORT_RULE_VERSION,
        case_id=row['case_id'], source_case_key=row['source_case_key'],
        source_entity_type='FEEDER',
        donor_source_entity_type=None, source_record_ref=source_record_ref,
        donor_source_record_ref=None, raw_field=None, raw_reference_value=None,
        evidence_refs=evidence_refs, closure_depth=None,
        reason=reason, **policy_fields))


def cohort_records(inputs: CompletionInputs) -> tuple[tuple[dict, ...], int]:
    """Emit one UNRESOLVED/NONE record per feeder in a cohort, per reason.

    The taxonomy is unconditional: it is not gated by ``enabled_rules``. A
    feeder may legitimately receive one record per matching reason, so the
    cohorts are deliberately not made exclusive. Ledger-only: appends no CSV
    row.

    Returns ``(records, overlap_members)`` where ``overlap_members`` counts the
    distinct ``(case_id, feeder_id)`` identities reported under more than one
    reason, keyed structurally from the input rows rather than parsed from any
    output field.
    """
    policy_fields = {'policy_version': inputs.policy.policy_version,
                     'policy_sha256': policy_sha256(inputs.policy)}
    seen = set()
    reasons_by_feeder = {}
    records = []
    for row in inputs.placement_feeders:
        status = row['primary_status']
        if status not in PLACEMENT_COHORT_REASONS:
            continue
        _emit_cohort(records, seen, reasons_by_feeder, row, status,
                     ['feeder_classification.jsonl/' + row['feeder_id']],
                     policy_fields)
    for row in inputs.backbone_taxonomy:
        if row['d3_primary'] != 'SYNTHETIC_BACKBONE_REQUIRED':
            continue
        if row['outcome'] != 'MANUAL_LAYOUT_REQUIRED':
            continue
        evidence_refs = ['feeder_gap_taxonomy.jsonl/' + row['feeder_id'],
                         row['d3_primary']]
        _emit_cohort(records, seen, reasons_by_feeder, row, 'MANUAL_LAYOUT_REQUIRED',
                     evidence_refs, policy_fields)
        if row['source_line_count'] == 0:
            _emit_cohort(records, seen, reasons_by_feeder, row,
                         'NO_SOURCE_LINE_LAYOUT_BASIS', evidence_refs, policy_fields)
    overlap_members = sum(1 for reasons in reasons_by_feeder.values() if len(reasons) > 1)
    return tuple(records), overlap_members


def eligible(row, tiers, cases):
    if row['classification'] != 'UNIQUE_EXTERNAL_MATCH':
        return False, row['classification']
    if row['external_candidate_count'] != 1:
        return False, 'MULTIPLE_EXTERNAL_MATCH'
    candidate = (row.get('candidates') or [None])[0]
    if candidate is None:
        return False, 'NO_CANONICAL_CANDIDATE'
    if candidate['identity_status'] != 'UNIQUE':
        return False, 'AMBIGUOUS_IDENTITY'
    if not candidate.get('type_compatible'):
        return False, 'TYPE_INCOMPATIBLE'
    if not candidate.get('canonical_ref'):
        return False, 'NO_CANONICAL_CANDIDATE'
    if candidate.get('voltage_relationship') != 'COMPATIBLE':
        return False, 'VOLTAGE_NOT_COMPATIBLE'
    if row.get('local_candidate_count'):
        return False, 'ALSO_RESOLVES_CASE_LOCALLY'
    if cases.get(row['case_id'], {}).get('hard_blockers'):
        return False, 'REFERRING_CASE_HARD_BLOCKER'
    if cases.get(candidate['case_id'], {}).get('hard_blockers'):
        return False, 'DONOR_CASE_HARD_BLOCKER'
    if candidate['station_relationship'] not in tiers:
        return False, 'TIER_NOT_MATERIALIZED'
    return True, ''


def _source_case_key(inputs, case_id, context):
    key = inputs.source_case_key_by_case.get(case_id)
    if key is None:
        raise ValueError(f'v1 ledger unknown case {case_id!r} in {context}')
    return key


def cross_case_records(inputs: CompletionInputs):
    """Emit ``CROSS_CASE_REFERENCE_COPY_V1`` records and the append plan.

    Returns ``(completion_records, unresolved_records, append_plan)``. Gated by
    ``CROSS_CASE_RULE`` in ``policy.enabled_rules``. One ``PROPOSED``/
    ``UNIQUE_EVIDENCE`` record is emitted per audit reference that passes every
    precondition; each failing reference becomes an ``UNRESOLVED``/``NONE`` record
    under ``COHORT_RULE`` carrying the first failing reason. The append plan is
    de-duplicated on ``(destination_member, donor_source_record_ref)`` so a donor row
    shared by several references is written once, while every contributor's
    ``record_id`` is retained in that plan entry's ``record_ids``.
    """
    if CROSS_CASE_RULE not in inputs.policy.enabled_rules:
        return (), (), ()
    tiers = inputs.policy.materialize_tiers
    cases = {row['case_id']: row for row in inputs.audit_cases}
    policy_fields = {'policy_version': inputs.policy.policy_version,
                     'policy_sha256': policy_sha256(inputs.policy)}
    completion = []
    unresolved = []
    plan = {}
    for row in inputs.audit_rows:
        ok, reason = eligible(row, tiers, cases)
        candidate = (row.get('candidates') or [None])[0]
        source_case_key = _source_case_key(inputs, row['case_id'], 'cross-case references')
        if not ok:
            tier = (candidate['station_relationship']
                    if reason == 'TIER_NOT_MATERIALIZED' else None)
            evidence_refs = [row['reference_id']]
            if candidate is not None:
                evidence_refs.append(candidate['index_id'])
            unresolved.append(record(
                completion_status='UNRESOLVED', confidence_class='NONE',
                tier=tier, rule_id=COHORT_RULE, rule_version=COHORT_RULE_VERSION,
                case_id=row['case_id'], source_case_key=source_case_key,
                source_entity_type=row['source_entity_type'],
                donor_source_entity_type=None, source_record_ref=row['source_record_ref'],
                donor_source_record_ref=None, raw_field=None, raw_reference_value=None,
                evidence_refs=sorted(evidence_refs), closure_depth=None,
                reason=reason, **policy_fields))
            continue
        rec = record(
            completion_status='PROPOSED', confidence_class='UNIQUE_EVIDENCE',
            tier=candidate['station_relationship'],
            rule_id=CROSS_CASE_RULE, rule_version=CROSS_CASE_RULE_VERSION,
            case_id=row['case_id'], source_case_key=source_case_key,
            source_entity_type=row['source_entity_type'],
            donor_source_entity_type=candidate['source_entity_type'],
            source_record_ref=row['source_record_ref'],
            donor_source_record_ref=candidate['source_record_ref'],
            raw_field=row['raw_field'], raw_reference_value=row['raw_reference_value'],
            evidence_refs=sorted([row['reference_id'], candidate['index_id']]),
            closure_depth=0, reason=None, **policy_fields)
        completion.append(rec)
        donor_filename = member_path_of(candidate['source_record_ref']).rpartition('/')[2]
        destination_member = f'{source_case_key}/{donor_filename}'
        donor_ref = candidate['source_record_ref']
        key = (destination_member, donor_ref)
        entry = plan.get(key)
        if entry is None:
            # ``tier`` travels with the plan because the writer cannot derive it: with
            # more than one materialized tier the same rule emits both, so a literal in
            # the writer would report the wrong tier for a delivered row.
            plan[key] = {'destination_member': destination_member,
                         'donor_source_record_ref': donor_ref,
                         'source_record_ref': row['source_record_ref'],
                         'tier': rec['tier'],
                         'raw_field': row['raw_field'],
                         'raw_reference_value': row['raw_reference_value'],
                         'record_ids': [rec['record_id']]}
        else:
            entry['source_record_ref'] = min(entry['source_record_ref'],
                                             row['source_record_ref'])
            entry['record_ids'].append(rec['record_id'])
    # Merged entries necessarily agree on ``tier``: a shared destination member fixes
    # the referring Case's key, and a shared donor ref fixes the donor Case's, so both
    # references were audited against the same pair of Cases.
    append_plan = tuple(
        {'destination_member': entry['destination_member'],
         'donor_source_record_ref': entry['donor_source_record_ref'],
         'source_record_ref': entry['source_record_ref'],
         'tier': entry['tier'],
         'raw_field': entry['raw_field'],
         'raw_reference_value': entry['raw_reference_value'],
         'record_ids': tuple(sorted(entry['record_ids']))}
        for entry in sorted(plan.values(),
                            key=lambda e: (e['destination_member'],
                                           e['donor_source_record_ref'])))
    return tuple(completion), tuple(unresolved), append_plan


def station_value(bus_member_bytes) -> str | None:
    """Return the Case's single distinct non-empty ``Bus_Station_ID``, else ``None``.

    ``None`` means "no unambiguous evidence", which the rule records as
    ``STATION_EVIDENCE_NOT_UNIQUE``. It is never a tie-break: when several values are
    present, no ordering, proximity or name-similarity rule picks one. A member with
    no such column, or with no member bytes at all, is the same case.
    """
    if not bus_member_bytes:
        return None
    rows = list(csv.reader(io.StringIO(bus_member_bytes.decode('utf-8-sig'), newline='')))
    if not rows or 'Bus_Station_ID' not in rows[0]:
        return None
    index = rows[0].index('Bus_Station_ID')
    values = {row[index] for row in rows[1:] if len(row) > index and row[index]}
    return values.pop() if len(values) == 1 else None


def render_bus_row(values: Mapping) -> bytes:
    """Serialize one generated Bus row: CRLF-terminated, columns in source order.

    ``None`` is the ledger's and the sidecar's representation of an absent value and is
    mapped to an empty field here, at the serialization boundary only, which is the
    source format's own representation of absence.
    """
    missing = [name for name in PLACEMENT_BUS_COLUMNS if name not in values]
    if missing:
        raise ValueError(f'v1 placement bus row missing column {missing[0]!r}')
    unknown = [name for name in values if name not in PLACEMENT_BUS_COLUMNS]
    if unknown:
        raise ValueError(f'v1 placement bus row unknown column {unknown[0]!r}')
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\r\n')
    writer.writerow(['' if values[name] is None else values[name]
                     for name in PLACEMENT_BUS_COLUMNS])
    return stream.getvalue().encode('utf-8')


def _placement_ports(inputs: CompletionInputs) -> dict:
    """Group every non-accepted-node endpoint by ``(case_id, raw_endpoint_value)``.

    The group, not the port and not the proposal, is the rule's unit: one Bus row is
    written per group even when several ports or several proposals declare the same
    value. Grouping is per Case because the row lands in *that* Case's ``02_Bus.csv``.
    """
    groups = {}
    for proposal in inputs.placement_proposals:
        for endpoint in proposal['endpoints']:
            if endpoint['anchor_origin'] == ACCEPTED_NODE:
                continue
            side = endpoint['side']
            if side not in (1, 2):
                raise ValueError(f'v1 placement endpoint side: {side!r} (1 or 2)')
            port = {
                'source_line_id': proposal['source_line_id'],
                'source_line_record_ref': proposal['source_line_record_ref'],
                'endpoint_side': side,
                'proposal_id': proposal['proposal_id'],
                'anchor_id': endpoint['anchor_id'],
            }
            key = (proposal['case_id'], endpoint['raw_endpoint_value'])
            groups.setdefault(key, {})[(proposal['proposal_id'], side)] = port
    return groups


def _endpoint_evidence_locator(source_line_id, side) -> str:
    return f'line_endpoint_evidence.jsonl/{source_line_id}:{side}'


def _placement_bus(inputs: CompletionInputs) -> tuple:
    """Return ``(completion_records, unresolved_records, bus_plan)`` for the rule.

    Gated twice, as the contract states: the rule must be in ``enabled_rules`` and the
    ``placement_endpoint_bus`` policy lever must be on. Every port in a group is
    cross-checked against ``line_endpoint_evidence.jsonl`` before any value is copied;
    a disagreement is ``EVIDENCE_JOIN_MISMATCH`` and the group materializes nothing,
    because the join is what licenses the identity the row would carry. A value the
    evidence does not support stays null, and the null is reported as its own
    ``UNRESOLVED`` record: a materialized ledger record carries a null ``reason``, so
    the reason a field is empty can only live on an ``UNRESOLVED`` record.
    """
    if (PLACEMENT_BUS_RULE not in inputs.policy.enabled_rules
            or not inputs.policy.placement_endpoint_bus):
        return (), (), ()
    # The join key carries ``case_id`` even though the contract names only the line and
    # the side: ``Line_ID`` is unique within a Case, not across the artifact's Cases, so
    # the narrower key would collide two same-named Lines and drop one Case's evidence.
    evidence = {(row['case_id'], row['source_line_id'], row['endpoint_side']): row
                for row in inputs.endpoint_evidence}
    policy_fields = {'policy_version': inputs.policy.policy_version,
                     'policy_sha256': policy_sha256(inputs.policy)}
    completion, unresolved, plan = [], [], []
    for (case_id, raw_value), by_port in sorted(_placement_ports(inputs).items()):
        ports = [by_port[key] for key in sorted(by_port)]
        source_case_key = _source_case_key(inputs, case_id, 'placement proposals')
        # The cited raw reference is the lowest declaring Line row, and its field is
        # that same record's field: the citation is one record plus one of its columns.
        cited = min(ports, key=lambda p: (p['source_line_record_ref'], p['endpoint_side']))
        cited_ref = cited['source_line_record_ref']
        raw_field = LINE_ENDPOINT_FIELDS[cited['endpoint_side'] - 1]
        port_refs = sorted({p['proposal_id'] for p in ports}
                           | {p['anchor_id'] for p in ports})
        rule_fields = {
            'case_id': case_id, 'source_case_key': source_case_key,
            'source_entity_type': 'LINE', 'donor_source_entity_type': None,
            'source_record_ref': cited_ref, 'donor_source_record_ref': None,
            'raw_field': raw_field, 'raw_reference_value': raw_value,
            'rule_id': PLACEMENT_BUS_RULE, 'rule_version': PLACEMENT_BUS_RULE_VERSION,
            'tier': None, **policy_fields}

        malformed = []
        voltages = set()
        for port in ports:
            row = evidence.get((case_id, port['source_line_id'], port['endpoint_side']))
            if row is None or row['raw_endpoint_value'] != raw_value:
                malformed.append(port)
                continue
            if row.get('voltage_evidence') is not None:
                voltages.add(row['voltage_evidence'])
        if malformed:
            unresolved.append(record(
                completion_status='UNRESOLVED', confidence_class='NONE',
                evidence_refs=sorted(set(port_refs) | {
                    _endpoint_evidence_locator(p['source_line_id'], p['endpoint_side'])
                    for p in malformed}),
                closure_depth=None, reason=EVIDENCE_JOIN_MISMATCH, **rule_fields))
            continue

        evidence_refs = sorted(set(port_refs) | {
            _endpoint_evidence_locator(p['source_line_id'], p['endpoint_side'])
            for p in ports})
        if len(voltages) == 1:
            base_kv, voltage_reason = voltages.pop(), None
        else:
            base_kv, voltage_reason = None, VOLTAGE_CONFLICT if voltages else VOLTAGE_ABSENT
        station = station_value(inputs.bus_member_bytes_by_case.get(case_id))
        station_reason = None if station is not None else STATION_NOT_UNIQUE

        rec = record(
            completion_status='PROPOSED', confidence_class='ENGINEERING_DEFAULT',
            evidence_refs=evidence_refs, closure_depth=0, reason=None, **rule_fields)
        completion.append(rec)
        plan.append({
            'case_id': case_id, 'source_case_key': source_case_key,
            'destination_member': f'{source_case_key}/{PLACEMENT_BUS_FILE}',
            'values': {'Bus_ID': raw_value, 'Bus_Name': None, 'Bus_BaseKV': base_kv,
                       'Bus_Phase': None, 'Bus_Station_ID': station, 'Bus_IsSource': None},
            'source_record_ref': cited_ref, 'raw_field': raw_field,
            'raw_reference_value': raw_value, 'tier': rec['tier'],
            'record_ids': (rec['record_id'],)})
        for reason, refs in (
                (voltage_reason, evidence_refs),
                (station_reason, sorted(set(port_refs)
                                        | {f'{source_case_key}/{PLACEMENT_BUS_FILE}'}))):
            if reason is None:
                continue
            unresolved.append(record(
                completion_status='UNRESOLVED', confidence_class='NONE',
                evidence_refs=refs, closure_depth=None, reason=reason, **rule_fields))
    return tuple(completion), tuple(unresolved), tuple(plan)


def placement_bus_records(inputs: CompletionInputs) -> tuple[dict, ...]:
    """The rule's ``PROPOSED``/``ENGINEERING_DEFAULT`` records, one per materialized row."""
    return _placement_bus(inputs)[0]


def _completion_records(inputs: CompletionInputs, cross: tuple, placement: tuple) -> tuple:
    cross_completion, _, cross_plan = cross
    placement_completion, _, bus_plan = placement
    return recovery_records(inputs) + cross_completion + placement_completion, cross_plan, bus_plan


def _unresolved_records(inputs: CompletionInputs, cross: tuple, placement: tuple) -> tuple:
    cohort, overlap = cohort_records(inputs)
    _, cross_unresolved, _ = cross
    _, placement_unresolved, _ = placement
    return cohort + cross_unresolved + placement_unresolved, overlap


CASE_SUMMARY_KEYS = ('case_id', 'source_case_key', 'completion_status', 'rule_id', 'tier',
                     'record_count')


def case_summary_record(**fields) -> dict:
    """Build one ``case_summary`` row with an exact key set."""
    unknown = [name for name in fields if name not in CASE_SUMMARY_KEYS]
    if unknown:
        raise ValueError(f'unknown case summary field {unknown[0]!r}')
    return {name: fields.get(name) for name in CASE_SUMMARY_KEYS}


def _case_summary(completion, unresolved) -> tuple:
    """Count records per Case by state, rule and tier.

    One row per distinct ``(case, state, rule, tier)`` group with a positive count, so a
    consumer can reconcile a Case's ledger population without replaying the streams. The
    group is the contract's own triple; ``source_case_key`` rides along because every
    other artifact in the chain identifies the Case by it and a summary that omitted it
    would force a join back into the records.
    """
    groups = {}
    for r in (*completion, *unresolved):
        key = (r['case_id'], r['completion_status'], r['rule_id'], r['tier'])
        if key in groups:
            groups[key][1] += 1
            continue
        if r['source_case_key'] is None:
            raise ValueError(f'v1 ledger case summary without a source case key: {key!r}')
        groups[key] = [r['source_case_key'], 1]
    return tuple(case_summary_record(
        case_id=case_id, source_case_key=key, completion_status=status, rule_id=rule_id,
        tier=tier, record_count=count)
        for (case_id, status, rule_id, tier), (key, count) in
        sorted(groups.items(), key=lambda item: (item[0][0], canonical_json_bytes(item[0]))))


def build_ledger(inputs: CompletionInputs) -> Ledger:
    cross = cross_case_records(inputs)
    placement = _placement_bus(inputs)
    completion, append_plan, bus_plan = _completion_records(inputs, cross, placement)
    completion = order_records(completion)
    unresolved, overlap = _unresolved_records(inputs, cross, placement)
    unresolved = order_unresolved(unresolved)
    summary = tuple(sorted(_case_summary(completion, unresolved),
                           key=lambda r: (r['case_id'], canonical_json_bytes(r))))
    # addition_count is the evidence trail: one per PROPOSED record a materializing rule
    # contributed. appended_row_count is the row arithmetic: what the delivered CSVs
    # actually gained, across both plans. They differ whenever a row is shared.
    addition_count = sum(1 for r in completion
                         if r['rule_id'] in (CROSS_CASE_RULE, PLACEMENT_BUS_RULE))
    return Ledger(
        completion_records=completion, unresolved_records=unresolved, case_summary=summary,
        counts={'completion_records': len(completion), 'unresolved_records': len(unresolved),
                'addition_count': addition_count,
                'appended_row_count': len(append_plan) + len(bus_plan),
                'cohort_overlap_members': overlap},
        append_plan=append_plan, bus_plan=bus_plan)
