"""Run E2 exclusively from a verified E1 artifact."""
import argparse
import json
from .topology import load_topology_config
from grid_case_generator.io.topology_artifacts import audit_source_artifact


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--config',default='configs/nanjing_topology.toml')
    parser.add_argument('--case-id')
    args=parser.parse_args()
    def progress(index,total,result):
        if index % 100 == 0 or index == total:
            print(f'E2 {index}/{total}: {result.coverage.case_id}',flush=True)
    result=audit_source_artifact(args.source,args.output,load_topology_config(args.config),case_id=args.case_id,progress=progress)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
