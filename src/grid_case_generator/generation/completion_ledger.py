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
from grid_case_generator.models.completion_export import CompletionPolicy, ledger_id

RECORD_KEYS = ('record_id', 'completion_status', 'confidence_class', 'tier', 'rule_id',
    'rule_version', 'case_id', 'source_case_key', 'source_entity_type',
    'donor_source_entity_type', 'source_record_ref', 'donor_source_record_ref',
    'raw_field', 'raw_reference_value', 'evidence_refs', 'closure_depth',
    'policy_version', 'policy_sha256', 'reason')

COUNTS_KEYS = ('completion_records', 'unresolved_records', 'materialized_rows',
               'cohort_overlap_members')


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

    ``lookup(key)`` must return a finite iterable of 3-tuples and must not
    raise; any exception propagates lazily at iteration time, by design. The
    ``max_depth`` guard likewise raises on the first iteration of the generator,
    not at call time, consistent with that lazy-exception note.
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


def _completion_records(inputs: CompletionInputs) -> tuple:
    return ()


def _unresolved_records(inputs: CompletionInputs) -> tuple:
    return ()


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
                'materialized_rows': 0, 'cohort_overlap_members': 0})
