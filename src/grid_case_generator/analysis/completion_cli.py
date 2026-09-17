"""D1 contract analysis only; deliberately no propose/apply/topology writer command."""
import argparse
import json

from grid_case_generator.io.completion_artifacts import run_completion_analysis, verify_completion_artifact


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    for command in ('analyze','verify'):
        sub=subs.add_parser(command)
        for key in ('source','baseline','projection','feeder','recovery'):
            sub.add_argument('--'+key,required=command=='analyze')
        if command=='analyze':sub.add_argument('--output',required=True)
        else:sub.add_argument('artifact')
    args=parser.parse_args()
    roots={k:getattr(args,k) for k in ('source','baseline','projection','feeder','recovery')}
    if any(roots.values()) and not all(roots.values()):parser.error('supply all five input roots or none')
    if args.command=='verify':
        manifest=verify_completion_artifact(args.artifact,roots if all(roots.values()) else None)
        print(json.dumps({'verified':True,'input_bound':all(roots.values()),'feeder_count':manifest['feeder_count']}))
    else:
        def progress(i,p):
            if i%100==0:print(f'D1 profile {i}: {p["case_id"]}',flush=True)
        s=run_completion_analysis(roots,args.output,progress=progress)
        print(json.dumps({k:s[k] for k in ('case_count','feeder_count','primary_action_cohorts','synthetic_objects_created')},sort_keys=True))


if __name__=='__main__':main()
