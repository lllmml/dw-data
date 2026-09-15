"""Frozen Nanjing E2 interpretation from persisted source records and evidence."""
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
import re
import tomllib

from grid_case_generator.models import records as source
from grid_case_generator.models.types import EntityRef, Identifier, CanonicalId, IdentityStatus, SourceReferenceStatus
from grid_case_generator.models.topology import (
    DerivedIdFactory, DerivedRole, ElectricalNode, ElectricalBranch, ElectricalTopology,
    TopologyProjectionRecord, TopologyCaseResult, TopologyCoverage, TopologyConfig,
    ProjectionStatus as Status, ExclusionReason as Reason, RuleId as Rule,
    VoltageSource, RULE_VERSION,
)
from grid_case_generator.io.canonical_json import canonical_json_bytes
from grid_case_generator.validation.topology import reachable_nodes, validate_topology


NAME_VOLTAGES = {'10': Decimal('10.5'), '20': Decimal('20.0')}


def load_topology_config(path):
    with open(path, 'rb') as stream:
        values = tomllib.load(stream, parse_float=Decimal)
    if set(values) != {'fallback_nominal_voltage_kv'}:
        raise ValueError('expected only fallback_nominal_voltage_kv')
    value = values['fallback_nominal_voltage_kv']
    if type(value) not in (int, Decimal):
        raise TypeError('voltage must be numeric')
    return TopologyConfig(Decimal(value))


def entity_ref(record):
    if isinstance(record, source.GridCase):
        kind, value = 'GRID_CASE', record.case_id
    elif isinstance(record, source.Feeder):
        kind, value = 'FEEDER', record.feeder_id
    elif isinstance(record, source.Bus):
        kind, value = 'BUS', record.bus_id
    elif isinstance(record, source.Station):
        kind, value = 'STATION', record.station_id
    elif isinstance(record, source.Terminal):
        kind, value = 'TERMINAL', record.terminal_id
    elif isinstance(record, source.SimulationProfile):
        kind, value = 'SIMULATION_PROFILE', record.simulation_profile_id
    else:
        kind, value = 'EQUIPMENT', record.equipment_id
    return EntityRef(entity_type=Identifier(kind), entity_id=CanonicalId(value))


def _voltage_compatible(value, voltage):
    return value == voltage or (voltage == NAME_VOLTAGES['10'] and value == Decimal('10'))


def interpret_topology(details, config):
    records = details.records
    case, = (r for r in records if isinstance(r, source.GridCase))
    case_ref = entity_ref(case)
    equipment = {r.equipment_id:r for r in records if isinstance(r, source.Equipment)}
    buses = {r.bus_id:r for r in records if isinstance(r, source.Bus)}
    stations = {r.station_id:r for r in records if isinstance(r, source.Station)}
    feeders = sorted((r for r in records if isinstance(r, source.Feeder)), key=lambda r:r.feeder_id)
    terminals = defaultdict(list)
    for record in records:
        if isinstance(record, source.Terminal):
            terminals[record.equipment_id].append(record)
    terminal_by_locator = defaultdict(list)
    for group in terminals.values():
        for terminal in group:
            terminal_by_locator[(terminal.source_record_ref, terminal.terminal_no)].append(terminal)
    switches = {r.equipment_id:r for r in records if isinstance(r, source.SwitchingDevice)}
    for group in terminals.values():
        group.sort(key=lambda r:(r.terminal_no, r.terminal_id))
    rows = sorted((a.raw_record for a in details.accounting), key=lambda r:r.source_record_ref)
    by_entity = defaultdict(set)
    by_source_identity = defaultdict(list)
    for account in details.accounting:
        row = account.raw_record
        if account.canonical_ref:
            by_entity[account.canonical_ref.entity_id].add(str(row.source_record_ref))
        fields = dict(row.fields or ())
        id_fields = [k for k in fields if k.endswith('_ID') and k != 'Bus_Station_ID']
        if id_fields:
            by_source_identity[(row.source_file_type.value, fields[id_fields[0]])].append(row)
    rows_by_raw_id = defaultdict(list)
    for (_, raw_id), group in by_source_identity.items():
        rows_by_raw_id[raw_id].extend(group)
    for record in records:
        if isinstance(record, (source.GridCase, source.Feeder, source.Bus, source.Station,
                               source.Equipment, source.Terminal, source.SimulationProfile)):
            if record.source_record_ref:
                by_entity[entity_ref(record).entity_id].add(record.source_record_ref)
    # Full persisted rows, including rejected and duplicate Line evidence.
    line_rows = [r for r in rows if r.source_file_type.value == 'LINE']
    incident = defaultdict(list)
    malformed_lines = [r for r in line_rows if r.fields is None]
    line_identity_counts = Counter(dict(r.fields or ()).get('Line_ID') for r in line_rows)
    for row in line_rows:
        fields = dict(row.fields or ())
        for number, key in ((1,'Line_FromBus'),(2,'Line_ToBus')):
            if fields.get(key):
                incident[fields[key]].append((row, number, fields.get('Line_ID')))
    projections, nodes, branches = [], {}, {}

    def evidence(*items, extra=()):
        refs = set(extra)
        for item in items:
            if item is not None:
                refs.update(by_entity[entity_ref(item).entity_id])
        return tuple(sorted(refs))

    def project(owner, rule, targets=(), reason=None, terminal=None, refs=(), voltage=None, voltage_source=None):
        status = Status.PROJECTED
        if reason:
            status = Status.EXCLUDED
            if reason in (Reason.AMBIGUOUS_REFERENCE, Reason.AMBIGUOUS_FEEDER, Reason.IDENTITY_NOT_UNIQUE):
                status = Status.AMBIGUOUS
            elif reason in (Reason.MISSING_REFERENCE, Reason.UNRESOLVED_REFERENCE, Reason.MISSING_FEEDER,
                            Reason.INVALID_FEEDER_BUS, Reason.NO_FEEDER_HEAD):
                status = Status.UNRESOLVED
            elif reason in (Reason.ACCESS_POINT_UNSUPPORTED, Reason.CONNECTION_UNSUPPORTED):
                status = Status.UNSUPPORTED
        voltage_refs = anchor_refs if (voltage is not None or rule in (Rule.BUS, Rule.VOLTAGE)
            or reason is Reason.NAME_VOLTAGE_CONFLICT) else ()
        projection = TopologyProjectionRecord(case_ref, entity_ref(owner),
            entity_ref(terminal) if terminal else None, evidence(owner, terminal, extra=(*refs, *voltage_refs)),
            rule, RULE_VERSION, status, tuple(targets) if not reason else (), reason, voltage, voltage_source)
        projections.append(projection)
        return projection

    def node(owner, role, voltage, voltage_source):
        identifier = DerivedIdFactory.make(role, case.case_id, entity_ref(owner).entity_id)
        nodes[identifier] = ElectricalNode(identifier, role, entity_ref(owner), voltage, voltage_source)
        return identifier

    def branch(owner, role, first, second, conducting):
        identifier = DerivedIdFactory.make(role, case.case_id, entity_ref(owner).entity_id)
        branches[identifier] = ElectricalBranch(identifier, role, entity_ref(owner), first, second, conducting)
        return identifier

    def exact_bus(ref):
        if ref and ref.resolution_status is SourceReferenceStatus.EXACT and ref.resolved_source_ref.entity_type == 'BUS':
            bus = buses.get(ref.resolved_source_ref.entity_id)
            if bus and bus.identity_status is IdentityStatus.UNIQUE:
                return bus
        return None

    names = [PurePosixPath(case.source_case_key or '').name] + [f.name or '' for f in feeders]
    matches = set(re.findall(r'(?<![\d.])(10|20)\s*kv(?![a-z])', ' '.join(names), flags=re.IGNORECASE))
    voltage = NAME_VOLTAGES[next(iter(matches))] if len(matches) == 1 else config.fallback_nominal_voltage_kv
    voltage_source = VoltageSource.NAME_INFERENCE if len(matches) == 1 else VoltageSource.DEFAULT
    anchor_reason = None
    upstream = None
    feeder_rows = [r for r in rows if r.source_file_type.value == 'FEEDER']
    if not feeders:
        anchor_reason = Reason.MISSING_FEEDER if not feeder_rows else Reason.AMBIGUOUS_FEEDER
    elif len(feeders) != 1 or len(feeder_rows) != 1 or feeders[0].identity_status is not IdentityStatus.UNIQUE:
        anchor_reason = Reason.AMBIGUOUS_FEEDER
    else:
        upstream = exact_bus(feeders[0].source_bus_source_ref)
        if upstream is None:
            anchor_reason = Reason.INVALID_FEEDER_BUS
    anchor_refs = evidence(case, *feeders, upstream, extra=(str(r.source_record_ref) for r in feeder_rows))
    head = None
    if anchor_reason is None and len(matches) > 1:
        anchor_reason = Reason.NAME_VOLTAGE_CONFLICT
    if anchor_reason is None:
        head = node(feeders[0], DerivedRole.FEEDER_HEAD, voltage, voltage_source)
    project(feeders[0] if len(feeders)==1 else case, Rule.FEEDER_HEAD,
            (head,) if head else (), anchor_reason, refs=anchor_refs,
            voltage=voltage if head else None, voltage_source=voltage_source if head else None)

    for profile in (r for r in records if isinstance(r, source.SimulationProfile)):
        value = profile.source_voltage_kv
        if value is not None and (not value.is_finite() or value <= 0 or not _voltage_compatible(value, voltage)):
            project(profile, Rule.VOLTAGE, reason=Reason.SIM_CONFIG_VOLTAGE_CONFLICT, refs=anchor_refs)

    # Conflicting/rejected identities have no source Equipment EntityRef. Retain
    # their evidence against the existing GridCase, never invent source identities.
    for raw in rows:
        if raw.fields is None and raw.source_file_type.value in ('SWITCH','TRANSFORMER','ACCESS_POINT','LINE'):
            rule = {'SWITCH':Rule.SWITCH,'TRANSFORMER':Rule.TRANSFORMER,'ACCESS_POINT':Rule.ACCESS_POINT,'LINE':Rule.LINE}[raw.source_file_type.value]
            project(case, rule, reason=Reason.IDENTITY_NOT_UNIQUE, refs=(str(raw.source_record_ref),))
    for kind, rule in (('SWITCH', Rule.SWITCH), ('TRANSFORMER', Rule.TRANSFORMER), ('ACCESS_POINT', Rule.ACCESS_POINT), ('LINE', Rule.LINE)):
        published_ids = {e.source_id for e in equipment.values() if e.equipment_type.value == kind}
        for (raw_kind, raw_id), raw_group in sorted(by_source_identity.items()):
            if raw_kind == kind and raw_id not in published_ids:
                project(case, rule, reason=Reason.IDENTITY_NOT_UNIQUE,
                    refs=tuple(str(r.source_record_ref) for r in raw_group))

    device_results = {}
    state_counts = Counter()
    for device in sorted(equipment.values(), key=lambda r:r.equipment_id):
        kind = device.equipment_type.value
        if kind not in ('SWITCH','TRANSFORMER','ACCESS_POINT'):
            continue
        if kind == 'ACCESS_POINT':
            project(device, Rule.ACCESS_POINT, reason=Reason.ACCESS_POINT_UNSUPPORTED)
            continue
        rule = Rule.SWITCH if kind == 'SWITCH' else Rule.TRANSFORMER
        raw_incident = incident.get(device.source_id, [])
        own_rows = by_source_identity.get((kind, device.source_id), [])
        related_refs = {str(r.source_record_ref) for r, _, _ in raw_incident}
        related_refs.update(str(r.source_record_ref) for r in own_rows)
        related_refs.update(str(r.source_record_ref) for r in malformed_lines)
        refs = evidence(device, extra=related_refs)
        reason = None
        if device.identity_status is not IdentityStatus.UNIQUE or len(own_rows) != 1:
            reason = Reason.IDENTITY_NOT_UNIQUE
        elif malformed_lines:
            reason = Reason.INCOMPLETE_LINE_EVIDENCE
        elif any(not line_id or line_identity_counts[line_id] != 1 for _, _, line_id in raw_incident):
            reason = Reason.INCIDENT_IDENTITY_CONFLICT
        else:
            line_ids = {line_id for _, _, line_id in raw_incident}
            if len(line_ids) != (2 if kind == 'SWITCH' else 1):
                reason = Reason.SWITCH_DEGREE if kind == 'SWITCH' else Reason.TRANSFORMER_DEGREE
            elif sorted(n for _, n, _ in raw_incident) != ([1,2] if kind == 'SWITCH' else [2]):
                reason = Reason.SWITCH_DIRECTION if kind == 'SWITCH' else Reason.TRANSFORMER_DIRECTION
            elif any(dict(r.fields or ()).get(f'{kind.title()}_{side}Bus') for r in own_rows for side in ('From','To')):
                reason = Reason.EXPLICIT_ENDPOINT_EVIDENCE
            else:
                # Raw degree alone cannot accept unresolved or nonpublished incident records.
                for raw, number, _ in raw_incident:
                    candidates = terminal_by_locator[(raw.source_record_ref, number)]
                    if len(candidates) != 1 or candidates[0].source_ref_status is not SourceReferenceStatus.EXACT or candidates[0].resolved_source_ref != entity_ref(device):
                        reason = Reason.INCIDENT_REFERENCE_NOT_EXACT
                        break
        targets = ()
        if reason is None and len(matches)>1:
            reason = Reason.NAME_VOLTAGE_CONFLICT
        if reason is None:
            if kind == 'SWITCH':
                first = node(device, DerivedRole.SWITCH_IN, voltage, voltage_source)
                second = node(device, DerivedRole.SWITCH_OUT, voltage, voltage_source)
                switch = switches[device.equipment_id]
                state = switch.normal_state.value if switch.normal_state else 'UNKNOWN'
                state_counts[state] += 1
                connection = branch(device, DerivedRole.SWITCH, first, second, state == 'CLOSED')
                targets = (first, second, connection)
            else:
                targets = (node(device, DerivedRole.TRANSFORMER_MV, voltage, voltage_source),)
        device_results[device.equipment_id] = project(device, rule, targets, reason, refs=refs,
            voltage=voltage if targets else None, voltage_source=voltage_source if targets else None)

    def endpoint(line, terminal):
        ref = terminal.resolved_source_ref
        target = None
        if ref:
            target = buses.get(ref.entity_id) or stations.get(ref.entity_id) or equipment.get(ref.entity_id)
        rule = Rule.UNSUPPORTED
        if isinstance(target, source.Bus): rule = Rule.BUS
        elif isinstance(target, source.Station): rule = Rule.STATION
        elif isinstance(target, source.Equipment):
            rule = {'SWITCH':Rule.SWITCH,'TRANSFORMER':Rule.TRANSFORMER,'ACCESS_POINT':Rule.ACCESS_POINT}.get(target.equipment_type.value, Rule.UNSUPPORTED)
        candidate_rows = rows_by_raw_id.get(terminal.raw_connected_ref, ())
        if target is None and candidate_rows:
            candidate_kinds = {r.source_file_type.value for r in candidate_rows}
            if candidate_kinds == {'BUS'}: rule = Rule.BUS
            elif candidate_kinds == {'STATION'}: rule = Rule.STATION
        refs = evidence(line, terminal, target, extra=(str(r.source_record_ref) for r in candidate_rows))
        reason, identifier = None, None
        if terminal.source_ref_status is not SourceReferenceStatus.EXACT:
            reason = {'MISSING':Reason.MISSING_REFERENCE,'AMBIGUOUS':Reason.AMBIGUOUS_REFERENCE}.get(terminal.source_ref_status.value, Reason.UNRESOLVED_REFERENCE)
        elif target is None:
            reason = Reason.UNRESOLVED_REFERENCE
        elif target.identity_status is not IdentityStatus.UNIQUE:
            reason = Reason.IDENTITY_NOT_UNIQUE
        elif len(matches)>1:
            reason = Reason.NAME_VOLTAGE_CONFLICT
        elif isinstance(target, source.Bus):
            value = target.base_voltage_kv
            raw_values = [dict(r.fields or ()).get('Bus_BaseKV','') for r in by_source_identity.get(('BUS', target.source_id), [])]
            invalid = False
            for raw_value in raw_values:
                if raw_value:
                    try:
                        parsed = Decimal(raw_value)
                        invalid |= not parsed.is_finite() or parsed <= 0
                    except InvalidOperation:
                        invalid = True
            if invalid:
                reason = Reason.INVALID_VOLTAGE_EVIDENCE
            elif value is not None and not _voltage_compatible(value, voltage):
                reason = Reason.BUS_VOLTAGE_CONFLICT
            else:
                identifier = node(target, DerivedRole.BUS_JUNCTION, voltage, voltage_source)
        elif isinstance(target, source.Station):
            refs = evidence(target, extra=anchor_refs)
            station_ref = upstream.station_source_ref if upstream else None
            if terminal.terminal_no != 1:
                reason = Reason.STATION_DIRECTION
            elif head is None:
                reason = Reason.NO_FEEDER_HEAD
            elif not station_ref or station_ref.resolution_status is not SourceReferenceStatus.EXACT or station_ref.resolved_source_ref != entity_ref(target):
                reason = Reason.STATION_CHAIN_MISMATCH
            else:
                identifier = head
        elif target.equipment_type.value in ('SWITCH','TRANSFORMER'):
            device_projection = device_results[target.equipment_id]
            refs = evidence(line, terminal, extra=device_projection.supporting_source_refs)
            reason = device_projection.exclusion_reason
            if reason is None:
                identifier = device_projection.derived_target_ids[0 if terminal.terminal_no == 2 else 1] if target.equipment_type.value == 'SWITCH' else device_projection.derived_target_ids[0]
        elif target.equipment_type.value == 'ACCESS_POINT':
            reason = Reason.ACCESS_POINT_UNSUPPORTED
        else:
            reason = Reason.CONNECTION_UNSUPPORTED
        return project(line, rule, (identifier,) if identifier else (), reason, terminal, refs,
            voltage if identifier else None, voltage_source if identifier else None)

    line_count = 0
    for line in sorted((r for r in equipment.values() if r.equipment_type.value=='LINE'), key=lambda r:r.equipment_id):
        line_count += 1
        endpoints = []
        reason = None
        if line.identity_status is not IdentityStatus.UNIQUE:
            reason = Reason.IDENTITY_NOT_UNIQUE
        elif len(terminals[line.equipment_id]) != 2 or [t.terminal_no for t in terminals[line.equipment_id]] != [1,2]:
            reason = Reason.INCOMPLETE_LINE_EVIDENCE
        else:
            endpoints = [endpoint(line, t) for t in terminals[line.equipment_id]]
            if any(p.projection_status is not Status.PROJECTED for p in endpoints):
                reason = Reason.LINE_ENDPOINT_EXCLUDED
        targets = ()
        if reason is None:
            targets = (branch(line, DerivedRole.LINE, endpoints[0].derived_target_ids[0], endpoints[1].derived_target_ids[0], True),)
        project(line, Rule.LINE, targets, reason,
            refs=tuple(sorted({ref for p in endpoints for ref in p.supporting_source_refs})))

    ordered_branches = tuple(sorted(branches.values(), key=lambda b:b.branch_id))
    reachable = reachable_nodes(head, ordered_branches)
    reachable_set = set(reachable)
    reachable_transformers = tuple(sorted(n.source_entity_ref.entity_id for n in nodes.values()
        if n.role is DerivedRole.TRANSFORMER_MV and n.node_id in reachable_set))
    usable = head is not None and any(b.role is DerivedRole.LINE and b.conducting and b.from_node_id in reachable_set for b in ordered_branches)
    projections.sort(key=canonical_json_bytes)
    rule_counts = {rule.value:{status.value:0 for status in Status} for rule in Rule}
    for p in projections:
        # Device rule counts describe devices, not their line endpoint mappings.
        if p.rule_id in (Rule.SWITCH, Rule.TRANSFORMER, Rule.ACCESS_POINT) and p.source_terminal_ref is not None:
            continue
        rule_counts[p.rule_id.value][p.projection_status.value] += 1
    projected_lines = sum(b.role is DerivedRole.LINE for b in branches.values())
    counts = {'source_line_rows':len(line_rows), 'published_lines':line_count,
        'unpublished_line_rows':sum(a.raw_record.source_file_type.value == 'LINE' and a.canonical_ref is None for a in details.accounting),
        'unpublished_line_groups':sum(p.rule_id is Rule.LINE and p.source_entity_ref == case_ref for p in projections),
        'cases_without_lines':int(not line_rows),
        'projected_lines':projected_lines,'excluded_lines':line_count-projected_lines,
        'synthetic_mv_heads':int(head is not None), 'valid_feeder_anchors':int(anchor_reason is None or anchor_reason is Reason.NAME_VOLTAGE_CONFLICT),
        'invalid_feeder_anchors':int(anchor_reason is not None and anchor_reason is not Reason.NAME_VOLTAGE_CONFLICT),
        'heads_name_inference':int(head is not None and voltage_source is VoltageSource.NAME_INFERENCE),
        'heads_default':int(head is not None and voltage_source is VoltageSource.DEFAULT),
        'reachable_transformers':len(reachable_transformers),
        'switch_closed':state_counts['CLOSED'],'switch_open':state_counts['OPEN'],'switch_unknown':state_counts['UNKNOWN']}
    for kind, rule in (('switch',Rule.SWITCH),('transformer',Rule.TRANSFORMER),('access_point',Rule.ACCESS_POINT)):
        values = rule_counts[rule.value]
        counts[kind+'_candidates'] = sum(values.values())
        counts[kind+'_projected'] = values[Status.PROJECTED.value]
        counts[kind+'_excluded'] = sum(values.values())-values[Status.PROJECTED.value]
    for kind, label in (('SWITCH','switch'),('TRANSFORMER','transformer'),('ACCESS_POINT','access_point')):
        counts['source_'+label+'_rows'] = sum(r.source_file_type.value == kind for r in rows)
        counts['published_'+label+('es' if label=='switch' else 's')] = sum(e.equipment_type.value == kind for e in equipment.values())
    counts['voltage_conflicts'] = sum(p.exclusion_reason in (Reason.NAME_VOLTAGE_CONFLICT, Reason.BUS_VOLTAGE_CONFLICT, Reason.SIM_CONFIG_VOLTAGE_CONFLICT) for p in projections)
    counts['voltage_unresolved'] = sum(p.exclusion_reason is Reason.INVALID_VOLTAGE_EVIDENCE for p in projections)
    topology = ElectricalTopology(str(case.case_id), head, tuple(sorted(nodes.values(),key=lambda n:n.node_id)), ordered_branches, reachable, reachable_transformers)
    coverage = TopologyCoverage(str(case.case_id), case.source_case_key, anchor_reason.value if anchor_reason else 'VALID',
        voltage if len(matches)<2 else None, voltage_source if len(matches)<2 else None, usable, bool(reachable_transformers), counts,
        {s.value:sum(p.projection_status is s for p in projections) for s in Status},
        dict(sorted(Counter(p.exclusion_reason.value for p in projections if p.exclusion_reason).items())), rule_counts)
    result = TopologyCaseResult(topology, tuple(projections), coverage)
    validate_topology(result)
    return result
