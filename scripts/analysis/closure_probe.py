"""Read-only probe: would wiring the CROSS_CASE_REFERENCE_COPY_V1 closure change anything?"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, '/data/limingliang/dw-data/data-generation/src')

from grid_case_generator.io.completion_ledger_artifacts import inputs_from_artifacts
from grid_case_generator.generation.completion_ledger import (
    build_ledger, eligible, closure_key, CROSS_CASE_RULE)
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
print('append_plan entries:', len(plan))
print('audit_rows:', len(inputs.audit_rows))
print('audit_cases:', len(inputs.audit_cases))

# cross-rule MATERIALIZE records
mat = [r for r in ledger.completion_records if r['rule_id'] == CROSS_CASE_RULE]
print('CROSS_CASE completion records (materializing):', len(mat))

# D = donor refs
D = {e['donor_source_record_ref'] for e in plan}
print('distinct donor_source_record_ref:', len(D))

# donor ref -> donor case_id(s), from the materializing records' candidates
# The append plan entry does not carry candidate case_id, so recover from audit rows:
donor_cases = defaultdict(set)
ref_to_row_ids = defaultdict(list)
for r in mat:
    donor_cases[r['donor_source_record_ref']].add(None)  # placeholder, filled below

# Build from audit_rows: candidate source_record_ref -> candidate case_id
cand_case_of = defaultdict(set)
for row in inputs.audit_rows:
    for c in (row.get('candidates') or []):
        cand_case_of[c['source_record_ref']].add(c['case_id'])

for ref in D:
    if ref not in cand_case_of:
        print('  !! donor ref with no candidate case:', ref)

# --- 3. scan cross_case_references for rows whose source_record_ref is in D
rows_in_D = []
for row in inputs.audit_rows:
    if row['source_record_ref'] in D:
        rows_in_D.append(row)
print()
print('cross_case_references rows whose source_record_ref is in D:', len(rows_in_D))
print('distinct source_record_ref among them:', len({r['source_record_ref'] for r in rows_in_D}))
print('distinct case_id among them:', len({r['case_id'] for r in rows_in_D}))

# Does the row's case_id equal the donor case for that ref?
same_case = [r for r in rows_in_D
             if r['case_id'] in cand_case_of[r['source_record_ref']]]
diff_case = [r for r in rows_in_D
             if r['case_id'] not in cand_case_of[r['source_record_ref']]]
print('  rows whose case_id IS the donor case:', len(same_case))
print('  rows whose case_id is NOT the donor case:', len(diff_case))
if diff_case:
    for r in diff_case[:5]:
        print('   ', r['case_id'], r['source_record_ref'], sorted(cand_case_of[r['source_record_ref']]))

cases = {row['case_id']: row for row in inputs.audit_cases}
tiers = policy.materialize_tiers
ok_rows = [r for r in same_case if eligible(r, tiers, cases)[0]]
print()
print('rows whose source_record_ref in D and case_id == donor case and eligible():', len(ok_rows))
print('  reason breakdown for the others:')
print('   ', dict(Counter(eligible(r, tiers, cases)[1] for r in same_case if not eligible(r, tiers, cases)[0])))
print('  classification breakdown of same_case:', dict(Counter(r['classification'] for r in same_case)))

# 2-level chain: does following those rows yield a further candidate that itself has a row in D?
chain2 = []
for r in ok_rows:
    for c in (r.get('candidates') or []):
        if c['source_record_ref'] in D:
            chain2.append((r, c))
print()
print('2-level chains (eligible donor-row references a candidate that is itself a materialized donor row):', len(chain2))

# Also: any row at all (regardless of eligibility) whose candidate ref is in D -> depth-2 potential
potential2 = [(r, c) for r in same_case for c in (r.get('candidates') or []) if c['source_record_ref'] in D]
print('depth-2 candidates among ALL same_case rows (not only eligible):', len(potential2))
potential2b = [(r, c) for r in rows_in_D for c in (r.get('candidates') or []) if c['source_record_ref'] in D]
print('depth-2 candidates among ALL rows_in_D:', len(potential2b))

# --- 5. audit coverage per case
per_case = Counter(r['case_id'] for r in inputs.audit_rows)
case_ids = {c['case_id'] for c in inputs.audit_cases}
print()
print('cases with >=1 row in cross_case_references:', len(per_case))
print('cases in case_inventory:', len(case_ids))
print('cases in inventory with 0 rows:', len(case_ids - set(per_case)))
print('rows whose case_id is not in case_inventory:', sum(1 for r in inputs.audit_rows if r['case_id'] not in case_ids))
# rows whose case_id differs from all candidate case_ids (i.e. not cross-case)
no_cross = [r for r in inputs.audit_rows
            if not any(c['case_id'] != r['case_id'] for c in (r.get('candidates') or []))]
print('rows with no candidate in a different case:', len(no_cross))

# --- 6. closure_depth values
print()
print('closure_depth values in completion_records:', dict(Counter(
    repr(r['closure_depth']) for r in ledger.completion_records)))
print('closure_depth values in unresolved_records:', dict(Counter(
    repr(r['closure_depth']) for r in ledger.unresolved_records)))

# policy max depth
print('policy max_reference_closure_depth:', policy.max_reference_closure_depth)
print('policy materialize_tiers:', policy.materialize_tiers)
