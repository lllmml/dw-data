"""D2 detailed counterfactual accounting, never accepted coverage."""
from collections import Counter
from grid_case_generator.models.proposals import ProposalClass, VERSION


class ProposalSummary:
    def __init__(self):
        self.cases=set();self.feeders=set();self.primary=Counter();self.hard=Counter();self.states=Counter()
        self.types=Counter();self.counts=Counter();self.transitions={k:Counter() for k in ('physical','conducting')}
        self.before={k:Counter() for k in self.transitions};self.after={k:Counter() for k in self.transitions}
        self.model_before={k:Counter() for k in self.transitions};self.model_after={k:Counter() for k in self.transitions}
        self.d1_cross=Counter();self.roles=Counter();self.stages=Counter()

    def add(self,c,r):
        if c['case_id'] in self.cases:raise ValueError('duplicate proposal case')
        self.cases.add(c['case_id'])
        for f in r['feeder_eligibility']:
            if f['feeder_id'] in self.feeders:raise ValueError('duplicate proposal Feeder')
            self.feeders.add(f['feeder_id']);self.primary[f['primary_class']]+=1
            self.hard.update(set(f['physical_topology_blockers']))
            self.states.update({s['kind']+':'+s['state'] for s in f['scenario_state_constraints']})
            self.d1_cross[f['d1_primary']+' -> '+f['primary_class']]+=1
            if not c['targets']:self.roles[f['role_status']]+=1
            for mode in self.transitions:
                b=r['coverage'][mode]['before'];a=r['coverage'][mode]['after']
                self.before[mode][b['target_coverage']]+=1;self.after[mode][a['target_coverage']]+=1
                self.transitions[mode][b['target_coverage']+' -> '+a['target_coverage']]+=1
                for m,values in ((self.model_before,b),(self.model_after,a)):
                    n=values['model_target_count'];reach=values['reachable_model_transformers']
                    m[mode]['NO_SOURCE_TARGET' if not n else 'FULL' if reach==n else 'PARTIAL' if reach else 'FAILED']+=1
                self.counts[mode+'_feeders_improved']+=a['reachable_transformers']>b['reachable_transformers']
                self.counts[mode+'_unchanged']+=a['reachable_transformers']==b['reachable_transformers']
            self.counts['automatic_eligible_feeders']+=f['automatic_proposal_eligible']
        self.counts['proposal_bundles']+=len(r['proposal_bundles'])
        self.stages.update(b['stage'] for b in r['proposal_bundles'])
        self.types.update(o['kind'] for o in r['proposal_devices']+r['proposal_edges'])
        self.counts['rejected_candidates']+=len(r['rejected_candidates'])
        self.counts['rejected_bundles']+=sum(v['structural_status']=='REJECTED' for v in r['proposal_validation'])
        self.counts['attempted_bundles']+=len(r['proposal_validation'])

    def coverage(self):
        statuses=('FULL','PARTIAL','FAILED','NO_SOURCE_TARGET')
        return {'label':'PROPOSAL_ONLY_COUNTERFACTUAL','source_target_coverage':{
            mode:{'before':{s:self.before[mode][s] for s in statuses},'after':{s:self.after[mode][s] for s in statuses},
                  'transitions':dict(self.transitions[mode]),'feeders_improved':self.counts[mode+'_feeders_improved'],
                  'unchanged_reachability':self.counts[mode+'_unchanged']} for mode in self.transitions},
            'model_target_coverage':{mode:{'before':dict(self.model_before[mode]),'after':dict(self.model_after[mode])} for mode in self.transitions}}

    def finish(self):
        return {'version':VERSION,'label':'PROPOSAL_ONLY_COUNTERFACTUAL','case_count':len(self.cases),'feeder_count':len(self.feeders),
            'primary_classes':{k:self.primary[k] for k in ProposalClass},'hard_blocker_feeders':dict(self.hard),
            'operating_constraint_feeders':dict(self.states),'d1_to_d2_primary':dict(self.d1_cross),
            'zero_transformer_roles':dict(self.roles),'automatic_eligible_feeders':self.counts['automatic_eligible_feeders'],
            'proposal_bundles':self.counts['proposal_bundles'],'attempted_bundles':self.counts['attempted_bundles'],
            'rejected_bundles':self.counts['rejected_bundles'],'rejected_candidates':self.counts['rejected_candidates'],
            'proposal_types':{k:self.types[k] for k in ('SYNTHETIC_ATTACHMENT_EDGE','SYNTHETIC_MV_ATTACHMENT','SYNTHETIC_JUNCTION',
                'SYNTHETIC_LV_BUS','SYNTHETIC_TRANSFORMER','SYNTHETIC_BACKBONE_EDGE','TRANSFORMER_TRANSFER')},
            'bundle_stages':dict(self.stages),'coverage_impact':self.coverage(),
            'accepted_topology_changed':False,'s2_accepted':False,'approved_objects':0,'applied_objects':0,'e3_ready':False}


def render_report(s):
    rows='\n'.join(f'| {k} | {v} |' for k,v in sorted(s['primary_classes'].items()))
    coverage='\n'.join(f'- {mode}: before {dict(sorted(v["before"].items()))}; after {dict(sorted(v["after"].items()))}.'
                       for mode,v in sorted(s['coverage_impact']['source_target_coverage'].items()))
    return f'''# E2.3-D2 — Synthetic topology proposal only

PROPOSAL_ONLY_COUNTERFACTUAL; no accepted topology changes, no S2 acceptance.
Cases {s['case_count']}; source Feeders {s['feeder_count']}.

| Primary class | Feeder count |
|---|---:|
{rows}

Automatic proposal eligible: {s['automatic_eligible_feeders']}.
Structurally retained bundles: {s['proposal_bundles']}; attempted: {s['attempted_bundles']};
rejected bundles: {s['rejected_bundles']}; rejected candidates/gaps: {s['rejected_candidates']}.
Object counts: {dict(sorted(s['proposal_types'].items()))}.
Bundle lifecycle: {dict(sorted(s['bundle_stages'].items()))}.
Zero-Transformer role status: {dict(sorted(s['zero_transformer_roles'].items()))}.

## Original source-target coverage

{coverage}

Source-target inventory and generated model-target inventory are separate axes. An empty
source Transformer file stays NO_SOURCE_TARGET even if a confirmed future device is proposed.
Physical graph retains OPEN branches; conducting view uses unchanged accepted source-state
flags. Unprojected state connectivity is UNRESOLVED, not silently energized or grounded.

D1 whole-case state veto is removed. Explicit identity/voltage/ownership witnesses remain
hard; candidate-local closed earthing rejects only affected attachments. Missing MV side
and case-local engineering ownership are declared modeling assumptions, not source facts.
Only accepted S0 unique regions are used; S2-only backbones remain review candidates.
No default Transformer count, LV voltage, random layout, branch parameters or load is generated.

Structural validation does not certify electrical adequacy. Unknown scenario locations,
MV direction assumptions and unassessed degree limits remain explicit; E3/OpenDSS-ready=false.
All bundles stop before APPROVED/APPLIED. Next review should assess concrete proposals,
engineering limits and bound business decisions. STOP; no apply or E3 in this slice.
'''
