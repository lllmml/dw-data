"""Pure eligibility/prohibition evaluation, preceding any future candidate generator."""
from grid_case_generator.models.completion import (
    ActionCohort as A, CandidateStage, CompletionFacts, CompletionReadiness as R,
    Operation as O, Prohibition as P,
)
from grid_case_generator.models.recovery import EvidenceClass

VERSION = 'synthetic-completion-contract-v1'
RULE_VERSION = '1.0.0'


def operation_prohibitions(f: CompletionFacts, operation: O):
    reasons = set(f.explicit_prohibitions)
    if 'D' in f.flags and not reasons:
        reasons.add(P.EXISTING_NEGATIVE_SOURCE_EVIDENCE)
    if not f.ownership_confirmed or f.ownership_conflict:
        reasons.add(P.OWNERSHIP_UNRESOLVED)
    if f.cross_case_requested: reasons.add(P.CROSS_CASE_CONNECTION)
    if f.open_bypass_requested: reasons.add(P.KNOWN_OPEN_BYPASS)
    if f.unknown_switch_state: reasons.add(P.STATE_UNDETERMINED)
    if not f.voltage_confirmed: reasons.add(P.VOLTAGE_UNDETERMINED)
    if operation == O.SYNTHETIC_ATTACHMENT_EDGE:
        if not f.unreferenced_count: reasons.add(P.NO_UNREFERENCED_TARGET)
        if not f.mv_side_confirmed: reasons.add(P.UNKNOWN_TRANSFORMER_SIDE)
        if not f.valid_head or not f.s0_usable: reasons.add(P.NO_ACCEPTED_BACKBONE)
        if f.accepted_junction_count != 1: reasons.add(P.ATTACHMENT_REGION_UNDETERMINED)
        if not f.placement_policy_approved: reasons.add(P.POLICY_APPROVAL_REQUIRED)
        if 'C' in f.flags: reasons.add(P.EXISTING_REFERENCE_REQUIRES_REVIEW)
    elif operation == O.SYNTHETIC_LV_BUS:
        if not f.located_transformer_count: reasons.add(P.NO_LOCATED_TRANSFORMER)
        if not f.lv_side_confirmed: reasons.add(P.UNKNOWN_TRANSFORMER_SIDE)
        if not f.lv_policy_approved: reasons.add(P.POLICY_APPROVAL_REQUIRED)
    elif operation == O.SYNTHETIC_TRANSFORMER:
        if f.target_count: reasons.add(P.DUPLICATE_GENERATION)
        if not f.distribution_role_confirmed: reasons.add(P.ROLE_UNDETERMINED)
        if not f.demand_confirmed: reasons.add(P.DEMAND_EVIDENCE_MISSING)
        if not f.device_count_policy_approved: reasons.add(P.DEVICE_COUNT_POLICY_REQUIRED)
        if not f.lv_side_confirmed: reasons.add(P.UNKNOWN_TRANSFORMER_SIDE)
        if not f.capacity_source_policy_approved: reasons.add(P.POLICY_APPROVAL_REQUIRED)
        reasons.add(P.HIGH_RISK_AUTHORIZATION_REQUIRED)
    elif operation == O.SYNTHETIC_COMPONENT_BRIDGE:
        reasons.add(P.UNSAFE_COMPONENT_BRIDGE)
    else:
        reasons.add(P.HIGH_RISK_AUTHORIZATION_REQUIRED)
    return sorted(reasons)


def evaluate(f: CompletionFacts):
    operations = {op: {'eligible': not (codes := operation_prohibitions(f, op)), 'reasons': codes}
                  for op in O}
    if f.explicit_prohibitions or 'D' in f.flags or f.ownership_conflict or f.cross_case_requested or f.open_bypass_requested:
        action = A.BLOCKED_BY_SOURCE_CONFLICT
    elif 'B' in f.flags or not f.target_count:
        action = A.ROLE_CONFIRMATION_REQUIRED
    elif f.s0_full:
        action = A.ALREADY_TARGET_COMPLETE
    elif 'C' in f.flags or f.s2_full or (not f.s0_usable and f.s2_usable):
        action = A.DETERMINISTIC_RULE_REVIEW
    elif not f.valid_head or not f.source_line_count or not (f.s0_usable or f.s2_usable) or not f.accepted_junction_count:
        action = A.INSUFFICIENT_STRUCTURE
    elif 'A' in f.flags and operations[O.SYNTHETIC_ATTACHMENT_EDGE]['eligible']:
        action = A.AUTO_SYNTHETIC_ELIGIBLE
    else:
        action = A.ROLE_CONFIRMATION_REQUIRED if 'A' in f.flags else A.DETERMINISTIC_RULE_REVIEW
    readiness = {A.BLOCKED_BY_SOURCE_CONFLICT: R.BLOCKED,
                 A.ROLE_CONFIRMATION_REQUIRED: R.ROLE_CONFIRMATION_REQUIRED,
                 A.ALREADY_TARGET_COMPLETE: R.NOT_ELIGIBLE,
                 A.DETERMINISTIC_RULE_REVIEW: R.RULE_REVIEW_REQUIRED,
                 A.INSUFFICIENT_STRUCTURE: R.NOT_ELIGIBLE,
                 A.AUTO_SYNTHETIC_ELIGIBLE: R.SYNTHETIC_ELIGIBLE}[action]
    return {'primary_action': action, 'readiness': readiness, 'original_flags': sorted(f.flags),
            'role_assessment': 'ROLE_UNDETERMINED' if not f.target_count else 'EXISTING_TRANSFORMER_INVENTORY',
            'operations': operations, 'prohibition_codes': sorted({c for o in operations.values() for c in o['reasons']}),
            'stage': CandidateStage.ELIGIBLE if action == A.AUTO_SYNTHETIC_ELIGIBLE else CandidateStage.OBSERVED,
            'decision_reason': action, 'evidence_class': EvidenceClass.UNRESOLVED,
            'generated_object_count': 0, 'e3_ready': False, 'opendss_ready': False}
