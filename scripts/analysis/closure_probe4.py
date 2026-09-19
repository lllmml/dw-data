import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, '/data/limingliang/dw-data/data-generation/src')
from grid_case_generator.io.completion_ledger_artifacts import inputs_from_artifacts
from grid_case_generator.generation.completion_ledger import build_ledger, eligible
from grid_case_generator.models.completion_export import parse_policy

REPO = Path('/data/limingliang/dw-data/data-generation')
policy = parse_policy(REPO / 'configs/nanjing_completion_policy_v1.json')
roots = {
 'source': REPO/'outputs/nanjing-e1/source-import-v2','baseline': REPO/'outputs/nanjing-e2/topology-v1',
 'projection': REPO/'outputs/nanjing-e2-2/switch-projection-design-v1','feeder': REPO/'outputs/nanjing-e2-2/feeder-coverage-v1',
 'recovery': REPO/'outputs/nanjing-e2-3/topology-recovery-evidence-v1','d1': REPO/'outputs/nanjing-e2-3/synthetic-completion-contract-v1',
 'd2': REPO/'outputs/nanjing-e2-3/synthetic-topology-proposals-v1','frozen': REPO/'outputs/nanjing-e2/topology-v1',
 'd3_analysis': REPO/'outputs/nanjing-e2-3/deterministic-topology-recovery-v1','accepted_v2': REPO/'outputs/nanjing-e2-3/accepted-topology-v2',
 'd4': REPO/'outputs/nanjing-e2-3/synthetic-backbone-proposals-v1','placement': REPO/'outputs/nanjing-e2-3/placement-evidence-v1-1',
 'audit': REPO/'outputs/nanjing-e2-3/case-boundary-audit-v1'}
inputs = inputs_from_artifacts({k: str(v) for k, v in roots.items()}, policy)
ledger = build_ledger(inputs)
plan = ledger.append_plan
D = {e['donor_source_record_ref'] for e in plan}

ref_own_case = defaultdict(set)
for row in inputs.audit_rows:
    ref_own_case[row['source_record_ref']].add(row['case_id'])
by_case_ref = defaultdict(list)
for row in inputs.audit_rows:
    by_case_ref[(row['case_id'], row['source_record_ref'])].append(row)

# distinct closure-level-1 audit rows reachable from the plan (dedup by reference_id)
visited_refs = set()
reachable_rows = {}
for e in plan:
    ref = e['donor_source_record_ref']
    for c in ref_own_case[ref]:
        for row in by_case_ref[(c, ref)]:
            reachable_rows[row['reference_id']] = row
print('DISTINCT audit rows on materialized donor rows (dedup by reference_id):', len(reachable_rows))
print('  distinct donor rows (source_record_ref) with >=1 such row:',
      len({r['source_record_ref'] for r in reachable_rows.values()}))
print('  by classification:', dict(Counter(r['classification'] for r in reachable_rows.values())))
cases = {r['case_id']: r for r in inputs.audit_cases}
ok = [r for r in reachable_rows.values() if eligible(r, policy.materialize_tiers, cases)[0]]
print('  eligible among them:', len(ok))

# ledger coverage of the audit stream
cross_completion = [r for r in ledger.completion_records if r['rule_id'] == 'CROSS_CASE_REFERENCE_COPY_V1']
cross_unresolved = [r for r in ledger.unresolved_records
                    if r['reason'] in ('VOLTAGE_NOT_COMPATIBLE','TIER_NOT_MATERIALIZED','UNDEFINED_GLOBAL',
                                       'LOCAL_UNRESOLVED_ONLY','MULTIPLE_EXTERNAL_MATCH',
                                       'REFERRING_CASE_HARD_BLOCKER','DONOR_CASE_HARD_BLOCKER')]
print()
print('audit rows:', len(inputs.audit_rows), '| ledger PROPOSED(CROSS_CASE):', len(cross_completion),
      '| ledger UNRESOLVED carrying a cross-case reason:', len(cross_unresolved),
      '| sum:', len(cross_completion)+len(cross_unresolved))

# the destination for the single closure copy
dest_case_key = ok[0]['source_case_key'] if ok else None
print()
print('single closure copy destination case key:', dest_case_key)
rows_here = [e for e in plan if e['destination_member'].startswith(dest_case_key + '/')]
print('  existing append-plan entries into that case:', len(rows_here))
print('  existing members:', sorted({e['destination_member'].rsplit("/",1)[1] for e in rows_here}))
print('  would add member: 07_AccessPoint.csv -> existing entries into it:',
      len([e for e in rows_here if e['destination_member'].endswith('/07_AccessPoint.csv')]))

# closure_depth semantics: contract vs code
print()
print('closure_depth in CROSS_CASE completion records:', dict(Counter(
    repr(r['closure_depth']) for r in cross_completion)))
print('closure_depth in recovery completion records:', dict(Counter(
    repr(r['closure_depth']) for r in ledger.completion_records
    if r['rule_id'] == 'ACCEPTED_DETERMINISTIC_RECOVERY_V1')))
print('closure_depth in PLACEMENT_MISSING_ENDPOINT_BUS_V1 records:', dict(Counter(
    repr(r['closure_depth']) for r in ledger.completion_records
    if r['rule_id'] == 'PLACEMENT_MISSING_ENDPOINT_BUS_V1')))
print('closure_depth in unresolved records:', dict(Counter(
    repr(r['closure_depth']) for r in ledger.unresolved_records)))
print('policy max_reference_closure_depth:', policy.max_reference_closure_depth)

# who records the tier for the closure copy
print()
print('single closure copy row in detail:')
r = ok[0]
print('  destination case:', r['case_id'], r['source_case_key'])
print('  donor row:', r['candidates'][0]['source_record_ref'])
print('  donor case:', r['candidates'][0]['case_id'])
print('  donor entity type:', r['candidates'][0]['source_entity_type'], '-> member 07_AccessPoint.csv?')
