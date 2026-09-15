"""E2.1 source motif investigation. Never modifies or emits accepted topology."""
from collections import Counter, defaultdict
from decimal import Decimal
import re

from grid_case_generator.models import records as source
from grid_case_generator.models.types import IdentityStatus, SourceReferenceStatus
from grid_case_generator.models.topology import DerivedRole, ProjectionStatus, RuleId
from grid_case_generator.generation.topology import entity_ref

VERSION = 'switch-semantics-investigation-v1'
DISCLAIMER = ('COUNTERFACTUAL ONLY', 'NOT ACCEPTED TOPOLOGY')
ID_FIELDS = {'STATION':'Station_ID', 'BUS':'Bus_ID', 'FEEDER':'Feeder_ID',
    'SWITCH':'Switch_ID', 'LINE':'Line_ID', 'TRANSFORMER':'Transformer_ID',
    'ACCESS_POINT':'AccessPoint_ID', 'DISCONNECTOR':'Disconnector_ID',
    'EARTHING_SWITCH':'EarthingSwitch_ID', 'LOAD':'Load_ID', 'DER':'DER_ID'}
SCIENTIFIC = re.compile(r'[+-]?\d+(?:\.\d+)?[eE][+-]?\d+\Z')
DIGITS = re.compile(r'[0-9]+\Z')


def ratio(numerator, denominator, scale=1):
    return (Decimal(numerator)*scale/Decimal(denominator)).quantize(Decimal('0.000001')) if denominator else None


def literal_motif(a, b, x, y):
    equal = lambda first,second: bool(first and second and first == second)
    flags = {'X_A':equal(x,a), 'Y_B':equal(y,b), 'X_B':equal(x,b), 'Y_A':equal(y,a),
        'X_EQUALS_Y':equal(x,y), 'BOTH_MISSING':not x and not y,
        'X_MISSING':not x and bool(y), 'Y_MISSING':bool(x) and not y}
    flags['DIRECT'] = flags['X_A'] and flags['Y_B']
    flags['REVERSE'] = flags['X_B'] and flags['Y_A']
    flags['BOTH_DIFFERENT'] = bool(x and y and not any(flags[k] for k in ('X_A','Y_B','X_B','Y_A')))
    for key in ('X_A','Y_B','X_B','Y_A'):
        flags[key+'_ONLY'] = flags[key] and sum(flags[k] for k in ('X_A','Y_B','X_B','Y_A')) == 1
    motif = 'OTHER'
    for key in ('BOTH_MISSING','X_MISSING','Y_MISSING','DIRECT','REVERSE','X_EQUALS_Y',
                'X_A_ONLY','Y_B_ONLY','X_B_ONLY','Y_A_ONLY','BOTH_DIFFERENT'):
        if flags[key]:
            motif = key
            break
    if motif == 'OTHER' and any(flags[k] for k in ('X_A','Y_B','X_B','Y_A')):
        motif = 'OTHER_PARTIAL'
    return {'motif':motif, 'flags':flags}


def id_pattern(first, second):
    """Compare only this supplied pair. These features never feed graph logic."""
    prefix = 0
    for left,right in zip(first,second):
        if left != right: break
        prefix += 1
    digits = bool(DIGITS.fullmatch(first) and DIGITS.fullmatch(second))
    return {'exact_same':bool(first and first == second),
        'numeric_looking_but_different':digits and first != second,
        'common_prefix_length':prefix,
        'differing_suffix_width':max(len(first),len(second))-prefix,
        'same_length':len(first)==len(second),
        'suffix_equal':{str(n):bool(len(first)>=n and len(second)>=n and first[-n:]==second[-n:]) for n in (1,2,3,6)},
        'scientific_notation':bool(SCIENTIFIC.fullmatch(first) or SCIENTIFIC.fullmatch(second)),
        'leading_zero_only':digits and first!=second and (first.lstrip('0') or '0')==(second.lstrip('0') or '0')}


class SourceMotifIndex:
    """Case-local indexes over unchanged E1 evidence, not a replacement resolver."""
    def __init__(self, details):
        self.records = details.records
        self.case, = (r for r in self.records if isinstance(r,source.GridCase))
        self.entities = {}
        for record in self.records:
            if isinstance(record,(source.Equipment,source.Bus,source.Station,source.Feeder)):
                self.entities[entity_ref(record).entity_id] = record
        self.terminals = defaultdict(list)
        self.terms_by_row = defaultdict(list)
        for record in self.records:
            if isinstance(record,source.Terminal):
                self.terminals[record.equipment_id].append(record)
                self.terms_by_row[(record.source_record_ref,record.terminal_no)].append(record)
        for values in self.terminals.values(): values.sort(key=lambda t:(t.terminal_no,t.terminal_id))
        self.devices = {r.equipment_id:r for r in self.records if isinstance(r,source.SwitchingDevice)}
        self.groups = defaultdict(list)
        self.lookup = defaultdict(list)
        self.entity_refs = defaultdict(set)
        self.line_groups = defaultdict(list)
        self.incident = defaultdict(list)
        self.malformed_lines = []
        self.rows = sorted(details.accounting,key=lambda a:a.raw_record.source_record_ref)
        for account in self.rows:
            row=account.raw_record
            kind=row.source_file_type.value
            fields=dict(row.fields or ())
            raw_id=fields.get(ID_FIELDS.get(kind,''),'')
            if kind in ID_FIELDS:
                self.groups[(kind,('ID',raw_id) if raw_id else ('ROW',str(row.source_record_ref)))].append(account)
            if raw_id: self.lookup[raw_id].append(account)
            if account.canonical_ref:
                self.entity_refs[account.canonical_ref.entity_id].add(str(row.source_record_ref))
            if kind=='LINE':
                line_key=('ID',raw_id) if raw_id else ('ROW',str(row.source_record_ref))
                self.line_groups[line_key].append(account)
                if row.fields is None: self.malformed_lines.append(row.source_record_ref)
                for number,key in ((1,'Line_FromBus'),(2,'Line_ToBus')):
                    if fields.get(key): self.incident[fields[key]].append((line_key,number,account))
        self.adjacency=defaultdict(set)
        self.edge_refs=defaultdict(set)
        self.membership={}
        for record in self.records:
            if isinstance(record,source.Terminal) and record.source_ref_status is SourceReferenceStatus.EXACT:
                self._edge(record.equipment_id,record.resolved_source_ref.entity_id,record.source_record_ref)
            elif isinstance(record,(source.Bus,source.Feeder)):
                reference=record.station_source_ref if isinstance(record,source.Bus) else record.source_bus_source_ref
                if reference and reference.resolution_status is SourceReferenceStatus.EXACT:
                    owner=entity_ref(record).entity_id
                    target=reference.resolved_source_ref.entity_id
                    self._edge(owner,target,record.source_record_ref)
                    if isinstance(record,source.Bus) and reference.resolved_source_ref.entity_type=='STATION':
                        self.membership[owner]=target
        self.component={}
        for vertex in sorted(self.entities):
            if vertex in self.component: continue
            pending=[vertex]; self.component[vertex]=vertex
            while pending:
                for neighbor in self.adjacency[pending.pop()]:
                    if neighbor not in self.component:
                        self.component[neighbor]=vertex; pending.append(neighbor)

    def _edge(self, left, right, locator):
        if any(v not in self.entities or self.entities[v].identity_status is not IdentityStatus.UNIQUE for v in (left,right)):
            return
        self.adjacency[left].add(right); self.adjacency[right].add(left)
        refs=self.edge_refs[tuple(sorted((left,right)))]
        if locator: refs.add(str(locator))
        refs.update(self.entity_refs[left]); refs.update(self.entity_refs[right])

    def source_type(self, ref):
        if ref is None: return None
        record=self.entities.get(ref.entity_id)
        return record.equipment_type.value if isinstance(record,source.Equipment) else str(ref.entity_type)

    def endpoint(self, raw_value, owner_row, terminal_no):
        terms=self.terms_by_row.get((owner_row.source_record_ref,terminal_no),())
        term=terms[0] if len(terms)==1 else None
        accounts=self.lookup.get(raw_value,()) if raw_value else ()
        target=None; dtype=None
        if not raw_value: status='MISSING'
        elif not accounts: status='UNRESOLVED'
        elif len(accounts)!=1 or accounts[0].identity_status not in (None,IdentityStatus.UNIQUE): status='AMBIGUOUS'
        elif accounts[0].canonical_ref is None: status='UNRESOLVED'
        else:
            status='EXACT'; target=accounts[0].canonical_ref; dtype=accounts[0].raw_record.source_file_type.value
        return {'raw_value':raw_value,
            'source_reference_status':term.source_ref_status.value if term else 'NOT_PUBLISHED',
            'source_target_ref':term.resolved_source_ref if term else None,
            'source_entity_type':self.source_type(term.resolved_source_ref) if term else None,
            'diagnostic_status':status,'diagnostic_entity_type':dtype,'diagnostic_target_ref':target,
            'diagnostic_candidates':tuple({'source_entity_type':a.raw_record.source_file_type.value,
                'identity_status':a.identity_status.value if a.identity_status else None,
                'source_entity_ref':a.canonical_ref,'source_record_ref':str(a.raw_record.source_record_ref)} for a in accounts),
            'supporting_source_refs':tuple(sorted({str(owner_row.source_record_ref),*(str(a.raw_record.source_record_ref) for a in accounts)}))}

    def relation(self, first, second):
        def endpoint_ref(ep):
            if ep['source_reference_status']=='EXACT': return ep['source_target_ref']
            return ep['diagnostic_target_ref'] if ep['diagnostic_status']=='EXACT' else None
        first_ref,second_ref=endpoint_ref(first),endpoint_ref(second)
        if first_ref is None or second_ref is None:
            return {'distance':'UNRESOLVED','witness_path':(),'supporting_source_refs':(),
                'direct_bus_station_membership':False,'shared_station_ids':()}
        left=first_ref.entity_id; right=second_ref.entity_id
        path=()
        if left==right: distance='0'; path=(left,)
        elif right in self.adjacency[left]: distance='1'; path=(left,right)
        else:
            common=self.adjacency[left]&self.adjacency[right]
            if common: distance='2'; path=(left,min(common),right)
            else: distance='GT2' if self.component[left]==self.component[right] else 'DISCONNECTED'
        refs=set()
        for a,b in zip(path,path[1:]): refs.update(self.edge_refs[tuple(sorted((a,b)))])
        def stations(vertex):
            record=self.entities[vertex]
            if isinstance(record,source.Station):
                refs.update(self.entity_refs[vertex])
                return {vertex}
            if vertex in self.membership:
                refs.update(self.edge_refs[tuple(sorted((vertex,self.membership[vertex])))])
                return {self.membership[vertex]}
            # Explicit terminal→Bus→Station source paths, not asserted ownership.
            found=set()
            for term in self.terminals.get(vertex,()):
                if term.source_ref_status is SourceReferenceStatus.EXACT:
                    target=term.resolved_source_ref.entity_id
                    if target in self.membership:
                        found.add(self.membership[target])
                        refs.update(self.edge_refs[tuple(sorted((vertex,target)))])
                        refs.update(self.edge_refs[tuple(sorted((target,self.membership[target])))])
            return found
        shared_stations=tuple(sorted(stations(left)&stations(right)))
        return {'distance':distance,'witness_path':path,'supporting_source_refs':tuple(sorted(refs)),
            'direct_bus_station_membership':self.membership.get(left)==right or self.membership.get(right)==left,
            'shared_station_ids':shared_stations}


def classify_evidence(endpoints, motif, relations):
    states={e['diagnostic_status'] for e in endpoints.values()}
    layer=all(relations[k]['distance']=='0' or relations[k]['direct_bus_station_membership'] for k in ('A_X','B_Y')) and any(relations[k]['direct_bus_station_membership'] for k in ('A_X','B_Y'))
    source_exact=all(e['source_reference_status']=='EXACT' for e in endpoints.values())
    if source_exact and motif['flags']['DIRECT']: bucket='EXACT_COMPATIBLE'
    elif source_exact and motif['flags']['REVERSE']: bucket='REVERSE_COMPATIBLE'
    elif layer: bucket='DIFFERENT_SOURCE_LAYER'
    elif 'AMBIGUOUS' in states: bucket='ENDPOINT_AMBIGUOUS'
    elif 'UNRESOLVED' in states: bucket='ENDPOINT_UNRESOLVED'
    elif motif['motif']=='BOTH_MISSING': bucket='BOTH_ENDPOINTS_MISSING'
    elif 'MISSING' in states: bucket='ONE_ENDPOINT_MISSING'

    elif any(motif['flags'][k] for k in ('X_A','Y_B','X_B','Y_A')): bucket='PARTIAL_COMPATIBLE'
    elif motif['flags']['BOTH_DIFFERENT']: bucket='BOTH_ENDPOINTS_DIFFERENT'
    else: bucket='OTHER'
    assessment='UNRESOLVED_SEMANTICS'
    if bucket in ('EXACT_COMPATIBLE','REVERSE_COMPATIBLE'): assessment='COMPATIBLE_SOURCE_EVIDENCE'
    elif bucket=='DIFFERENT_SOURCE_LAYER': assessment='DIFFERENT_ABSTRACTION_EVIDENCE'
    return bucket,assessment


def _counterfactual(index, baseline, candidates, selection):
    """Metrics over temporary adjacency, reusing every non-Switch v1 decision."""
    chosen={c['source_entity_ref'].entity_id:c for c in candidates if c['inner_references_exact'] and selection(c)}
    adjacency=defaultdict(set)
    def edge(first,second):
        adjacency[first].add(second); adjacency[second].add(first)
    line_pairs=[]
    for branch in baseline.topology.branches:
        if branch.conducting: edge(branch.from_node_id,branch.to_node_id)
        if branch.role is DerivedRole.LINE: line_pairs.append((branch.from_node_id,branch.to_node_id))
    endpoint_targets={p.source_terminal_ref.entity_id:p.derived_target_ids[0] for p in baseline.projections
        if p.source_terminal_ref is not None and p.projection_status is ProjectionStatus.PROJECTED}
    already_projected={p.source_entity_ref.entity_id for p in baseline.projections
        if p.rule_id is RuleId.SWITCH and p.source_terminal_ref is None and p.projection_status is ProjectionStatus.PROJECTED}
    for owner,candidate in chosen.items():
        if owner not in already_projected and candidate['normal_state']=='CLOSED':
            edge('analysis-only:'+owner+':in','analysis-only:'+owner+':out')
    for record in index.entities.values():
        if not isinstance(record,source.Equipment) or record.equipment_type.value!='LINE' or record.identity_status is not IdentityStatus.UNIQUE: continue
        terminals=index.terminals[record.equipment_id]
        if len(terminals)!=2 or [t.terminal_no for t in terminals]!=[1,2]: continue
        targets=[]
        for term in terminals:
            ref=term.resolved_source_ref
            if term.source_ref_status is SourceReferenceStatus.EXACT and ref.entity_id in chosen and ref.entity_id not in already_projected:
                targets.append('analysis-only:'+ref.entity_id+(':in' if term.terminal_no==2 else ':out'))
            else: targets.append(endpoint_targets.get(term.terminal_id))
        if all(t is not None for t in targets): edge(*targets); line_pairs.append(tuple(targets))
    head=baseline.topology.feeder_head_id
    seen=set() if head is None else {head}; pending=list(seen)
    while pending:
        for neighbor in adjacency[pending.pop()]:
            if neighbor not in seen: seen.add(neighbor); pending.append(neighbor)
    transformers=sum(n.role is DerivedRole.TRANSFORMER_MV and n.node_id in seen for n in baseline.topology.nodes)
    usable=head is not None and any(a in seen and b in seen for a,b in line_pairs)
    return {'selected_switches':len(chosen),'reachable_transformers':transformers,
        'cases_with_reachable_transformers':int(transformers>0),'usable_subgraph_cases':int(usable)}


def investigate_case(details, baseline):
    index=SourceMotifIndex(details)
    if index.case.case_id!=baseline.topology.case_id: raise ValueError('source/baseline case mismatch')
    reasons={p.source_entity_ref.entity_id:p.exclusion_reason.value if p.exclusion_reason else None
        for p in baseline.projections if p.rule_id is RuleId.SWITCH and p.source_terminal_ref is None
        and p.source_entity_ref.entity_type=='EQUIPMENT'}
    degree={name:Counter({k:0 for k in ('0','1','2','3','GT3')}) for name in ('all_identity_groups','unique_switches','baseline_SWITCH_DEGREE')}
    directions={name:Counter({k:0 for k in ('ONE_IN_ONE_OUT','TWO_IN','TWO_OUT','OTHER')}) for name in degree}
    candidates=[]; exclusions=Counter(); raw_rows=0; unique_count=0
    for (kind,key),accounts in sorted(index.groups.items()):
        if kind!='SWITCH': continue
        raw_rows+=len(accounts)
        incidences=index.incident.get(key[1] if key[0]=='ID' else None,())
        line_ids={line_id for line_id,_,_ in incidences}
        degree_key=str(len(line_ids)) if len(line_ids)<=3 else 'GT3'
        pairs={(line_id,number) for line_id,number,_ in incidences}
        counts=Counter(number for _,number in pairs)
        direction='OTHER'
        if len(line_ids)==2:
            if counts[1]==counts[2]==1: direction='ONE_IN_ONE_OUT'
            elif counts[2]==2 and counts[1]==0: direction='TWO_IN'
            elif counts[1]==2 and counts[2]==0: direction='TWO_OUT'
        ref=accounts[0].canonical_ref if len(accounts)==1 else None
        record=index.entities.get(ref.entity_id) if ref else None
        unique=bool(record and record.identity_status is IdentityStatus.UNIQUE and len(accounts)==1)
        baseline_reason=reasons.get(record.equipment_id) if isinstance(record,source.Equipment) else None
        populations=['all_identity_groups']
        if unique: populations.append('unique_switches'); unique_count+=1
        # Identical duplicate groups can still have a published canonical ref.
        group_refs={a.canonical_ref.entity_id for a in accounts if a.canonical_ref}
        if any(reasons.get(owner)=='SWITCH_DEGREE' for owner in group_refs): populations.append('baseline_SWITCH_DEGREE')
        for population in populations:
            degree[population][degree_key]+=1
            if len(line_ids)==2: directions[population][direction]+=1
        if not unique: exclusions['SWITCH_IDENTITY_NOT_UNIQUE']+=1; continue
        if len(line_ids)!=2 or direction!='ONE_IN_ONE_OUT': exclusions['NOT_ONE_IN_ONE_OUT']+=1; continue
        if index.malformed_lines: exclusions['MALFORMED_LINE_EVIDENCE']+=1; continue
        valid=True
        for line_id in line_ids:
            rows=index.line_groups[line_id]
            if line_id[0]=='ROW' or len(rows)!=1 or rows[0].identity_status is not IdentityStatus.UNIQUE or rows[0].canonical_ref is None:
                valid=False
        if not valid: exclusions['INCIDENT_LINE_IDENTITY_NOT_UNIQUE']+=1; continue
        incoming,= (a.raw_record for _,number,a in incidences if number==2)
        outgoing,= (a.raw_record for _,number,a in incidences if number==1)
        switch=accounts[0].raw_record
        sf=dict(switch.fields or ()); inf=dict(incoming.fields); outf=dict(outgoing.fields)
        endpoints={'A':index.endpoint(inf['Line_FromBus'],incoming,1),
            'B':index.endpoint(outf['Line_ToBus'],outgoing,2),
            'X':index.endpoint(sf['Switch_FromBus'],switch,1),
            'Y':index.endpoint(sf['Switch_ToBus'],switch,2)}
        inner=(index.endpoint(inf['Line_ToBus'],incoming,2),index.endpoint(outf['Line_FromBus'],outgoing,1))
        inner_exact=all(e['source_reference_status']=='EXACT' and e['source_target_ref']==ref for e in inner)
        motif=literal_motif(*(endpoints[k]['raw_value'] for k in ('A','B','X','Y')))
        relations={name:index.relation(endpoints[left],endpoints[right]) for name,left,right in
            (('A_X','A','X'),('B_Y','B','Y'),('A_Y','A','Y'),('B_X','B','X'))}
        bucket,assessment=classify_evidence(endpoints,motif,relations)
        device=index.devices[record.equipment_id]
        refs={str(switch.source_record_ref),str(incoming.source_record_ref),str(outgoing.source_record_ref)}
        for ep in (*endpoints.values(),*inner): refs.update(ep['supporting_source_refs'])
        for relation in relations.values(): refs.update(relation['supporting_source_refs'])
        candidates.append({'case_id':str(index.case.case_id),'source_case_key':index.case.source_case_key,
            'switch_id':sf['Switch_ID'],'source_entity_ref':ref,'source_record_ref':str(switch.source_record_ref),
            'switch_fields':{k:sf.get(k,'') for k in ('Switch_FromBus','Switch_ToBus','Switch_NormalState','Switch_IsTie','Switch_HasMeasurement')},
            'normal_state':device.normal_state.value if device.normal_state else 'UNKNOWN',
            'is_tie':device.is_tie,'has_measurement':device.measurement_capable,
            'incoming_line':{'line_id':inf['Line_ID'],'from_bus':inf['Line_FromBus'],'to_bus':inf['Line_ToBus'],'source_record_ref':str(incoming.source_record_ref)},
            'outgoing_line':{'line_id':outf['Line_ID'],'from_bus':outf['Line_FromBus'],'to_bus':outf['Line_ToBus'],'source_record_ref':str(outgoing.source_record_ref)},
            'endpoints':endpoints,'inner_line_endpoints':inner,'inner_references_exact':inner_exact,
            'motif':motif['motif'],'equality_flags':motif['flags'],'breakdown':bucket,
            'semantic_assessment':assessment,'baseline_exclusion_reason':baseline_reason,'relations':relations,
            'id_patterns':{key:id_pattern(endpoints[a]['raw_value'],endpoints[b]['raw_value']) for key,a,b in (('A_X','A','X'),('B_Y','B','Y'))},
            'supporting_source_refs':tuple(sorted(refs))})
    candidates.sort(key=lambda c:(c['case_id'],c['source_record_ref']))
    motifs=Counter(c['motif'] for c in candidates)
    maximum=max(motifs.values(),default=0)
    case_summary={'case_id':str(index.case.case_id),'source_case_key':index.case.source_case_key,
        'candidate_switches':len(candidates),'motifs':dict(sorted(motifs.items())),
        'dominant_motifs':tuple(sorted(k for k,v in motifs.items() if v==maximum)),
        'motif_purity':ratio(maximum,len(candidates)), 'minority_motif_count':len(candidates)-maximum,
        'semantic_assessments':dict(sorted(Counter(c['semantic_assessment'] for c in candidates).items()))}
    compatible=lambda c:c['semantic_assessment']=='COMPATIBLE_SOURCE_EVIDENCE'
    layer=lambda c:c['semantic_assessment'] in ('COMPATIBLE_SOURCE_EVIDENCE','DIFFERENT_ABSTRACTION_EVIDENCE')
    counterfactual={'labels':DISCLAIMER,
        'baseline':{'selected_switches':baseline.coverage.counts['switch_projected'],
            'reachable_transformers':baseline.coverage.counts['reachable_transformers'],
            'cases_with_reachable_transformers':int(baseline.coverage.has_reachable_transformer),
            'usable_subgraph_cases':int(baseline.coverage.usable_subgraph)},
        'A':_counterfactual(index,baseline,candidates,lambda c:True),
        'B':_counterfactual(index,baseline,candidates,compatible),
        'C':_counterfactual(index,baseline,candidates,layer)}
    case_summary['counterfactual']=counterfactual
    return {'candidates':tuple(candidates),'case_summary':case_summary,'degree':{k:dict(v) for k,v in degree.items()},
        'degree_two_directions':{k:dict(v) for k,v in directions.items()},'counterfactual':counterfactual,
        'counts':{'source_switch_rows':raw_rows,'published_switch_entities':sum(isinstance(r,source.Equipment) and r.equipment_type.value=='SWITCH' for r in index.records),
            'source_switch_identity_groups':sum(kind=='SWITCH' for kind,_ in index.groups),
            'unique_switches':unique_count,'candidate_switches':len(candidates),
            'baseline_explicit_devices':sum(reason=='EXPLICIT_ENDPOINT_EVIDENCE' for reason in reasons.values()),
            'baseline_explicit_reconstructed':sum(c['baseline_exclusion_reason']=='EXPLICIT_ENDPOINT_EVIDENCE' for c in candidates),
            'inner_reference_exact_candidates':sum(c['inner_references_exact'] for c in candidates)},
        'candidate_exclusion_reasons':dict(exclusions)}


class Distribution:
    def __init__(self):
        self.counts=Counter()
        self.cases=defaultdict(set)

    def add(self,key,case_id):
        self.counts[key]+=1; self.cases[key].add(case_id)

    def report(self,denominator):
        return {key:{'switch_count':count,'case_count':len(self.cases[key]),
            'percentage':ratio(count,denominator,100)} for key,count in sorted(self.counts.items())}


class InvestigationSummary:
    def __init__(self):
        self.counts=Counter(); self.case_ids=set(); self.case_summaries=[]
        self.motifs=Distribution(); self.flags=Distribution(); self.explicit=Distribution(); self.assessments=Distribution()
        self.all_breakdowns=Distribution()
        self.endpoint_types={k:{'persisted':Counter(),'diagnostic':Counter(),'cross':Counter()} for k in ('A','B','X','Y','IN_SWITCH','OUT_SWITCH')}
        self.type_pairs=defaultdict(Counter); self.distances=defaultdict(Counter)
        self.groups=defaultdict(lambda:defaultdict(Counter))
        self.degree=defaultdict(Counter); self.directions=defaultdict(Counter)
        self.id_features=defaultdict(lambda:defaultdict(Counter))
        self.examples=defaultdict(list); self.counterfactual=defaultdict(Counter)
        self.exclusions=Counter(); self.raw_state_values=Counter()

    def add(self,result):
        summary=result['case_summary']; cid=summary['case_id']
        if cid in self.case_ids: raise ValueError('duplicate diagnostic case')
        self.case_ids.add(cid); self.case_summaries.append(summary)
        self.counts.update(result['counts']); self.counts['total_cases']+=1
        self.counts['cases_with_candidates']+=int(bool(result['candidates']))
        self.exclusions.update(result['candidate_exclusion_reasons'])
        for key,counts in result['degree'].items(): self.degree[key].update(counts)
        for key,counts in result['degree_two_directions'].items(): self.directions[key].update(counts)
        for key in ('baseline','A','B','C'): self.counterfactual[key].update(result['counterfactual'][key])
        for c in result['candidates']:
            self.motifs.add(c['motif'],cid); self.all_breakdowns.add(c['breakdown'],cid)
            self.assessments.add(c['semantic_assessment'],cid)
            if c['baseline_exclusion_reason']=='EXPLICIT_ENDPOINT_EVIDENCE': self.explicit.add(c['breakdown'],cid)
            for key,value in c['equality_flags'].items():
                if value: self.flags.add(key,cid)
            endpoints=dict(c['endpoints'],IN_SWITCH=c['inner_line_endpoints'][0],OUT_SWITCH=c['inner_line_endpoints'][1])
            types={}
            for key,ep in endpoints.items():
                persisted=ep['source_entity_type'] if ep['source_reference_status']=='EXACT' else ep['source_reference_status']
                diagnostic=ep['diagnostic_entity_type'] if ep['diagnostic_status']=='EXACT' else ep['diagnostic_status']
                types[key]=diagnostic
                self.endpoint_types[key]['persisted'][persisted]+=1
                self.endpoint_types[key]['diagnostic'][diagnostic]+=1
                self.endpoint_types[key]['cross'][persisted+' -> '+diagnostic]+=1
            for pair,a,b in (('A_B','A','B'),('X_Y','X','Y'),('A_X','A','X'),('B_Y','B','Y')):
                self.type_pairs[pair][types[a]+' / '+types[b]]+=1
            for key,relation in c['relations'].items(): self.distances[key][relation['distance']]+=1
            for key,features in c['id_patterns'].items():
                for feature,value in features.items():
                    if isinstance(value,dict):
                        for n,flag in value.items(): self.id_features[key][feature+'_'+n][str(flag)]+=1
                    else: self.id_features[key][feature][str(value)]+=1
            flag_group=lambda v:'UNKNOWN' if v is None else ('TRUE' if v else 'FALSE')
            groups={'normal_state':c['normal_state'],'is_tie':flag_group(c['is_tie']),
                'has_measurement':flag_group(c['has_measurement']),'outer_entity_types':types['A']+' / '+types['B']}
            for group,value in groups.items():
                self.groups[group][value]['motif:'+c['motif']]+=1
                self.groups[group][value]['breakdown:'+c['breakdown']]+=1
                self.groups[group][value]['total']+=1
            self.raw_state_values[c['switch_fields']['Switch_NormalState']]+=1
            for example_key in ('motif:'+c['motif'],'breakdown:'+c['breakdown']):
                examples=self.examples[example_key]; examples.append(c)
                examples.sort(key=lambda e:(e['case_id'],e['source_record_ref']))
                del examples[3:]

    def finish(self):
        n=self.counts['candidate_switches']; explicit_n=self.counts['baseline_explicit_reconstructed']
        categories=('EXACT_COMPATIBLE','REVERSE_COMPATIBLE','PARTIAL_COMPATIBLE','BOTH_ENDPOINTS_DIFFERENT',
            'ONE_ENDPOINT_MISSING','BOTH_ENDPOINTS_MISSING','ENDPOINT_UNRESOLVED','ENDPOINT_AMBIGUOUS','DIFFERENT_SOURCE_LAYER','OTHER')
        for key in categories:
            self.explicit.counts.setdefault(key,0); self.all_breakdowns.counts.setdefault(key,0)
        for key in literal_motif('','','','')['flags']: self.flags.counts.setdefault(key,0)
        for key in ('COMPATIBLE_SOURCE_EVIDENCE','DIFFERENT_ABSTRACTION_EVIDENCE','UNRESOLVED_SEMANTICS','CONFIRMED_CONFLICT'):
            self.assessments.counts.setdefault(key,0)
        counter={key:dict(sorted(value.items())) for key,value in sorted(self.counterfactual.items())}
        counter['labels']=DISCLAIMER
        counter['definitions']={'baseline':'unchanged E2-v1 artifact',
            'A':'ignore Switch explicit fields only; one-in-one-out with exact inner references',
            'B':'unique direct/reverse literal compatible endpoint evidence',
            'C':'B plus explicit Bus/Station membership on differing endpoint pairs'}
        counter['C_data_supported']=bool(self.assessments.counts['DIFFERENT_ABSTRACTION_EVIDENCE'])
        if not counter['C_data_supported']:
            counter['C']=None; counter['C_not_evaluated_reason']='NO_DEMONSTRATED_DIFFERENT_LAYER_SUBSET'
        case_summaries=tuple(sorted(self.case_summaries,key=lambda c:c['case_id']))
        purity=Counter('NO_CANDIDATES' if c['motif_purity'] is None else
            'ONE_MOTIF' if c['motif_purity']==1 else 'PURITY_GE_0_9' if c['motif_purity']>=Decimal('0.9') else 'MIXED'
            for c in case_summaries)
        return {'dataset_summary':{'analysis_version':VERSION,'accepted_topology':False,**dict(sorted(self.counts.items())),
                'candidate_exclusion_reasons':dict(sorted(self.exclusions.items())),
                'semantic_assessments':self.assessments.report(n),'case_purity_distribution':dict(sorted(purity.items())),
                'raw_normal_state_values':dict(sorted(self.raw_state_values.items()))},
            'motif_distribution':{'exclusive':self.motifs.report(n),'overlapping_equality_flags':self.flags.report(n),
                'stratifications':{g:{v:dict(sorted(counts.items())) for v,counts in sorted(groups.items())} for g,groups in sorted(self.groups.items())}},
            'endpoint_type_distribution':{'positions':{p:{k:dict(sorted(v.items())) for k,v in groups.items()} for p,groups in self.endpoint_types.items()},
                'type_pairs':{k:dict(sorted(v.items())) for k,v in sorted(self.type_pairs.items())},
                'source_reference_distances':{k:dict(sorted(v.items())) for k,v in sorted(self.distances.items())},
                'id_patterns':{pair:{feature:dict(sorted(counts.items())) for feature,counts in sorted(features.items())} for pair,features in sorted(self.id_features.items())}},
            'case_pattern_summary':case_summaries,
            'explicit_endpoint_breakdown':{'baseline_explicit_devices':self.counts['baseline_explicit_devices'],
                'reconstructed_candidates':explicit_n,'baseline_only':self.explicit.report(explicit_n),
                'all_candidates':self.all_breakdowns.report(n)},
            'degree_distribution':{'degree':{k:dict(sorted(v.items())) for k,v in sorted(self.degree.items())},
                'degree_two_directions':{k:dict(sorted(v.items())) for k,v in sorted(self.directions.items())}},
            'counterfactual_reachability':counter,
            'representative_examples':{'selection':'first 3 by case_id + source_record_ref per category',
                'examples':dict(sorted(self.examples.items()))}}


def aggregate_cases(results):
    summary=InvestigationSummary()
    for result in results: summary.add(result)
    return summary.finish()
