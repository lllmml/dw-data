"""Canonical source-case checks, independent of import completeness/readiness."""
from dataclasses import fields
from decimal import Decimal

from grid_case_generator.models.records import TraceableRecord, Terminal, OperationalValue, TransformerWinding
from grid_case_generator.models.types import EntityRef, SourceReference

ID_FIELDS = {
    'GridCase':'case_id','Station':'station_id','Bus':'bus_id','Feeder':'feeder_id',
    'Equipment':'equipment_id','Terminal':'terminal_id','TransformerWinding':'winding_id',
    'SimulationProfile':'simulation_profile_id','OperationalSeries':'series_id',
}
ENTITY_TYPES = {'GridCase':'GRID_CASE','TransformerWinding':'TRANSFORMER_WINDING',
    'SimulationProfile':'SIMULATION_PROFILE','OperationalSeries':'OPERATIONAL_SERIES'}


def canonical_case_errors(records, issues=(), provenance=()):
    errors = []
    targets = set()
    equipment = set()
    terminals = set()
    series = set()
    for record in records:
        kind = type(record).__name__
        id_field = ID_FIELDS.get(kind)
        if id_field:
            key = (ENTITY_TYPES.get(kind,kind.upper()),getattr(record,id_field))
            if key in targets:
                errors.append(f'duplicate canonical identity: {key}')
            targets.add(key)
            if kind == 'Equipment': equipment.add(record.equipment_id)
            if kind == 'Terminal': terminals.add(record.terminal_id)
            if kind == 'OperationalSeries': series.add(record.series_id)
        if kind == 'Station' and (record.longitude is not None or record.latitude is not None) and not record.coordinate_crs:
            errors.append('Station: coordinates have no confirmed CRS')
        if kind in ('Station','Bus','Feeder','Equipment') and not record.source_id:
            errors.append(f'{kind}: missing source identity')
        if record.record_origin.value == 'SOURCE' and kind not in ('GridCase','SimulationProfile') and not record.source_record_ref:
            errors.append(f'{kind}: missing source locator')
    case_ids = {r.case_id for r in records if type(r).__name__ == 'GridCase'}
    for record in records:
        kind = type(record).__name__
        if hasattr(record,'case_id') and record.case_id not in case_ids:
            errors.append(f'{kind}: record belongs to another case')
        if hasattr(record,'equipment_id') and kind != 'Equipment' and record.equipment_id not in equipment:
            errors.append(f'{kind}: missing Equipment')
        if isinstance(record,TransformerWinding) and record.terminal_id not in terminals:
            errors.append('missing winding Terminal')
        if isinstance(record,OperationalValue) and record.series_id not in series:
            errors.append('missing operational series')
        if isinstance(record,Terminal) and (record.connectivity_node_ref is not None or record.connectivity_status.value != 'NOT_ASSESSED'):
            errors.append('source connectivity was assessed during import')
        for field in fields(record):
            value = getattr(record,field.name)
            ref = value.resolved_source_ref if isinstance(value,SourceReference) else value
            if isinstance(ref,EntityRef) and (ref.entity_type,ref.entity_id) not in targets:
                errors.append(f'{kind}.{field.name}: invalid EntityRef')
            if isinstance(value,Decimal) and not value.is_finite():
                errors.append(f'{kind}.{field.name}: non-finite value')
    provenance_targets = {(p.target_ref.entity_type,p.target_ref.entity_id,p.field_path) for p in provenance}
    for record in records:
        if type(record).__name__ != 'SimulationProfile':
            continue
        for field in fields(record):
            value = getattr(record,field.name)
            if field.name in ('record_origin','source_record_ref','source_mapping_id',
                    'source_mapping_version','simulation_profile_id','case_id','scenario_id') or value is None:
                continue
            paths = (tuple(f'simulation_profile.extensions.{key}' for key in value)
                if field.name == 'extensions' else (f'simulation_profile.{field.name}',))
            for path in paths:
                if ('SIMULATION_PROFILE',record.simulation_profile_id,path) not in provenance_targets:
                    errors.append('SimulationProfile: missing field provenance: '+path)
    for item in provenance:
        if (item.target_ref.entity_type,item.target_ref.entity_id) not in targets:
            errors.append('FieldProvenance: missing target')
        if item.origin.value == 'SOURCE' and (not item.source_record_ref or not item.source_field):
            errors.append('FieldProvenance: missing source locator/field')
    for issue in issues:
        if issue.code.value == 'SOURCE_VALUE_OUT_OF_RANGE' and issue.target_ref is None:
            continue
        if issue.code.value in ('SOURCE_VALUE_OUT_OF_RANGE','CANONICAL_REQUIRED_FIELD_MISSING',
                'CANONICAL_UNIQUE_CONSTRAINT_VIOLATION','CANONICAL_REFERENCE_INTEGRITY_ERROR'):
            errors.append(issue.code.value+':'+(issue.field_path or ''))
    return tuple(errors)
