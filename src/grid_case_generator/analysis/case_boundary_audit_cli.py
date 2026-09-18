"""Build or source-replay an analysis-only D4.2 case boundary audit."""
import argparse
import json
import logging
from pathlib import Path
from grid_case_generator.io.case_boundary_audit import write_artifact, verify_artifact


def main():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('analyze', 'verify'))
    for name in ('source', 'accepted', 'd3', 'd4', 'placement', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    roots = {k: getattr(args,k) for k in ('source','accepted','d3','d4','placement')}
    result = verify_artifact(roots,args.output) if args.command == 'verify' else write_artifact(roots,args.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
