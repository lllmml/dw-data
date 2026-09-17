"""D1 assessment records and independently reaggregatable coverage statistics."""
from collections import Counter, defaultdict
from hashlib import sha256

from grid_case_generator.analysis.completion_profiles import validate_profile
from grid_case_generator.analysis.completion_contract import VERSION, RULE_VERSION, evaluate
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.models.completion import CompletionFacts, ActionCohort, Operation

STREAMS = ('feeder_completion_cohorts', 'synthetic_eligibility', 'prohibitions',
           'role_evidence', 'operation_eligibility')


def profile_records(profile):
    streams = {k: [] for k in STREAMS}
    for feeder in profile['feeders']:
        facts = CompletionFacts.from_dict(feeder['facts']); decision = evaluate(facts)
        def base(kind, key=''):
            return {'assessment_id':'completion-evidence:'+sha256(canonical_json_bytes(
                        [VERSION, kind, facts.case_id, facts.feeder_id, key])).hexdigest(),
                    'case_id':facts.case_id, 'feeder_id':facts.feeder_id,
                    'source_case_key':profile['source_case_key'], 'case_profile_ref':profile['profile_id'],
                    'supporting_source_refs':feeder['source_record_refs'],
                    'supporting_evidence_refs':[profile['profile_id']], 'conflict_refs':profile['conflict_refs'],
                    'rule_id':'SYNTHETIC_COMPLETION_ELIGIBILITY_V1', 'rule_version':RULE_VERSION,
                    'decision_reason':decision['decision_reason'], 'evidence_class':'UNRESOLVED',
                    'stage':decision['stage'], 'generated_object_count':0}
        streams['feeder_completion_cohorts'].append(dict(base('cohort'),
            primary_action=decision['primary_action'], original_flags=decision['original_flags'],
            readiness=decision['readiness'], source_evidence_cohort=feeder['source_evidence_cohort'],
            target_coverage={p:profile['graphs'][p]['target_coverage'] for p in ('S0','S2')},
            e3_ready=False, opendss_ready=False))
        streams['synthetic_eligibility'].append(dict(base('eligibility'),
            readiness=decision['readiness'], primary_action=decision['primary_action'],
            eligible_operations=[op for op, d in decision['operations'].items() if d['eligible']],
            prohibition_codes=decision['prohibition_codes'], e3_ready=False, opendss_ready=False))
        streams['prohibitions'].append(dict(base('prohibitions'), codes=decision['prohibition_codes'],
            explicit_source_prohibitions=sorted(facts.explicit_prohibitions),
            by_operation={op:d['reasons'] for op,d in decision['operations'].items()}))
        streams['role_evidence'].append(dict(base('role'), role_assessment=decision['role_assessment'],
            zero_transformer_source_rows='B' in facts.flags, source_rows=profile['source']['row_counts'],
            name_weak_evidence_only=feeder['name_weak_evidence_only'],
            business_confirmation_required=decision['role_assessment']=='ROLE_UNDETERMINED',
            engineering_semantics_missing=not (facts.ownership_confirmed and facts.mv_side_confirmed),
            ownership_basis='CASE_SCOPE_ONLY', voltage_evidence_ref=profile['profile_id'],
            count_policy='REQUIRES_GENERATION_POLICY_OR_BUSINESS_CONFIRMATION'))
        for op, result in decision['operations'].items():
            streams['operation_eligibility'].append(dict(base('operation',op), operation=op, **result,
                placement_semantics='ENGINEERING_PLACEMENT', generated_evidence_class_if_later_applied='RULE_GENERATED'))
    return streams


class CompletionSummary:
    def __init__(self):
        self.case_ids=set(); self.feeder_ids=set(); self.primary=Counter(); self.flags=Counter()
        self.ops=Counter(); self.prohibitions=Counter(); self.roles=Counter(); self.readiness=Counter()
        self.no_feeder=0; self.s0_full=0;self.s2_full=0;self.hist_n=0;self.hist_edges=0
        self.groups=defaultdict(lambda: {'feeders':0,'row_totals':Counter(),'row_distributions':defaultdict(Counter),
            'usable':Counter(),'components':defaultdict(Counter),'regions':defaultdict(Counter),
            'station_type_rows':Counter(),'simconfig':defaultdict(Counter),'voltage':Counter(),
            'action_cohorts':Counter(), 'state_counts':Counter()})
        self.a_details=Counter()

    def add(self, p):
        validate_profile(p)
        if p['case_id'] in self.case_ids:raise ValueError('duplicate completion case')
        self.case_ids.add(p['case_id']);self.no_feeder+=not p['feeders']
        for feeder in p['feeders']:
            f=CompletionFacts.from_dict(feeder['facts']);d=evaluate(f)
            if f.feeder_id in self.feeder_ids:raise ValueError('duplicate completion feeder')
            self.feeder_ids.add(f.feeder_id);self.primary[d['primary_action']]+=1;self.flags.update(f.flags)
            self.readiness[d['readiness']]+=1;self.prohibitions.update(d['prohibition_codes'])
            for op,result in d['operations'].items():self.ops[op]+=result['eligible']
            if 'B' in f.flags:self.roles[d['role_assessment']]+=1
            self.s0_full+=f.s0_full;self.s2_full+=f.s2_full
            if ('A' in f.flags and 'D' not in f.flags and f.s2_usable
                and len(p['graphs']['S2']['candidate_junctions'])==1
                and not p['source']['state_counts'].get('SWITCH:OPEN',0)):
                self.hist_n+=1;self.hist_edges+=f.unreferenced_count
            if 'A' in f.flags:
                for key,value in {'total':1,'unreferenced_transformers':f.unreferenced_count,
                    'valid_head':f.valid_head,'source_line_present':bool(f.source_line_count),
                    'accepted_usable':f.s0_usable,'s2_usable':f.s2_usable,
                    'accepted_unique_region':f.accepted_junction_count==1,
                    'accepted_multiple_regions':f.accepted_junction_count>1,
                    's2_unique_region':len(p['graphs']['S2']['candidate_junctions'])==1,
                    's2_multiple_unranked_regions':len(p['graphs']['S2']['candidate_junctions'])>1,
                    'insufficient_structure_primary':d['primary_action']==ActionCohort.INSUFFICIENT_STRUCTURE,
                    'attachment_eligible':d['operations'][Operation.SYNTHETIC_ATTACHMENT_EDGE]['eligible']}.items():
                    self.a_details[key]+=value
            groups=['all', 'B' if 'B' in f.flags else 'with_transformer']
            groups += [flag for flag in f.flags if flag!='B']
            for name in groups:
                g=self.groups[name];g['feeders']+=1;g['row_totals'].update(p['source']['row_counts'])
                g['state_counts'].update(p['source']['state_counts']);g['action_cohorts'][d['primary_action']]+=1
                for k,v in p['source']['row_counts'].items():g['row_distributions'][k][str(v)]+=1
                for policy,graph in p['graphs'].items():
                    g['usable'][policy]+=graph['usable_backbone']
                    g['components'][policy][str(graph['conducting_components'])]+=1
                    g['regions'][policy][str(len(graph['candidate_junctions']))]+=1
                g['station_type_rows'].update(p['source']['field_values'].get('Station_Type',{}))
                for k,v in p['source']['field_values'].items():
                    if k.startswith('SimConfig:'):g['simconfig'][k].update(v)
                g['voltage'][p['head']['nominal_voltage_kv'] if p['head'] else '<NO_HEAD>']+=1

    def finish(self):
        return {'contract_version':VERSION,'case_count':len(self.case_ids),'feeder_count':len(self.feeder_ids),
            'cases_without_feeder':self.no_feeder,
            'primary_action_cohorts':{a:self.primary[a] for a in ActionCohort},'original_cohorts':dict(self.flags),
            'operation_eligible_feeders':{op:self.ops[op] for op in Operation},
            'conservative_synthetic_eligible':self.primary[ActionCohort.AUTO_SYNTHETIC_ELIGIBLE],
            'role_confirmation_primary':self.primary[ActionCohort.ROLE_CONFIRMATION_REQUIRED],
            'blocked_primary':self.primary[ActionCohort.BLOCKED_BY_SOURCE_CONFLICT],
            'zero_transformer_role_cohorts':{k:self.roles[k] for k in ('ROLE_UNDETERMINED',
                'NO_TRANSFORMER_REQUIRED_CANDIDATE','SYNTHETIC_TRANSFORMER_ROLE_CANDIDATE')},
            'prohibition_feeders':dict(self.prohibitions),'readiness':dict(self.readiness),
            'accepted_s0_target_full':self.s0_full,'counterfactual_s2_target_full':self.s2_full,
            'historical_counterfactual_only':{'screened_feeders':self.hist_n,'hypothetical_connections':self.hist_edges,
                'prior_review_target_full_upper_bound':93,'is_eligibility':False},
            'a_refinement':dict(self.a_details),'structure_comparison':dict(self.groups),
            'synthetic_objects_created':0,'accepted_topology_changed':False,'s2_accepted':False,
            'e3_ready_feeders':0,'opendss_ready_feeders':0}


def render_report(s):
    rows='\n'.join(f'| {key} | {value} |' for key,value in s['primary_action_cohorts'].items())
    return f'''# E2.3-D1 — Synthetic completion contract and cohort refinement

Contract only; no generated topology. Cases {s['case_count']}; Feeders {s['feeder_count']};
no-Feeder cases {s['cases_without_feeder']}. Source/accepted/frozen artifacts unchanged.

| Primary action cohort | Feeders |
|---|---:|
{rows}

Original overlapping flags: {dict(sorted(s['original_cohorts'].items()))}.
Conservative eligible: {s['conservative_synthetic_eligible']}.
Zero-Transformer roles: {dict(sorted(s['zero_transformer_role_cohorts'].items()))}.
Accepted S0 target FULL: {s['accepted_s0_target_full']}; unaccepted S2 FULL: {s['counterfactual_s2_target_full']}.
Historical counterfactual only: {s['historical_counterfactual_only']}.

Primary conflict priority retains role-undetermined as a secondary reason for blocked B.
Whole-case source OPEN screening is stricter than reachable-frontier-only screening.
Case-scoped ownership is not confirmed equipment ownership; absent MV voltage/side is
not voltage compatibility. Names, AP IDs and generic SimConfig do not certify business role.
All operation reasons, including missing confirmations, are retained in detail files.
Structure comparison includes source Line/AP/Load/DER/Switch/Station counts, voltage,
SimConfig, conducting component and attachment-region distributions for B and with-T cases.

Candidate stages stop at ELIGIBLE in this analysis. Evidence remains UNRESOLVED.
Synthetic objects: 0; E3/OpenDSS-ready: 0. No completed topology file exists.
Next: review business owner/MV/role/region-policy evidence before authorizing D2.
STOP: D1 does not authorize D2, S2 acceptance, E3, parameters or OpenDSS.
'''
