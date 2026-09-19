import sys, time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, '/data/limingliang/dw-data/data-generation/src')
from grid_case_generator.io.completion_ledger_artifacts import inputs_from_artifacts
from grid_case_generator.generation.completion_ledger import build_ledger, eligible
from grid_case_generator.models.completion_export import parse_policy

t0 = time.time()
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
print('load %.1fs' % (time.time()-t0))
ledger = build_ledger(inputs)
print('ledger %.1fs' % (time.time()-t0))
plan = ledger.append_plan
D = {e['donor_source_record_ref'] for e in plan}

# --- is the closure's donor row already in the plan for that destination? ---
dest = '数据/上新河变_10kV渔人#2线256/07_AccessPoint.csv'
print()
print('existing plan entries for', dest)
for e in plan:
    if e['destination_member'] == dest:
        print('  donor:', e['donor_source_record_ref'], '| record_ids:', len(e['record_ids']))

# --- tier-relaxed scenario: would a chain appear if CROSS_STATION were enabled? ---
both = ('SAME_STATION', 'CROSS_STATION')
cases = {r['case_id']: r for r in inputs.audit_cases}
ref_own_case = defaultdict(set)
by_case_ref = defaultdict(list)
for row in inputs.audit_rows:
    ref_own_case[row['source_record_ref']].add(row['case_id'])
    by_case_ref[(row['case_id'], row['source_record_ref'])].append(row)

ok_both = [r for r in inputs.audit_rows if eligible(r, both, cases)[0]]
print()
print('level-0 materialized under both tiers:', len(ok_both), '(vs', len(plan), 'appended rows shipped)')
D2 = {r['candidates'][0]['source_record_ref'] for r in ok_both}
print('D(both) size:', len(D2))
lvl1 = {}
for ref in D2:
    for c in ref_own_case[ref]:
        for row in by_case_ref[(c, ref)]:
            lvl1[row['reference_id']] = row
print('distinct audit rows on D(both) donor rows:', len(lvl1))
ok1b = [r for r in lvl1.values() if eligible(r, both, cases)[0]]
print('  eligible under both tiers:', len(ok1b))
lvl2 = {}
for r in ok1b:
    c = r['candidates'][0]
    for row in by_case_ref.get((c['case_id'], c['source_record_ref']), ()):
        lvl2[row['reference_id']] = row
print('level-2 rows reached:', len(lvl2), '| eligible:', sum(1 for r in lvl2.values() if eligible(r, both, cases)[0]))
print('elapsed %.1fs' % (time.time()-t0))
