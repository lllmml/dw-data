"""Command line for D2 proposal generation and verification; no apply operation."""
import argparse
import json
from pathlib import Path
from grid_case_generator.io.proposal_artifacts import INPUTS, run_proposal_analysis, verify_proposal_artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for name in ('analyze', 'verify'):
        sub = subs.add_parser(name)
        for key in sorted(INPUTS):
            sub.add_argument('--'+key, type=Path, required=name=='analyze')
        sub.add_argument('--output', type=Path, required=True)
        if name=='analyze':
            sub.add_argument('--decisions', type=Path, required=True)
    args = parser.parse_args()
    roots = {k:getattr(args,k) for k in INPUTS if getattr(args,k) is not None}
    if roots and set(roots)!=INPUTS:
        parser.error('supply all six input roots for bound verification')
    if args.command=='analyze':
        result = run_proposal_analysis(roots,args.decisions,args.output)
    else:
        result = verify_proposal_artifact(args.output,roots or None)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))


if __name__=='__main__':
    main()
