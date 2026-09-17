import json
from decimal import Decimal

from source_fixture import mapped
from test_completion_profiles import profile
from test_topology_recovery import analyze
from test_switch_semantics import fixture
from grid_case_generator.generation.topology import interpret_topology
from grid_case_generator.models.topology import TopologyConfig
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.analysis.proposal_inputs import build_case_input
from grid_case_generator.validation.topology_proposals import measure_graph


def test_real_mapper_input_preserves_s0_coverage_and_reclassifies_states():
    rows=fixture();rows['TRANSFORMER'].append({'Transformer_ID':'orphan'})
    d=mapped(rows);t=interpret_topology(d,TopologyConfig(Decimal('10.5')))
    recovery=json.loads(canonical_json_bytes(analyze(rows)))
    raw=json.loads(canonical_json_bytes(d.accounting));top=json.loads(canonical_json_bytes(t.topology))
    exc=json.loads(canonical_json_bytes([p for p in t.projections if p.exclusion_reason]))
    p=profile(rows)
    c=build_case_input(p,raw,top,recovery['transformers'],exc)
    assert measure_graph(c)['reachable_transformers']==recovery['graphs']['S0']['reachable_transformers']
    assert all(s['source_record_ref'] for s in c['state_constraints'])
    assert not any(h['code']=='KNOWN_OPEN_PRESENT' for h in c['hard_blockers'])
    assert c==build_case_input(p,list(reversed(raw)),top,list(reversed(recovery['transformers'])),list(reversed(exc)))
