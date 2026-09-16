"""Aggregation is shared by the writer and the independent detail verifier."""
from collections import Counter
from itertools import combinations
import json

from grid_case_generator.io.canonical_json import canonical_json_bytes

from grid_case_generator.analysis.topology_recovery import VERSION, RULES, EXPERIMENTS, PRIMARY_ORDER


class RecoverySummary:
    def __init__(self):
        self.case_ids = set()
        self.counts = Counter()
        self.cohorts = Counter(); self.cross = Counter(); self.coverage = Counter(); self.legacy = Counter()
        self.transformers = Counter(); self.all_transformers = Counter(); self.audit = Counter()
        self.readiness = Counter(); self.flags = Counter(); self.constraints = Counter()
        self.frontier = {p:{'primary':Counter(), 'observed_feeders':Counter(), 'boundary_records':Counter()} for p in ('S0','S2')}
        self.candidates = {r:{'eligible_devices':0,'eligible_feeders':0,'eligible_cases':0} for r in RULES}
        self.overlaps = Counter()
        self.experiments = {p:{'status_transitions':Counter(), 'reachable_transformer_delta':0,
                              'target_coverage':Counter(), 'structural_cycle_rank_delta':0, 'conducting_cycle_rank_delta':0} for p in EXPERIMENTS}
        self.largest = []

    def add(self, result):
        cid=result['case_id']
        if cid in self.case_ids: raise ValueError('duplicate recovery case')
        self.case_ids.add(cid); n=len(result['feeders'])
        self.counts.update(case_count=1,feeder_count=n,cases_without_feeder=int(not n),
                           cases_with_unresolved_ownership=int(result['case_ownership_unresolved']))
        self.all_transformers.update(t['reference_composition'] for t in result['transformers'])
        if n:
            self.transformers.update(t['reference_composition'] for t in result['transformers'])
            self.counts['feeder_case_transformer_groups']+=len(result['transformers'])
            for t in result['transformers']:
                for key in ('identity_ambiguous','unresolved_reference','ambiguous_reference'):
                    self.audit[key]+=int(t[key])
                for policy in ('S0','S2'):
                    for key in ('projected','reachable'):self.audit[policy+'_'+key]+=int(t['attachment'][policy][key])
        present={w['rule_id'] for w in result['candidates']}
        for rule in RULES:
            count=sum(w['rule_id']==rule for w in result['candidates'])
            self.candidates[rule]['eligible_devices']+=count
            self.candidates[rule]['eligible_cases']+=int(count>0)
            self.candidates[rule]['eligible_feeders']+=n if count and not result['case_ownership_unresolved'] else 0
        for a,b in combinations(RULES,2):
            self.overlaps[a+' & '+b]+=n if a in present and b in present else 0
        for f in result['feeders']:
            self.cohorts[f['source_evidence_cohort']]+=1
            self.cross[f['source_evidence_cohort']+'/'+f['legacy_target_status']]+=1
            self.coverage[f['target_coverage']]+=1;self.legacy[f['legacy_target_status']]+=1
            self.readiness[f['recovery_readiness']]+=1;self.flags.update(f['completion_cohorts']);self.constraints.update(f['constraint_tags'])
            self.counts['synthetic_connections']+=f['evidence_composition']['synthetic_connections']
            self.counts['e3_ready_feeders']+=int(f['e3_ready'])
            for policy in ('S0','S2'):
                bs=[b for b in result['blockers'] if b['policy']==policy];tags={b['tag'] for b in bs}
                primary=next((t for t in PRIMARY_ORDER if t in tags),'NONE')
                self.frontier[policy]['primary'][primary]+=1
                self.frontier[policy]['observed_feeders'].update(tags)
                self.frontier[policy]['boundary_records'].update(b['tag'] for b in bs)
            for name, values in result['experiments'].items():
                target=values['target_coverage'];before=f['target_coverage'];e=self.experiments[name]
                e['status_transitions'][before+'->'+target]+=1;e['target_coverage'][target]+=1
                e['reachable_transformer_delta']+=values['reachable_transformers']-result['graphs']['S2']['reachable_transformers']
                for kind in ('structural','conducting'):
                    e[kind+'_cycle_rank_delta']+=values[kind+'_cycle_rank']-result['graphs']['S2'][kind+'_cycle_rank']
        self.largest.append({'case_id':cid,'source_case_key':result['source_case_key'],
                             'transformer_groups':len(result['transformers']),
                             'unreferenced_transformers':sum(t['reference_composition']=='NO_REFERENCE' for t in result['transformers'])})
        self.largest.sort(key=lambda x:(-x['transformer_groups'],x['case_id']));del self.largest[5:]

    def finish(self):
        c={key:self.counts[key] for key in ('case_count','feeder_count','cases_without_feeder','cases_with_unresolved_ownership',
                                           'feeder_case_transformer_groups','synthetic_connections','e3_ready_feeders')}
        return dict(c, analysis_version=VERSION,
                    source_evidence_cohorts=dict(self.cohorts),source_evidence_by_legacy_status=dict(self.cross),
                    target_coverage=dict(self.coverage),legacy_target_coverage=dict(self.legacy),
                    necessary_evidence_upper_bound={'label':'necessary evidence upper-bound cohort',
                                                   'feeder_count':self.cohorts['ALL_TARGETS_HAVE_REFERENCE'],
                                                   'achievable_full_prediction':False},
                    transformer_reference_composition=dict(self.transformers),all_case_transformer_reference_composition=dict(self.all_transformers),
                    transformer_audit=dict(self.audit),recovery_readiness=dict(self.readiness),completion_cohorts=dict(self.flags),
                    constraint_feeders=dict(self.constraints),frontier=self.frontier,candidate_rules=self.candidates,
                    candidate_feeder_overlaps=dict(self.overlaps),counterfactual_experiments=self.experiments,
                    largest_transformer_cases=self.largest,
                    accepted_topology_changed=False,next_review='E2.3-D Synthetic Topology Completion Contract',
                    automatic_candidate_implementation=False)


def render_report(s):
    s=json.loads(canonical_json_bytes(s))
    cohort_rows='\n'.join(f"| {key} | {value} |" for key,value in sorted(s['source_evidence_cohorts'].items()))
    audit_rows='\n'.join(f"| {key} | {value} |" for key,value in sorted(s['transformer_reference_composition'].items()))
    rows=[]
    for rule in RULES:
        c=s['candidate_rules'][rule];e=s['counterfactual_experiments'][rule];t=e['status_transitions']
        rows.append(f"| {rule} | {c['eligible_devices']} | {c['eligible_feeders']} | {e['reachable_transformer_delta']} | {t.get('FAILED->PARTIAL',0)} | {t.get('FAILED->FULL',0)} | {t.get('PARTIAL->FULL',0)} |")
    return f'''# E2.3-A — Topology Recovery Evidence & Readiness Foundation

**ANALYSIS ONLY. Accepted topology unchanged. No synthetic connections generated.**

## Population and target coverage

Cases: {s['case_count']}; source Feeder identity groups: {s['feeder_count']};
no-Feeder cases: {s['cases_without_feeder']}. All cases retained, including abnormal large cases.
Legacy S2 FULL/PARTIAL/FAILED: {s['legacy_target_coverage']}.
Independent target coverage (zero targets never FULL): {s['target_coverage']}.
FULL is not E3_READY; E3-ready feeders: {s['e3_ready_feeders']}.
S2 remains counterfactual, not a newly accepted topology policy.

## Mutually exclusive source evidence cohorts

| Source evidence cohort | Feeders |
|---|---:|
{cohort_rows}

ALL_TARGETS_HAVE_REFERENCE is the **necessary evidence upper-bound cohort**, not
recoverable, achievable or expected FULL. Raw references do not prove electrical semantics.
Full cohort/status cross table is in summary.json; per-feeder evidence is in feeder_details.jsonl.
ZERO_TRANSFORMER_ROWS is verified E1 file accounting, not inferred from missing published records.
Missing/ambiguous source evidence is retained separately. No raw data is reinterpreted or repaired.

## Transformer evidence (cases with source Feeders)

| Reference composition | Identity groups |
|---|---:|
{audit_rows}

Identity and reference ambiguity, unresolved declarations, and S0/S2 attachment projection
and reachability are separate fields in transformer_evidence.jsonl. All-case totals include
no-Feeder cases separately. Largest source cases are reported in summary.json, never deleted.

## Frontier and readiness

S0 and S2 frontiers are separate. Observed blockers overlap; primary observations use the
specified deterministic priority and are not causal diagnoses. The boundary witness records
identify Line/Terminal/target evidence, known OPEN, voltage and unresolved/ambiguous references.
No Line, no head-reachable Line and reachable Line without reachable Transformer are distinct.
Readiness: {s['recovery_readiness']}.
Completion cohorts (overlap allowed): {s['completion_cohorts']}.
A: existing Transformer needs connection/attachment/ownership; never create a duplicate.
B: zero source records, ROLE_UNDETERMINED; no automatic Transformer generation.
C: referenced but incomplete paths, eligible for rule review rather than promised recovery.
D: identity/voltage/OPEN/ownership constraints; do not bridge around them synthetically.

## Candidate experiments, never applied to accepted topology

| Rule | Devices | Feeders | Reachable Transformer delta | FAILED→PARTIAL | FAILED→FULL | PARTIAL→FULL |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

MULTI_LINE_T_AS_MV_JUNCTION is RISK_EXPERIMENT_ONLY and NOT_RECOMMENDED. Its hypothetical
MV-port merging cannot establish safe FULL. No candidate evidence is promoted to approved
RULE_INFERRED. Known OPEN is preserved. Counterfactual graph hashes, cycle-rank diagnostics,
cumulative policies, transitions and overlaps are included; do not add overlapping gains.
Cycle rank is a diagnostic, not a complete equipment/voltage/ownership safety certificate.

## Evidence and next gate

Synthetic connections: {s['synthetic_connections']}. Existing synthetic feeder-head *nodes*
remain explicit modeling assumptions, not source-confirmed connections. Exact resolver
status alone never establishes SOURCE_CONFIRMED. S0 branches retain approved v1 provenance;
S2-only connections stay UNRESOLVED in connection_evidence.jsonl.

E2.3-A evidence foundation completed; topology completion is not completed.
B adds representation without primary coverage; C1 does not improve feeder status; C2's
limited PARTIAL recovery does not establish new safe FULL. Next major review:
**E2.3-D — Synthetic Topology Completion Contract**. B/C require separate authorization.
STOP: no B/C/D implementation, E3, OpenDSS, Load/PV or 8760 generation.
'''
