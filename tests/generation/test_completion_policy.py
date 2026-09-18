import json
from dataclasses import FrozenInstanceError

import pytest
from grid_case_generator.models.completion_export import (
    INFERENCE_RULES, SCHEMA, CompletionPolicy, parse_policy, policy_bytes, policy_sha256,
)

VALID = {
    'schema_version': SCHEMA,
    'policy_version': '1.0.0',
    'materialize_tiers': ['SAME_STATION'],
    'enabled_rules': list(INFERENCE_RULES),
    'max_reference_closure_depth': 2,
    'placement_endpoint_bus': True,
}


def write(tmp_path, policy):
    path = tmp_path / 'policy.json'
    path.write_bytes(json.dumps(policy).encode())
    return path


def test_shipped_v1_policy_parses_and_is_frozen():
    policy = parse_policy('configs/nanjing_completion_policy_v1.json')
    assert isinstance(policy, CompletionPolicy)
    assert policy.materialize_tiers == ('SAME_STATION',)
    assert policy.max_reference_closure_depth == 2
    assert policy.placement_endpoint_bus is True
    with pytest.raises(FrozenInstanceError):
        policy.materialize_tiers = ('CROSS_STATION',)


def test_unknown_field_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='unknown or missing field'):
        parse_policy(write(tmp_path, dict(VALID, materialize_cross_case=True)))


@pytest.mark.parametrize('key', sorted(VALID))
def test_missing_field_is_rejected(tmp_path, key):
    bad = {k: v for k, v in VALID.items() if k != key}
    with pytest.raises(ValueError, match='unknown or missing field'):
        parse_policy(write(tmp_path, bad))


def test_schema_version_is_pinned(tmp_path):
    with pytest.raises(ValueError, match='schema version'):
        parse_policy(write(tmp_path, dict(VALID, schema_version='nanjing_v1')))


def test_source_passthrough_is_not_a_lever(tmp_path):
    with pytest.raises(ValueError, match='enabled rules'):
        parse_policy(write(tmp_path, dict(VALID, enabled_rules=['SOURCE_PASSTHROUGH_V1'])))


@pytest.mark.parametrize('payload', [None, 5, [], 'x'])
def test_non_object_document_is_rejected(tmp_path, payload):
    path = tmp_path / 'policy.json'
    path.write_bytes(json.dumps(payload).encode())
    with pytest.raises(ValueError, match='JSON object'):
        parse_policy(path)


@pytest.mark.parametrize('value', ['', 5, None])
def test_bad_policy_version_is_rejected(tmp_path, value):
    with pytest.raises(ValueError, match='policy version'):
        parse_policy(write(tmp_path, dict(VALID, policy_version=value)))


def test_direct_construction_is_validated_and_normalized():
    with pytest.raises(ValueError, match='enabled rules'):
        CompletionPolicy(policy_version='1.0.0', materialize_tiers=('SAME_STATION',),
                         enabled_rules=(), max_reference_closure_depth=2,
                         placement_endpoint_bus=True)
    policy = CompletionPolicy(policy_version='1.0.0',
                              materialize_tiers=('CROSS_STATION', 'SAME_STATION'),
                              enabled_rules=tuple(reversed(INFERENCE_RULES)),
                              max_reference_closure_depth=2, placement_endpoint_bus=True)
    assert policy.materialize_tiers == ('CROSS_STATION', 'SAME_STATION')
    assert policy.enabled_rules == INFERENCE_RULES


@pytest.mark.parametrize('field,value', [
    ('materialize_tiers', []),
    ('materialize_tiers', ['SAME_STATION', 'SAME_STATION']),
    ('materialize_tiers', ['CROSS_FEEDER']),
    ('materialize_tiers', 'SAME_STATION'),
    ('enabled_rules', []),
    ('enabled_rules', ['CROSS_CASE_REFERENCE_COPY_V1', 'CROSS_CASE_REFERENCE_COPY_V1']),
    ('max_reference_closure_depth', -1),
    ('max_reference_closure_depth', 9),
    ('max_reference_closure_depth', True),
    ('max_reference_closure_depth', 2.5),
    ('max_reference_closure_depth', '2'),
    ('placement_endpoint_bus', 'yes'),
    ('placement_endpoint_bus', 1),
])
def test_invalid_values_are_rejected(tmp_path, field, value):
    with pytest.raises(ValueError):
        parse_policy(write(tmp_path, dict(VALID, **{field: value})))


@pytest.mark.parametrize('field', ['materialize_tiers', 'enabled_rules'])
def test_unhashable_elements_raise_value_error_not_type_error(tmp_path, field):
    with pytest.raises(ValueError):
        parse_policy(write(tmp_path, dict(VALID, **{field: [['nested']]})))


def test_policy_bytes_ignore_input_order(tmp_path):
    a = parse_policy(write(tmp_path, VALID))
    b = parse_policy(write(tmp_path, dict(VALID, enabled_rules=list(reversed(INFERENCE_RULES)))))
    assert policy_bytes(a) == policy_bytes(b)
    assert policy_sha256(a) == policy_sha256(b)
    assert policy_bytes(a).endswith(b'\n')
    assert json.loads(policy_bytes(a)) == dict(VALID)
