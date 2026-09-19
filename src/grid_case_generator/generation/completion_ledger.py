"""Deterministic completion ledger scaffold and bounded closure walker.

This slice builds the pure scaffold only: the record shape, the identity rule,
the explicit ordering helpers, the depth-bounded cycle-safe closure walker, and
an IO-free ``build_ledger`` whose rule bodies arrive in later slices.

Forward constraint for Slices 4-7: ``record_id`` hashes ``evidence_refs`` in
list order, so any rule assembling ``evidence_refs`` from a set or dict must
sort it first, or record identity will churn between runs.
"""
from collections.abc import Mapping
from dataclasses import dataclass

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.models.completion_export import (
    RECOVERY_RULE, CompletionPolicy, ledger_id, policy_sha256)

RECORD_KEYS = ('record_id', 'completion_status', 'confidence_class', 'tier', 'rule_id',
    'rule_version', 'case_id', 'source_case_key', 'source_entity_type',
    'donor_source_entity_type', 'source_record_ref', 'donor_source_record_ref',
    'raw_field', 'raw_reference_value', 'evidence_refs', 'closure_depth',
    'policy_version', 'policy_sha256', 'reason')

COUNTS_KEYS = ('completion_records', 'unresolved_records', 'materialized_rows',
               'cohort_overlap_members')

RECOVERY_RULE_VERSION = '1.0.0'
COHORT_RULE = 'COHORT_TAXONOMY_V1'
COHORT_RULE_VERSION = '1.0.0'
COHORT_REASONS = ('INSUFFICIENT_PLACEMENT_EVIDENCE', 'NON_UNIQUE_PLACEMENT',
                  'MANUAL_LAYOUT_REQUIRED', 'NO_SOURCE_LINE_LAYOUT_BASIS')


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


@dataclass(frozen=True, slots=True, kw_only=True)
class Ledger:
    completion_records: tuple[dict, ...]
    unresolved_records: tuple[dict, ...]
    case_summary: tuple[dict, ...]
    counts: dict


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
            raise ValueError(f'unknown case {case_id!r} in accepted additions')
        supporting_refs = sorted(addition['supporting_source_refs'])
        records.append(record(
            completion_status='CONFIRMED', confidence_class='EXACT_STRUCTURAL',
            tier=None, rule_id=RECOVERY_RULE, rule_version=RECOVERY_RULE_VERSION,
            case_id=case_id, source_case_key=source_case_key,
            source_entity_type='EQUIPMENT',
            donor_source_entity_type=None, source_record_ref=supporting_refs[0],
            donor_source_record_ref=None, raw_field=None, raw_reference_value=None,
            evidence_refs=[addition['edge_id'],
                           addition['rule_id'] + '/' + addition['rule_version']],
            closure_depth=0, reason=None, **policy_fields))
    return tuple(records)


def _cohort_source_record_ref(row, reason) -> str:
    return f'cohort:{reason}:{row["case_id"]}:{row["feeder_id"]}'


def _emit_cohort(records, seen, row, reason, evidence_refs, policy_fields) -> None:
    source_record_ref = _cohort_source_record_ref(row, reason)
    key = (reason, row['case_id'], source_record_ref)
    if key in seen:
        return
    seen.add(key)
    records.append(record(
        completion_status='UNRESOLVED', confidence_class='NONE',
        tier=None, rule_id=COHORT_RULE, rule_version=COHORT_RULE_VERSION,
        case_id=row['case_id'], source_case_key=row['source_case_key'],
        source_entity_type='FEEDER',
        donor_source_entity_type=None, source_record_ref=source_record_ref,
        donor_source_record_ref=None, raw_field=None, raw_reference_value=None,
        evidence_refs=evidence_refs, closure_depth=None,
        reason=reason, **policy_fields))


def cohort_records(inputs: CompletionInputs) -> tuple[dict, ...]:
    """Emit one UNRESOLVED/NONE record per feeder in a cohort, per reason.

    The taxonomy is unconditional: it is not gated by ``enabled_rules``. A
    feeder may legitimately receive one record per matching reason, so the
    cohorts are deliberately not made exclusive. Ledger-only: appends no CSV
    row.
    """
    policy_fields = {'policy_version': inputs.policy.policy_version,
                     'policy_sha256': policy_sha256(inputs.policy)}
    seen = set()
    records = []
    for row in inputs.placement_feeders:
        status = row['primary_status']
        if status not in COHORT_REASONS[:2]:
            continue
        _emit_cohort(records, seen, row, status,
                     ['feeder_classification.jsonl/' + row['feeder_id']],
                     policy_fields)
    for row in inputs.backbone_taxonomy:
        if row['d3_primary'] != 'SYNTHETIC_BACKBONE_REQUIRED':
            continue
        if row['outcome'] != 'MANUAL_LAYOUT_REQUIRED':
            continue
        evidence_refs = ['feeder_gap_taxonomy.jsonl/' + row['feeder_id'],
                         row['d3_primary']]
        _emit_cohort(records, seen, row, 'MANUAL_LAYOUT_REQUIRED',
                     evidence_refs, policy_fields)
        if row['source_line_count'] == 0:
            _emit_cohort(records, seen, row, 'NO_SOURCE_LINE_LAYOUT_BASIS',
                         evidence_refs, policy_fields)
    return tuple(records)


def _cohort_overlap_members(records) -> int:
    """Count distinct feeders reported under more than one reason."""
    reasons_by_feeder = {}
    for r in records:
        reason = r['reason']
        prefix = f'cohort:{reason}:'
        # source_record_ref == f'cohort:{reason}:{case_id}:{feeder_id}'
        feeder_key = r['source_record_ref'][len(prefix):]
        reasons_by_feeder.setdefault((r['case_id'], feeder_key), set()).add(reason)
    return sum(1 for reasons in reasons_by_feeder.values() if len(reasons) > 1)


def _completion_records(inputs: CompletionInputs) -> tuple:
    return recovery_records(inputs)


def _unresolved_records(inputs: CompletionInputs) -> tuple:
    return cohort_records(inputs)


def _case_summary(completion, unresolved) -> tuple:
    return ()


def build_ledger(inputs: CompletionInputs) -> Ledger:
    completion = order_records(_completion_records(inputs))
    unresolved = order_unresolved(_unresolved_records(inputs))
    summary = tuple(sorted(_case_summary(completion, unresolved),
                           key=lambda r: (r['case_id'], canonical_json_bytes(r))))
    return Ledger(
        completion_records=completion, unresolved_records=unresolved, case_summary=summary,
        counts={'completion_records': len(completion), 'unresolved_records': len(unresolved),
                'materialized_rows': 0,
                'cohort_overlap_members': _cohort_overlap_members(unresolved)})
