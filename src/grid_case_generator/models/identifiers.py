"""Centralized deterministic Canonical ID factory for Source Import."""

from __future__ import annotations

import hashlib
import json
import re

from .quality import QualityIssueCode
from .types import (
    CanonicalId,
    EntityRef,
    EquipmentType,
    RecordOrigin,
    SourceId,
)


_ID_CONTRACT_VERSION = "source-import-id-v1"
_SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if value == "":
        raise ValueError(f"{field_name} must not be empty")
    return value


class SourceImportIdFactory:
    """Construct every CanonicalId created by the Source Import MVP."""

    @staticmethod
    def _make(kind: str, *parts: str | int | None) -> CanonicalId:
        payload = json.dumps(
            [_ID_CONTRACT_VERSION, kind, *parts],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        return CanonicalId(f"{kind}:{digest}")

    @classmethod
    def dataset_id(cls, source_artifact_sha256: str) -> CanonicalId:
        checksum = _required_text(source_artifact_sha256, "source_artifact_sha256")
        if _SHA256_PATTERN.fullmatch(checksum) is None:
            raise ValueError("source_artifact_sha256 must be exactly 64 hexadecimal digits")
        return cls._make("dataset", f"sha256:{checksum.lower()}")

    @classmethod
    def case_id(cls, dataset_id: CanonicalId, source_case_key: str) -> CanonicalId:
        cls._require_canonical_id(dataset_id, "dataset_id")
        return cls._make("case", dataset_id, _required_text(source_case_key, "source_case_key"))

    @classmethod
    def station_id(
        cls, case_id: CanonicalId, source_id: SourceId, source_record_ref: str
    ) -> CanonicalId:
        return cls._source_entity_id(
            "station", case_id, "STATION", source_id, source_record_ref
        )

    @classmethod
    def feeder_id(
        cls, case_id: CanonicalId, source_id: SourceId, source_record_ref: str
    ) -> CanonicalId:
        return cls._source_entity_id(
            "feeder", case_id, "FEEDER", source_id, source_record_ref
        )

    @classmethod
    def bus_id(
        cls, case_id: CanonicalId, source_id: SourceId, source_record_ref: str
    ) -> CanonicalId:
        return cls._source_entity_id("bus", case_id, "BUS", source_id, source_record_ref)

    @classmethod
    def equipment_id(
        cls,
        case_id: CanonicalId,
        equipment_type: EquipmentType,
        source_id: SourceId,
        source_record_ref: str,
    ) -> CanonicalId:
        if not isinstance(equipment_type, EquipmentType):
            raise TypeError("equipment_type must be EquipmentType")
        return cls._source_entity_id(
            "equipment", case_id, equipment_type.value, source_id, source_record_ref
        )

    @classmethod
    def _source_entity_id(
        cls,
        kind: str,
        case_id: CanonicalId,
        source_entity_type: str,
        source_id: SourceId,
        source_record_ref: str,
    ) -> CanonicalId:
        cls._require_canonical_id(case_id, "case_id")
        if not isinstance(source_id, SourceId):
            raise TypeError("source_id must be SourceId")
        return cls._make(
            kind,
            case_id,
            source_entity_type,
            source_id,
            _required_text(source_record_ref, "source_record_ref"),
        )

    @classmethod
    def terminal_id(cls, equipment_id: CanonicalId, terminal_no: int) -> CanonicalId:
        cls._require_canonical_id(equipment_id, "equipment_id")
        cls._require_positive_number(terminal_no, "terminal_no")
        return cls._make("terminal", equipment_id, terminal_no)

    @classmethod
    def winding_id(cls, equipment_id: CanonicalId, winding_no: int) -> CanonicalId:
        cls._require_canonical_id(equipment_id, "equipment_id")
        cls._require_positive_number(winding_no, "winding_no")
        return cls._make("winding", equipment_id, winding_no)

    @classmethod
    def simulation_profile_id(cls, case_id: CanonicalId) -> CanonicalId:
        cls._require_canonical_id(case_id, "case_id")
        return cls._make("simulation-profile", case_id, "source_sim_config")

    @classmethod
    def operational_series_id(
        cls,
        case_id: CanonicalId,
        target_ref: EntityRef,
        source_record_ref: str,
        source_field: str,
    ) -> CanonicalId:
        cls._require_canonical_id(case_id, "case_id")
        cls._require_entity_ref(target_ref)
        return cls._make(
            "operational-series",
            case_id,
            target_ref.entity_type,
            target_ref.entity_id,
            _required_text(source_record_ref, "source_record_ref"),
            _required_text(source_field, "source_field"),
        )

    @classmethod
    def field_provenance_id(
        cls,
        target_ref: EntityRef,
        field_path: str,
        origin: RecordOrigin,
        source_record_ref: str | None,
        source_field: str | None,
        source_mapping_id: str,
        source_mapping_version: str,
    ) -> CanonicalId:
        cls._require_entity_ref(target_ref)
        if not isinstance(origin, RecordOrigin):
            raise TypeError("origin must be RecordOrigin")
        if source_record_ref is not None:
            _required_text(source_record_ref, "source_record_ref")
        if source_field is not None:
            _required_text(source_field, "source_field")
        return cls._make(
            "field-provenance",
            target_ref.entity_type,
            target_ref.entity_id,
            _required_text(field_path, "field_path"),
            origin.value,
            source_record_ref,
            source_field,
            _required_text(source_mapping_id, "source_mapping_id"),
            _required_text(source_mapping_version, "source_mapping_version"),
        )

    @classmethod
    def quality_issue_id(
        cls,
        dataset_id: CanonicalId,
        case_id: CanonicalId | None,
        target_ref: EntityRef | None,
        field_path: str | None,
        code: QualityIssueCode,
        source_record_ref: str | None,
        occurrence_key: str,
    ) -> CanonicalId:
        cls._require_canonical_id(dataset_id, "dataset_id")
        if case_id is not None:
            cls._require_canonical_id(case_id, "case_id")
        if target_ref is not None:
            cls._require_entity_ref(target_ref)
        if field_path is not None:
            _required_text(field_path, "field_path")
        if not isinstance(code, QualityIssueCode):
            raise TypeError("code must be QualityIssueCode")
        if source_record_ref is not None:
            _required_text(source_record_ref, "source_record_ref")
        if not isinstance(occurrence_key, str):
            raise TypeError("occurrence_key must be str")
        return cls._make(
            "quality-issue",
            dataset_id,
            case_id,
            target_ref.entity_type if target_ref else None,
            target_ref.entity_id if target_ref else None,
            field_path,
            code.value,
            source_record_ref,
            occurrence_key,
        )

    @staticmethod
    def _require_canonical_id(value: CanonicalId, field_name: str) -> None:
        if not isinstance(value, CanonicalId):
            raise TypeError(f"{field_name} must be CanonicalId")

    @staticmethod
    def _require_entity_ref(value: EntityRef) -> None:
        if not isinstance(value, EntityRef):
            raise TypeError("target_ref must be EntityRef")

    @staticmethod
    def _require_positive_number(value: int, field_name: str) -> None:
        if type(value) is not int:
            raise TypeError(f"{field_name} must be int")
        if value < 1:
            raise ValueError(f"{field_name} must start at 1")
