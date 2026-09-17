"""D3 evidence adapters, read-only D2 eligibility and stream aggregation."""
from collections import Counter, defaultdict
from itertools import combinations

from grid_case_generator.io.canonical_json import to_canonical_data
from grid_case_generator.models.proposals import unknown_decision, positive_voltage, voltage_compatible
from grid_case_generator.analysis.topology_proposals import _regions
from grid_case_generator.validation.topology_proposals import measure_graph
from grid_case_generator.generation.deterministic_recovery import FAMILIES, SERIES, LEAF, RULE_VERSION


def make_input(details, baseline):
    """Typed source fixture adapter; production uses the verified D2 base snapshot."""
    from grid_case_generator.models import records
    from grid_case_generator.analysis.topology_recovery import evidence_id
    top = to_canonical_data(baseline.topology)
    accounts = to_canonical_data(details.accounting)
    terminals = to_canonical_data([r for r in details.records if isinstance(r, records.Terminal)])
    cid = top['case_id']; case, = [r for r in details.records if isinstance(r, records.GridCase)]
    feeders = [{'feeder_id': str(r.feeder_id), 'source_record_refs': [str(r.source_record_ref)],
                'original_flags': [], 'd1_primary': 'FIXTURE'} for r in details.records if isinstance(r, records.Feeder)]
    all_raw_refs = {v for a in accounts for k, v in a['raw_record']['fields'] or []
                   if k in ('Line_FromBus', 'Line_ToBus', 'Switch_FromBus', 'Switch_ToBus') and v}
    targets = []
    for r in details.records:
        if isinstance(r, records.Equipment) and r.equipment_type.value == 'TRANSFORMER':
            targets.append({'target_key': evidence_id('fixture-target', cid, r.equipment_id),
                'source_entity_id': str(r.equipment_id), 'identity_unique': r.identity_status.value == 'UNIQUE',
                'reference_composition': 'LINE_ONLY' if r.source_id in all_raw_refs else 'NO_REFERENCE',
                'hv_kv': None, 'lv_kv': None, 'source_record_refs': [str(r.source_record_ref)]})
    target_map = {t['source_entity_id']: t['target_key'] for t in targets}
    nodes = [{'node_id': n['node_id'], 'case_id': cid, 'voltage_kv': n['nominal_voltage_kv'],
              'kind': {'junction/bus':'JUNCTION', 'feeder-head/mv':'HEAD', 'transformer-mv/mv':'TRANSFORMER_MV'}.get(n['role'], 'OTHER'),
              'transformer_key': target_map.get(n['source_entity_ref']['entity_id']) if n['role'] == 'transformer-mv/mv' else None} for n in top['nodes']]
    edges = [{'edge_id': e['branch_id'], 'case_id': cid, 'a':e['from_node_id'], 'b':e['to_node_id'],
              'conducting':e['conducting'], 'kind':'LINE' if e['role']=='line/connection' else 'SWITCH'} for e in top['branches']]
    identity_refs = sorted(a['raw_record']['source_record_ref'] for a in accounts if a['identity_status'] not in (None, 'UNIQUE'))
    hard = [{'code':'AMBIGUOUS_IDENTITY', 'source_refs':identity_refs, 'scope':'CASE'}] if identity_refs else []
    voltage_refs = sorted({ref for p in baseline.projections if p.exclusion_reason and 'VOLTAGE' in p.exclusion_reason.value for ref in p.supporting_source_refs})
    if voltage_refs: hard.append({'code':'INCOMPATIBLE_VOLTAGE', 'source_refs':voltage_refs, 'scope':'CASE'})
    base = {'case_id':cid, 'source_case_key':case.source_case_key, 'feeders':feeders,
            'hard_blockers':hard, 'state_constraints':[], 'head_id':top['feeder_head_id'],
            'nominal_voltage_kv':str(baseline.coverage.nominal_voltage_kv) if baseline.coverage.nominal_voltage_kv else None,
            's2_usable':True, 'source_line_count':sum(a['raw_record']['source_file_type']=='LINE' for a in accounts),
            'base_nodes':sorted(nodes,key=lambda x:x['node_id']), 'base_edges':sorted(edges,key=lambda x:x['edge_id']),
            'targets':sorted(targets,key=lambda x:x['target_key']), 'evidence_refs':[], 'region_source_refs':{}}
    return {'base':base, 'accounts':sorted(accounts,key=lambda a:a['raw_record']['source_record_ref']),
            'terminals':sorted(terminals,key=lambda t:t['terminal_id']), 'topology':top,
            'projections':sorted(to_canonical_data(baseline.projections),key=lambda p:repr(p))}


def eligibility(c, decisions=None):
    """D2 attachment eligibility without instantiating proposals or generated objects.

    D3 accepts only the existing unconfirmed official business snapshot. New-device
    permission is deliberately outside this slice, rather than silently ignored.
    """
    decisions = decisions or {}; output = []
    for f in sorted(c['feeders'], key=lambda f:f['feeder_id']):
        d = decisions.get((c['case_id'], f['feeder_id']), unknown_decision(c['case_id'], f['feeder_id']))
        if d != unknown_decision(c['case_id'], f['feeder_id']):
            raise ValueError('D3 eligibility requires unconfirmed D2 business policy')
        usable, regions = _regions(c, d)
        hard = {b['code'] for b in c['hard_blockers']}
        gaps = []
        if not c['nominal_voltage_kv']: gaps.append('MV_VOLTAGE_UNDETERMINED')
        if not usable: gaps.append('NO_ACCEPTED_PHYSICAL_BACKBONE')
        if len(regions) != 1: gaps.append('ATTACHMENT_REGION_UNDETERMINED')
        eligible = []; rejected = []; candidate_hard = set()
        unreferenced = [t for t in c['targets'] if t['reference_composition'] == 'NO_REFERENCE']
        if not hard and c['targets']:
            for t in unreferenced:
                reasons = list(gaps)
                if not t['identity_unique']: reasons.append('AMBIGUOUS_IDENTITY')
                if t['source_entity_id'] is None: reasons.append('UNPUBLISHED_TARGET_IDENTITY')
                try:
                    if t['hv_kv'] and c['nominal_voltage_kv'] and not voltage_compatible(t['hv_kv'], c['nominal_voltage_kv']): reasons.append('INCOMPATIBLE_VOLTAGE')
                    if t['lv_kv'] and c['nominal_voltage_kv'] and positive_voltage(t['lv_kv']) >= positive_voltage(c['nominal_voltage_kv']): reasons.append('INCOMPATIBLE_LV_VOLTAGE')
                except ValueError: reasons.append('INVALID_SOURCE_VOLTAGE')
                candidate_hard.update(set(reasons) & {'AMBIGUOUS_IDENTITY','INCOMPATIBLE_VOLTAGE','INCOMPATIBLE_LV_VOLTAGE','INVALID_SOURCE_VOLTAGE'})
                if not reasons:
                    if any(n.get('transformer_key') == t['target_key'] for n in c['base_nodes']): reasons.append('DUPLICATE_ATTACHMENT')
                    if any(s['kind']=='EARTHING_SWITCH' and s['state']=='CLOSED' and regions[0] in s['node_ids'] for s in c['state_constraints']): reasons.append('CLOSED_EARTHING_AT_ATTACHMENT')
                if reasons: rejected.append({'target_key':t['target_key'], 'reasons':sorted(set(reasons))})
                else: eligible.append(t['target_key'])
        if hard: primary = 'HARD_SOURCE_CONTRADICTION'
        elif not c['targets']: primary = 'ROLE_CONFIRMATION_REQUIRED'
        elif eligible: primary = 'SYNTHETIC_ATTACHMENT_ELIGIBLE'
        elif candidate_hard: primary = 'HARD_SOURCE_CONTRADICTION'
        elif measure_graph(c)['target_coverage'] == 'FULL': primary = 'ALREADY_COMPLETE'
        elif c['s2_usable'] and (not usable or not unreferenced): primary = 'DETERMINISTIC_RECOVERY'
        elif not usable: primary = 'SYNTHETIC_BACKBONE_REQUIRED'
        else: primary = 'INSUFFICIENT_FOR_AUTOMATIC_PROPOSAL'
        output.append({'case_id':c['case_id'], 'feeder_id':f['feeder_id'], 'primary_class':primary,
            'accepted_physical_backbone':usable, 'candidate_region_count':len(regions),
            'eligible_target_keys':sorted(eligible), 'synthetic_candidate_count':len(eligible),
            'missing_backbone_or_region_count':sum(bool(set(r['reasons']) & {'NO_ACCEPTED_PHYSICAL_BACKBONE','ATTACHMENT_REGION_UNDETERMINED'}) for r in rejected),
            'missing_backbone_count':sum('NO_ACCEPTED_PHYSICAL_BACKBONE' in r['reasons'] for r in rejected),
            'missing_region_count':sum('ATTACHMENT_REGION_UNDETERMINED' in r['reasons'] for r in rejected),
            'rejected_targets':sorted(rejected,key=lambda t:t['target_key']), 'generated_object_count':0})
    return output


def taxonomy(base, result, before):
    rows = result['candidates']; tags = {r['family'] for r in rows}
    if any(r['source_state']=='OPEN' for r in rows if r['source_kind']=='SWITCH'):
        tags.add('KNOWN_OPEN_STRUCTURAL_RECOVERY')
    if base['s2_usable'] and not before['accepted_physical_backbone']: tags.add('S2_ONLY_BACKBONE_RECOVERY')
    priority = []
    if any(r['family']=='SERIES_SWITCH_RECOVERY' and r['status']=='ACCEPTED' for r in rows): priority.append('SERIES_SWITCH_RECOVERY')
    if 'MULTI_INCOMING_TRANSFORMER_REVIEW' in tags: priority.append('MULTI_INCOMING_TRANSFORMER_REVIEW')
    if any(r['family']=='REFERENCED_TRANSFORMER_RECOVERY' and r['status']!='BASELINE_PRESERVED' for r in rows): priority.append('REFERENCED_TRANSFORMER_RECOVERY')
    priority.extend(k for k in ('SWITCH_TERMINAL_REPRESENTATION','ACCESS_POINT_RECOVERY','KNOWN_OPEN_STRUCTURAL_RECOVERY','S2_ONLY_BACKBONE_RECOVERY') if k in tags)
    primary = priority[0] if priority else 'OTHER_DETERMINISTIC_REVIEW'
    return {'case_id':base['case_id'], 'feeder_id':before['feeder_id'],
        'original_d2_primary':before['primary_class'], 'taxonomy_primary':primary,
        'overlapping_rules':sorted(tags), 'candidate_counts':dict(sorted(Counter(r['family'] for r in rows).items())),
        'candidate_ids':[r['candidate_id'] for r in rows],
        'conflict_refs':sorted({ref for r in rows for ref in r['conflict_refs']}),
        'coverage':result['coverage']}


def rule_reviews():
    reviews = []
    for family in FAMILIES:
        enabled = family in ('SERIES_SWITCH_RECOVERY','SWITCH_TERMINAL_REPRESENTATION')
        reviews.append({'family':family, 'rule_id':SERIES if family=='SERIES_SWITCH_RECOVERY' else LEAF if family=='SWITCH_TERMINAL_REPRESENTATION' else family+'_V1',
            'rule_version':RULE_VERSION, 'acceptance_result':'ACCEPTED' if enabled else 'NEEDS_REVIEW',
            'rule_status':'APPROVED_DETERMINISTIC_DERIVED_RULE' if enabled else 'UNRESOLVED',
            'preconditions':['UNIQUE_CASE_LOCAL_IDENTITIES','FULL_SOURCE_INCIDENCE','EXACT_DIRECT_DECLARATIONS','KNOWN_ORDINARY_SWITCH_STATE','ACCEPTED_MV_DOMAIN','NO_HARD_CONFLICT'] if enabled else ['UNIQUE_PHYSICAL_PORT_SEMANTICS_REQUIRED'],
            'exclusions':['AMBIGUITY','CROSS_CASE','VOLTAGE_CONFLICT','TIE_OR_UNKNOWN_STATE','REVERSE_OR_PARTIAL_OR_UNRESOLVED_ENDPOINTS'] if enabled else ['NO_ARBITRARY_PORT_SELECTION'],
            'source_evidence_contract':'Original row fields + exact Canonical Terminal targets + complete incidence + immutable S0 mappings',
            'deterministic_rationale':'Unique direct declarations extend accepted series interpretation; no remote placement is selected' if enabled else 'Reference existence alone does not identify a physical port',
            'multiple_interpretations':'Excluded candidates remain unresolved; leaf remote explicitly UNBOUND' if enabled else 'Possible; no new connection accepted',
            'state_semantics':'Physical branch exists; conducting iff original CLOSED; raw state retained',
            'voltage_semantics':'Inherited approved MV domain; explicit Bus declarations must agree; no Transformer winding mapping',
            'cross_case_safety':'Exact case-bound source evidence only', 'entity_type_safety':'No new outer entity mapping; source Line needs two accepted terminal mappings',
            'identity_safety':'No representative for nonunique identities; hard case contradiction veto',
            'component_bridge_safety':'Only evidenced source Line endpoints and existing Switch internal branch; leaf remote unbound',
            'broad_s2_acceptance':False})
    for variant in ('SERIES_TIE_OR_UNKNOWN_TYPE','SERIES_INVALID_INCIDENCE','SERIES_UNRESOLVED_ENDPOINT','SERIES_EXACT_REVERSE','SERIES_DIFFERENT_OR_PARTIAL_ENDPOINT'):
        row = dict(reviews[0], family=variant, rule_id=variant+'_REVIEW_V1', acceptance_result='NEEDS_REVIEW',
                   rule_status='UNRESOLVED', deterministic_rationale='Existing source evidence does not meet the exact direct rule; no alternate interpretation accepted',
                   multiple_interpretations='Not excluded by current evidence')
        reviews.append(row)
    reviews.append({'family':'MULTI_LINE_T_AS_MV_JUNCTION', 'rule_id':'MULTI_LINE_T_AS_MV_JUNCTION',
        'rule_version':RULE_VERSION, 'acceptance_result':'REJECTED',
        'reason':'Unknown winding/port semantics cannot justify collapsing multiple incidences; cycles in prior risk experiment do not validate it'})
    return reviews


class RecoverySummary:
    def __init__(self):
        self.cases = 0; self.feeders = 0; self.taxonomy = Counter(); self.overlaps = Counter()
        self.rules = {k:{'candidate_count':0, 'status_counts':Counter(), 'reason_distribution':Counter(),
                         'feeders':set(), 'status_feeders':defaultdict(set), 'isolated_impact':{m:Counter() for m in ('physical','conducting')}} for k in FAMILIES}
        self.coverage = {m:{s:Counter() for s in ('before','after','transitions','topology_before','topology_after','metrics_before','metrics_after')} for m in ('physical','conducting')}
        self.d2 = {s:{'primary':Counter(), 'counts':Counter()} for s in ('before','after')}
        self.additions = Counter(); self.status_transitions = Counter(); self.inherited_heads = 0
        self.variants = defaultdict(lambda: {'candidates':Counter(), 'feeders':defaultdict(set)})
        self.switches = Counter()

    def add(self, c, r, before, after, feeders):
        self.cases += 1; self.feeders += len(before)
        self.inherited_heads += sum(n['kind']=='HEAD' for n in c['base']['base_nodes'])
        for x in r['candidates']:
            variant = self.variants[x['rule_variant']]
            variant['candidates'][x['status']] += 1
            variant['feeders'][x['status']].update((x['case_id'], f) for f in x['feeder_ids'])
            if x['source_kind'] == 'SWITCH':
                self.switches[x['status']] += 1
                if x['status'] == 'ACCEPTED': self.switches[x['source_state']] += 1
            k = self.rules[x['family']]; k['candidate_count'] += 1
            k['status_counts'][x['status']] += 1; k['reason_distribution'].update(x['reason_codes'])
            fs = {(x['case_id'], f) for f in x['feeder_ids']}
            k['feeders'].update(fs); k['status_feeders'][x['status']].update(fs)
        for f in feeders:
            if f['original_d2_primary']=='DETERMINISTIC_RECOVERY':
                self.taxonomy[f['taxonomy_primary']] += 1
                self.overlaps.update(f['overlapping_rules'])
                self.overlaps.update(' + '.join(pair) for pair in combinations(f['overlapping_rules'],2))
        for family, modes in r['coverage']['single_family_delta'].items():
            for mode, delta in modes.items(): self.rules[family]['isolated_impact'][mode].update(delta)
        for obj in r['additions']: self.additions[obj['kind']] += 1
        for b,a in zip(before,after): self.status_transitions[b['primary_class']+' -> '+a['primary_class']] += 1
        for label, records in (('before',before),('after',after)):
            for item in records:
                self.d2[label]['primary'][item['primary_class']] += 1
                for key in ('accepted_physical_backbone','synthetic_candidate_count','missing_backbone_or_region_count','missing_backbone_count','missing_region_count'):
                    self.d2[label]['counts'][key] += int(item[key])
        for mode in self.coverage:
            cv = self.coverage[mode]; metrics = r['coverage'][mode]
            for label in ('before','after'):
                item = metrics[label]; cv[label][item['target_coverage']] += len(before)
                cv['topology_'+label][item['topology_coverage']] += len(before)
                cv['metrics_'+label].update({k:item[k] for k in ('reachable_lines','reachable_transformers','components','cycle_rank','node_count','edge_count','active_edge_count')})
            key = metrics['before']['target_coverage']+' -> '+metrics['after']['target_coverage']
            cv['transitions'][key] += len(before)

    def finish(self):
        rules = {}
        for family, r in self.rules.items():
            rules[family] = {'candidate_count':r['candidate_count'], 'candidate_feeders':len(r['feeders']),
                'status_counts':{s:r['status_counts'][s] for s in ('ACCEPTED','REJECTED','NEEDS_REVIEW','BASELINE_PRESERVED')},
                'status_feeders':{s:len(r['status_feeders'][s]) for s in ('ACCEPTED','REJECTED','NEEDS_REVIEW','BASELINE_PRESERVED')},
                'reason_distribution':dict(sorted(r['reason_distribution'].items())),
                'isolated_impact':{m:dict(sorted(v.items())) for m,v in r['isolated_impact'].items()}}
        for mode in self.coverage:
            for label in ('before','after'):
                for status in ('FULL','PARTIAL','FAILED','NO_SOURCE_TARGET'): self.coverage[mode][label].setdefault(status,0)
                for status in ('FULL','PARTIAL','FAILED'): self.coverage[mode]['topology_'+label].setdefault(status,0)
            for pair in ('FAILED -> PARTIAL','FAILED -> FULL','PARTIAL -> FULL'): self.coverage[mode]['transitions'].setdefault(pair,0)
            self.coverage[mode]['transitions']['unchanged'] = sum(n for k,n in self.coverage[mode]['transitions'].items() if ' -> ' in k and len(set(k.split(' -> '))) == 1)
        for label in ('before','after'):
            for k in ('DETERMINISTIC_RECOVERY','SYNTHETIC_ATTACHMENT_ELIGIBLE','SYNTHETIC_DEVICE_ELIGIBLE','SYNTHETIC_BACKBONE_REQUIRED','ROLE_CONFIRMATION_REQUIRED','HARD_SOURCE_CONTRADICTION','INSUFFICIENT_FOR_AUTOMATIC_PROPOSAL','ALREADY_COMPLETE'):
                self.d2[label]['primary'].setdefault(k,0)
        for k in (*FAMILIES,'KNOWN_OPEN_STRUCTURAL_RECOVERY','S2_ONLY_BACKBONE_RECOVERY'): self.taxonomy.setdefault(k,0)
        return {'case_count':self.cases, 'feeder_count':self.feeders, 'rule_summary':rules,
                'deterministic_cohort_taxonomy':dict(sorted(self.taxonomy.items())),
                'switch_candidate_status_and_state':dict(sorted(self.switches.items())),
                'rule_variant_summary':{k:{'candidate_status':dict(sorted(v['candidates'].items())),
                    'feeder_status':{s:len(fs) for s,fs in sorted(v['feeders'].items())}} for k,v in sorted(self.variants.items())},
                'deterministic_cohort_overlaps':dict(sorted(self.overlaps.items())),
                'coverage_impact':{m:{k:dict(sorted(v.items())) for k,v in c.items()} for m,c in self.coverage.items()},
                'd2_reclassification':{**{s:{k:dict(sorted(v.items())) for k,v in d.items()} for s,d in self.d2.items()},
                                     'transitions':dict(sorted(self.status_transitions.items()))},
                'new_objects_by_kind':dict(sorted(self.additions.items())),
                'new_accepted_deterministic_edges':sum(self.additions[k] for k in ('LINE','SWITCH')),
                'inherited_synthetic_head_nodes':self.inherited_heads,
                'new_rule_generated_objects':0, 'source_changed':False, 'frozen_v1_changed':False,
                's2_blanket_accepted':False, 'e3_ready':False}


def render_report(summary):
    import json
    return '# E2.3-D3 deterministic topology recovery\n\nAccepted v2 is an immutable deterministic overlay; S2 as a whole remains unaccepted.\n' + \
        'Physical, conducting and source-target coverage are separate. No synthetic completion or E3.\n\n```json\n' + json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + '\n```\n'
