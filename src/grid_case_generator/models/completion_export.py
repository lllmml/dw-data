"""Completion/export policy contract and canonical identity; no source or accepted objects."""
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path

from grid_case_generator.io.canonical_json import canonical_json_bytes

VERSION = '1.4.0'
RULE_VERSION = '1.0.0'
PLACEMENT_BUS_RULE_VERSION = '1.1.0'
SCHEMA = 'nanjing_completion_policy_v1'
PASSTHROUGH_RULE = 'SOURCE_PASSTHROUGH_V1'
RECOVERY_RULE = 'ACCEPTED_DETERMINISTIC_RECOVERY_V1'
CROSS_CASE_RULE = 'CROSS_CASE_REFERENCE_COPY_V1'
PLACEMENT_BUS_RULE = 'PLACEMENT_MISSING_ENDPOINT_BUS_V1'
INFERENCE_RULES = (RECOVERY_RULE, CROSS_CASE_RULE, PLACEMENT_BUS_RULE)
TIERS = ('SAME_STATION', 'CROSS_STATION')
LEDGER_NAMESPACE = 'v1-completion:ledger:'
PROVENANCE_NAMESPACE = 'v1-completion:provenance:'
REQUIRED_KEYS = frozenset({'schema_version', 'policy_version', 'materialize_tiers',
    'enabled_rules', 'max_reference_closure_depth', 'placement_endpoint_bus'})


class CompletionStatus(StrEnum):
    CONFIRMED = 'CONFIRMED'
    PROPOSED = 'PROPOSED'
    UNRESOLVED = 'UNRESOLVED'


class ConfidenceClass(StrEnum):
    EXACT_STRUCTURAL = 'EXACT_STRUCTURAL'
    UNIQUE_EVIDENCE = 'UNIQUE_EVIDENCE'
    ENGINEERING_DEFAULT = 'ENGINEERING_DEFAULT'
    NONE = 'NONE'


def _check_version(value):
    if type(value) is not str or not value:
        raise ValueError(f'v1 policy version: {value!r}')


def _check_tiers(value):
    if (not isinstance(value, (list, tuple)) or not value
            or not all(type(t) is str for t in value)
            or not set(value) <= set(TIERS)
            or len(set(value)) != len(value)):
        raise ValueError(f'v1 policy materialize tiers: {value!r} (subset of {list(TIERS)})')


def _check_rules(value):
    if (not isinstance(value, (list, tuple)) or not value
            or not all(type(r) is str for r in value)
            or not set(value) <= set(INFERENCE_RULES)
            or len(set(value)) != len(value)):
        raise ValueError(f'v1 policy enabled rules: {value!r} (subset of {list(INFERENCE_RULES)})')


def _check_depth(value):
    if type(value) is not int or not 0 <= value <= 8:
        raise ValueError(f'v1 policy closure depth: {value!r} (int in 0..8)')


def _check_flag(value):
    if type(value) is not bool:
        raise ValueError(f'v1 policy placement flag: {value!r} (bool)')


@dataclass(frozen=True, slots=True, kw_only=True)
class CompletionPolicy:
    policy_version: str
    materialize_tiers: tuple[str, ...]
    enabled_rules: tuple[str, ...]
    max_reference_closure_depth: int
    placement_endpoint_bus: bool

    def __post_init__(self):
        _check_version(self.policy_version)
        _check_tiers(self.materialize_tiers)
        _check_rules(self.enabled_rules)
        _check_depth(self.max_reference_closure_depth)
        _check_flag(self.placement_endpoint_bus)
        object.__setattr__(self, 'materialize_tiers', tuple(sorted(self.materialize_tiers)))
        object.__setattr__(self, 'enabled_rules', tuple(sorted(self.enabled_rules)))


def parse_policy(path) -> CompletionPolicy:
    raw = json.loads(Path(path).read_bytes())
    if not isinstance(raw, dict):
        raise ValueError(f'v1 policy must be a JSON object, got {type(raw).__name__}')
    if set(raw) != REQUIRED_KEYS:
        raise ValueError(f'v1 policy unknown or missing field: {sorted(set(raw) ^ REQUIRED_KEYS)}')
    if raw['schema_version'] != SCHEMA:
        raise ValueError(f'v1 policy schema version: {raw["schema_version"]!r}')
    return CompletionPolicy(
        policy_version=raw['policy_version'],
        materialize_tiers=raw['materialize_tiers'],
        enabled_rules=raw['enabled_rules'],
        max_reference_closure_depth=raw['max_reference_closure_depth'],
        placement_endpoint_bus=raw['placement_endpoint_bus'],
    )


def policy_bytes(policy: CompletionPolicy) -> bytes:
    return canonical_json_bytes({
        'schema_version': SCHEMA,
        'policy_version': policy.policy_version,
        'materialize_tiers': list(policy.materialize_tiers),
        'enabled_rules': list(policy.enabled_rules),
        'max_reference_closure_depth': policy.max_reference_closure_depth,
        'placement_endpoint_bus': policy.placement_endpoint_bus,
    }) + b'\n'


def policy_sha256(policy: CompletionPolicy) -> str:
    return sha256(policy_bytes(policy)).hexdigest()


def ledger_id(payload: dict) -> str:
    return LEDGER_NAMESPACE + sha256(canonical_json_bytes(payload)).hexdigest()


def provenance_id(payload: dict) -> str:
    return PROVENANCE_NAMESPACE + sha256(canonical_json_bytes(payload)).hexdigest()
