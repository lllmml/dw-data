"""Case-local complete source import. No topology or generated electrical data."""
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from collections.abc import Iterable

from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.models.identifiers import SourceImportIdFactory as IDs
from grid_case_generator.models.records import DataQualityIssue, Terminal, Station, Bus, Feeder, GridCase, TraceableRecord, FieldProvenance
from grid_case_generator.models.types import (CanonicalId, EntityRef, Identifier, SourceId, RecordOrigin, ImportStatus, IdentityStatus, SourceReferenceStatus)
from grid_case_generator.models.quality import QualityIssueCode as Code
from grid_case_generator.validation.identity import SourceIdentityRecord, SourceEntityType, classify_source_identities
from grid_case_generator.validation.reference_resolution import ReferenceResolutionRequest, ReferenceResolutionResult, resolve_source_reference
from grid_case_generator.validation.quality import default_severity_for_issue
from .models import SourceCaseInventory, RawSourceFile, IntakeDiagnostic
from .mapping import UnmappedSourceRecord
from .schema import NANJING_SOURCE_SCHEMA as SCHEMA, SourceFileType as FT
from .mapping import map_grid_case, map_dataset, map_station, map_bus, map_feeder, _malformed_outcome, _missing_id_outcome
from .case_assembly import CaseRowMappingOutcome, RowAccountability, RowTerminalCategory, assemble_station_feeder_bus_case, _issue_sort_key
from .equipment_mapping import map_equipment, PREFIXES
from .equipment_assembly import assemble_equipment
from .operational_mapping import map_sim_config
from .reference_integration import build_nanjing_reference_candidate_index
from .reference_issue_policy import reference_issues_for_result
from .field_mapping import SourceFields


@dataclass(frozen=True, slots=True)
class SourceCaseResult:
    grid_case: GridCase
    records: tuple[TraceableRecord, ...]
    issues: tuple[DataQualityIssue, ...]
    provenance: tuple[FieldProvenance, ...]
    unmapped_records: tuple[UnmappedSourceRecord, ...]
    resolutions: tuple[ReferenceResolutionResult, ...]
    accounting: tuple[RowAccountability, ...]
    files: tuple[RawSourceFile, ...]
    diagnostics: tuple[IntakeDiagnostic, ...]
    import_status: ImportStatus
    canonical_valid: bool


def _diagnostic_issue(diagnostic, dataset_id, case_id):
    code = Code(diagnostic.code.value)
    return DataQualityIssue(record_origin=RecordOrigin.DERIVED,
        source_record_ref=diagnostic.source_record_ref,source_mapping_id=SCHEMA.mapping_id,
        source_mapping_version=SCHEMA.mapping_version,
        issue_id=IDs.quality_issue_id(dataset_id,case_id,None,None,code,
            diagnostic.source_record_ref,diagnostic.member_path or ''),
        case_id=case_id,target_ref=None,field_path=None,code=code,
        severity=default_severity_for_issue(code),observed_value=diagnostic.member_path,
        message=diagnostic.message)


def _check_primary_fields(raw, outcome, dataset_id, case_id):
    record = outcome.record
    if record is not None:
        prefix = type(record).__name__
        ref = EntityRef(entity_type=Identifier(prefix.upper()),entity_id=getattr(record,prefix.lower()+'_id'))
        f = SourceFields(raw,dataset_id,case_id,ref)
        f.identifier(prefix+'_ID',prefix.lower()+'.source_id')
        if isinstance(record,Bus):
            f.identifier('Bus_Station_ID','bus.station_source_ref',reference=True)
            if record.base_voltage_kv is not None and record.base_voltage_kv <= 0:
                f.issue('Bus_BaseKV','bus.base_voltage_kv',Code.SOURCE_VALUE_OUT_OF_RANGE,'source voltage must be positive')
        if isinstance(record,Station) and record.nominal_voltage_kv is not None and record.nominal_voltage_kv <= 0:
            f.issue('Station_Voltage_Level','station.nominal_voltage_kv',Code.SOURCE_VALUE_OUT_OF_RANGE,'source voltage must be positive')
        if isinstance(record,Feeder):
            f.identifier('Feeder_SourceBus','feeder.source_bus_source_ref',reference=True)
        outcome = replace(outcome, issues=(*outcome.issues,*f.issues))
    return outcome


def map_source_case(
    inventory: SourceCaseInventory,
    files: Iterable[RawSourceFile],
    *,
    dataset_id: CanonicalId,
    diagnostics: Iterable[IntakeDiagnostic] = (),
) -> SourceCaseResult:
    files = tuple(sorted(files,key=lambda f:f.source_file_type.value))
    grid_case = map_grid_case(inventory,dataset_id=dataset_id)
    case_id = grid_case.case_id
    if any(f.source_case_key != inventory.source_case_key for f in files):
        raise ValueError('raw file belongs to another case')
    for file in files:
        if inventory.member_for(file.source_file_type) != file.member_path:
            raise ValueError('raw file does not match inventory member')
        for row in file.records:
            if row.source_case_key != inventory.source_case_key or row.source_file_type is not file.source_file_type:
                raise ValueError('raw row does not match enclosing source file')
    if len({f.source_file_type for f in files}) != len(files):
        raise ValueError('duplicate raw file input')
    rows = tuple(r for f in files for r in f.records)
    if len({r.source_record_ref for r in rows}) != len(rows):
        raise ValueError('duplicate row locator')
    prefix_by_type = dict(PREFIXES)
    prefix_by_type.update({FT.STATION:'Station',FT.BUS:'Bus',FT.FEEDER:'Feeder'})
    classifications = classify_source_identities(
        SourceIdentityRecord(case_id=case_id,source_entity_type=SourceEntityType(r.source_file_type.value),
            source_id=SourceId(dict(r.fields)[prefix_by_type[r.source_file_type]+'_ID']),
            source_record_ref=r.source_record_ref,decoded_fields=r.fields)
        for r in rows if r.source_file_type is not FT.SIM_CONFIG and r.fields is not None
        and dict(r.fields)[prefix_by_type[r.source_file_type]+'_ID'] != '')
    by_locator = {c.record.source_record_ref:c for c in classifications}
    primary_rows, equipment_rows = [], []
    for raw in rows:
        kind = raw.source_file_type
        if kind is FT.SIM_CONFIG:
            continue
        classification = by_locator.get(raw.source_record_ref)
        status = classification.identity_status if classification else None
        if kind in PREFIXES:
            outcome = map_equipment(raw,dataset_id=dataset_id,case_id=case_id,identity_status=status)
            equipment_rows.append((raw,outcome))
            continue
        if raw.fields is None:
            outcome = _malformed_outcome(raw,dataset_id=dataset_id,case_id=case_id)
        elif classification is None:
            outcome = _missing_id_outcome(raw,dataset_id=dataset_id,case_id=case_id,
                field_path=kind.value.lower()+'.source_id',source_field=prefix_by_type[kind]+'_ID')
        elif kind is FT.BUS:
            outcome = map_bus(raw,classification,dataset_id=dataset_id)
        else:
            mapper = map_station if kind is FT.STATION else map_feeder
            outcome = mapper(raw,dataset_id=dataset_id,case_id=case_id,identity_status=status)
        outcome = _check_primary_fields(raw,outcome,dataset_id,case_id)
        primary_rows.append(CaseRowMappingOutcome(raw_record=raw,identity_status=status,mapping_outcome=outcome))
    primary = assemble_station_feeder_bus_case(grid_case,primary_rows,dataset_id=dataset_id)
    bundles, eq_issues, eq_unmapped, eq_conflicts, eq_refs = assemble_equipment(
        equipment_rows,dataset_id=dataset_id,case_id=case_id)
    # Recover primary conflict evidence from existing classifier output; no reclassification.
    from grid_case_generator.validation.reference_resolution import ReferenceIdentityConflict
    conflicts = defaultdict(list)
    for c in classifications:
        if c.record.source_entity_type.value in ('STATION','BUS','FEEDER') and c.identity_status is IdentityStatus.DUPLICATE_CONFLICT:
            conflicts[(c.record.source_entity_type,c.record.source_id)].append(c.record.source_record_ref)
    primary_conflicts = tuple(ReferenceIdentityConflict(case_id=case_id,source_entity_type=kind,
        source_id=source_id,source_record_refs=tuple(sorted(refs))) for (kind,source_id),refs in conflicts.items())
    index = build_nanjing_reference_candidate_index(
        (*primary.records,*(b.equipment for b in bundles)),identity_conflicts=(*primary_conflicts,*eq_conflicts))
    records = [primary.grid_case,*primary.records]
    issues = [*primary.issues,*eq_issues]
    resolutions = list(primary.resolutions)
    mixed = tuple(SourceEntityType(k) for k in ('BUS','SWITCH','STATION','TRANSFORMER','ACCESS_POINT'))
    for bundle in bundles:
        eq = bundle.equipment
        records.append(eq)
        for child in bundle.children:
            if isinstance(child,Terminal):
                request = ReferenceResolutionRequest(case_id=case_id,
                    owner_source_entity_type=Identifier(eq.equipment_type.value),owner_source_id=eq.source_id,
                    owner_source_record_ref=eq.source_record_ref,
                    reference_field_path=f'terminal[{child.terminal_no}].raw_connected_ref',
                    raw_reference_value=child.raw_connected_ref or '',
                    allowed_candidate_source_entity_types=mixed if eq.equipment_type.value in ('LINE','SWITCH') else ())
                result = resolve_source_reference(index,request)
                resolutions.append(result)
                child = replace(child,resolved_source_ref=result.resolved_ref,source_ref_status=result.resolution_status)
                issues.extend(reference_issues_for_result(result,dataset_id=dataset_id,
                    target_ref=EntityRef(entity_type=Identifier('TERMINAL'),entity_id=child.terminal_id)))
            records.append(child)
    sim_records,sim_issues,sim_unmapped,provenance,sim_resolutions,sim_refs = map_sim_config(
        (r for r in rows if r.source_file_type is FT.SIM_CONFIG),dataset_id=dataset_id,case_id=case_id,index=index)
    records.extend(sim_records)
    issues.extend(sim_issues)
    resolutions.extend(sim_resolutions)
    all_diagnostics = tuple(diagnostics)+tuple(d for f in files for d in f.diagnostics)
    issues.extend(_diagnostic_issue(d,dataset_id,case_id) for d in all_diagnostics)
    raw_by_locator = {r.source_record_ref:r for r in rows}
    issues_by_id = {}
    for issue in issues:
        previous = issues_by_id.setdefault(issue.issue_id,issue)
        if previous != issue:
            raise ValueError('conflicting quality issue identity')
    issues = tuple(sorted(issues_by_id.values(),key=_issue_sort_key))
    resolutions = tuple(sorted(resolutions,key=lambda r:(r.request.owner_source_entity_type,r.request.owner_source_record_ref,r.request.reference_field_path)))
    unmapped = (*primary.unmapped_records,*eq_unmapped,*sim_unmapped)
    rejected = {r.source_record_ref for r in unmapped}
    refs = {a.raw_record.source_record_ref:a.canonical_ref for a in primary.accounting}
    refs.update(eq_refs)
    refs.update(sim_refs)
    issue_ids = defaultdict(list)
    for issue in issues:
        issue_ids[issue.source_record_ref].append(issue.issue_id)
    resolution_positions = defaultdict(list)
    for n,result in enumerate(resolutions):
        resolution_positions[result.request.owner_source_record_ref].append(n)
    representative_locator = {a.canonical_ref:a.raw_record.source_record_ref for a in reversed(primary.accounting) if a.canonical_ref}
    representative_locator.update({EntityRef(entity_type=Identifier('EQUIPMENT'),entity_id=b.equipment.equipment_id):b.equipment.source_record_ref for b in bundles})
    accounting = []
    for raw in sorted(rows,key=lambda r:(r.source_file_type.value,r.source_record_ref)):
        locator = raw.source_record_ref
        ref = refs.get(locator)
        classification = by_locator.get(locator)
        status = classification.identity_status if classification else None
        positions = tuple(resolution_positions.get(representative_locator.get(ref,locator),()))
        if locator in rejected:
            category = RowTerminalCategory.REJECTED
        elif status is not None and status is not IdentityStatus.UNIQUE:
            category = RowTerminalCategory.DUPLICATE
        elif any(resolutions[n].resolution_status in (SourceReferenceStatus.UNRESOLVED,SourceReferenceStatus.AMBIGUOUS) for n in positions):
            category = RowTerminalCategory.UNRESOLVED
        else:
            category = RowTerminalCategory.MAPPED
        accounting.append(RowAccountability(raw_record=raw,terminal_category=category,identity_status=status,
            canonical_ref=ref,issue_ids=tuple(issue_ids[locator]),resolution_indexes=positions))
    supplied = {f.source_file_type for f in files}
    failed_read = any(d.code.value == 'SOURCE_FILE_READ_FAILED' or
        (d.code.value == 'SOURCE_ROW_MALFORMED' and d.source_record_ref not in raw_by_locator) for d in all_diagnostics)
    missing_processing = any(member is not None and kind not in supplied for kind,member in inventory.members)
    status = ImportStatus.INCOMPLETE if failed_read or missing_processing else ImportStatus.COMPLETE
    from grid_case_generator.validation.source_import import canonical_case_errors
    errors = canonical_case_errors(tuple(records),issues,provenance)
    return SourceCaseResult(primary.grid_case,tuple(sorted(records,key=lambda r:(type(r).__name__,canonical_json_bytes(r)))),
        issues,provenance,tuple(sorted(unmapped,key=lambda r:r.source_record_ref)),resolutions,tuple(accounting),files,
        all_diagnostics,status,not errors)


def import_archive(archive_path: str | Path, output: str | Path, *, imported_at: str) -> dict:
    from .archive import inventory_archive, iter_raw_cases
    from grid_case_generator.io.source_artifacts import SourceArtifactWriter

    from datetime import datetime
    timestamp = datetime.fromisoformat(imported_at)
    if timestamp.utcoffset() is None:
        raise ValueError('imported_at requires an explicit timezone offset')
    writer = SourceArtifactWriter(output,archive_path)
    try:
        inventory = inventory_archive(archive_path)
    except Exception as error:
        writer.write('failure.json',{'import_status':'FAILED','error_type':type(error).__name__,'message':str(error)})
        raise
    dataset = map_dataset(inventory,name='Nanjing source',imported_at=imported_at,import_status=ImportStatus.INCOMPLETE)
    writer.write('inventory.json',inventory)
    summaries = []
    diagnostics_by_case = defaultdict(list)
    for diagnostic in inventory.diagnostics:
        diagnostics_by_case[diagnostic.source_case_key].append(diagnostic)
    try:
        for case,files in iter_raw_cases(archive_path,inventory):
            case_id = IDs.case_id(dataset.dataset_id,case.source_case_key)
            try:
                result = map_source_case(case,files,dataset_id=dataset.dataset_id,
                    diagnostics=diagnostics_by_case[case.source_case_key])
                summary = writer.write_case(result)
            except Exception as error:
                summary = {'case_id':case_id,'source_case_key':case.source_case_key,
                    'import_status':'INCOMPLETE','canonical_valid':False,
                    'error_type':type(error).__name__,'message':str(error)}
                writer.write(f'cases/{case_id}/failed_input.json',files)
                writer.write(f'cases/{case_id}/case_report.json',summary)
            summaries.append(summary)
    except Exception as error:
        done = {s['case_id'] for s in summaries}
        for case in inventory.cases:
            case_id = IDs.case_id(dataset.dataset_id,case.source_case_key)
            if case_id not in done:
                summary = {'case_id':case_id,'source_case_key':case.source_case_key,
                    'import_status':'INCOMPLETE','canonical_valid':False,
                    'error_type':type(error).__name__,'message':str(error)}
                writer.write(f'cases/{case_id}/case_report.json',summary)
                summaries.append(summary)
    status = ImportStatus.COMPLETE if all(s['import_status']=='COMPLETE' for s in summaries) else ImportStatus.INCOMPLETE
    dataset = replace(dataset,import_status=status)
    report = {'import_status':status.value,'case_count':len(summaries),'cases':summaries,
        'canonical_valid':all(s['canonical_valid'] for s in summaries)}
    writer.write('dataset.json',dataset)
    writer.write('import_report.json',report)
    writer.finish(dataset)
    return report
