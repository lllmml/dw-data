"""Drill-down: the one eligible donor-row reference and the 2-level candidates."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, '/data/limingliang/dw-data/data-generation/src')

from grid_case_generator.io.completion_ledger_artifacts import inputs_from_artifacts
from grid_case_generator.generation.completion_ledger import (
    build_ledger, eligible, CROSS_CASE_RULE, walk_closure)
from grid_case_generator.models.completion_export import parse_policy

REPO = Path('/data/limingliang/dw-data/data-generation')
policy = parse_policy(REPO / 'configs/nanjing_completion_policy_v1.json')
roots = {
    'source': REPO / 'outputs/nanjing-e1/source-import-v2',
    'baseline': REPO / 'outputs/nanjing-e2/topology-v1',
    'projection': REPO / 'outputs/nanjing-e2-2/switch-projection-design-v1',
    'feeder': REPO / 'outputs/nanjing-e2-2/feeder-coverage-v1',
    'recovery': REPO / 'outputs/nanjing-e2-3/topology-recovery-evidence-v1',
    'd1': REPO / 'outputs/nanjing-e2-3/synthetic-completion-contract-v1',
    'd2': REPO / 'outputs/nanjing-e2-3/synthetic-topology-proposals-v1',
    'frozen': REPO / 'outputs/nanjing-e2/topology-v1',
    'd3_analysis': REPO / 'outputs/nanjing-e2-3/deterministic-topology-recovery-v1',
    'accepted_v2': REPO / 'outputs/nanjing-e2-3/accepted-topology-v2',
    'd4': REPO / 'outputs/nanjing-e2-3/synthetic-backbone-proposals-v1',
    'placement': REPO / 'outputs/nanjing-e2-3/placement-evidence-v1-1',
    'audit': REPO / 'outputs/nanjing-e2-3/case-boundary-audit-v1',
}
inputs = inputs_from_artifacts({k: str(v) for k, v in roots.items()}, policy)
ledger = build_ledger(inputs)
plan = ledger.append_plan
D = {e['donor_source_record_ref'] for e in plan}

cand_case_of = defaultdict(set)
for row in inputs.audit_rows:
    for c in (row.get('candidates') or []):
        cand_case_of[c['source_record_ref']].add(c['case_id'])

rows_in_D = [r for r in inputs.audit_rows if r['source_record_ref'] in D]
donor_refs_with_rows = {r['source_record_ref'] for r in rows_in_D}
print('donor refs total:', len(D), 'donor refs with an audit row:', len(donor_refs_with_rows))
print('audit rows on donor rows:', len(rows_in_D))
print('  raw_field histogram:', dict(Counter(r['raw_field'] for r in rows_in_D)))
print('  owner entity type:', dict(Counter(r['source_entity_type'] for r in rows_in_D)))
print('  classification:', dict(Counter(r['classification'] for r in rows_in_D)))

cases = {row['case_id']: row for row in inputs.audit_cases}
ok_rows = [r for r in rows_in_D if eligible(r, policy.materialize_tiers, cases)[0]]
print()
print('=== THE ELIGIBLE DONOR-ROW REFERENCE(S) ===')
for r in ok_rows:
    print(json.dumps(r, ensure_ascii=False, sort_keys=True, indent=1)[:3000])
    print('  referring case:', r['case_id'])
    print('  donor case    :', r['candidates'][0]['case_id'])
    print('  candidate ref :', r['candidates'][0]['source_record_ref'])

print()
print('=== depth-2: rows_in_D whose candidate ref is itself in D ===')
for r in rows_in_D:
    for c in (r.get('candidates') or []):
        if c['source_record_ref'] in D:
            print(' source_record_ref:', r['source_record_ref'], '| field:', r['raw_field'],
                  '| raw:', r['raw_reference_value'], '| class:', r['classification'],
                  '| cand case:', c['case_id'], '| station:', c['station_relationship'],
                  '| volt:', c['voltage_relationship'], '| eligible:', eligible(r, policy.materialize_tiers, cases))

print()
print('=== depth-2 in the strict chain sense ===')
# chain: materialized donor row R -> audit row(s) on R -> candidate C -> is C itself a row
# with an audit row on it? (i.e. C's own refs would be followed at level 2)
refs_with_audit_row = Counter(r['source_record_ref'] for r in inputs.audit_rows)
for r in rows_in_D:
    for c in (r.get('candidates') or []):
        n = refs_with_audit_row.get(c['source_record_ref'], 0)
        if n:
            print(' level2 node:', c['source_record_ref'], 'belongs to case', c['case_id'],
                  'declares', n, 'further references',
                  '| in D:', c['source_record_ref'] in D)

# Which donor rows share a candidate-set
print()
print('=== do any of the 342 rows resolve back into a case already in the append plan destination set? ===')
dest_keys = {e['destination_member'].rsplit('/', 1)[0] for e in plan}
print('distinct destination source_case_keys in append plan:', len(dest_keys))
print('distinct donor cases of all append-plan rows:', len({c for ref in D for c in cand_case_of[ref]}))
print('D donor refs with no candidate-case mapping:', sum(1 for ref in D if ref not in cand_case_of))

# walk_closure smoke: run the shipped walker over a synthetic lookup on the one eligible row
print()
print('=== walk_closure behaviour demo (synthetic lookup, max_depth=2) ===')
def lookup(key):
    return []
print(list(walk_closure(('x', 'LINE', 'y'), lookup, max_depth=2)))
try:
    print(list(walk_closure(('x', 'LINE', 'y'), lookup, max_depth=None)))
except ValueError as exc:
    print('max_depth=None raises:', exc)
