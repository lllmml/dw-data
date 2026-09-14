"""Source Equipment and child-record mapping, independent of topology."""
from dataclasses import dataclass

from grid_case_generator.models.identifiers import SourceImportIdFactory as IDs
from grid_case_generator.models.records import (
    Equipment, Terminal, Line, SwitchingDevice, Transformer, TransformerWinding,
    AccessPoint, Load, DER, TraceableRecord,
)
from grid_case_generator.models.types import (
    EntityRef, Identifier, SourceId, EquipmentType, SwitchKind, ConnectivityStatus,
    SourceReferenceStatus, PowerFactorMode,
)
from grid_case_generator.validation.quality import ImportErrorCategory
from .mapping import RecordMappingOutcome, _source_trace, _validated_fields, _malformed_outcome, _missing_id_outcome
from .field_mapping import SourceFields
from .schema import SourceFileType

PREFIXES = {
    SourceFileType.SWITCH: 'Switch', SourceFileType.DISCONNECTOR: 'Disconnector',
    SourceFileType.EARTHING_SWITCH: 'EarthingSwitch', SourceFileType.ACCESS_POINT: 'AccessPoint',
    SourceFileType.LINE: 'Line', SourceFileType.TRANSFORMER: 'Transformer',
    SourceFileType.LOAD: 'Load', SourceFileType.DER: 'DER',
}


@dataclass(frozen=True, slots=True)
class EquipmentBundle:
    equipment: Equipment
    children: tuple[TraceableRecord, ...]


def map_equipment(raw, *, dataset_id, case_id, identity_status):
    prefix = PREFIXES[raw.source_file_type]
    values = _validated_fields(raw, expected_file_type=raw.source_file_type)
    if values is None:
        return _malformed_outcome(raw, dataset_id=dataset_id, case_id=case_id)
    if not values[f'{prefix}_ID']:
        return _missing_id_outcome(raw, dataset_id=dataset_id, case_id=case_id,
            field_path='equipment.source_id', source_field=f'{prefix}_ID')
    kind = EquipmentType(raw.source_file_type.value)
    equipment_id = IDs.equipment_id(case_id, kind, SourceId(values[f'{prefix}_ID']), raw.source_record_ref)
    ref = EntityRef(entity_type=Identifier('EQUIPMENT'), entity_id=equipment_id)
    f = SourceFields(raw, dataset_id, case_id, ref)
    trace = _source_trace(raw.source_record_ref)
    equipment = Equipment(**trace, equipment_id=equipment_id, case_id=case_id,
        source_id=SourceId(values[f'{prefix}_ID']), equipment_type=kind, identity_status=identity_status,
        name=None, phases=f.phase(f'{prefix}_Phase', 'equipment.phases'), in_service=None)
    f.identifier(f'{prefix}_ID', 'equipment.source_id')
    endpoint_names = (f'{prefix}_FromBus', f'{prefix}_ToBus') if kind in (
        EquipmentType.LINE, EquipmentType.SWITCH, EquipmentType.DISCONNECTOR, EquipmentType.TRANSFORMER
    ) else (f'{prefix}_Bus',)
    terminals = []
    for n, name in enumerate(endpoint_names, 1):
        value = f.text(name)
        f.identifier(name, f'terminal[{n}].raw_connected_ref', reference=True)
        terminals.append(Terminal(**trace, terminal_id=IDs.terminal_id(equipment_id, n), case_id=case_id,
            equipment_id=equipment_id, terminal_no=n, raw_connected_ref=SourceId(value) if value else None,
            resolved_source_ref=None, source_ref_status=SourceReferenceStatus.UNRESOLVED if value else SourceReferenceStatus.MISSING,
            connectivity_node_ref=None, connectivity_status=ConnectivityStatus.NOT_ASSESSED, phases=None))
    base = dict(trace, equipment_id=equipment_id)
    children = list(terminals)
    if kind is EquipmentType.LINE:
        children.append(Line(**base, line_type=f.text('Line_Type'), model=f.text('Line_Model'),
            length_km=f.decimal('Line_Length_km','line.length_km', positive=True),
            r1_ohm_per_km=f.decimal('Line_R1_ohm_per_km','line.r1_ohm_per_km'),
            x1_ohm_per_km=f.decimal('Line_X1_ohm_per_km','line.x1_ohm_per_km'),
            r0_ohm_per_km=None, x0_ohm_per_km=None, c1_nf_per_km=None, c0_nf_per_km=None,
            rated_current_a=None, number_of_circuits=f.integer('Line_NumCircuits','line.number_of_circuits'), parameter_set_ref=None))
    elif kind in (EquipmentType.SWITCH, EquipmentType.DISCONNECTOR, EquipmentType.EARTHING_SWITCH):
        children.append(SwitchingDevice(**base, switch_kind=SwitchKind(kind.value),
            normal_state=f.state(f'{prefix}_NormalState','switching_device.normal_state'),
            observed_state=f.state(f'{prefix}_State','switching_device.observed_state'),
            is_tie=f.boolean(f'{prefix}_IsTie','switching_device.is_tie'),
            rated_current_a=f.decimal(f'{prefix}_RatedCurrent_A','switching_device.rated_current_a', positive=True),
            measurement_capable=f.boolean(f'{prefix}_HasMeasurement','switching_device.measurement_capable')))
        if kind is EquipmentType.SWITCH:
            from .operational_mapping import map_switch_measurements
            records, issues = map_switch_measurements(raw, dataset_id=dataset_id, case_id=case_id, target_ref=ref)
            children.extend(records)
            f.issues.extend(issues)
    elif kind is EquipmentType.TRANSFORMER:
        children.append(Transformer(**base,
            rated_capacity_kva=f.decimal('Transformer_RatedCapacity_kVA','transformer.rated_capacity_kva',positive=True),
            r_pct=f.decimal('Transformer_R_pct','transformer.r_pct'), x_pct=f.decimal('Transformer_X_pct','transformer.x_pct'),
            number_of_taps=f.integer('Transformer_NumTaps','transformer.number_of_taps'),
            tap_min_pu=None, tap_max_pu=None, tap_range_raw=f.text('Transformer_TapRange')))
        for n, voltage, connection in ((1,'HighVoltage','ConnHV'),(2,'LowVoltage','ConnLV')):
            children.append(TransformerWinding(**base, winding_id=IDs.winding_id(equipment_id,n), winding_no=n,
                terminal_id=terminals[n-1].terminal_id,
                rated_voltage_kv=f.decimal(f'Transformer_{voltage}_kV',f'transformer_winding[{n}].rated_voltage_kv',positive=True),
                connection=f.text(f'Transformer_{connection}'), rated_capacity_kva=None))
    elif kind is EquipmentType.ACCESS_POINT:
        children.append(AccessPoint(**base, user_type=f.text('AccessPoint_UserType'),
            contract_capacity_kva=f.decimal('AccessPoint_ContractCapacity_kVA','access_point.contract_capacity_kva', nonnegative=True)))
    elif kind is EquipmentType.LOAD:
        children.append(Load(**base, active_power_kw=f.decimal('Load_P_kW','load.active_power_kw'),
            reactive_power_kvar=f.decimal('Load_Q_kVAR','load.reactive_power_kvar'),
            power_factor=f.decimal('Load_PF','load.power_factor',pf=True), power_factor_mode=PowerFactorMode.UNKNOWN,
            connection=None, load_model=None, nominal_voltage_kv=None))
    else:
        children.append(DER(**base, der_type=f.text('DER_Type'),
            rated_capacity_kva=f.decimal('DER_RatedCapacity_kVA','der.rated_capacity_kva',nonnegative=True),
            rated_power_kw=f.decimal('DER_RatedPower_kW','der.rated_power_kw',nonnegative=True),
            power_factor=f.decimal('DER_PF','der.power_factor',pf=True), connection=f.text('DER_ConnType'),
            control_mode=f.text('DER_ControlMode'), nominal_voltage_kv=None))
    return RecordMappingOutcome(record=EquipmentBundle(equipment,tuple(children)), issues=tuple(f.issues),
        unmapped_record=None, error_category=ImportErrorCategory.FIELD_RECOVERABLE if f.issues else None)
