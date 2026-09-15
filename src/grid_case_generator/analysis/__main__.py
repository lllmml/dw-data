"""Run E2.1 diagnostics without altering E1 or E2."""
import argparse
import json
from grid_case_generator.io.canonical_json import to_canonical_data
from grid_case_generator.io.switch_semantics_artifacts import run_investigation


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True)
    parser.add_argument('--baseline',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--case-id')
    args=parser.parse_args()
    def progress(index,total,result):
        if index%100==0 or index==total:
            print(f'E2.1 {index}/{total}: {result["case_summary"]["case_id"]}',flush=True)
    result=run_investigation(args.source,args.baseline,args.output,case_id=args.case_id,progress=progress)
    print(json.dumps(to_canonical_data(result),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
