"""D3 deterministic recovery and immutable accepted v2 verification."""
import argparse
import json
from pathlib import Path
from grid_case_generator.io.deterministic_recovery_artifacts import INPUTS, run_recovery, verify_artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('analyze', 'verify'):
        p = sub.add_parser(command)
        for key in sorted(INPUTS): p.add_argument('--'+key, type=Path, required=True)
        p.add_argument('--output', type=Path, required=True)
        p.add_argument('--accepted-output', type=Path, required=True)
    args = parser.parse_args(); roots = {k:getattr(args,k) for k in INPUTS}
    if args.command=='analyze':
        result = run_recovery(roots,args.output,args.accepted_output,
            progress=lambda n,c:print('case',n,c,flush=True) if n%500==0 else None)
    else: result = verify_artifacts(args.output,args.accepted_output,roots)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))


if __name__=='__main__': main()
