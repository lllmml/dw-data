"""Source-only CLI: python -m grid_case_generator.io.nanjing_source."""
import argparse
import json

from .archive import inventory_archive
from .import_pipeline import import_archive
from grid_case_generator.io.source_artifacts import verify_source_artifact


def main():
    parser = argparse.ArgumentParser(description='Read-only Nanjing source import (E1)')
    sub = parser.add_subparsers(dest='command',required=True)
    inspect = sub.add_parser('inspect')
    inspect.add_argument('archive')
    importer = sub.add_parser('import-source')
    importer.add_argument('archive')
    importer.add_argument('--output',required=True)
    importer.add_argument('--imported-at',required=True,help='Explicit ISO 8601 timestamp with offset')
    verify = sub.add_parser('verify')
    verify.add_argument('artifact')
    args = parser.parse_args()
    if args.command == 'inspect':
        inventory = inventory_archive(args.archive)
        print(json.dumps({'source_checksum':inventory.source_checksum,'case_count':len(inventory.cases),
            'csv_member_count':inventory.csv_member_count,'diagnostic_count':len(inventory.diagnostics)}))
        return 0
    if args.command == 'verify':
        manifest = verify_source_artifact(args.artifact)
        print(json.dumps({'verified':True,'import_status':manifest['import_status'],'files':len(manifest['files'])}))
        return 0
    report = import_archive(args.archive,args.output,imported_at=args.imported_at)
    print(json.dumps({'import_status':report['import_status'],'case_count':report['case_count'],
        'canonical_valid':report['canonical_valid']}))
    return 0 if report['import_status'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
