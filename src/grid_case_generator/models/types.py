"""Canonical value objects and enums."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Identifier(str):
    """A non-empty Unicode string with no implicit normalization."""

    __slots__ = ()

    def __new__(cls, value: str) -> Identifier:
        if not isinstance(value, str):
            raise TypeError(f"{cls.__name__} requires str, got {type(value).__name__}")
        if value == "":
            raise ValueError(f"{cls.__name__} must not be empty")
        return str.__new__(cls, value)


class CanonicalId(Identifier):
    """A stable internal Canonical identifier."""


class SourceId(Identifier):
    """Source identifier text after structural CSV quote removal."""


class SwitchState(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class RecordOrigin(StrEnum):
    SOURCE = "SOURCE"
    RULE_GENERATED = "RULE_GENERATED"
    DERIVED = "DERIVED"
    REPAIRED = "REPAIRED"
    MANUAL = "MANUAL"


class SourceReferenceStatus(StrEnum):
    MISSING = "MISSING"
    EXACT = "EXACT"
    NORMALIZED_CANDIDATE = "NORMALIZED_CANDIDATE"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"
    CONFIRMED_REPAIR = "CONFIRMED_REPAIR"


class ConnectivityStatus(StrEnum):
    NOT_ASSESSED = "NOT_ASSESSED"
    MISSING = "MISSING"
    CONFIRMED = "CONFIRMED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


class DataQuality(StrEnum):
    VALID = "VALID"
    SUSPECT = "SUSPECT"
    INVALID = "INVALID"
    TIME_UNKNOWN = "TIME_UNKNOWN"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class IdentityStatus(StrEnum):
    UNIQUE = "UNIQUE"
    DUPLICATE_IDENTICAL = "DUPLICATE_IDENTICAL"
    DUPLICATE_CONFLICT = "DUPLICATE_CONFLICT"


class ImportStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"


class TimeBase(StrEnum):
    ABSOLUTE = "ABSOLUTE"
    RELATIVE = "RELATIVE"


class EquipmentType(StrEnum):
    LINE = "LINE"
    SWITCH = "SWITCH"
    DISCONNECTOR = "DISCONNECTOR"
    EARTHING_SWITCH = "EARTHING_SWITCH"
    TRANSFORMER = "TRANSFORMER"
    ACCESS_POINT = "ACCESS_POINT"
    LOAD = "LOAD"
    DER = "DER"


class SwitchKind(StrEnum):
    SWITCH = "SWITCH"
    DISCONNECTOR = "DISCONNECTOR"
    EARTHING_SWITCH = "EARTHING_SWITCH"


class PowerFactorMode(StrEnum):
    LEADING = "LEADING"
    LAGGING = "LAGGING"
    UNKNOWN = "UNKNOWN"


class SeriesKind(StrEnum):
    SNAPSHOT = "SNAPSHOT"
    TIME_SERIES = "TIME_SERIES"


class ValueType(StrEnum):
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"
    CATEGORY = "CATEGORY"


@dataclass(frozen=True, slots=True, kw_only=True)
class EntityRef:
    entity_type: Identifier
    entity_id: CanonicalId

    def __post_init__(self) -> None:
        if not isinstance(self.entity_type, Identifier):
            raise TypeError("entity_type must be Identifier")
        if not isinstance(self.entity_id, CanonicalId):
            raise TypeError("entity_id must be CanonicalId")


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceReference:
    raw_ref: SourceId | None
    resolved_source_ref: EntityRef | None
    resolution_status: SourceReferenceStatus

    def __post_init__(self) -> None:
        if self.raw_ref is not None and not isinstance(self.raw_ref, SourceId):
            raise TypeError("raw_ref must be SourceId or None")
        if self.resolved_source_ref is not None and not isinstance(
            self.resolved_source_ref, EntityRef
        ):
            raise TypeError("resolved_source_ref must be EntityRef or None")
        if not isinstance(self.resolution_status, SourceReferenceStatus):
            raise TypeError("resolution_status must be SourceReferenceStatus")

        if self.resolution_status is SourceReferenceStatus.MISSING:
            if self.raw_ref is not None or self.resolved_source_ref is not None:
                raise ValueError("MISSING reference must not contain raw or resolved values")
            return

        if self.raw_ref is None:
            raise ValueError("non-MISSING reference requires raw_ref")

        resolved_statuses = {
            SourceReferenceStatus.EXACT,
            SourceReferenceStatus.CONFIRMED_REPAIR,
        }
        if self.resolution_status in resolved_statuses:
            if self.resolved_source_ref is None:
                raise ValueError(f"{self.resolution_status} requires resolved_source_ref")
        elif self.resolved_source_ref is not None:
            raise ValueError(f"{self.resolution_status} must not contain resolved_source_ref")
