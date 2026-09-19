"""Build or verify the v1 completion export: ledger, delivery, archive and sidecar.

Thirteen verified upstream roots are required, not just the source archive: the
completion rules decide from persisted evidence the D-series artifacts publish, and
none of it is derivable from the source ZIP. Deep re-verification of any upstream is
its own command (`placement_evidence_cli verify`, `case_boundary_audit_cli verify`);
this command binds their manifest digests and re-checks them before and after the run.
"""
import argparse
import json
from pathlib import Path

from grid_case_generator.analysis.completion_export import run_export, verify_export
from grid_case_generator.io.completion_ledger_artifacts import INPUTS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('analyze', 'verify'))
    for name in sorted(INPUTS | {'policy', 'ledger', 'output'}):
        parser.add_argument('--' + name.replace('_', '-'), dest=name, type=Path, required=True)
    args = parser.parse_args()
    roots = {k: getattr(args, k) for k in INPUTS}
    if args.command == 'verify':
        result = verify_export(roots, args.policy, args.ledger, args.output)
    else:
        result = run_export(roots, args.policy, args.ledger, args.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))


if __name__ == '__main__':
    main()
