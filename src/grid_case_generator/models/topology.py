"""Independent E2 records; all voltages are finite positive Decimal kV."""
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json

from .types import EntityRef


class DerivedRole(StrEnum):
    FEEDER_HEAD = 'feeder-head/mv'
    BUS_JUNCTION = 'junction/bus'
    SWITCH_IN = 'switch-port/in'
    SWITCH_OUT = 'switch-port/out'
    SWITCH = 'switch/series'
    TRANSFORMER_MV = 'transformer-mv/mv'
    LINE = 'line/connection'


class DerivedIdFactory:
    namespace = 'nanjing-derived-topology-id-v1'

    @classmethod
    def make(cls, role: DerivedRole, case_id: str, owner: str) -> str:
        if not isinstance(role, DerivedRole):
            raise TypeError('role must be DerivedRole')
        if not isinstance(case_id,str) or not isinstance(owner,str):
            raise TypeError('case and owner must be strings')
        if not case_id or not owner:
            raise ValueError('case and owner must be nonempty')
        kind, port = role.value.split('/')
        data = json.dumps([cls.namespace, kind, case_id, owner, port],
                          ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        return f'{kind}:{sha256(data).hexdigest()}'


class ProjectionStatus(StrEnum):
    PROJECTED = 'PROJECTED'
    UNRESOLVED = 'UNRESOLVED'
    AMBIGUOUS = 'AMBIGUOUS'
    UNSUPPORTED = 'UNSUPPORTED'
    EXCLUDED = 'EXCLUDED'


class VoltageSource(StrEnum):
    NAME_INFERENCE = 'NAME_INFERENCE'
    SOURCE = 'SOURCE'
    DEFAULT = 'DEFAULT'


class ExclusionReason(StrEnum):
    MISSING_FEEDER = 'MISSING_FEEDER'
    AMBIGUOUS_FEEDER = 'AMBIGUOUS_FEEDER'
    INVALID_FEEDER_BUS = 'INVALID_FEEDER_BUS'
    NAME_VOLTAGE_CONFLICT = 'NAME_VOLTAGE_CONFLICT'
    BUS_VOLTAGE_CONFLICT = 'BUS_VOLTAGE_CONFLICT'
    INVALID_VOLTAGE_EVIDENCE = 'INVALID_VOLTAGE_EVIDENCE'
    SIM_CONFIG_VOLTAGE_CONFLICT = 'SIM_CONFIG_VOLTAGE_CONFLICT'
    MISSING_REFERENCE = 'MISSING_REFERENCE'
    AMBIGUOUS_REFERENCE = 'AMBIGUOUS_REFERENCE'
    UNRESOLVED_REFERENCE = 'UNRESOLVED_REFERENCE'
    IDENTITY_NOT_UNIQUE = 'IDENTITY_NOT_UNIQUE'
    NO_FEEDER_HEAD = 'NO_FEEDER_HEAD'
    STATION_DIRECTION = 'STATION_DIRECTION'
    STATION_CHAIN_MISMATCH = 'STATION_CHAIN_MISMATCH'
    SWITCH_DEGREE = 'SWITCH_DEGREE'
    SWITCH_DIRECTION = 'SWITCH_DIRECTION'
    TRANSFORMER_DEGREE = 'TRANSFORMER_DEGREE'
    TRANSFORMER_DIRECTION = 'TRANSFORMER_DIRECTION'
    EXPLICIT_ENDPOINT_EVIDENCE = 'EXPLICIT_ENDPOINT_EVIDENCE'
    INCOMPLETE_LINE_EVIDENCE = 'INCOMPLETE_LINE_EVIDENCE'
    INCIDENT_IDENTITY_CONFLICT = 'INCIDENT_IDENTITY_CONFLICT'
    INCIDENT_REFERENCE_NOT_EXACT = 'INCIDENT_REFERENCE_NOT_EXACT'
    ACCESS_POINT_UNSUPPORTED = 'ACCESS_POINT_UNSUPPORTED'
    CONNECTION_UNSUPPORTED = 'CONNECTION_UNSUPPORTED'
    LINE_ENDPOINT_EXCLUDED = 'LINE_ENDPOINT_EXCLUDED'


class RuleId(StrEnum):
    FEEDER_HEAD = 'SYNTHETIC_MV_FEEDER_HEAD_V1'
    BUS = 'BUS_JUNCTION_V1'
    STATION = 'STATION_FEEDER_HEAD_V1'
    SWITCH = 'SERIES_SWITCH_V1'
    TRANSFORMER = 'LEAF_TRANSFORMER_MV_V1'
    LINE = 'LINE_CONNECTION_V1'
    ACCESS_POINT = 'ACCESS_POINT_EXCLUSION_V1'
    UNSUPPORTED = 'UNSUPPORTED_CONNECTION_V1'
    VOLTAGE = 'SOURCE_VOLTAGE_AUDIT_V1'


RULE_VERSION = '1.0.0'


def positive_voltage(value):
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError('voltage must be a finite positive Decimal in kV')


@dataclass(frozen=True, slots=True)
class TopologyConfig:
    fallback_nominal_voltage_kv: Decimal

    def __post_init__(self):
        positive_voltage(self.fallback_nominal_voltage_kv)


@dataclass(frozen=True, slots=True)
class ElectricalNode:
    node_id: str
    role: DerivedRole
    source_entity_ref: EntityRef
    nominal_voltage_kv: Decimal
    voltage_source: VoltageSource

    def __post_init__(self):
        positive_voltage(self.nominal_voltage_kv)


@dataclass(frozen=True, slots=True)
class ElectricalBranch:
    branch_id: str
    role: DerivedRole
    source_entity_ref: EntityRef
    from_node_id: str
    to_node_id: str
    conducting: bool


@dataclass(frozen=True, slots=True)
class TopologyProjectionRecord:
    source_case_ref: EntityRef
    source_entity_ref: EntityRef
    source_terminal_ref: EntityRef | None
    supporting_source_refs: tuple[str, ...]
    rule_id: RuleId
    rule_version: str
    projection_status: ProjectionStatus
    derived_target_ids: tuple[str, ...]
    exclusion_reason: ExclusionReason | None
    nominal_voltage_kv: Decimal | None
    voltage_source: VoltageSource | None

    def __post_init__(self):
        if self.supporting_source_refs != tuple(sorted(set(self.supporting_source_refs))):
            raise ValueError('supporting refs must be ordered and unique')
        if self.projection_status is ProjectionStatus.PROJECTED:
            if not self.derived_target_ids or self.exclusion_reason is not None:
                raise ValueError('projected record requires targets and no exclusion')
        elif self.derived_target_ids or self.exclusion_reason is None:
            raise ValueError('nonprojected record requires reason and no targets')
        if self.nominal_voltage_kv is not None:
            positive_voltage(self.nominal_voltage_kv)


@dataclass(frozen=True, slots=True)
class ElectricalTopology:
    case_id: str
    feeder_head_id: str | None
    nodes: tuple[ElectricalNode, ...]
    branches: tuple[ElectricalBranch, ...]
    reachable_node_ids: tuple[str, ...]
    reachable_transformer_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TopologyCoverage:
    case_id: str
    source_case_key: str | None
    feeder_anchor_status: str
    nominal_voltage_kv: Decimal | None
    voltage_source: VoltageSource | None
    usable_subgraph: bool
    has_reachable_transformer: bool
    counts: dict[str, int]
    projection_status_counts: dict[str, int]
    exclusion_reasons: dict[str, int]
    rule_counts: dict[str, dict[str, int]]


@dataclass(frozen=True, slots=True)
class TopologyCaseResult:
    topology: ElectricalTopology
    projections: tuple[TopologyProjectionRecord, ...]
    coverage: TopologyCoverage
