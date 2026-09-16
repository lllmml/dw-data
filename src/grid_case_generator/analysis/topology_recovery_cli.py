"""E2.3-A evidence foundation. No accepted topology or synthetic implementation."""
import argparse
import json

from grid_case_generator.io.topology_recovery_artifacts import run_recovery_analysis, verify_recovery_artifact


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    run=sub.add_parser('analyze')
    for key in ('source','baseline','projection','feeder','output'):run.add_argument('--'+key,required=True)
    verify=sub.add_parser('verify');verify.add_argument('artifact')
    args=parser.parse_args()
    if args.command=='verify':
        m=verify_recovery_artifact(args.artifact)
        print(json.dumps({'verified':True,'case_count':m['case_count'],'feeder_count':m['feeder_count']},sort_keys=True));return
    def progress(i,total,result):
        if i%100==0 or i==total:print(f'Recovery evidence {i}/{total}: {result["case_id"]}',flush=True)
    s=run_recovery_analysis(args.source,args.baseline,args.projection,args.feeder,args.output,progress=progress)
    print(json.dumps({k:s[k] for k in ('case_count','feeder_count','source_evidence_cohorts','legacy_target_coverage','synthetic_connections')},sort_keys=True),flush=True)


if __name__=='__main__':main()
