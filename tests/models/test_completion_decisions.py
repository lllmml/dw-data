import json
from copy import deepcopy

import pytest
from grid_case_generator.models.proposals import unknown_decision, parse_decisions, decision_bytes, proposal_id


def policy():
    return {'schema_version':'nanjing_completion_decisions_v1','decision_version':'1.0.0',
            'input_manifest_sha256':{'source':'a'*64,'d1':'b'*64},
            'decisions':[unknown_decision('case:a','feeder:a')]}


def parse(p):
    return parse_decisions(json.dumps(p), {('case:a','feeder:a')}, {'source':'a'*64,'d1':'b'*64})


def confirmed():
    p=policy();p['decisions'][0].update(role='DISTRIBUTION_WITH_TRANSFORMER',transformer_required=True,
        synthetic_transformer_allowed=True,transformer_count=2,demand_basis='business:load-scope',
        nominal_voltage_kv='10.5',lv_voltage_kv='0.4',confirmation_ref='business:review-1')
    return p


def test_official_unknown_is_not_permission():
    p=parse(policy()); assert not p['decisions'][0]['synthetic_transformer_allowed']
    assert parse(confirmed())['decisions'][0]['transformer_count']==2


@pytest.mark.parametrize('change', [dict(role='UNKNOWN',synthetic_transformer_allowed=True),
    dict(transformer_count=True),dict(nominal_voltage_kv='NaN'),dict(confirmation_ref=None),
    dict(role='NO_TRANSFORMER_REQUIRED'),dict(transformer_count=None),dict(demand_basis=None),
    dict(feeder_id='feeder:other'),dict(extra='bad')])
def test_invalid_business_confirmation_fails_closed(change):
    p=confirmed();p['decisions'][0].update(change)
    with pytest.raises(ValueError):parse(p)


def test_duplicate_entries_keys_and_stale_binding_rejected():
    p=policy();p['decisions']*=2
    with pytest.raises(ValueError):parse(p)
    p=policy();p['input_manifest_sha256']['source']='c'*64
    with pytest.raises(ValueError):parse(p)
    with pytest.raises(ValueError):parse_decisions('{"schema_version":"x","schema_version":"y"}',set(),{})


def test_canonical_policy_and_stable_namespace():
    p=parse(confirmed());q=deepcopy(p)
    q['decisions'][0]=dict(reversed(list(q['decisions'][0].items())))
    assert decision_bytes(p)==decision_bytes(q)
    assert proposal_id('case:a','feeder:a','edge',['n1','n2'],'a'*64)==proposal_id('case:a','feeder:a','edge',['n1','n2'],'a'*64)
    assert proposal_id('case:a','feeder:a','edge',['n1','n2'],'a'*64)!=proposal_id('case:b','feeder:a','edge',['n1','n2'],'a'*64)
