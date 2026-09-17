"""Build or verify D4.1 source-constrained placement-evidence artifacts."""
import argparse
import json
from pathlib import Path

from grid_case_generator.io.deterministic_recovery_artifacts import INPUTS
from grid_case_generator.io.placement_evidence_artifacts import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('analyze', 'verify'))
    for name in sorted(INPUTS | {'analysis', 'accepted', 'd4', 'output'}):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = run(args.analysis, args.accepted, {k: getattr(args, k) for k in INPUTS},
                 args.d4, args.output, args.command == 'verify')
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
