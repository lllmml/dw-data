"""Pure source-reference candidate indexing and exact resolution."""

from dataclasses import dataclass
from typing import Iterable

from grid_case_generator.models.types import (
    CanonicalId,
    EntityRef,
    Identifier,
    IdentityStatus,
    SourceId,
    SourceReferenceStatus,
)
from grid_case_generator.validation.identity import SourceEntityType


ReferenceCandidateKey = tuple[CanonicalId, SourceEntityType, SourceId]
_DIRECT_ENTITY_TYPES = {
    SourceEntityType.STATION,
    SourceEntityType.FEEDER,
    SourceEntityType.BUS,
}
_IDENTITY_SOURCE_ENTITY_TYPE_VALUES = frozenset(
    item.value for item in SourceEntityType
)
_RESOLUTION_STATUSES = {
    SourceReferenceStatus.MISSING,
    SourceReferenceStatus.EXACT,
    SourceReferenceStatus.AMBIGUOUS,
    SourceReferenceStatus.UNRESOLVED,
}


def _index_key_sort_key(
    key: ReferenceCandidateKey,
) -> tuple[str, str, str]:
    return (key[0], key[1].value, key[2])


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceResolutionRequest:
    case_id: CanonicalId
    owner_source_entity_type: Identifier
    owner_source_id: SourceId | None
    owner_source_record_ref: str
    reference_field_path: str
    raw_reference_value: str
    allowed_candidate_source_entity_types: tuple[SourceEntityType, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, CanonicalId):
            raise TypeError("case_id must be CanonicalId")
        if not isinstance(self.owner_source_entity_type, Identifier):
            raise TypeError("owner_source_entity_type must be Identifier")
        if self.owner_source_id is not None and not isinstance(
            self.owner_source_id, SourceId
        ):
            raise TypeError("owner_source_id must be SourceId or None")
        if (
            self.owner_source_entity_type in _IDENTITY_SOURCE_ENTITY_TYPE_VALUES
            and self.owner_source_id is None
        ):
            raise ValueError("identity-bearing owner requires owner_source_id")
        for field_name in ("owner_source_record_ref", "reference_field_path"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be str")
            if value == "":
                raise ValueError(f"{field_name} must be non-empty")
        if not isinstance(self.raw_reference_value, str):
            raise TypeError("raw_reference_value must be str")
        allowed_types = self.allowed_candidate_source_entity_types
        if not isinstance(allowed_types, tuple) or not all(
            isinstance(item, SourceEntityType) for item in allowed_types
        ):
            raise TypeError(
                "allowed_candidate_source_entity_types must be a tuple of "
                "SourceEntityType values"
            )
        if len(set(allowed_types)) != len(allowed_types):
            raise ValueError("allowed candidate source entity types must be unique")
        if any(item.value == "EQUIPMENT" for item in allowed_types):
            raise ValueError("generic EQUIPMENT is not a source identity type")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceCandidate:
    case_id: CanonicalId
    candidate_source_entity_type: SourceEntityType
    source_id: SourceId
    source_record_ref: str
    identity_status: IdentityStatus
    entity_ref: EntityRef

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, CanonicalId):
            raise TypeError("case_id must be CanonicalId")
        if not isinstance(self.candidate_source_entity_type, SourceEntityType):
            raise TypeError("candidate_source_entity_type must be SourceEntityType")
        if not isinstance(self.source_id, SourceId):
            raise TypeError("source_id must be SourceId")
        if self.source_id == "":
            raise ValueError("source_id must be non-empty")
        if not isinstance(self.source_record_ref, str):
            raise TypeError("source_record_ref must be str")
        if self.source_record_ref == "":
            raise ValueError("source_record_ref must be non-empty")
        if not isinstance(self.identity_status, IdentityStatus):
            raise TypeError("identity_status must be IdentityStatus")
        if self.identity_status is IdentityStatus.DUPLICATE_CONFLICT:
            raise ValueError(
                "conflicting identity must use ReferenceIdentityConflict"
            )
        if not isinstance(self.entity_ref, EntityRef):
            raise TypeError("entity_ref must be EntityRef")
        expected_entity_type = (
            self.candidate_source_entity_type.value
            if self.candidate_source_entity_type in _DIRECT_ENTITY_TYPES
            else "EQUIPMENT"
        )
        if self.entity_ref.entity_type != expected_entity_type:
            raise ValueError(
                "entity_ref type does not match candidate source entity type"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceIdentityConflict:
    """A conflicting source identity group with no published Canonical entity."""

    case_id: CanonicalId
    source_entity_type: SourceEntityType
    source_id: SourceId
    source_record_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, CanonicalId):
            raise TypeError("case_id must be CanonicalId")
        if not isinstance(self.source_entity_type, SourceEntityType):
            raise TypeError("source_entity_type must be SourceEntityType")
        if not isinstance(self.source_id, SourceId):
            raise TypeError("source_id must be SourceId")
        if self.source_id == "":
            raise ValueError("source_id must be non-empty")
        if (
            not isinstance(self.source_record_refs, tuple)
            or len(self.source_record_refs) < 2
            or not all(
                isinstance(item, str) and item != ""
                for item in self.source_record_refs
            )
        ):
            raise ValueError(
                "source_record_refs must contain at least two non-empty strings"
            )
        if (
            tuple(sorted(self.source_record_refs)) != self.source_record_refs
            or len(set(self.source_record_refs)) != len(self.source_record_refs)
        ):
            raise ValueError("source_record_refs must be unique and sorted")

    @property
    def key(self) -> ReferenceCandidateKey:
        return (self.case_id, self.source_entity_type, self.source_id)


def _candidate_sort_key(
    candidate: ReferenceCandidate,
) -> tuple[str, str, str, str, str, str]:
    return (
        candidate.case_id,
        candidate.candidate_source_entity_type.value,
        candidate.source_id,
        candidate.source_record_ref,
        candidate.entity_ref.entity_type,
        candidate.entity_ref.entity_id,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceCandidateIndex:
    entries: tuple[
        tuple[ReferenceCandidateKey, tuple[ReferenceCandidate, ...]], ...
    ]
    identity_conflicts: tuple[
        tuple[ReferenceCandidateKey, ReferenceIdentityConflict], ...
    ] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple):
            raise TypeError("entries must be tuple")
        keys: list[ReferenceCandidateKey] = []
        for entry in self.entries:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise TypeError("each index entry must be a key and candidate tuple")
            key, candidates = entry
            if (
                not isinstance(key, tuple)
                or len(key) != 3
                or not isinstance(key[0], CanonicalId)
                or not isinstance(key[1], SourceEntityType)
                or not isinstance(key[2], SourceId)
            ):
                raise TypeError("candidate index key has invalid types")
            if not isinstance(candidates, tuple) or not candidates:
                raise ValueError("candidate index buckets must be non-empty tuples")
            if not all(isinstance(item, ReferenceCandidate) for item in candidates):
                raise TypeError("candidate index contains an invalid candidate")
            if tuple(sorted(candidates, key=_candidate_sort_key)) != candidates:
                raise ValueError(
                    "candidate index bucket must be deterministically sorted"
                )
            if any(
                (
                    candidate.case_id,
                    candidate.candidate_source_entity_type,
                    candidate.source_id,
                )
                != key
                for candidate in candidates
            ):
                raise ValueError("candidate is stored under the wrong index key")
            keys.append(key)
        if (
            tuple(sorted(keys, key=_index_key_sort_key)) != tuple(keys)
            or len(set(keys)) != len(keys)
        ):
            raise ValueError("candidate index keys must be unique and sorted")

        if not isinstance(self.identity_conflicts, tuple):
            raise TypeError("identity_conflicts must be tuple")
        conflict_keys: list[ReferenceCandidateKey] = []
        for entry in self.identity_conflicts:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise TypeError("each conflict entry must be a key and marker")
            key, conflict = entry
            if not isinstance(conflict, ReferenceIdentityConflict):
                raise TypeError("identity conflict index contains an invalid marker")
            if key != conflict.key:
                raise ValueError("identity conflict is stored under the wrong index key")
            conflict_keys.append(key)
        if (
            tuple(sorted(conflict_keys, key=_index_key_sort_key))
            != tuple(conflict_keys)
            or len(set(conflict_keys)) != len(conflict_keys)
        ):
            raise ValueError("identity conflict keys must be unique and sorted")
        if set(keys).intersection(conflict_keys):
            raise ValueError(
                "candidate and identity conflict cannot share an index key"
            )

    def _lookup(
        self, key: ReferenceCandidateKey
    ) -> tuple[ReferenceCandidate, ...]:
        lower = 0
        upper = len(self.entries)
        target_sort_key = _index_key_sort_key(key)
        while lower < upper:
            middle = (lower + upper) // 2
            middle_key = self.entries[middle][0]
            if _index_key_sort_key(middle_key) < target_sort_key:
                lower = middle + 1
            else:
                upper = middle
        if lower < len(self.entries) and self.entries[lower][0] == key:
            return self.entries[lower][1]
        return ()

    def _lookup_conflict(
        self, key: ReferenceCandidateKey
    ) -> ReferenceIdentityConflict | None:
        lower = 0
        upper = len(self.identity_conflicts)
        target_sort_key = _index_key_sort_key(key)
        while lower < upper:
            middle = (lower + upper) // 2
            middle_key = self.identity_conflicts[middle][0]
            if _index_key_sort_key(middle_key) < target_sort_key:
                lower = middle + 1
            else:
                upper = middle
        if (
            lower < len(self.identity_conflicts)
            and self.identity_conflicts[lower][0] == key
        ):
            return self.identity_conflicts[lower][1]
        return None


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceResolutionResult:
    resolution_status: SourceReferenceStatus
    request: ReferenceResolutionRequest
    candidates: tuple[ReferenceCandidate, ...]
    identity_conflicts: tuple[ReferenceIdentityConflict, ...]
    resolved_ref: EntityRef | None

    def __post_init__(self) -> None:
        if not isinstance(self.resolution_status, SourceReferenceStatus):
            raise TypeError("resolution_status must be SourceReferenceStatus")
        if self.resolution_status not in _RESOLUTION_STATUSES:
            raise ValueError("resolution_status is not supported by this contract")
        if not isinstance(self.request, ReferenceResolutionRequest):
            raise TypeError("request must be ReferenceResolutionRequest")
        if not isinstance(self.candidates, tuple) or not all(
            isinstance(item, ReferenceCandidate) for item in self.candidates
        ):
            raise TypeError("candidates must be a tuple of ReferenceCandidate values")
        if tuple(sorted(self.candidates, key=_candidate_sort_key)) != self.candidates:
            raise ValueError("candidates must be deterministically sorted")
        if not isinstance(self.identity_conflicts, tuple) or not all(
            isinstance(item, ReferenceIdentityConflict)
            for item in self.identity_conflicts
        ):
            raise TypeError(
                "identity_conflicts must be a tuple of ReferenceIdentityConflict values"
            )
        if tuple(
            sorted(
                self.identity_conflicts,
                key=lambda item: (
                    item.case_id,
                    item.source_entity_type.value,
                    item.source_id,
                    item.source_record_refs,
                ),
            )
        ) != self.identity_conflicts:
            raise ValueError("identity_conflicts must be deterministically sorted")
        if self.resolved_ref is not None and not isinstance(
            self.resolved_ref, EntityRef
        ):
            raise TypeError("resolved_ref must be EntityRef or None")
        if any(
            candidate.case_id != self.request.case_id
            or candidate.source_id != self.request.raw_reference_value
            or candidate.candidate_source_entity_type
            not in self.request.allowed_candidate_source_entity_types
            for candidate in self.candidates
        ):
            raise ValueError("candidate does not satisfy the request scope")
        if any(
            conflict.case_id != self.request.case_id
            or conflict.source_id != self.request.raw_reference_value
            or conflict.source_entity_type
            not in self.request.allowed_candidate_source_entity_types
            for conflict in self.identity_conflicts
        ):
            raise ValueError("identity conflict does not satisfy the request scope")
        self._validate_status_invariants()

    def _validate_status_invariants(self) -> None:
        raw_value = self.request.raw_reference_value
        if self.resolution_status is SourceReferenceStatus.MISSING:
            if (
                raw_value != ""
                or self.candidates
                or self.identity_conflicts
                or self.resolved_ref is not None
            ):
                raise ValueError("MISSING result invariants are not satisfied")
            return
        if raw_value == "":
            raise ValueError("only MISSING may have an empty raw reference value")
        if self.resolution_status is SourceReferenceStatus.EXACT:
            if (
                len(self.candidates) != 1
                or self.candidates[0].identity_status is not IdentityStatus.UNIQUE
                or self.identity_conflicts
                or self.resolved_ref != self.candidates[0].entity_ref
            ):
                raise ValueError("EXACT result invariants are not satisfied")
            return
        if self.resolution_status is SourceReferenceStatus.AMBIGUOUS:
            is_ambiguous = (
                bool(self.identity_conflicts)
                or len(self.candidates) > 1
                or (
                    len(self.candidates) == 1
                    and self.candidates[0].identity_status
                    is not IdentityStatus.UNIQUE
                )
            )
            if not is_ambiguous or self.resolved_ref is not None:
                raise ValueError("AMBIGUOUS result invariants are not satisfied")
            return
        if self.candidates or self.identity_conflicts or self.resolved_ref is not None:
            raise ValueError("UNRESOLVED result invariants are not satisfied")


def build_reference_candidate_index(
    candidates: Iterable[ReferenceCandidate],
    *,
    identity_conflicts: Iterable[ReferenceIdentityConflict] = (),
) -> ReferenceCandidateIndex:
    """Build an immutable index without merging any candidates."""

    input_candidates = tuple(candidates)
    if not all(isinstance(item, ReferenceCandidate) for item in input_candidates):
        raise TypeError("candidates must contain ReferenceCandidate values")
    groups: dict[ReferenceCandidateKey, list[ReferenceCandidate]] = {}
    for candidate in input_candidates:
        key = (
            candidate.case_id,
            candidate.candidate_source_entity_type,
            candidate.source_id,
        )
        groups.setdefault(key, []).append(candidate)
    entries = tuple(
        (key, tuple(sorted(group, key=_candidate_sort_key)))
        for key, group in sorted(
            groups.items(), key=lambda item: _index_key_sort_key(item[0])
        )
    )
    input_conflicts = tuple(identity_conflicts)
    if not all(
        isinstance(item, ReferenceIdentityConflict) for item in input_conflicts
    ):
        raise TypeError(
            "identity_conflicts must contain ReferenceIdentityConflict values"
        )
    conflict_entries = tuple(
        (conflict.key, conflict)
        for conflict in sorted(
            input_conflicts, key=lambda item: _index_key_sort_key(item.key)
        )
    )
    return ReferenceCandidateIndex(
        entries=entries,
        identity_conflicts=conflict_entries,
    )


def resolve_source_reference(
    index: ReferenceCandidateIndex,
    request: ReferenceResolutionRequest,
) -> ReferenceResolutionResult:
    """Resolve one raw source reference by exact typed lookup only."""

    if not isinstance(index, ReferenceCandidateIndex):
        raise TypeError("index must be ReferenceCandidateIndex")
    if not isinstance(request, ReferenceResolutionRequest):
        raise TypeError("request must be ReferenceResolutionRequest")
    if request.raw_reference_value == "":
        return ReferenceResolutionResult(
            resolution_status=SourceReferenceStatus.MISSING,
            request=request,
            candidates=(),
            identity_conflicts=(),
            resolved_ref=None,
        )

    source_id = SourceId(request.raw_reference_value)
    candidates = tuple(
        sorted(
            (
                candidate
                for source_entity_type in request.allowed_candidate_source_entity_types
                for candidate in index._lookup(
                    (request.case_id, source_entity_type, source_id)
                )
            ),
            key=_candidate_sort_key,
        )
    )
    identity_conflicts = tuple(
        sorted(
            (
                conflict
                for source_entity_type in request.allowed_candidate_source_entity_types
                if (
                    conflict := index._lookup_conflict(
                        (request.case_id, source_entity_type, source_id)
                    )
                )
                is not None
            ),
            key=lambda item: (
                item.case_id,
                item.source_entity_type.value,
                item.source_id,
                item.source_record_refs,
            ),
        )
    )
    if identity_conflicts:
        status = SourceReferenceStatus.AMBIGUOUS
        resolved_ref = None
    elif not candidates:
        status = SourceReferenceStatus.UNRESOLVED
        resolved_ref = None
    elif len(candidates) == 1 and (
        candidates[0].identity_status is IdentityStatus.UNIQUE
    ):
        status = SourceReferenceStatus.EXACT
        resolved_ref = candidates[0].entity_ref
    else:
        status = SourceReferenceStatus.AMBIGUOUS
        resolved_ref = None
    return ReferenceResolutionResult(
        resolution_status=status,
        request=request,
        candidates=candidates,
        identity_conflicts=identity_conflicts,
        resolved_ref=resolved_ref,
    )
