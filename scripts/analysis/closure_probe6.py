import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, '/data/limingliang/dw-data/data-generation/src')
from grid_case_generator.io.completion_ledger_artifacts import inputs_from_artifacts
from grid_case_generator.generation.completion_ledger import (
    build_ledger, eligible, CROSS_CASE_RULE)
from grid_case_generator.io.source_bytes import member_path_of
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
plan_keys = {(e['destination_member'], e['donor_source_record_ref']) for e in plan}

ref_own_case = defaultdict(set)
by_case_ref = defaultdict(list)
for row in inputs.audit_rows:
    ref_own_case[row['source_record_ref']].add(row['case_id'])
    by_case_ref[(row['case_id'], row['source_record_ref'])].append(row)
cases = {r['case_id']: r for r in inputs.audit_cases}

# the closure's single eligible level-1 row
lvl1 = {}
for ref in D:
    for c in ref_own_case[ref]:
        for row in by_case_ref[(c, ref)]:
            lvl1[row['reference_id']] = row
ok1 = [r for r in lvl1.values() if eligible(r, policy.materialize_tiers, cases)[0]]
print('eligible level-1 rows:', len(ok1))
r = ok1[0]
c = r['candidates'][0]
donor_filename = member_path_of(c['source_record_ref']).rpartition('/')[2]
destination_member = f"{r['source_case_key']}/{donor_filename}"
key = (destination_member, c['source_record_ref'])
print('closure would want to append:', key)
print('already in the shipped append plan:', key in plan_keys)
print()
print('the existing shipped plan entry for that key:')
for e in plan:
    if (e['destination_member'], e['donor_source_record_ref']) == key:
        print('  tier:', e['tier'], '| source_record_ref:', e['source_record_ref'],
              '| record_ids:', len(e['record_ids']))

# which reference_ids contributed
mat = [x for x in ledger.completion_records if x['rule_id'] == CROSS_CASE_RULE]
existing = [x for x in mat if x['donor_source_record_ref'] == c['source_record_ref']
            and x['source_case_key'] == r['source_case_key']]
print('  shipped PROPOSED records already copying that donor into that case:', len(existing))
for x in existing:
    print('    ref field', x['raw_field'], 'raw', x['raw_reference_value'],
          'from referring case record', x['source_record_ref'])

# tier-relaxed: dedup check for the 18 level-1 rows
both = ('SAME_STATION', 'CROSS_STATION')
ok_both = [x for x in inputs.audit_rows if eligible(x, both, cases)[0]]
D2 = {x['candidates'][0]['source_record_ref'] for x in ok_both}
lvl1b = {}
for ref in D2:
    for cc in ref_own_case[ref]:
        for row in by_case_ref[(cc, ref)]:
            lvl1b[row['reference_id']] = row
ok1b = [x for x in lvl1b.values() if eligible(x, both, cases)[0]]
# would these need new rows? build the plan keys under the relaxed policy
plan_keys_b = set()
for x in ok_both:
    cc = x['candidates'][0]
    plan_keys_b.add((f"{x['source_case_key']}/{member_path_of(cc['source_record_ref']).rpartition('/')[2]}",
                     cc['source_record_ref']))
new = 0
for x in ok1b:
    cc = x['candidates'][0]
    k2 = (f"{x['source_case_key']}/{member_path_of(cc['source_record_ref']).rpartition('/')[2]}",
          cc['source_record_ref'])
    if k2 not in plan_keys_b:
        new += 1
print()
print('CROSS_STATION-enabled scenario: level-0 rows', len(ok_both),
      '| level-1 eligible', len(ok1b), '| of which would need a NEW csv row:', new)
