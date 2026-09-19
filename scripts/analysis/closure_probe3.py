"""Simulate wiring CROSS_CASE_REFERENCE_COPY_V1 closure (depth 1 and 2) on real data."""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, '/data/limingliang/dw-data/data-generation/src')

from grid_case_generator.io.completion_ledger_artifacts import inputs_from_artifacts
from grid_case_generator.generation.completion_ledger import (
    build_ledger, eligible, walk_closure, CROSS_CASE_RULE)
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

# The one materialized donor -> donor case mapping (a donor ref is only ever copied into
# a case; a ref belongs to exactly one case because it embeds the case directory).
ref_case_of = defaultdict(set)
for row in inputs.audit_rows:
    for c in (row.get('candidates') or []):
        ref_case_of[c['source_record_ref']].add(c['case_id'])
# direct: audit row's own case
ref_own_case = defaultdict(set)
for row in inputs.audit_rows:
    ref_own_case[row['source_record_ref']].add(row['case_id'])

# audit rows indexed by (case_id, source_record_ref)
by_case_ref = defaultdict(list)
for row in inputs.audit_rows:
    by_case_ref[(row['case_id'], row['source_record_ref'])].append(row)
refs_with_row = Counter(r['source_record_ref'] for r in inputs.audit_rows)

cases = {row['case_id']: row for row in inputs.audit_cases}
tiers = policy.materialize_tiers

# A copied row lands in a destination case; the closure follows *its own* declared
# references. The only published evidence for a row's declared references is the audit's
# rows in the row's OWN case.
def lookup(copied_ref, own_case):
    out = []
    for row in by_case_ref.get((own_case, copied_ref), ()):
        for c in (row.get('candidates') or []):
            out.append((c['case_id'], c['source_entity_type'], c['source_record_ref']))
    return out

# seeds: every materialized copy (destination, donor ref)
# donor ref -> its own case. A ref embeds the case directory, so derive from the plan.
seeds = []
for entry in plan:
    dest_case = entry['destination_member'].rsplit('/', 1)[0]
    donor_ref = entry['donor_source_record_ref']
    own = ref_own_case.get(donor_ref) or ref_case_of.get(donor_ref)
    seeds.append((entry, donor_ref, own))

no_own = [s for s in seeds if not s[2]]
print('plan entries:', len(seeds), '| donor refs with no case attribution:', len(no_own))

depth1 = defaultdict(list)
for entry, donor_ref, own in seeds:
    own_case = sorted(own)[0] if own else None
    if own_case is None:
        continue
    for row in by_case_ref.get((own_case, donor_ref), ()):
        ok, reason = eligible(row, tiers, cases)
        depth1[ok].append(row)
print()
print('depth-1 audit rows encountered on materialized donor rows:', sum(len(v) for v in depth1.values()))
print('  eligible:', len(depth1[True]), '| ineligible:', len(depth1[False]))
print('  ineligibility reasons:', dict(Counter(eligible(r, tiers, cases)[1] for r in depth1[False])))

ok1 = depth1[True]
print()
print('=== depth-1 copies the closure would add ===')
for row in ok1:
    c = row['candidates'][0]
    print(' destination case:', row['case_id'], '|', row['source_case_key'])
    print('   copies:', c['source_entity_type'], c['source_record_ref'], 'from case', c['case_id'])
    print('   field:', row['raw_field'], 'raw:', row['raw_reference_value'], 'tier:', c['station_relationship'])

# depth 2: for each new copied row, follow its own references
print()
print('=== depth-2 ===')
for row in ok1:
    c = row['candidates'][0]
    new_ref, new_case = c['source_record_ref'], c['case_id']
    n = refs_with_row.get(new_ref, 0)
    print(' level-2 node', new_ref)
    print('   declares', n, 'audit rows in its own case', new_case)
    for row2 in by_case_ref.get((new_case, new_ref), ()):
        ok2, reason2 = eligible(row2, tiers, cases)
        print('    -> field', row2['raw_field'], 'raw', row2['raw_reference_value'],
              'class', row2['classification'], 'eligible', (ok2, reason2))

# Total additionally-materialized rows if closure were wired
print()
print('SUMMARY: additional PROPOSED records / appended rows at depth 1 =',
      len(ok1), '; at depth 2 =', sum(
          1 for row in ok1 for row2 in by_case_ref.get(
              (row['candidates'][0]['case_id'], row['candidates'][0]['source_record_ref']), ())
          if eligible(row2, tiers, cases)[0]))
