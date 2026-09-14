"""Versioned source-only artifacts with deterministic JSON and verified readers."""
from collections import Counter, defaultdict
from dataclasses import dataclass, fields, is_dataclass
from functools import lru_cache
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import types
from typing import Union, get_args, get_origin, get_type_hints

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.models import records as models
from grid_case_generator.models.types import Identifier

from grid_case_generator.io.nanjing_source.case_assembly import RowAccountability
from grid_case_generator.io.nanjing_source.mapping import UnmappedSourceRecord
from grid_case_generator.io.nanjing_source.locator import SourceRecordRef
from grid_case_generator.validation.reference_resolution import ReferenceResolutionResult

FORMAT_VERSION = '0.1.0'
_cached_type_hints = lru_cache(maxsize=None)(get_type_hints)
RECORD_TYPES = {name:cls for name,cls in vars(models).items()
    if isinstance(cls,type) and issubclass(cls,models.TraceableRecord) and cls is not models.TraceableRecord}


def _safe_relative(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or '\\' in value or ':' in path.parts[0]:
        raise ValueError('unsafe artifact path')
    return path


class SourceArtifactWriter:
    def __init__(self, output, source):
        self.root = Path(output).absolute()
        source = Path(source).resolve()
        resolved = self.root.resolve()
        raw = Path(__file__).resolve().parents[3] / 'data' / 'raw'
        if resolved == raw or raw in resolved.parents or resolved == source or resolved in source.parents:
            raise ValueError('output cannot overwrite raw/source input')
        if any(p.is_symlink() for p in (self.root,*self.root.parents)):
            raise ValueError('symlink output directories are not allowed')
        self.root.mkdir(parents=True,exist_ok=False)
        self.entries = {}

    def write(self, relative, value, *, lines=False):
        path = self.root / str(_safe_relative(relative))
        path.parent.mkdir(parents=True,exist_ok=True)
        count = 0
        digest = sha256()
        with path.open('xb') as stream:
            if lines:
                for record in value:
                    data = canonical_json_bytes(record)+b'\n'
                    stream.write(data)
                    digest.update(data)
                    count += 1
            else:
                data = canonical_json_bytes(value)+b'\n'
                stream.write(data)
                digest.update(data)
                count = 1
        self.entries[relative] = {'sha256':digest.hexdigest(),'record_count':count}

    def write_case(self,result):
        case_id = result.grid_case.case_id
        prefix = f'cases/{case_id}/'
        groups = defaultdict(list)
        for record in result.records:
            groups[type(record).__name__].append(record)
        for kind,records in sorted(groups.items()):
            self.write(prefix+f'records/{kind}.jsonl',records,lines=True)
        for name,values in (('quality_issues',result.issues),('field_provenance',result.provenance),
                ('resolutions',result.resolutions),('row_accountability',result.accounting),
                ('unmapped_source_records',result.unmapped_records)):
            self.write(prefix+name+'.jsonl',values,lines=True)
        self.write(prefix+'file_accounting.json',{
            'files':[{'source_file_type':f.source_file_type,'member_path':f.member_path,'header':f.header,
                'row_count':len(f.records),'diagnostics':f.diagnostics} for f in result.files],
            'diagnostics':result.diagnostics})
        from grid_case_generator.validation.source_import import canonical_case_errors
        summary = {'case_id':case_id,'source_case_key':result.grid_case.source_case_key,
            'import_status':result.import_status.value,'canonical_valid':result.canonical_valid,
            'canonical_errors':canonical_case_errors(result.records,result.issues,result.provenance),
            'source_rows':dict(sorted(Counter(a.raw_record.source_file_type.value for a in result.accounting).items())),
            'record_counts':{kind:len(records) for kind,records in sorted(groups.items())},
            'row_categories':dict(sorted(Counter(a.terminal_category.value for a in result.accounting).items())),
            'reference_counts':dict(sorted(Counter(r.resolution_status.value for r in result.resolutions).items())),
            'issue_counts':dict(sorted(Counter(i.code.value for i in result.issues).items()))}
        self.write(prefix+'case_report.json',summary)
        return summary

    def finish(self,dataset):
        from grid_case_generator.io.nanjing_source.schema import NANJING_SOURCE_SCHEMA
        from importlib.metadata import version
        value = {'format_version':FORMAT_VERSION,'source_checksum':dataset.source_checksum,
            'canonical_spec_version':dataset.canonical_spec_version,
            'mapping_id':NANJING_SOURCE_SCHEMA.mapping_id,'mapping_version':NANJING_SOURCE_SCHEMA.mapping_version,
            'software_version':version('grid-case-generator'),'import_status':dataset.import_status,
            'files':dict(sorted(self.entries.items()))}
        (self.root / 'manifest.json').write_bytes(canonical_json_bytes(value)+b'\n')


def verify_source_artifact(root):
    root = Path(root)
    if root.is_symlink() or any(p.is_symlink() for p in root.parents):
        raise ValueError('symlink artifact root')
    manifest_path = root/'manifest.json'
    if manifest_path.is_symlink():
        raise ValueError('symlink manifest')
    manifest = json.loads(manifest_path.read_text())
    if manifest['format_version'] != FORMAT_VERSION:
        raise ValueError('unsupported source artifact version')
    for relative,entry in manifest['files'].items():
        path = root/str(_safe_relative(relative))
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):
            raise ValueError('symlink artifact member')
        digest = sha256()
        count = 0
        with path.open('rb') as stream:
            for line in stream:
                digest.update(line)
                count += 1
        if digest.hexdigest() != entry['sha256'] or count != entry['record_count']:
            raise ValueError(f'artifact checksum/count mismatch: {relative}')
    observed = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p != manifest_path}
    if observed != set(manifest['files']):
        raise ValueError('artifact file inventory mismatch')
    return manifest


def _decode(value, annotation):
    origin = get_origin(annotation)
    if origin in (Union,types.UnionType):
        if value is None and type(None) in get_args(annotation):
            return None
        for member in get_args(annotation):
            if member is type(None): continue
            try: return _decode(value,member)
            except (TypeError,ValueError): pass
        raise ValueError('value does not match record union')
    if origin is tuple:
        args = get_args(annotation)
        if len(args)==2 and args[1] is Ellipsis:
            return tuple(_decode(item,args[0]) for item in value)
        return tuple(_decode(item,kind) for item,kind in zip(value,args,strict=True))
    if origin is dict:
        key_type,item_type = get_args(annotation)
        return {_decode(k,key_type):_decode(v,item_type) for k,v in value.items()}
    if annotation is Decimal:
        if not isinstance(value,str): raise TypeError('Decimal must be text')
        result = Decimal(value)
        if not result.is_finite(): raise ValueError('non-finite Decimal')
        return result
    if isinstance(annotation,type) and issubclass(annotation,(Identifier,Enum,SourceRecordRef)):
        return annotation(value)
    if is_dataclass(annotation):
        hints = _cached_type_hints(annotation)
        if set(value) != {f.name for f in fields(annotation)}:
            raise ValueError('record fields do not match schema')
        return annotation(**{key:_decode(item,hints[key]) for key,item in value.items()})
    if annotation in (str,int,bool,type(None)) and type(value) is annotation:
        return value
    raise TypeError(f'unsupported record value for {annotation}')


def read_source_case(root, case_id, *, verified_manifest=None):
    manifest = verified_manifest if verified_manifest is not None else verify_source_artifact(root)
    if not isinstance(case_id,str) or not case_id.startswith('case:') or len(case_id) != 69 or any(c not in '0123456789abcdef' for c in case_id[5:]):
        raise ValueError('invalid source case ID')
    prefix = f'cases/{case_id}/records/'
    output = []
    for relative in sorted(manifest['files']):
        if not relative.startswith(prefix): continue
        kind = Path(relative).stem
        if kind not in RECORD_TYPES: raise ValueError('unknown source record type')
        with (Path(root)/relative).open() as stream:
            output.extend(_decode(json.loads(line),RECORD_TYPES[kind]) for line in stream)
    if not output:
        raise ValueError('case has no published records')
    return tuple(output)


@dataclass(frozen=True, slots=True)
class SourceCaseDetails:
    records: tuple[models.TraceableRecord, ...]
    issues: tuple[models.DataQualityIssue, ...]
    provenance: tuple[models.FieldProvenance, ...]
    resolutions: tuple[ReferenceResolutionResult, ...]
    accounting: tuple[RowAccountability, ...]
    unmapped_records: tuple[UnmappedSourceRecord, ...]


def read_source_case_details(root, case_id, *, verified_manifest=None) -> SourceCaseDetails:
    manifest = verified_manifest if verified_manifest is not None else verify_source_artifact(root)
    records = read_source_case(root,case_id,verified_manifest=manifest)
    values = []
    for name,kind in (
        ('quality_issues',models.DataQualityIssue),
        ('field_provenance',models.FieldProvenance),
        ('resolutions',ReferenceResolutionResult),
        ('row_accountability',RowAccountability),
        ('unmapped_source_records',UnmappedSourceRecord),
    ):
        relative = f'cases/{case_id}/{name}.jsonl'
        if relative not in manifest['files']:
            raise ValueError('missing source case evidence file')
        with (Path(root)/relative).open() as stream:
            values.append(tuple(_decode(json.loads(line),kind) for line in stream))
    return SourceCaseDetails(records,*values)
