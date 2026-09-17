"""Read-only E2.3-D design screening; never generates topology or accepted candidates.
Run from this checkout: .venv/bin/python docs/analysis/e23d_feasibility.py --output outputs/nanjing-e2-3-d/design-screening-v2
Output directory must not exist. Counts are conditional upper bounds, not safety approval.
"""
import json,hashlib,collections,statistics
from pathlib import Path
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',required=True)
args=parser.parse_args()
R=Path(__file__).resolve().parents[2]
E=R/'outputs/nanjing-e2-3/topology-recovery-evidence-v1'
OUT=Path(args.output).resolve()
if not OUT.is_relative_to(R/'outputs/nanjing-e2-3-d'):
 raise ValueError('design analysis output must be a new directory under outputs/nanjing-e2-3-d')
OUT.mkdir(parents=True,exist_ok=False)
def rows(p):
 with p.open() as f:
  for l in f: yield json.loads(l)
def read(p):return json.loads(p.read_text())
F={x['case_id']:x for x in rows(E/'feeder_details.jsonl')}; T=collections.defaultdict(list); C=collections.defaultdict(list); FB=collections.defaultdict(collections.Counter); W=collections.defaultdict(collections.Counter)
for x in rows(E/'transformer_evidence.jsonl'):T[x['case_id']].append(x)
for x in rows(E/'connection_evidence.jsonl'):C[x['case_id']].append(x)
for x in rows(E/'frontier_blockers.jsonl'):FB[x['case_id']][x['policy']+':'+x['tag']]+=1
for x in rows(E/'candidate_rule_witnesses.jsonl'):W[x['case_id']][x['rule_id']]+=1
cohorts=list(rows(E/'recovery_cohorts.jsonl'))
assert len(cohorts)==len(F)==5134
for cohort in cohorts:
 assert all(F[cohort['case_id']][k]==v for k,v in cohort.items())
all_transformer_ids=collections.defaultdict(set)
for cid,targets in T.items():
 for target in targets: all_transformer_ids[target['source_id']].add(cid)
assert all(len(case_ids)==1 for case_ids in all_transformer_ids.values())
shared=collections.defaultdict(set); allrows=[]; fieldstats=collections.defaultdict(collections.Counter); configs=collections.defaultdict(collections.Counter); stations=collections.defaultdict(collections.Counter)
for i,(cid,f) in enumerate(F.items()):
 p=R/'outputs/nanjing-e1/source-import-v2/cases'/cid
 a=list(rows(p/'row_accountability.jsonl')); by=collections.defaultdict(list)
 for r in a:
  raw=r['raw_record']; fields=dict(raw['fields'] or []); by[raw['source_file_type']].append(fields)
  if raw['source_file_type']=='TRANSFORMER':shared[fields.get('Transformer_ID')].add(cid)
 group='B' if 'B' in f['completion_cohorts'] else 'with_T'
 for raw in by['STATION']: stations[group][str((raw.get('Station_Type'),raw.get('Station_Voltage_Level')))]+=1
 for typ in ['TRANSFORMER','ACCESS_POINT','FEEDER','STATION','BUS']:
  for raw in by[typ]:
   for k,v in raw.items():
    if v:fieldstats[group][k]+=1
 for raw in by['SIM_CONFIG']:configs[group][str((raw.get('Config_Key'),raw.get('Config_Value')))]+=1
 top=read(R/'outputs/nanjing-e2/topology-v2/cases'/cid/'topology.json')
 nodes={n['node_id']:n for n in top['nodes']}; head=top['feeder_head_id']; gs={}
 for policy in ['S0','S2']:
  adj=collections.defaultdict(list)
  for edge in C[cid]:
   if edge['policy']==policy and edge['conducting']:
    _,u,v=edge['derived_ids'];adj[u].append(v);adj[v].append(u)
  seen=set([head]) if head else set(); todo=list(seen)
  while todo:
   for v in adj[todo.pop()]:
    if v not in seen:seen.add(v);todo.append(v)
  if policy=='S0': assert seen==set(top['reachable_node_ids'])
  candidates=[n for n in seen if n in nodes and nodes[n]['role']=='junction/bus']
  gs[policy]={'junctions':len(candidates),'junction_degrees':sorted(len(adj[n]) for n in candidates),'reachable_nodes':len(seen),'usable':f['graphs'][policy]['reachable_lines']>0,'target_full':f['graphs'][policy]['target_coverage']=='FULL'}
 ts=T[cid]; unref=[t for t in ts if t['reference_composition']=='NO_REFERENCE']
 allrows.append({'case_id':cid,'feeder_id':f['feeder_id'],'source_case_key':f['source_case_key'],'name':f['name'],'cohorts':f['completion_cohorts'],'constraint_tags':f['constraint_tags'],'observed_blockers':f['observed_blockers'],'graphs':gs,'source_rows':{k:len(v) for k,v in by.items()},'targets':len(ts),'unreferenced':len(unref),'remaining_referenced':{s:sum(t['reference_composition']!='NO_REFERENCE' and not t['attachment'][s]['reachable'] for t in ts) for s in ['S0','S2']},'open_switches':sum(r.get('Switch_NormalState','').lower()=='open' for r in by['SWITCH']),'transformer_ids':[t['source_id'] for t in unref],'transformer_nonempty_fields':dict(collections.Counter(k for r in by['TRANSFORMER'] for k,v in r.items() if v)),'candidate_witnesses':dict(W[cid]),'frontiers':dict(FB[cid]),'simconfig':by['SIM_CONFIG'],'bus_voltages':dict(collections.Counter(r.get('Bus_BaseKV') for r in by['BUS']))})
 if (i+1)%1000==0: print('read',i+1,flush=True)
for r in allrows:r['cross_case_unreferenced_ids']=sum(len(shared[t])>1 for t in r.pop('transformer_ids'))
summary={}
for cohort in ['A','B','C','D','with_T','all']:
 rs=[r for r in allrows if cohort=='all' or (cohort=='with_T' and r['targets']) or cohort in r['cohorts']]
 summary[cohort]={'feeders':len(rs),'no_D':sum('D' not in r['cohorts'] for r in rs),'with_line':sum(r['source_rows'].get('LINE',0)>0 for r in rs),'with_AP':sum(r['source_rows'].get('ACCESS_POINT',0)>0 for r in rs),'with_load':sum(r['source_rows'].get('LOAD',0)>0 for r in rs),'with_DER':sum(r['source_rows'].get('DER',0)>0 for r in rs),'any_open_switch':sum(r['open_switches']>0 for r in rs),'cross_case_unreferenced':sum(r['cross_case_unreferenced_ids']>0 for r in rs),'unreferenced':sum(r['unreferenced'] for r in rs),'unreferenced_quantiles':{str(q): sorted(r['unreferenced'] for r in rs)[int((len(rs)-1)*q)] for q in [0,.5,.9,.99,1]},'line_rows_median':statistics.median(r['source_rows'].get('LINE',0) for r in rs),'AP_rows_median':statistics.median(r['source_rows'].get('ACCESS_POINT',0) for r in rs),'cohort_overlaps':dict(collections.Counter(c for r in rs for c in r['cohorts'])),'name_tokens':{t:sum(t.lower() in (r['name'] or '').lower() for r in rs) for t in ['10kV','20kV','联络','备用','专线','test']},'graphs':{s:{'usable':sum(r['graphs'][s]['usable'] for r in rs),'usable_no_D':sum(r['graphs'][s]['usable'] and 'D' not in r['cohorts'] for r in rs),'junction_count_distribution':dict(collections.Counter(r['graphs'][s]['junctions'] for r in rs)),'full':sum(r['graphs'][s]['target_full'] for r in rs)} for s in ['S0','S2']}}
policies={}
for s in ['S0','S2']:
 for label,pred in [('usable_no_D',lambda r:True),('junction_no_D',lambda r:r['graphs'][s]['junctions']>0),('unique_junction_no_D',lambda r:r['graphs'][s]['junctions']==1),('unique_junction_no_D_no_open_no_shared',lambda r:r['graphs'][s]['junctions']==1 and r['open_switches']==0 and r['cross_case_unreferenced_ids']==0)]:
  rs=[r for r in allrows if 'A' in r['cohorts'] and 'D' not in r['cohorts'] and r['graphs'][s]['usable'] and pred(r)]
  newfull=[r for r in rs if r['remaining_referenced'][s]==0]
  policies[s+':'+label]={'screened_feeders':len(rs),'hypothetical_leaf_connections':sum(r['unreferenced'] for r in rs),'new_target_full_upper_bound':len(newfull),'total_target_full_upper_bound':summary['all']['graphs'][s]['full']+len(newfull),'full_case_ids':[r['case_id'] for r in newfull],'screened_case_ids':[r['case_id'] for r in rs]}
summary['policies']=policies;summary['nonempty_source_fields']=fieldstats;summary['simconfig_values']=configs;summary['station_type_voltage_rows']=stations
summary['B_structure']=dict(collections.Counter(f"line={bool(r['source_rows'].get('LINE'))},AP={bool(r['source_rows'].get('ACCESS_POINT'))},S2usable={r['graphs']['S2']['usable']},D={'D' in r['cohorts']}" for r in allrows if 'B' in r['cohorts']))
summary['C_witnesses']={k:sum(bool(r['candidate_witnesses'].get(k)) for r in allrows if 'C' in r['cohorts']) for k in read(E/'summary.json')['candidate_rules']}
summary['interpretation']={'analysis_only':True,'synthetic_objects_created':0,'approved_eligible_feeders':0,'full_is_target_coverage_only':True,'policy_counts_are_conditional_upper_bounds':True}
summary['degree_cap_sensitivity']={}
for cap in [4,8,16,32,64]:
 selected=[r for r in allrows if r['case_id'] in policies['S2:unique_junction_no_D_no_open_no_shared']['screened_case_ids'] and r['graphs']['S2']['junction_degrees'][0]+r['unreferenced']<=cap]
 summary['degree_cap_sensitivity'][cap]={'feeders':len(selected),'connections':sum(r['unreferenced'] for r in selected)}
assert sum(r['unreferenced'] for r in allrows)==96038
assert summary['all']['graphs']['S0']['full']==0 and summary['all']['graphs']['S2']['full']==80
assert {c:summary[c]['feeders'] for c in 'ABCD'}=={'A':3114,'B':1713,'C':227,'D':1884}
summary['inputs']={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [E/'manifest.json',R/'outputs/nanjing-e1/source-import-v2/manifest.json',R/'outputs/nanjing-e2/topology-v2/manifest.json']}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
(OUT/'feeder_screening.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in allrows))
print(json.dumps({k:v for k,v in summary.items() if k not in ['nonempty_source_fields','policies','simconfig_values']},ensure_ascii=False,indent=2))
print('POLICIES',json.dumps({k:{a:b for a,b in v.items() if not a.endswith('ids')} for k,v in policies.items()}))
print('FIELDS',json.dumps(fieldstats));print('CONFIG',json.dumps(configs))
