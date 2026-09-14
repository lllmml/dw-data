"""Source snapshots and source SimConfig aggregation (not simulation settings)."""
from collections import defaultdict
from datetime import datetime

from grid_case_generator.models.identifiers import SourceImportIdFactory as IDs
from grid_case_generator.models.records import OperationalSeries, OperationalValue, SimulationProfile, FieldProvenance
from grid_case_generator.models.types import (Identifier, EntityRef, RecordOrigin, DataQuality, SeriesKind, ValueType)
from grid_case_generator.models.quality import QualityIssueCode as Code
from grid_case_generator.validation.reference_resolution import ReferenceResolutionRequest, resolve_source_reference
from .field_mapping import SourceFields
from .mapping import _source_trace, _malformed_outcome, _missing_id_outcome
from .reference_integration import _canonical_source_reference
from .reference_issue_policy import reference_issues_for_result
from grid_case_generator.validation.identity import SourceEntityType


def map_switch_measurements(raw, *, dataset_id, case_id, target_ref):
    f = SourceFields(raw,dataset_id,case_id,target_ref)
    records = []
    timestamp = f.text('Switch_Meas_Timestamp')
    try:
        known_time = timestamp is not None and datetime.fromisoformat(timestamp).utcoffset() is not None
    except ValueError:
        known_time = False
    quality = DataQuality.VALID if known_time else DataQuality.TIME_UNKNOWN
    for field, metric, unit in (('Switch_Meas_I_A','current','A'),
            ('Switch_Meas_P_kW','active_power','kW'), ('Switch_Meas_Q_kVAR','reactive_power','kvar')):
        value = f.decimal(field, f'operational_series.{metric}')
        if value is None:
            continue
        series_id = IDs.operational_series_id(case_id,target_ref,raw.source_record_ref,field)
        records.append(OperationalSeries(**_source_trace(raw.source_record_ref), series_id=series_id,
            scenario_id=None,target_ref=target_ref,metric=metric,unit=unit,phase=None,
            series_kind=SeriesKind.SNAPSHOT,value_type=ValueType.DECIMAL,interval_seconds=None,quality=quality))
        records.append(OperationalValue(**_source_trace(raw.source_record_ref),series_id=series_id,
            timestamp=timestamp if known_time else None,offset_seconds=None,sequence_no=0,decimal_value=value,boolean_value=None,
            category_value=None,quality=quality))
        if not known_time:
            f.issue(field,f'operational_series.{metric}',Code.SOURCE_MEASUREMENT_TIME_UNKNOWN,
                'source snapshot time is missing or unconfirmed; raw timestamp retained in row accounting')
    return tuple(records), tuple(f.issues)


CONFIG_FIELDS = {
    'SimulationMode': ('mode','text'), 'Algorithm': ('solver','text'),
    'BaseFrequency': ('frequency_hz','positive'), 'BaseVoltage_kV': ('source_voltage_kv','positive'),
    'SourceBus': ('source_bus_source_ref','reference'),
    'OutputVoltageBus': ('output_voltage_bus_source_ref','reference'),
    'MaxIterations': ('max_iterations','integer'), 'Tolerance': ('tolerance','positive'),
    'MVAsc3': ('mva_sc3','positive'), 'MVAsc1': ('mva_sc1','positive'), 'UnitSystem': ('unit_system','text'),
}


def map_sim_config(rows, *, dataset_id, case_id, index):
    rows = tuple(sorted(rows,key=lambda r:r.source_record_ref))
    groups = defaultdict(list)
    issues, unmapped, provenance, resolutions = [], [], [], []
    profile_id = IDs.simulation_profile_id(case_id)
    ref = EntityRef(entity_type=Identifier('SIMULATION_PROFILE'),entity_id=profile_id)
    for raw in rows:
        if raw.fields is None:
            outcome = _malformed_outcome(raw,dataset_id=dataset_id,case_id=case_id)
        elif not dict(raw.fields)['Config_Key']:
            outcome = _missing_id_outcome(raw,dataset_id=dataset_id,case_id=case_id,
                field_path='simulation_profile',source_field='Config_Key')
        else:
            groups[dict(raw.fields)['Config_Key']].append(raw)
            continue
        issues.extend(outcome.issues)
        unmapped.append(outcome.unmapped_record)
    if not groups:
        return (),tuple(issues),tuple(unmapped),(),(),{}
    values = {field:None for field,_ in CONFIG_FIELDS.values()}
    extensions = {}
    refs_by_row = {}
    for key, group in sorted(groups.items()):
        field, conversion = CONFIG_FIELDS.get(key,(f'extensions.nanjing.{key}','text'))
        path = f'simulation_profile.{field}'
        distinct = {dict(r.fields)['Config_Value'] for r in group}
        for raw in group:
            refs_by_row[raw.source_record_ref] = ref
        if len(distinct) != 1:
            for raw in group:
                f = SourceFields(raw,dataset_id,case_id,ref)
                f.issue('Config_Key',path,Code.SOURCE_VALUE_PARSE_FAILED,'conflicting source Config_Key values; no value selected')
                issues.extend(f.issues)
            continue
        raw = group[0]
        f = SourceFields(raw,dataset_id,case_id,ref)
        if conversion == 'reference':
            f.identifier('Config_Value',path,reference=True)
            request = ReferenceResolutionRequest(case_id=case_id,owner_source_entity_type=Identifier('SIM_CONFIG'),
                owner_source_id=None,owner_source_record_ref=raw.source_record_ref,
                reference_field_path=path,raw_reference_value=dict(raw.fields)['Config_Value'],
                allowed_candidate_source_entity_types=(SourceEntityType.BUS,))
            result = resolve_source_reference(index,request)
            value = _canonical_source_reference(result)
            resolutions.append(result)
            issues.extend(reference_issues_for_result(result,dataset_id=dataset_id,target_ref=ref))
        elif conversion == 'positive':
            value = f.decimal('Config_Value',path,positive=True)
        elif conversion == 'integer':
            value = f.integer('Config_Value',path)
        else:
            value = f.text('Config_Value')
        issues.extend(f.issues)
        if key in CONFIG_FIELDS:
            values[field] = value
        else:
            extensions[f'nanjing.{key}'] = dict(raw.fields)['Config_Value']
        trace = _source_trace(raw.source_record_ref)
        provenance.append(FieldProvenance(**trace,
            provenance_id=IDs.field_provenance_id(ref,path,RecordOrigin.SOURCE,raw.source_record_ref,
                'Config_Value',trace['source_mapping_id'],trace['source_mapping_version']),
            case_id=case_id,target_ref=ref,field_path=path,origin=RecordOrigin.SOURCE,source_field='Config_Value',
            rule_id=None,rule_version=None,config_ref=None,random_seed=None,assumption=None,changed_by=None))
    profile = SimulationProfile(**_source_trace(None),simulation_profile_id=profile_id,
        case_id=case_id,scenario_id=None,extensions=extensions or None,**values)
    return (profile,),tuple(issues),tuple(unmapped),tuple(provenance),tuple(resolutions),refs_by_row
