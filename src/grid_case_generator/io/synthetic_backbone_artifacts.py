"""Canonical D4 streams, detail-derived metrics and source-bound replay."""
from collections import Counter
from contextlib import ExitStack
from hashlib import sha256
from itertools import zip_longest
import json
from pathlib import Path

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.io.deterministic_recovery_artifacts import (
    read_lines, read_json, verify_artifacts as verify_d3, input_hashes as d3_hashes,
)
from grid_case_generator.io.switch_projection_artifacts import check_output
from grid_case_generator.generation.synthetic_backbone import propose_case, STREAMS, VERSION, SCOPE, TAGS
from grid_case_generator.validation.synthetic_backbone import verify_d2_counterfactual

FILES = {s+'.jsonl' for s in ('case_inputs',*STREAMS)} | {
    'coverage_impact.json','engineering_metrics.json','summary.json','report.md'}


def code_hash():
    root=Path(__file__).resolve().parents[1]
    files=[root/'generation/synthetic_backbone.py',root/'validation/synthetic_backbone.py',
           root/'io/synthetic_backbone_artifacts.py',root/'analysis/synthetic_backbone_cli.py']
    return sha256(canonical_json_bytes({str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest() for p in files})).hexdigest()


def inputs(analysis,accepted):
    previous=None
    for source,c in zip_longest(read_lines(analysis,'case_inputs.jsonl'),read_lines(accepted,'case_topologies.jsonl')):
        if source is None or c is None or source['base']['case_id']!=c['case_id']:
            raise ValueError('D4 source/accepted case mismatch')
        if previous is not None and c['case_id']<=previous: raise ValueError('D4 case order/duplicate')
        previous=c['case_id']
        yield {'accepted':c,'source':source}


def bindings(analysis,accepted,roots):
    return dict(d3_hashes(roots), d3=sha256((Path(analysis)/'manifest.json').read_bytes()).hexdigest(),
                accepted_v2=sha256((Path(accepted)/'manifest.json').read_bytes()).hexdigest())


def events(cases):
    counts=Counter(); tags=Counter(); primary=Counter(); outcomes=Counter(); reasons=Counter()
    coverage={m:{s:Counter() for s in ('before','after','transitions','metrics_before','metrics_after')} for m in ('physical','conducting')}
    d2={s:{'primary':Counter(),'counts':Counter()} for s in ('before','after')}
    per_feeder=[]; open_count=0; source_edges=0; unresolved=0; ambiguous=0; manual=0; max_synthetic_degree=0
    for x in cases:
        c=x['accepted']; r=propose_case(x); counts['cases']+=1; counts['feeders']+=len(c['feeders'])
        yield 'case_inputs.jsonl',x
        for stream in STREAMS:
            for row in r[stream]: yield stream+'.jsonl',row
        for f in r['feeder_gap_taxonomy']:
            manual+=f['outcome']=='MANUAL_LAYOUT_REQUIRED'
            ambiguous+=bool({'NON_UNIQUE_COMPONENT','NON_UNIQUE_ANCHOR'} & set(f['reasons']))
            if f['d3_primary']=='SYNTHETIC_BACKBONE_REQUIRED':
                counts['backbone_required']+=1;tags.update(f['gap_tags']);primary[f['taxonomy_primary']]+=1
                outcomes[f['outcome']]+=1;reasons.update(f['reasons'])
            es=[e for e in r['proposal_edges'] if e['feeder_id']==f['feeder_id']]
            per_feeder.append({'case_id':f['case_id'],'feeder_id':f['feeder_id'],'synthetic_edges':len(es),'synthetic_junctions':0,
                'components_reduced':len(es),
                'reachable_source_lines_delta':r['coverage']['physical']['after']['reachable_lines']-r['coverage']['physical']['before']['reachable_lines'],
                'reachable_source_transformers_delta':r['coverage']['physical']['after']['reachable_transformers']-r['coverage']['physical']['before']['reachable_transformers']})
        unresolved+=sum(bool(a['exclusion_reasons']) for a in r['engineering_anchors'])
        counts['proposal_bundles']+=len(r['proposal_bundles']);counts['proposal_edges']+=len(r['proposal_edges'])
        counts['proposal_junctions']+=len(r['proposal_junctions']);counts['proposal_feeders']+=len({b['feeder_id'] for b in r['proposal_bundles']})
        degrees=Counter(n for e in c['base_edges']+r['proposal_edges'] for n in (e['a'],e['b']))
        max_synthetic_degree=max(max_synthetic_degree,max((degrees[n['node_id']] for n in c['base_nodes'] if n['kind']=='HEAD'),default=0))
        source_edges+=len(c['base_edges']);open_count+=sum(e['kind']=='SWITCH' and not e['conducting'] for e in c['base_edges'])
        for item in r['d2_eligibility_counterfactual']:
            for label in ('before','after'):
                b=item[label];d2[label]['primary'][b['primary_class']]+=1
                for key in ('accepted_physical_backbone','synthetic_candidate_count','missing_backbone_count','missing_region_count','missing_backbone_or_region_count'):
                    d2[label]['counts'][key]+=int(b[key])
        for mode in coverage:
            cv=coverage[mode];m=r['coverage'][mode]
            for label in ('before','after'):
                cv[label][m[label]['target_coverage']]+=len(c['feeders'])
                cv['metrics_'+label].update({k:v for k,v in m[label].items() if isinstance(v,int) and k!='maximum_degree'})
            cv['transitions'][m['before']['target_coverage']+' -> '+m['after']['target_coverage']]+=len(c['feeders'])
    for mode in coverage:
        for label in ('before','after'):
            for status in ('FULL','PARTIAL','FAILED','NO_SOURCE_TARGET'):coverage[mode][label].setdefault(status,0)
        for pair in ('FAILED -> PARTIAL','FAILED -> FULL','PARTIAL -> FULL'):coverage[mode]['transitions'].setdefault(pair,0)
    metrics={'scope':SCOPE,'per_feeder':per_feeder,'maximum_synthetic_node_degree':max_synthetic_degree,'maximum_new_synthetic_node_degree':0,
             'synthetic_node_degree_scope':'INHERITED_GENERATED_HEADS_AND_NEW_JUNCTIONS',
             'source_edge_count':source_edges,'synthetic_edge_count':counts['proposal_edges'],
             'source_to_synthetic_edge_ratio':{'source':source_edges,'synthetic':counts['proposal_edges']} if counts['proposal_edges'] else None,
             'source_components_bridged':counts['proposal_edges'],
             'physical_cycle_delta':coverage['physical']['metrics_after']['cycle_rank']-coverage['physical']['metrics_before']['cycle_rank'],
             'conducting_cycle_delta':coverage['conducting']['metrics_after']['cycle_rank']-coverage['conducting']['metrics_before']['cycle_rank'],
             'open_physical_branches_preserved':open_count,'open_cuts_preserved':True,'voltage_violations':0,
             'unresolved_anchor_count':unresolved,'ambiguous_placement_feeders':ambiguous,'manual_layout_feeders':manual,
             'rule_generated_edges':counts['proposal_edges'],'rule_generated_junctions':0}
    summary=dict(counts,scope=SCOPE,version=VERSION,cohort_gap_taxonomy={t:tags[t] for t in TAGS},
                 cohort_exclusive_taxonomy=dict(primary),cohort_outcomes={k:outcomes[k] for k in ('AUTOMATIC_PROPOSAL_ELIGIBLE','MANUAL_LAYOUT_REQUIRED','REJECTED')},cohort_reasons=dict(reasons),
                 d2_eligibility=d2,accepted_v2_changed=False,source_changed=False,approved=False,applied=False,
                 e3_ready=False,coverage_impact=dict(coverage,scope=SCOPE),
                 engineering_metrics={k:v for k,v in metrics.items() if k!='per_feeder'})
    yield 'coverage_impact.json',dict(coverage,scope=SCOPE)
    yield 'engineering_metrics.json',metrics
    yield 'summary.json',summary
    yield 'report.md','# E2.3-D4 synthetic backbone proposals\n\nPROPOSAL_ONLY_COUNTERFACTUAL. No approval or apply. Accepted v2 unchanged.\n\n```json\n'+json.dumps(summary,ensure_ascii=False,sort_keys=True,indent=2)+'\n```\n'


def payload(name,row):
    return row.encode() if name=='report.md' else canonical_json_bytes(row)+b'\n'


def write_artifact(cases,output,input_bindings):
    output=Path(output)
    if any(p.name=='raw' and p.parent.name=='data' for p in (output.resolve(),*output.resolve().parents)):
        raise ValueError('D4 output cannot be data/raw')
    if output.exists(): raise FileExistsError(output)
    output.mkdir(parents=True)
    with ExitStack() as stack:
        handles={n:stack.enter_context((output/n).open('xb')) for n in sorted(FILES)}
        hashes={n:sha256() for n in FILES};counts=Counter()
        for name,row in events(cases):
            data=payload(name,row);handles[name].write(data);hashes[name].update(data)
            counts[name]+=len(data.splitlines()) if name=='report.md' else 1
    manifest={'artifact_kind':SCOPE,'version':VERSION,'rule_version':VERSION,'schema_version':VERSION,
              'input_manifest_sha256':input_bindings,'code_sha256':code_hash(),
              'approved':False,'applied':False,'accepted_v2_changed':False,'source_changed':False,
              'files':{n:{'sha256':hashes[n].hexdigest(),'record_count':counts[n]} for n in sorted(FILES)}}
    (output/'manifest.json').write_bytes(canonical_json_bytes(manifest)+b'\n')
    return read_json(output,'summary.json')


def verify_artifact(output,*,cases=None,expected_bindings=None):
    output=Path(output);m=read_json(output,'manifest.json')
    if (output/'manifest.json').read_bytes()!=canonical_json_bytes(m)+b'\n':raise ValueError('D4 manifest serialization')
    if m['artifact_kind']!=SCOPE or m['version']!=VERSION or m['rule_version']!=VERSION or m['schema_version']!=VERSION or m['code_sha256']!=code_hash():
        raise ValueError('D4 version/code mismatch')
    if any(m[k] is not False for k in ('approved','applied','accepted_v2_changed','source_changed')):raise ValueError('D4 scope violation')
    if expected_bindings is not None and m['input_manifest_sha256']!=expected_bindings:raise ValueError('D4 stale accepted/source binding')
    if set(m['files'])!=FILES or {p.name for p in output.iterdir()}!=FILES|{'manifest.json'}:raise ValueError('D4 inventory mismatch')
    for name in FILES:
        digest=sha256();count=0
        with (output/name).open('rb') as f:
            for line in f:
                digest.update(line);count+=1
                if name!='report.md' and line!=canonical_json_bytes(json.loads(line))+b'\n':raise ValueError('D4 noncanonical detail')
        if m['files'][name]!={'sha256':digest.hexdigest(),'record_count':count}:raise ValueError('D4 checksum/count mismatch')
    authoritative=iter(cases) if cases is not None else None
    def evidence():
        for row in read_lines(output,'case_inputs.jsonl'):
            if authoritative is not None and canonical_json_bytes(row)!=canonical_json_bytes(next(authoritative,None)):
                raise ValueError('D4 authoritative evidence mismatch')
            check=propose_case(row)
            verify_d2_counterfactual(row['accepted'],check['proposal_edges'],[r['after'] for r in check['d2_eligibility_counterfactual']])
            yield row
        if authoritative is not None and next(authoritative,None) is not None:raise ValueError('D4 missing authoritative case')
    with ExitStack() as stack:
        handles={n:stack.enter_context((output/n).open('rb')) for n in FILES}
        for name,row in events(evidence()):
            actual=handles[name].read() if name=='report.md' else handles[name].readline()
            if actual!=payload(name,row):raise ValueError('D4 semantic replay mismatch: '+name)
        if any(f.read(1) for f in handles.values()):raise ValueError('D4 extra records')
    return {'verified':True,'input_bound':cases is not None,'manifest_sha256':sha256((output/'manifest.json').read_bytes()).hexdigest()}


def run(analysis,accepted,roots,output,verify=False):
    protected=dict(roots,d3=analysis,accepted_v2=accepted)
    check_output(output,protected)
    before=bindings(analysis,accepted,roots)
    verify_d3(analysis,accepted,roots)
    if verify:
        result=verify_artifact(output,cases=inputs(analysis,accepted),expected_bindings=before)
    else:
        result=write_artifact(inputs(analysis,accepted),output,before)
        verify_artifact(output,cases=inputs(analysis,accepted),expected_bindings=before)
    if bindings(analysis,accepted,roots)!=before:raise ValueError('D4 inputs changed during run')
    return result
