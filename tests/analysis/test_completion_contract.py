from dataclasses import replace

import pytest

from grid_case_generator.models.completion import (
    CompletionFacts, ActionCohort, CandidateStage, Operation, Prohibition,
    validate_d1_transition,
)
from grid_case_generator.analysis.completion_contract import evaluate


def facts(**overrides):
    values = dict(case_id='case:test', feeder_id='feeder:test', flags=('A',),
                  target_count=2, unreferenced_count=2, source_line_count=1,
                  valid_head=True, s0_usable=True, s2_usable=True,
                  accepted_junction_count=1)
    values.update(overrides)
    return CompletionFacts(**values)


def approved(**overrides):
    values = dict(ownership_confirmed=True, mv_side_confirmed=True,
                  voltage_confirmed=True, placement_policy_approved=True)
    values.update(overrides)
    return facts(**values)


def test_unknown_owner_and_mv_side_do_not_grant_permission():
    d = evaluate(facts())
    assert d['primary_action'] == ActionCohort.ROLE_CONFIRMATION_REQUIRED
    assert not d['operations'][Operation.SYNTHETIC_ATTACHMENT_EDGE]['eligible']
    assert Prohibition.UNKNOWN_TRANSFORMER_SIDE in d['prohibition_codes']
    assert Prohibition.OWNERSHIP_UNRESOLVED in d['prohibition_codes']


@pytest.mark.parametrize('code', [Prohibition.AMBIGUOUS_IDENTITY,
    Prohibition.INCOMPATIBLE_VOLTAGE, Prohibition.KNOWN_OPEN_PRESENT,
    Prohibition.EXISTING_NEGATIVE_SOURCE_EVIDENCE])
def test_explicit_conflict_precedes_overlapping_roles(code):
    d = evaluate(facts(flags=('B', 'D'), target_count=0, unreferenced_count=0,
                       explicit_prohibitions=(code,)))
    assert d['primary_action'] == ActionCohort.BLOCKED_BY_SOURCE_CONFLICT
    assert d['original_flags'] == ['B', 'D']
    assert d['role_assessment'] == 'ROLE_UNDETERMINED'
    assert not any(x['eligible'] for x in d['operations'].values())


def test_zero_transformer_not_vacuously_complete_or_eligible():
    d = evaluate(facts(flags=('B',), target_count=0, unreferenced_count=0))
    assert d['primary_action'] == ActionCohort.ROLE_CONFIRMATION_REQUIRED
    assert not d['operations'][Operation.SYNTHETIC_TRANSFORMER]['eligible']


def test_duplicate_transformer_permission_forbidden():
    d = evaluate(approved())
    assert d['primary_action'] == ActionCohort.AUTO_SYNTHETIC_ELIGIBLE
    assert Prohibition.DUPLICATE_GENERATION in d['operations'][Operation.SYNTHETIC_TRANSFORMER]['reasons']
    assert d['stage'] == CandidateStage.ELIGIBLE
    assert d['evidence_class'] == 'UNRESOLVED'
    assert not d['e3_ready'] and d['generated_object_count'] == 0


@pytest.mark.parametrize('field,code', [('cross_case_requested', Prohibition.CROSS_CASE_CONNECTION),
    ('open_bypass_requested', Prohibition.KNOWN_OPEN_BYPASS),
    ('ownership_conflict', Prohibition.OWNERSHIP_UNRESOLVED)])
def test_operation_intents_cannot_override_hard_prohibitions(field, code):
    d = evaluate(approved(**{field: True}))
    assert not any(x['eligible'] for x in d['operations'].values())
    assert code in d['prohibition_codes']


def test_s2_full_is_review_not_already_accepted():
    d = evaluate(facts(flags=(), unreferenced_count=0, s0_usable=False, s2_full=True))
    assert d['primary_action'] == ActionCohort.DETERMINISTIC_RULE_REVIEW
    assert evaluate(facts(flags=(), s0_full=True, unreferenced_count=0))['primary_action'] == ActionCohort.ALREADY_TARGET_COMPLETE


def test_no_backbone_or_no_region_is_insufficient():
    for f in (facts(s0_usable=False, s2_usable=False), facts(accepted_junction_count=0)):
        assert evaluate(f)['primary_action'] == ActionCohort.INSUFFICIENT_STRUCTURE


def test_c_review_and_s2_backbone_priority():
    assert evaluate(facts(flags=('C',), unreferenced_count=0))['primary_action'] == ActionCohort.DETERMINISTIC_RULE_REVIEW
    assert evaluate(facts(s0_usable=False))['primary_action'] == ActionCohort.DETERMINISTIC_RULE_REVIEW


def test_multiple_regions_cannot_be_sorted_first():
    d = evaluate(approved(accepted_junction_count=2))
    assert not d['operations'][Operation.SYNTHETIC_ATTACHMENT_EDGE]['eligible']
    assert Prohibition.ATTACHMENT_REGION_UNDETERMINED in d['prohibition_codes']


def test_stage_gate_requires_reason_refs_and_does_not_apply():
    validate_d1_transition(CandidateStage.OBSERVED, CandidateStage.ELIGIBLE, 'passed', ('evidence:x',))
    validate_d1_transition(CandidateStage.ELIGIBLE, CandidateStage.PROPOSED, 'policy', ('evidence:y',))
    for before, after in [(CandidateStage.OBSERVED, CandidateStage.APPLIED),
                          (CandidateStage.PROPOSED, CandidateStage.VALIDATED)]:
        with pytest.raises(ValueError): validate_d1_transition(before, after, 'reachable', ('evidence:x',))
    with pytest.raises(ValueError): validate_d1_transition(CandidateStage.OBSERVED, CandidateStage.ELIGIBLE, '', ())


@pytest.mark.parametrize('changes', [{'target_count':-1}, {'valid_head':1}, {'unreferenced_count':3},
                                   {'flags':('X',)}, {'case_id':''}])
def test_typed_facts_reject_invalid_fields(changes):
    with pytest.raises((ValueError, TypeError)): facts(**changes)


def test_flags_and_conflict_order_do_not_change_decision():
    f = facts(flags=('A','D'), explicit_prohibitions=(Prohibition.INCOMPATIBLE_VOLTAGE, Prohibition.AMBIGUOUS_IDENTITY))
    assert evaluate(f) == evaluate(replace(f, flags=tuple(reversed(f.flags)), explicit_prohibitions=tuple(reversed(f.explicit_prohibitions))))
