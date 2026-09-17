"""D1 contract facts and lifecycle; no generated topology objects."""
from dataclasses import dataclass, fields
from enum import StrEnum


class ActionCohort(StrEnum):
    AUTO_SYNTHETIC_ELIGIBLE = 'AUTO_SYNTHETIC_ELIGIBLE'
    DETERMINISTIC_RULE_REVIEW = 'DETERMINISTIC_RULE_REVIEW'
    ROLE_CONFIRMATION_REQUIRED = 'ROLE_CONFIRMATION_REQUIRED'
    BLOCKED_BY_SOURCE_CONFLICT = 'BLOCKED_BY_SOURCE_CONFLICT'
    INSUFFICIENT_STRUCTURE = 'INSUFFICIENT_STRUCTURE'
    ALREADY_TARGET_COMPLETE = 'ALREADY_TARGET_COMPLETE'


class CompletionReadiness(StrEnum):
    NOT_ELIGIBLE = 'NOT_ELIGIBLE'
    RULE_REVIEW_REQUIRED = 'RULE_REVIEW_REQUIRED'
    SYNTHETIC_ELIGIBLE = 'SYNTHETIC_ELIGIBLE'
    ROLE_CONFIRMATION_REQUIRED = 'ROLE_CONFIRMATION_REQUIRED'
    BLOCKED = 'BLOCKED'
    READY_FOR_SYNTHETIC_PROPOSAL = 'READY_FOR_SYNTHETIC_PROPOSAL'


class CandidateStage(StrEnum):
    OBSERVED = 'OBSERVED'
    ELIGIBLE = 'ELIGIBLE'
    PROPOSED = 'PROPOSED'
    VALIDATED = 'VALIDATED'
    APPROVED = 'APPROVED'
    APPLIED = 'APPLIED'


class Operation(StrEnum):
    SYNTHETIC_ATTACHMENT_EDGE = 'SYNTHETIC_ATTACHMENT_EDGE'
    SYNTHETIC_JUNCTION = 'SYNTHETIC_JUNCTION'
    SYNTHETIC_LV_BUS = 'SYNTHETIC_LV_BUS'
    SYNTHETIC_TRANSFORMER = 'SYNTHETIC_TRANSFORMER'
    SYNTHETIC_BACKBONE_EDGE = 'SYNTHETIC_BACKBONE_EDGE'
    SYNTHETIC_COMPONENT_BRIDGE = 'SYNTHETIC_COMPONENT_BRIDGE'


class Prohibition(StrEnum):
    AMBIGUOUS_IDENTITY = 'AMBIGUOUS_IDENTITY'
    OWNERSHIP_UNRESOLVED = 'OWNERSHIP_UNRESOLVED'
    CROSS_CASE_CONNECTION = 'CROSS_CASE_CONNECTION'
    INCOMPATIBLE_VOLTAGE = 'INCOMPATIBLE_VOLTAGE'
    KNOWN_OPEN_BYPASS = 'KNOWN_OPEN_BYPASS'
    UNKNOWN_TRANSFORMER_SIDE = 'UNKNOWN_TRANSFORMER_SIDE'
    DUPLICATE_GENERATION = 'DUPLICATE_GENERATION'
    EXISTING_NEGATIVE_SOURCE_EVIDENCE = 'EXISTING_NEGATIVE_SOURCE_EVIDENCE'
    UNSAFE_COMPONENT_BRIDGE = 'UNSAFE_COMPONENT_BRIDGE'
    KNOWN_OPEN_PRESENT = 'KNOWN_OPEN_PRESENT'
    STATE_UNDETERMINED = 'STATE_UNDETERMINED'
    VOLTAGE_UNDETERMINED = 'VOLTAGE_UNDETERMINED'
    POLICY_APPROVAL_REQUIRED = 'POLICY_APPROVAL_REQUIRED'
    HIGH_RISK_AUTHORIZATION_REQUIRED = 'HIGH_RISK_AUTHORIZATION_REQUIRED'
    NO_ACCEPTED_BACKBONE = 'NO_ACCEPTED_BACKBONE'
    ATTACHMENT_REGION_UNDETERMINED = 'ATTACHMENT_REGION_UNDETERMINED'
    ROLE_UNDETERMINED = 'ROLE_UNDETERMINED'
    DEMAND_EVIDENCE_MISSING = 'DEMAND_EVIDENCE_MISSING'
    DEVICE_COUNT_POLICY_REQUIRED = 'DEVICE_COUNT_POLICY_REQUIRED'
    NO_UNREFERENCED_TARGET = 'NO_UNREFERENCED_TARGET'
    NO_LOCATED_TRANSFORMER = 'NO_LOCATED_TRANSFORMER'
    EXISTING_REFERENCE_REQUIRES_REVIEW = 'EXISTING_REFERENCE_REQUIRES_REVIEW'


@dataclass(frozen=True, kw_only=True)
class CompletionFacts:
    case_id: str
    feeder_id: str
    flags: tuple[str, ...] = ()
    explicit_prohibitions: tuple[Prohibition, ...] = ()
    target_count: int = 0
    unreferenced_count: int = 0
    source_line_count: int = 0
    accepted_junction_count: int = 0
    located_transformer_count: int = 0
    valid_head: bool = False
    s0_usable: bool = False
    s2_usable: bool = False
    s0_full: bool = False
    s2_full: bool = False
    ownership_confirmed: bool = False
    ownership_conflict: bool = False
    mv_side_confirmed: bool = False
    lv_side_confirmed: bool = False
    voltage_confirmed: bool = False
    placement_policy_approved: bool = False
    lv_policy_approved: bool = False
    distribution_role_confirmed: bool = False
    demand_confirmed: bool = False
    device_count_policy_approved: bool = False
    capacity_source_policy_approved: bool = False
    cross_case_requested: bool = False
    open_bypass_requested: bool = False
    unknown_switch_state: bool = False

    def __post_init__(self):
        if not self.case_id or not self.feeder_id:
            raise ValueError('case/feeder identity required')
        for field in fields(self):
            value = getattr(self, field.name)
            if field.type in (int, bool, str) and type(value) is not field.type:
                raise TypeError('invalid fact type: ' + field.name)
            if field.type is int and value < 0:
                raise ValueError('negative count: ' + field.name)
        if type(self.flags) is not tuple or set(self.flags) - set('ABCD') or len(set(self.flags)) != len(self.flags):
            raise ValueError('invalid original flags')
        if type(self.explicit_prohibitions) is not tuple or any(not isinstance(p, Prohibition) for p in self.explicit_prohibitions):
            raise TypeError('invalid prohibition codes')
        if self.unreferenced_count > self.target_count or self.located_transformer_count > self.target_count:
            raise ValueError('target subset exceeds denominator')
        if not self.target_count and (self.s0_full or self.s2_full):
            raise ValueError('zero targets cannot be FULL')

    @classmethod
    def from_dict(cls, value):
        return cls(**dict(value, flags=tuple(value['flags']),
                          explicit_prohibitions=tuple(Prohibition(p) for p in value['explicit_prohibitions'])))


def validate_d1_transition(before, after, reason, evidence_refs):
    allowed = {(CandidateStage.OBSERVED, CandidateStage.ELIGIBLE),
               (CandidateStage.ELIGIBLE, CandidateStage.PROPOSED)}
    if (before, after) not in allowed or not reason.strip() or not evidence_refs or not all(evidence_refs):
        raise ValueError('D1 transition requires adjacent allowed stages and decision evidence')
