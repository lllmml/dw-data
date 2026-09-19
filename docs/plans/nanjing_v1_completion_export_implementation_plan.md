# Nanjing v1 Completion and Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `nanjing-v1` completion/export layer that turns frozen source facts plus the published evidence chain into a completion ledger and a source-shaped v1 derived delivery, exactly as frozen in `docs/spec/nanjing_v1_completion_export.md`.

**Architecture:** Two-stage. A pure engine (`generation/completion_ledger.py`) reads verified upstream artifacts plus a policy file and emits a completion ledger; a separate IO layer materializes that ledger into byte-faithful source-shaped CSV copies with a per-row provenance sidecar and a deterministic archive. No canonical record, resolver result, GridCase boundary or accepted topology v2 object is read-modify-written anywhere.

**Tech Stack:** Python 3.11, stdlib only (`zipfile`, `csv`, `json`, `hashlib`, `argparse`, `enum`, `dataclasses`). No new dependencies. Test runner `pytest`. No lint/type-check tooling exists in this repo; the static check is `python -m compileall -q src tests`.

**Slice index.** Slice 3 is an addition not in the original slice list: it is a prerequisite, because the delivery cannot be byte-faithful without it. Slice 5 carries both `ACCEPTED_DETERMINISTIC_RECOVERY_V1` and the UNRESOLVED cohort taxonomy, because both are ledger-only and share their inputs' character.

---

## 0. Contract corrections required before implementation

**Status: resolved. Do not re-apply anything from this section.**

Four mismatches between the 1.0.0 contract and the persisted evidence were found by
measurement during planning. They were converted into an explicit contract revision
before implementation, as required by "do not silently edit frozen semantics":

- Revision: `docs/spec/revisions/nanjing_v1_completion_export_revision_001.md`
- Contract moved from 1.0.0 to **1.1.0**; the revision document carries the original
  statement, observed evidence, problem, corrected rule and compatibility impact for each
- Config moved to `policy_version` **1.1.0**; the policy schema identity is unchanged and
  its `description` now points at the revision
- `PLACEMENT_MISSING_ENDPOINT_BUS_V1` carries `rule_version` **1.1.0**; the other three
  rules stay at 1.0.0 and no rule id was renamed

Summary of the four, for readers of this plan who do not open the revision:

| # | 1.0.0 said | Corrected in 1.1.0 |
|---|---|---|
| 1 | `Bus_BaseKV` derived from the proposal's `voltage_evidence` — a field that does not exist on proposal rows | Joined from `line_endpoint_evidence.jsonl` on `(source_line_id, endpoint_side)`; null with `VOLTAGE_EVIDENCE_ABSENT` when absent, null with `VOLTAGE_EVIDENCE_CONFLICT` when occurrences disagree. All 815 unresolved endpoint occurrences are null |
| 2 | `Bus_Station_ID` is the Case-local station | Filled only when the Case's `02_Bus.csv` has exactly one distinct non-empty value; otherwise null with `STATION_EVIDENCE_NOT_UNIQUE`. Measured: 495 single, 4,644 multiple, 20 none |
| 3 | `Bus_Name`, `Bus_Phase`, `Bus_IsSource` "derived or left empty" | Null unless evidence exists; `Bus_ID` alone carries the endpoint identity the placement rule already determined. Never filled from station context |
| 4 | `manifest['files']` inventories every delivered file, while the archive contains the manifest | Manifest excludes itself and the archive; the archive sha256 lives in the verification sidecar. No recursive hashing |

**Contract constants this plan must match.** `VERSION = '1.1.0'` for the contract and
rule analysis; `POLICY_VERSION = '1.1.0'` as shipped in
`configs/nanjing_completion_policy_v1.json`. `PLACEMENT_BUS_RULE_VERSION = '1.1.0'` and, per
revision 003, `CROSS_CASE_RULE_VERSION = '1.1.0'` — that rule's published row set would
differ from its 1.0.0 form, though it has never run. `SOURCE_PASSTHROUGH_V1` and
`ACCEPTED_DETERMINISTIC_RECOVERY_V1` carry `'1.0.0'`, and `COHORT_TAXONOMY_V1` carries
its own `COHORT_RULE_VERSION = '1.0.0'`. Artifact directory names stay
`completion-ledger-v1` and `derived-delivery-v1` because no artifact was ever published
under 1.0.0.

---

## 1. Architecture boundary

Six responsibilities, six modules. Each boundary is crossed only by plain data values, never by a file handle or a shared mutable object.

| Responsibility | Module | Reads | Produces | Must not |
|---|---|---|---|---|
| Source ingestion | `io/source_bytes.py` | `data/raw/南京数据.zip` (read-only, caller-owned handle) | verbatim member bytes, raw logical-record slices | parse into the canonical model; write anything |
| Policy loading | `models/completion_export.py` | `configs/nanjing_completion_policy_v1.json` | `CompletionPolicy` | read any other config |
| Completion rule execution | `generation/completion_ledger.py` | upstream artifact rows + `CompletionPolicy` | `Ledger` of plain dicts | perform IO; open a zip; see a filesystem path |
| Ledger generation | `io/completion_ledger_artifacts.py` | the engine's `Ledger` | `outputs/nanjing-v1/completion-ledger-v1/` | re-derive any rule decision |
| Delivery + provenance generation | `io/derived_delivery_artifacts.py` | ledger artifact + source bytes | `data/**`, `provenance/**`, archive | invent a rule decision or an identifier |
| Validation / reporting | `validation/completion_export.py` | ledger + delivery + upstream | reason-code verdicts | import engine internals |

**Frozen upstreams — read-only, never written.** `outputs/nanjing-e1/source-import-v2/`, `outputs/nanjing-e2/topology-v1/`, `outputs/nanjing-e2-2/feeder-coverage-v1/`, `outputs/nanjing-e2-2/switch-projection-design-v1/`, `outputs/nanjing-e2-3/topology-recovery-evidence-v1/`, `.../synthetic-completion-contract-v1/`, `.../synthetic-topology-proposals-v1/`, `.../deterministic-topology-recovery-v1/`, `.../accepted-topology-v2/`, `.../synthetic-backbone-proposals-v1/`, `.../placement-evidence-v1-1/`, `.../case-boundary-audit-v1/`, and `data/raw/**`.

**Explicitly out of scope for edit.** `models/records.py`, `models/topology.py`, `models/identifiers.py`, `io/nanjing_source/locator.py`, `io/nanjing_source/csv_reader.py`, `io/nanjing_source/schema.py`, `io/nanjing_source/archive.py`, `validation/reference_resolution.py`, `generation/topology.py`, `generation/deterministic_recovery.py`, and every `io/*_artifacts.py` that predates this slice. `canonical_json.py`, `switch_projection_artifacts.check_output` and the `verify_*` functions are **imported, never copied**.

**Data flow.**

```text
data/raw/南京数据.zip ──(source_bytes, read-only)────────────────────────┐
                                                                        │
source ─┐                                                               │
baseline┤                                                               │
projection┤                                                             │
feeder ─┤                                                               │
recovery┤   verify_*  →  bindings                                       │
d1 ─────┤        │                                                      │
d2 ─────┤        ▼                                                      │
frozen ─┤  build_ledger(policy, inputs)  ──► Ledger ──► completion-ledger-v1/
d3_analysis┤      (pure, no IO)                 │                       │
accepted_v2┤                                    ▼                       │
d4 ─────┤                            materialize(ledger, source_bytes)  │
placement┤                                      │                       │
audit ──┘                                       ▼                       ▼
                                        derived-delivery-v1/ + archive
```

---

## 2. File map

**Create**

| Path | Slice | Responsibility |
|---|---:|---|
| `src/grid_case_generator/models/completion_export.py` | 1 | policy model, enums, ID namespaces |
| `src/grid_case_generator/io/source_bytes.py` | 3 | verbatim zip member bytes and raw logical-record slicing |
| `src/grid_case_generator/generation/completion_ledger.py` | 2,4–7 | the four rules plus the UNRESOLVED taxonomy; pure |
| `src/grid_case_generator/io/completion_ledger_artifacts.py` | 8 | ledger writer/verifier |
| `src/grid_case_generator/io/derived_delivery_artifacts.py` | 4,6,7,9,10,11 | CSV, provenance, manifest, report, archive |
| `src/grid_case_generator/validation/completion_export.py` | 11 | independent re-derivation |
| `src/grid_case_generator/analysis/completion_export_cli.py` | 12 | `analyze` / `verify` |
| `tests/generation/completion_fixture.py` | 4 | synthetic case, upstream artifact and delivery fixtures |
| `tests/generation/test_source_bytes.py` | 3 | |
| `tests/generation/test_completion_policy.py` | 1 | |
| `tests/generation/test_completion_ledger.py` | 2,5,6,7 | |
| `tests/generation/test_completion_ledger_artifacts.py` | 8,11 | |
| `tests/generation/test_derived_delivery_artifacts.py` | 4,6,7,9,10,11 | |
| `tests/generation/test_completion_export_e2e.py` | 12 | |
| `docs/guides/nanjing_v1_completion_export.md` | 12 | run instructions |

**Modify.** `README.md` (one line: the slice and its guide link). The spec is **not** modified by any slice: its 1.1.0 revision was committed separately, before this plan.

---

## 3. Slice 1 — Policy loading and validation

**Goal.** A validated, immutable `CompletionPolicy` whose canonical bytes are the run's identity, matching the 1.1.0 contract established by revision 001.

**Files.** Create `src/grid_case_generator/models/completion_export.py`, `tests/generation/test_completion_policy.py`. Modify `docs/spec/nanjing_v1_completion_export.md`.

**Interfaces.**

```python
VERSION = '1.1.0'
RULE_VERSION = '1.0.0'
PLACEMENT_BUS_RULE_VERSION = '1.1.0'
SCHEMA = 'nanjing_completion_policy_v1'
PASSTHROUGH_RULE = 'SOURCE_PASSTHROUGH_V1'
RECOVERY_RULE = 'ACCEPTED_DETERMINISTIC_RECOVERY_V1'
CROSS_CASE_RULE = 'CROSS_CASE_REFERENCE_COPY_V1'
PLACEMENT_BUS_RULE = 'PLACEMENT_MISSING_ENDPOINT_BUS_V1'
INFERENCE_RULES = (RECOVERY_RULE, CROSS_CASE_RULE, PLACEMENT_BUS_RULE)
TIERS = ('SAME_STATION', 'CROSS_STATION')
LEDGER_NAMESPACE = 'v1-completion:ledger:'
PROVENANCE_NAMESPACE = 'v1-completion:provenance:'
REQUIRED_KEYS = frozenset({'schema_version', 'policy_version', 'materialize_tiers',
    'enabled_rules', 'max_reference_closure_depth', 'placement_endpoint_bus'})


class CompletionStatus(StrEnum):
    CONFIRMED = 'CONFIRMED'
    PROPOSED = 'PROPOSED'
    UNRESOLVED = 'UNRESOLVED'


class ConfidenceClass(StrEnum):
    EXACT_STRUCTURAL = 'EXACT_STRUCTURAL'
    UNIQUE_EVIDENCE = 'UNIQUE_EVIDENCE'
    ENGINEERING_DEFAULT = 'ENGINEERING_DEFAULT'
    NONE = 'NONE'


@dataclass(frozen=True, slots=True, kw_only=True)
class CompletionPolicy:
    policy_version: str
    materialize_tiers: tuple[str, ...]
    enabled_rules: tuple[str, ...]
    max_reference_closure_depth: int
    placement_endpoint_bus: bool


def parse_policy(path) -> CompletionPolicy: ...
def policy_bytes(policy: CompletionPolicy) -> bytes: ...
def policy_sha256(policy: CompletionPolicy) -> str: ...
def ledger_id(payload: dict) -> str: ...
def provenance_id(payload: dict) -> str: ...
```

**Implementation.** `parse_policy` reads `Path(path).read_bytes()`, `json.loads`, then requires `set(raw) == REQUIRED_KEYS`, raising `ValueError('v1 policy unknown or missing field')` on any difference — an unknown field is a hard failure, matching the contract's "no rule may read configuration from anywhere else". Then, in order: `raw['schema_version'] != SCHEMA` → `ValueError('v1 policy schema version')`; `type(raw['policy_version']) is not str or not raw['policy_version']` → `ValueError('v1 policy version')`; `materialize_tiers` a non-empty `list[str]` subset of `TIERS` with no duplicates → else `ValueError('v1 policy materialize tiers')`; `enabled_rules` a non-empty `list[str]` subset of `INFERENCE_RULES` with no duplicates → else `ValueError('v1 policy enabled rules')`; `type(max_reference_closure_depth) is int` (note: `bool` is a subclass of `int`, so test `type(...) is int`) and `0 <= value <= 8` → else `ValueError('v1 policy closure depth')`; `type(placement_endpoint_bus) is bool` → else `ValueError('v1 policy placement flag')`. Both sequences are converted to `tuple` and **sorted**, so policy semantics never depend on file order.

`policy_bytes` is `canonical_json_bytes({...same six keys...}) + b'\n'`; `policy_sha256` is `sha256(policy_bytes(policy)).hexdigest()`. `ledger_id` / `provenance_id` are `NS + sha256(canonical_json_bytes(payload)).hexdigest()`.

- [ ] **Step 1: Write the failing test**

```python
import json

import pytest
from grid_case_generator.models.completion_export import (
    INFERENCE_RULES, SCHEMA, CompletionPolicy, parse_policy, policy_bytes, policy_sha256,
)

VALID = {
    'schema_version': SCHEMA,
    'policy_version': '1.0.0',
    'materialize_tiers': ['SAME_STATION'],
    'enabled_rules': list(INFERENCE_RULES),
    'max_reference_closure_depth': 2,
    'placement_endpoint_bus': True,
}


def write(tmp_path, policy):
    path = tmp_path / 'policy.json'
    path.write_bytes(json.dumps(policy).encode())
    return path


def test_shipped_v1_policy_parses_and_is_frozen():
    policy = parse_policy('configs/nanjing_completion_policy_v1.json')
    assert isinstance(policy, CompletionPolicy)
    assert policy.materialize_tiers == ('SAME_STATION',)
    assert policy.max_reference_closure_depth == 2
    assert policy.placement_endpoint_bus is True
    with pytest.raises(Exception):
        policy.materialize_tiers = ('CROSS_STATION',)


def test_unknown_field_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='unknown or missing field'):
        parse_policy(write(tmp_path, dict(VALID, materialize_cross_case=True)))


@pytest.mark.parametrize('key', sorted(VALID))
def test_missing_field_is_rejected(tmp_path, key):
    bad = {k: v for k, v in VALID.items() if k != key}
    with pytest.raises(ValueError, match='unknown or missing field'):
        parse_policy(write(tmp_path, bad))


def test_schema_version_is_pinned(tmp_path):
    with pytest.raises(ValueError, match='schema version'):
        parse_policy(write(tmp_path, dict(VALID, schema_version='nanjing_v1')))


def test_source_passthrough_is_not_a_lever(tmp_path):
    with pytest.raises(ValueError, match='enabled rules'):
        parse_policy(write(tmp_path, dict(VALID, enabled_rules=['SOURCE_PASSTHROUGH_V1'])))


@pytest.mark.parametrize('field,value', [
    ('materialize_tiers', []),
    ('materialize_tiers', ['SAME_STATION', 'SAME_STATION']),
    ('materialize_tiers', ['CROSS_FEEDER']),
    ('materialize_tiers', 'SAME_STATION'),
    ('enabled_rules', []),
    ('enabled_rules', ['CROSS_CASE_REFERENCE_COPY_V1', 'CROSS_CASE_REFERENCE_COPY_V1']),
    ('enabled_rules', ['SOURCE_PASSTHROUGH_V1']),
    ('max_reference_closure_depth', -1),
    ('max_reference_closure_depth', 9),
    ('max_reference_closure_depth', True),
    ('max_reference_closure_depth', '2'),
    ('placement_endpoint_bus', 'yes'),
    ('placement_endpoint_bus', 1),
])
def test_invalid_values_are_rejected(tmp_path, field, value):
    with pytest.raises(ValueError):
        parse_policy(write(tmp_path, dict(VALID, **{field: value})))


def test_policy_bytes_ignore_input_order(tmp_path):
    a = parse_policy(write(tmp_path, VALID))
    b = parse_policy(write(tmp_path, dict(VALID, enabled_rules=list(reversed(INFERENCE_RULES)))))
    assert policy_bytes(a) == policy_bytes(b)
    assert policy_sha256(a) == policy_sha256(b)
    assert policy_bytes(a).endswith(b'\n')
    assert json.loads(policy_bytes(a)) == dict(VALID)
```

- [ ] **Step 2: Run** `uv run --frozen python -m pytest tests/generation/test_completion_policy.py -v` — expect a collection error: `No module named 'grid_case_generator.models.completion_export'`.
- [ ] **Step 3: Implement** `models/completion_export.py`. Match `models/proposals.py`: `StrEnum` from `enum`, `@dataclass(frozen=True, slots=True, kw_only=True)`, `canonical_json_bytes` imported from `grid_case_generator.io.canonical_json`.
- [ ] **Step 4: Run** the same command — expect all PASS.
- [ ] **Step 5: Confirm the contract revision is already in place.** `docs/spec/nanjing_v1_completion_export.md` must read `1.1.0` and link
  `docs/spec/revisions/nanjing_v1_completion_export_revision_001.md`; `configs/nanjing_completion_policy_v1.json` must carry `policy_version` `1.1.0`. This was committed
  separately as the contract revision, before this plan. No spec edit belongs in this slice; if a discrepancy is found, stop and raise it rather than editing frozen semantics.
- [ ] **Step 6: Commit.**

```bash
git add src/grid_case_generator/models/completion_export.py \
        tests/generation/test_completion_policy.py \
        docs/spec/nanjing_v1_completion_export.md
git commit -m "feat: add v1 completion policy model and correct contract inputs"
```

**Acceptance criteria.** Every malformed policy raises `ValueError` before any output path is touched; the policy is immutable; two orderings of the same policy hash identically; the spec no longer claims a `voltage_evidence` field on proposal rows, a Case-local `Bus_Station_ID`, or a self-referential manifest.

---

## 4. Slice 2 — Completion rule execution framework

**Goal.** The pure scaffold: `Ledger` and record value types, deterministic record identity, deterministic emission order, and the bounded closure walker. Rule bodies land in Slices 4–7.

**Files.** Create `src/grid_case_generator/generation/completion_ledger.py`, `tests/generation/test_completion_ledger.py`.

**Interfaces.**

```python
RECORD_KEYS = ('record_id', 'completion_status', 'confidence_class', 'tier', 'rule_id',
    'rule_version', 'case_id', 'source_case_key', 'source_entity_type',
    'donor_source_entity_type', 'source_record_ref', 'donor_source_record_ref',
    'raw_field', 'raw_reference_value', 'evidence_refs', 'closure_depth',
    'policy_version', 'policy_sha256', 'reason')


@dataclass(frozen=True, slots=True, kw_only=True)
class CompletionInputs:
    policy: CompletionPolicy
    source_case_key_by_case: Mapping[str, str]
    audit_rows: tuple[dict, ...]
    accepted_additions: tuple[dict, ...]
    placement_proposals: tuple[dict, ...]
    endpoint_evidence: tuple[dict, ...]
    placement_feeders: tuple[dict, ...]
    backbone_taxonomy: tuple[dict, ...]
    audit_classification: tuple[dict, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Ledger:
    completion_records: tuple[dict, ...]
    unresolved_records: tuple[dict, ...]
    case_summary: tuple[dict, ...]
    counts: dict


def build_ledger(inputs: CompletionInputs) -> Ledger: ...
def closure_key(case_id: str, source_entity_type: str, source_id: str) -> tuple[str, str, str]: ...
def walk_closure(seed, lookup, *, max_depth): ...
def record(**fields) -> dict: ...
```

**Record shape.** Every record is a plain `dict` of `str`/`int`/`bool`/`None`/`list`/`dict` — `canonical_json_bytes` rejects floats outright, so no ratio is ever stored as a float. `record(**fields)` fills every `RECORD_KEYS` entry, defaulting the nullable ones to `None`, and computes `record_id` last as `ledger_id({k: r[k] for k in RECORD_KEYS if k not in ('record_id', 'reason')})`. `reason` is excluded from identity so refining a reason's wording does not change any `record_id`.

**Emission order.** `build_ledger` returns records sorted once, here, never in the writer: `completion_records` by `(rule_id, case_id, record_id, reason, canonical bytes)` and `unresolved_records` by `(reason, case_id, record_id, canonical bytes)`, with the leading fields coerced so a `None` never meets a `str`; the canonical-bytes tiebreak makes each order total over any canonical row shape. `case_summary` by `(case_id, canonical bytes)`.

**Closure walker.** `walk_closure(seed, lookup, *, max_depth)` yields `(key, meta)` in deterministic breadth-first order, where `key = closure_key(*ref)` and `meta = {'depth': int, 'depth_exceeded': bool, 'reference': ref}`. `lookup(key)` returns an iterable of refs. Behaviour: the seed is marked visited but not yielded; every frontier is `sorted()` before expansion; a key already visited is skipped; a key whose `depth > max_depth` is **yielded with `depth_exceeded=True` and not expanded**, so the overflow is reported rather than silently dropped; iteration terminates when the frontier empties. The walker never reads a clock, a random source, or filesystem order.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from grid_case_generator.generation.completion_ledger import (
    RECORD_KEYS, closure_key, record, walk_closure,
)


def chain(*pairs):
    edges = {}
    for a, b in pairs:
        edges.setdefault(closure_key('case:a', 'SWITCH', a), []).append(
            ('case:a', 'SWITCH', b))
    return edges


def keys(seed, edges, max_depth):
    return [k for k, _ in walk_closure(seed, lambda k: edges.get(k, ()), max_depth=max_depth)]


def test_record_key_set_is_exact():
    assert set(RECORD_KEYS) == {
        'record_id', 'completion_status', 'confidence_class', 'tier', 'rule_id',
        'rule_version', 'case_id', 'source_case_key', 'source_entity_type',
        'donor_source_entity_type', 'source_record_ref', 'donor_source_record_ref',
        'raw_field', 'raw_reference_value', 'evidence_refs', 'closure_depth',
        'policy_version', 'policy_sha256', 'reason'}


def test_record_fills_every_key_and_is_identity_stable():
    r = record(rule_id='SOURCE_PASSTHROUGH_V1', case_id='case:a', reason='FIRST')
    assert set(r) == set(RECORD_KEYS)
    assert r['tier'] is None and r['donor_source_record_ref'] is None
    renamed = record(rule_id='SOURCE_PASSTHROUGH_V1', case_id='case:a', reason='SECOND')
    assert r['record_id'] == renamed['record_id']
    assert r['record_id'].startswith('v1-completion:ledger:')


def test_closure_key_orders_case_locally():
    assert closure_key('case:a', 'SWITCH', '1') < closure_key('case:a', 'SWITCH', '2')
    assert closure_key('case:a', 'BUS', '1') < closure_key('case:a', 'SWITCH', '1')
    assert closure_key('case:a', 'SWITCH', '1') < closure_key('case:b', 'SWITCH', '1')


def test_closure_is_bounded_and_reports_the_overflow():
    edges = chain(('a', 'b'), ('b', 'c'), ('c', 'd'))
    seed = closure_key('case:a', 'SWITCH', 'a')

    full = list(walk_closure(seed, lambda k: edges.get(k, ()), max_depth=2))
    assert [m['depth'] for _, m in full] == [1, 2, 3]
    assert [m['depth_exceeded'] for _, m in full] == [False, False, True]

    shallow = list(walk_closure(seed, lambda k: edges.get(k, ()), max_depth=1))
    assert [m['depth'] for _, m in shallow] == [1, 2]
    assert [m['depth_exceeded'] for _, m in shallow] == [False, True]

    zero = list(walk_closure(seed, lambda k: edges.get(k, ()), max_depth=0))
    assert [m['depth_exceeded'] for _, m in zero] == [True]
    assert len(zero) == 1, 'an over-deep node must not be expanded'


def test_closure_terminates_on_a_cycle_and_a_self_reference():
    assert len(keys(closure_key('case:a', 'SWITCH', 'a'),
                     chain(('a', 'b'), ('b', 'a')), 8)) == 1
    # The seed is marked visited and never yielded, so a self-reference reaches an
    # already-visited node and yields nothing.
    assert len(keys(closure_key('case:a', 'SWITCH', 'a'),
                     chain(('a', 'a')), 8)) == 0


def test_closure_is_independent_of_lookup_order():
    forward = {'case:a': [('case:a', 'SWITCH', 'b'), ('case:a', 'SWITCH', 'c')]}
    backward = {'case:a': [('case:a', 'SWITCH', 'c'), ('case:a', 'SWITCH', 'b')]}
    lookup = lambda table: (lambda k: table.get(k[0], ()) if k[1] == 'SWITCH' and k[2] == 'a' else ())
    a = keys(closure_key('case:a', 'SWITCH', 'a'), lookup(forward), 2)
    b = keys(closure_key('case:a', 'SWITCH', 'a'), lookup(backward), 2)
    assert a == b
```

- [ ] **Step 2: Run** — expect a collection error.
- [ ] **Step 3: Implement** the scaffold. `build_ledger` returns empty tuples and zeroed counts at this stage.
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `feat: add v1 completion ledger scaffold and bounded closure walker`.

**Acceptance criteria.** `RECORD_KEYS` matches the contract exactly; `record_id` is stable under a `reason` change; the closure walker is depth-bounded, cycle-safe, never expands an over-deep node, and is independent of lookup order.

---

## 5. Slice 3 — Verbatim source byte access

**Goal.** The single read-only seam to `data/raw/南京数据.zip`: verbatim member bytes and raw logical-record slices, so a donor row copies byte-for-byte and an untouched Case is written through unchanged.

**Why this is its own slice.** `io/nanjing_source/csv_reader.py` parses into `RawCsvRecord`, which keeps only decoded field strings — quoting, delimiters, BOM and line endings are all discarded, so parsed values **cannot** reconstruct the original bytes. `SourceRecordRef` exposes only `.data_row` and has no member-path accessor. Both facts are load-bearing and neither module may be modified, so this slice adds a new read-only seam rather than extending either.

**Files.** Create `src/grid_case_generator/io/source_bytes.py`, `tests/generation/test_source_bytes.py`.

**Interfaces.**

```python
def member_path_of(ref) -> str: ...
def raw_member_bytes(archive: ZipFile, member_path: str) -> bytes: ...
def split_raw_records(member_bytes: bytes) -> tuple[bytes, ...]: ...
def raw_record_bytes(member_bytes: bytes, data_row: int) -> bytes: ...
```

**Implementation.** `member_path_of` re-derives the member path that `SourceRecordRef` does not expose, without touching that class:

```python
def member_path_of(ref):
    text = str(ref)
    if not text.startswith('zip-member:') or '#data-row=' not in text:
        raise ValueError('v1 export: not a source record ref')
    encoded = text[len('zip-member:'):text.index('#data-row=')]
    return unquote_to_bytes(encoded).decode('utf-8')
```

The anchor is the exact format produced by `io/nanjing_source/locator.py:65-73` and validated on construction by `SourceRecordRef.__new__`, so a malformed input cannot reach here. `raw_member_bytes` is `validate_zip_member_path(member_path)` (reused from `io/nanjing_source/locator.py:46`) followed by `archive.read(member_path)`; it never opens the archive itself — the handle is caller-owned, so the whole delivery run opens the ZIP exactly once.

`split_raw_records` is a small RFC-4180 state machine over `member_bytes` returning the raw byte slice of every logical record with its terminator stripped (`\r\n` or `\n`), index 0 being the header. It must agree with `csv.reader(strict=True)` on record boundaries; the tests assert that using `read_raw_csv_member` as the oracle rather than assuming it. `raw_record_bytes(member_bytes, data_row)` is `split_raw_records(member_bytes)[data_row]` — `data_row` is 1-based over data rows, so it indexes directly.

- [ ] **Step 1: Write the failing test**

```python
import csv
import io
from pathlib import Path
from zipfile import ZipFile

import pytest
from grid_case_generator.io.nanjing_source.csv_reader import read_raw_csv_member
from grid_case_generator.io.nanjing_source.locator import source_record_ref
from grid_case_generator.io.nanjing_source.schema import NANJING_SOURCE_SCHEMA
from grid_case_generator.io.source_bytes import (
    member_path_of, raw_member_bytes, raw_record_bytes, split_raw_records,
)

REAL = Path(__file__).parents[2] / 'data' / 'raw' / '南京数据.zip'
BOM = b'\xef\xbb\xbf'


def fixture_member():
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['Switch_ID', 'Switch_FromBus', 'Switch_Note'])
    writer.writerow(['S1', 'B1', 'plain'])
    writer.writerow(['S2', 'B2', 'has, comma'])
    writer.writerow(['S3', 'B3', 'has "quote"'])
    writer.writerow(['S4', 'B4', 'has\nnewline'])
    return BOM + stream.getvalue().encode()


def test_member_path_round_trips_the_locator():
    ref = source_record_ref('数据/甲变_10kV甲线101/03_Switch.csv', data_row=7)
    assert member_path_of(ref) == '数据/甲变_10kV甲线101/03_Switch.csv'


@pytest.mark.parametrize('bad', ['not-a-ref', 'zip-member:x.csv', 'file:x.csv#data-row=1'])
def test_member_path_rejects_a_non_locator(bad):
    with pytest.raises(ValueError, match='not a source record ref'):
        member_path_of(bad)


def test_split_preserves_quoting_verbatim():
    raw = split_raw_records(fixture_member())
    assert len(raw) == 5
    assert raw[0] == 'Switch_ID,Switch_FromBus,Switch_Note'.encode()
    assert raw[2] == b'S2,B2,"has, comma"'
    assert raw[3] == b'S3,B3,"has ""quote"""'
    assert raw[4] == b'S4,B4,"has\nnewline"'


def test_raw_record_index_is_one_based_over_data_rows():
    member = fixture_member()
    assert raw_record_bytes(member, 1) == b'S1,B1,plain'
    assert raw_record_bytes(member, 4) == b'S4,B4,"has\nnewline"'
    with pytest.raises(IndexError):
        raw_record_bytes(member, 5)


def test_empty_body_trailing_newline_and_crlf_variants():
    assert len(split_raw_records(BOM + b'A,B\r\n')) == 1
    assert len(split_raw_records(BOM + b'A,B\r\n1,2\r\n')) == 2
    assert len(split_raw_records(BOM + b'A,B\r\n1,2')) == 2
    assert len(split_raw_records(BOM + b'A,B\n1,2\n')) == 2


def test_terminators_are_stripped_but_content_bytes_are_not():
    raw = split_raw_records(BOM + b'A,B\r\n1,2\r\n')
    assert not any(b'\r' in r or b'\n' in r for r in raw)


@pytest.mark.skipif(not REAL.exists(), reason='raw archive not present')
def test_split_agrees_with_the_parser_on_real_members():
    schema = NANJING_SOURCE_SCHEMA.for_filename('03_Switch.csv')
    assert schema is not None
    with ZipFile(REAL, 'r') as archive:
        names = [n for n in archive.namelist() if n.endswith('/03_Switch.csv')][:200]
        assert names
        for name in names:
            member = raw_member_bytes(archive, name)
            parsed = read_raw_csv_member(
                archive, source_case_key=name.rpartition('/')[0],
                member_path=name, file_schema=schema)
            assert len(split_raw_records(member)) == len(parsed.records) + 1, name
```

- [ ] **Step 2: Run** — expect a collection error.
- [ ] **Step 3: Implement** `io/source_bytes.py`. Preserve the first record's BOM in its raw slice (index 0) so a passthrough of a header-only member is still byte-identical; only `test_split_preserves_quoting_verbatim`'s `raw[0]` assertion is written against the stripped form, so strip the BOM from index 0 and note it in the docstring.
- [ ] **Step 4: Run** `uv run --frozen python -m pytest tests/generation/test_source_bytes.py -v` — expect PASS, including the 200-member real-archive agreement test.
- [ ] **Step 5: Run** `git diff --stat` — expect only new files under `src/grid_case_generator/io/` and `tests/`. No module under `io/nanjing_source/` may appear.
- [ ] **Step 6: Commit** `feat: add verbatim source byte access for v1 export`.

**Acceptance criteria.** The splitter agrees with `read_raw_csv_member` on record count for every sampled real member; quoting, embedded newlines, commas and CRLF survive verbatim; no pre-existing module is modified.

---

## 6. Slice 4 — `SOURCE_PASSTHROUGH_V1` delivery writer

**Goal.** The unconditional baseline: every source member is written byte-identically, and one `SOURCE` provenance record is emitted per source row.

**Files.** Create `src/grid_case_generator/io/derived_delivery_artifacts.py` (writer core), `tests/generation/completion_fixture.py`, `tests/generation/test_derived_delivery_artifacts.py`.

**Interfaces.**

```python
DELIVERY_DATA_DIR = 'data'
PROVENANCE_DIR = 'provenance'
ARCHIVE_NAME = 'nanjing-derived-v1.zip'
ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def passthrough_member(archive, member_path, destination) -> None: ...
def write_delivery(root, *, cases, ledger, policy, progress=None) -> dict: ...
```

`cases` is an iterator of `(case_id, source_case_key, members)`, where `members` is the ordered `(SourceFileType, member_path)` tuple from the verified `source-import-v2/inventory.json`. For each member the writer calls `raw_member_bytes` and writes the bytes through a `Path.open('xb')` handle — **never** `csv.writer`, never a decode/encode round trip, never a newline translation. The destination is `data/<source_case_key>/<filename>`; `source_case_key` is used verbatim as path segments (`数据/<dir>`), and `validate_zip_member_path` on the source side already forbids `..`, absolute paths and drive letters.

`write_delivery` opens the archive once around the whole case loop, calls the per-row provenance callback (Slice 9) once per source row with `row_kind='SOURCE'`, and returns a counts dict.

- [ ] **Step 1: Write the failing test**

```python
import json
from zipfile import ZipFile

import pytest
from grid_case_generator.io.derived_delivery_artifacts import write_delivery


def test_untouched_case_is_byte_identical(tmp_path, delivery_fixture):
    root = tmp_path / 'delivery'
    write_delivery(root, **delivery_fixture.write_args())
    with ZipFile(delivery_fixture.archive, 'r') as archive:
        for _, member_path in delivery_fixture.members:
            assert (root / 'data' / member_path).read_bytes() == archive.read(member_path)


def test_output_is_write_once(tmp_path, delivery_fixture):
    root = tmp_path / 'delivery'
    write_delivery(root, **delivery_fixture.write_args())
    with pytest.raises(FileExistsError):
        write_delivery(root, **delivery_fixture.write_args())


def test_every_source_row_gets_a_provenance_record(tmp_path, delivery_fixture):
    root = tmp_path / 'delivery'
    result = write_delivery(root, **delivery_fixture.write_args())
    rows = [json.loads(line) for line in
            (root / 'provenance' / 'row_provenance.jsonl').read_bytes().splitlines()]
    source = [r for r in rows if r['row_kind'] == 'SOURCE']
    assert len(source) == delivery_fixture.source_row_count
    assert {r['rule_id'] for r in source} == {'SOURCE_PASSTHROUGH_V1'}
    assert {r['completion_status'] for r in source} == {'CONFIRMED'}
    assert {r['confidence_class'] for r in source} == {'EXACT_STRUCTURAL'}
    assert all(r['donor_source_record_ref'] is None for r in source)
    assert all(r['tier'] is None for r in source)
    assert result['source_rows'] == delivery_fixture.source_row_count


def test_all_twelve_files_are_delivered_for_a_case_with_no_feeder(tmp_path, delivery_fixture):
    root = tmp_path / 'delivery'
    write_delivery(root, **delivery_fixture.write_args())
    feaderless = root / 'data' / delivery_fixture.feederless_key
    assert len(list(feederless.iterdir())) == 12


def test_no_output_path_may_nest_inside_an_input_root(tmp_path, delivery_fixture):
    with pytest.raises(ValueError, match='separate from every input'):
        write_delivery(delivery_fixture.roots['source'] / 'delivery',
                       **delivery_fixture.write_args())
```

- [ ] **Step 2: Run** — expect a collection error.
- [ ] **Step 3: Implement** the writer core, reusing `check_output` imported from `io/switch_projection_artifacts.py:21`, then the inline `data/raw` predicate, `raise FileExistsError(root)`, `root.mkdir(parents=True)`, exactly as `io/placement_evidence_artifacts.py:295-303` does. Build `completion_fixture.py` with a `DeliveryFixture` exposing `archive`, `members`, `roots`, `key_for(...)`, `write_args()`, `source_row_count`, `feederless_key`.
- [ ] **Step 4: Run** `uv run --frozen python -m pytest tests/generation/test_derived_delivery_artifacts.py -v` — expect PASS.
- [ ] **Step 5: Commit** `feat: write byte-identical source passthrough for v1 delivery`.

**Acceptance criteria.** Every delivered member equals `archive.read(member_path)` byte-for-byte; the directory is write-once; one `SOURCE` provenance record exists per source row; a Case without a published Feeder still gets all twelve files; an output path inside an input root is refused.

---

## 7. Slice 5 — `ACCEPTED_DETERMINISTIC_RECOVERY_V1` and the UNRESOLVED cohort taxonomy

**Goal.** The two ledger-only rule families: recoveries that append no CSV row, and the cohort gaps that append no CSV row and must still be reported per item.

**Files.** Extend `generation/completion_ledger.py`, `tests/generation/test_completion_ledger.py`.

**Interfaces.**

```python
COHORT_REASONS = ('INSUFFICIENT_PLACEMENT_EVIDENCE', 'NON_UNIQUE_PLACEMENT',
                  'MANUAL_LAYOUT_REQUIRED', 'NO_SOURCE_LINE_LAYOUT_BASIS')


def recovery_records(inputs: CompletionInputs) -> tuple[dict, ...]: ...
def cohort_records(inputs: CompletionInputs) -> tuple[dict, ...]: ...
```

**`recovery_records`.** Consumes `inputs.accepted_additions` (`accepted-topology-v2/additions.jsonl`, 59,354 records, rules `SERIES_EXACT_DIRECT_V2` and `LEAF_SWITCH_REPRESENTATION_V2`, both `ACCEPTED`). Emits one `CONFIRMED` / `EXACT_STRUCTURAL` record per addition with `rule_id=RECOVERY_RULE`, `tier=None`, `source_entity_type='EQUIPMENT'`, `source_record_ref` set to the addition's first `supporting_source_refs` entry after sorting (the addition's refs are already sorted-unique by the D3 contract), `donor_source_entity_type=None`, `donor_source_record_ref=None`, `raw_field=None`, `raw_reference_value=None`, `closure_depth=0`, and `evidence_refs=[addition['edge_id'], f"{addition['rule_id']}/{addition['rule_version']}"]`. It appends **no** CSV row; the writer's appended-row set is empty for this rule and the delivery verifier asserts it.

**`cohort_records`.** Emits one `UNRESOLVED` / `NONE` record per cohort member. The predicates below were verified against the persisted artifacts, not inferred; measured populations are given for each.

| Reason | Source stream | Predicate | Measured |
|---|---|---|---:|
| `INSUFFICIENT_PLACEMENT_EVIDENCE` | `placement-evidence-v1-1/feeder_classification.jsonl` | `primary_status == 'INSUFFICIENT_PLACEMENT_EVIDENCE'` | 78 |
| `NON_UNIQUE_PLACEMENT` | same | `primary_status == 'NON_UNIQUE_PLACEMENT'` | 8 |
| `MANUAL_LAYOUT_REQUIRED` | `synthetic-backbone-proposals-v1/feeder_gap_taxonomy.jsonl` | `d3_primary == 'SYNTHETIC_BACKBONE_REQUIRED'` **and** `outcome == 'MANUAL_LAYOUT_REQUIRED'` | 1,401 |
| `NO_SOURCE_LINE_LAYOUT_BASIS` | same | `d3_primary == 'SYNTHETIC_BACKBONE_REQUIRED'` **and** `outcome == 'MANUAL_LAYOUT_REQUIRED'` **and** `source_line_count == 0` | 1,259 |

Field names matter and were wrong in an earlier draft of this plan. `feeder_classification.jsonl` keys its verdict as **`primary_status`**, not `classification`. `feeder_gap_taxonomy.jsonl` carries the D2-derived class in **`d3_primary`** and the D4 verdict in **`outcome`**; there is no `primary_gap` field, and `taxonomy_primary` is a *different* axis whose value set (`ACCESS_POINT_GAP`, `DISCONNECTED_SOURCE_LINE_COMPONENTS`, `HEAD_TO_SOURCE_COMPONENT_GAP`, `INSUFFICIENT_STRUCTURE`, `TRANSFORMER_REGION_GAP`, `REMOTE_SWITCH_PORT_GAP`) contains no `MANUAL_LAYOUT_REQUIRED` at all. Both streams already carry `case_id`, `source_case_key` and `feeder_id`.

**The `SYNTHETIC_BACKBONE_REQUIRED` cohort is 1,402 rows**, and its three-way split is exact: 1,259 with no source Line, 142 with source Lines, and 1 `AUTOMATIC_PROPOSAL_ELIGIBLE`. So `MANUAL_LAYOUT_REQUIRED` (1,401) is the first two groups and `NO_SOURCE_LINE_LAYOUT_BASIS` (1,259) is a **strict subset** of it. Those 1,259 Feeders therefore each receive **two** `UNRESOLVED` records, one per reason, and `counts['cohort_overlap_members']` reports 1,259 — the contract's "states the overlap rather than summing silently" exists for exactly this scale. The two reasons are genuinely distinct problems and both are reported; the cohorts are deliberately **not** made mutually exclusive.

Each record carries the cohort's own `case_id`, `source_case_key` and `feeder_id`. `source_record_ref` is a ledger-level identifier of the form `cohort:<reason>:<case_id>:<feeder_id>` — the streams' own `feeder_id` is a Canonical id, not a source locator, so synthesising a stable locator is honest whereas passing a Canonical id off as a source row would not be. It must **not** go through `SourceRecordRef`, which validates the `zip-member:…` format. `evidence_refs` cites the emitting artifact: `feeder_classification.jsonl/<feeder_id>` for the placement cohort, and `feeder_gap_taxonomy.jsonl/<feeder_id>` plus the `d3_primary` class for the backbone cohorts.

`build_ledger` de-duplicates on `(reason, case_id, source_record_ref)` so a stream that repeats a row cannot inflate a count; first occurrence wins.

**The overlap key is deliberately *not* `source_record_ref`.** That value embeds the reason, so the same Feeder under two reasons necessarily yields two distinct `source_record_ref`s and grouping by it would report zero overlap — against a true value of 1,259. `counts['cohort_overlap_members']` therefore counts distinct **`(case_id, feeder_id)`** identities appearing under more than one reason, which is the reason-independent notion of "this Feeder is in two cohorts". An earlier draft of this plan defined it on `source_record_ref` and was arithmetically incapable of ever returning a non-zero count.

- [ ] **Step 1: Write the failing test**

```python
def test_recovery_records_are_confirmed_and_append_nothing(ledger_fixture):
    ledger = ledger_fixture.build_recovery()
    assert ledger.completion_records
    assert {r['rule_id'] for r in ledger.completion_records} == {'ACCEPTED_DETERMINISTIC_RECOVERY_V1'}
    assert {r['completion_status'] for r in ledger.completion_records} == {'CONFIRMED'}
    assert {r['confidence_class'] for r in ledger.completion_records} == {'EXACT_STRUCTURAL'}
    assert all(r['donor_source_record_ref'] is None for r in ledger.completion_records)
    assert all(r['raw_reference_value'] is None for r in ledger.completion_records)
    assert ledger_fixture.appended_row_count(ledger) == 0


def test_recovery_records_cite_the_persisted_edge_and_rule(ledger_fixture):
    ledger = ledger_fixture.build_recovery()
    first = min(ledger.completion_records, key=lambda r: r['record_id'])
    assert any(e.startswith('deterministic-v2:') for e in first['evidence_refs'])
    assert any('LEAF_SWITCH_REPRESENTATION_V2' in e or 'SERIES_EXACT_DIRECT_V2' in e
               for e in first['evidence_refs'])


@pytest.mark.parametrize('source,reason', [
    ('placement', 'INSUFFICIENT_PLACEMENT_EVIDENCE'),
    ('placement', 'NON_UNIQUE_PLACEMENT'),
    ('backbone', 'MANUAL_LAYOUT_REQUIRED'),
    ('audit', 'NO_SOURCE_LINE_LAYOUT_BASIS'),
])
def test_each_cohort_reason_is_emitted(ledger_fixture, source, reason):
    ledger = ledger_fixture.build_cohort(source)
    assert {r['reason'] for r in ledger.unresolved_records} == {reason}
    assert {r['completion_status'] for r in ledger.unresolved_records} == {'UNRESOLVED'}
    assert {r['confidence_class'] for r in ledger.unresolved_records} == {'NONE'}
    assert not ledger.completion_records


def test_cohort_overlap_is_deduplicated_not_summed(ledger_fixture):
    ledger = ledger_fixture.build_cohort('placement', also_in_backbone=True)
    assert len(ledger.unresolved_records) == 2
    assert ledger.counts['cohort_overlap_members'] == 1


def test_no_cohort_record_produces_a_csv_row(ledger_fixture):
    ledger = ledger_fixture.build_cohort('all')
    assert ledger_fixture.appended_row_count(ledger) == 0
```

- [ ] **Step 2: Run** — expect failures.
- [ ] **Step 3: Implement** both rule families, and wire them into `build_ledger` behind `policy.enabled_rules` (recovery only) and unconditional for the cohort taxonomy.
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `feat: emit accepted-recovery records and the unresolved cohort taxonomy`.

**Acceptance criteria.** Recovery records are `CONFIRMED`/`EXACT_STRUCTURAL` and append nothing; every cohort reason is emitted per item, not merely counted; overlap between cohorts is de-duplicated with an explicit overlap count.

---

## 8. Slice 6 — `CROSS_CASE_REFERENCE_COPY_V1` materialization

**Goal.** Copy a donor Case's source row verbatim into the referring Case under the contract's nine preconditions (revision 003), with the tier gate and the bounded closure. This is the first slice that appends a row to a delivered CSV.

**Files.** Extend `generation/completion_ledger.py` and `io/derived_delivery_artifacts.py`.

**Interfaces.**

```python
def cross_case_records(inputs: CompletionInputs) -> tuple[dict, ...]: ...
def eligible(row, tiers) -> tuple[bool, str]: ...
def append_raw_rows(handle, archive, rows) -> int: ...
```

**Preconditions**, evaluated in this order so that exactly one reason is recorded per audit row. This is revision 003's corrected list, which is exactly the audit's `strict_candidate` predicate:

```python
def eligible(row, tiers, cases):
    if row['classification'] != 'UNIQUE_EXTERNAL_MATCH':
        return False, row['classification']
    if row['external_candidate_count'] != 1:
        return False, 'MULTIPLE_EXTERNAL_MATCH'
    candidate = (row.get('candidates') or [None])[0]
    if candidate is None:
        return False, 'NO_CANONICAL_CANDIDATE'
    if candidate['identity_status'] != 'UNIQUE':
        return False, 'AMBIGUOUS_IDENTITY'
    if not candidate.get('type_compatible'):
        return False, 'TYPE_INCOMPATIBLE'
    if not candidate.get('canonical_ref'):
        return False, 'NO_CANONICAL_CANDIDATE'
    if candidate.get('voltage_relationship') != 'COMPATIBLE':
        return False, 'VOLTAGE_NOT_COMPATIBLE'
    if row.get('local_candidate_count'):
        return False, 'ALSO_RESOLVES_CASE_LOCALLY'
    if cases[row['case_id']].get('hard_blockers'):
        return False, 'REFERRING_CASE_HARD_BLOCKER'
    if cases[candidate['case_id']].get('hard_blockers'):
        return False, 'DONOR_CASE_HARD_BLOCKER'
    if candidate['station_relationship'] not in tiers:
        return False, 'TIER_NOT_MATERIALIZED'
    return True, ''
```

`cases` is the audit's `case_inventory.jsonl` keyed by `case_id`; it is what supplies both `hard_blockers` gates. Note the last check is the **policy** gate and comes last, so a row excluded by both the tier policy and an evidence gate is attributed to the evidence gate. The order is the contract's and the report's per-reason counts depend on it.

**Measured gate-by-gate, under the v1 policy**, so an implementer can check each step against a known number:

| Gate | Survivors | Removed |
|---|---:|---:|
| six conditions of the superseded 1.0.0 list | 7,818 | — |
| `+ voltage_relationship == 'COMPATIBLE'` | 4,410 | 3,408 |
| `+ canonical_ref present` | 4,410 | 0 |
| `+ local_candidate_count == 0` | 4,410 | 0 |
| `+ referring Case has no hard_blockers` | 2,954 | 1,456 |
| `+ donor Case has no hard_blockers` | **2,544** | 410 |

`MULTIPLE_EXTERNAL_MATCH` must be counted once, not twice, when both `classification == 'MULTIPLE_EXTERNAL_MATCH'` and `external_candidate_count > 1` hold — the first branch returns, so the ordering above handles it. The report's per-reason counts depend on this ordering, so it is not free to reorder.

## The member cache

`raw_record_bytes(member_bytes, data_row)` re-partitions the **whole member** on every call, so a per-row call pattern re-scans a donor member once per copied row. Split each source member once and index the returned tuple:

```python
class _MemberCache:
    """Split each source member at most once, keyed by member path."""
    def __init__(self, archive):
        self._archive, self._records = archive, {}

    def records(self, member_path):
        if member_path not in self._records:
            self._records[member_path] = split_raw_records(
                raw_member_bytes(self._archive, member_path))
        return self._records[member_path]
```

Use `cache.records(donor_member)[donor_data_row]`, never `raw_record_bytes` inside the per-row loop. The same cache serves the member being written, so its own split is reused too.

**Cache footprint, measured for the v1 policy cohort**, which is what makes an unbounded dict safe here rather than merely convenient:

| Measure | Value |
|---|---:|
| materialized rows | 2,544 |
| unique referring Cases | 836 |
| unique referring members (files that receive appended rows) | 955 |
| unique donor Cases | 778 |
| unique donor members | 806 |
| **total uncompressed donor bytes** | **3,242,748 (3.1 MiB)** |
| donor member bytes, min / median / max | 132 / 2,469 / 53,405 |
| rows per donor member, max / mean | 82 / 3.16 |
| donor members reused by more than one referring Case | 361 |

At 3.1 MiB the cache cannot be a memory concern, and 361 of 806 donor members are reused, so it earns its keep. The bound grows only with the closure, which follows references out of the copied rows; measure the closure's incremental donor set when implementing and report it rather than assuming it is small.

## Writing a member that receives appended rows

One `'xb'` open per member, source bytes first, generated bytes last, and never a decode:

```python
def write_member(archive, member_path, destination, appended=()) -> bytes:
    data = raw_member_bytes(archive, member_path)
    with destination.open('xb') as stream:
        stream.write(data)
        if appended:
            if not data.endswith((b'\r\n', b'\n', b'\r')):
                stream.write(b'\r\n')
            stream.write(b'\r\n'.join(appended) + b'\r\n')
    return data
```

`passthrough_member` stays as the no-append entry point and delegates, so its signature and behaviour are unchanged.

The `endswith` check is load-bearing, not defensive. The intake's members all end with a terminator, but a member need not: the synthetic fixture's `06_EarthingSwitch.csv` deliberately does not. Without the check the appended block concatenates onto the final source row and two logical records silently become one, after which the member's row count disagrees with the provenance sidecar. Per revision 003 this separator **exists only to prevent record concatenation** — it is not source normalization, the source region stays verbatim, and a member whose own terminators differ ends up mixed. Report that case; do not normalize it.

The appended rows are the donor's own row bytes, including the donor's original quoting, taken from `cache.records(member_path_of(candidate['source_record_ref']))[candidate_ref.data_row]`.

## Provenance for appended rows

`row_kind` stays `SOURCE | APPENDED` — no new kind is introduced. The recovery reason is carried by the record's other fields, which is what they are for: `rule_id = 'CROSS_CASE_REFERENCE_COPY_V1'`, `rule_version = '1.1.0'`, `completion_status = 'PROPOSED'`, `confidence_class = 'UNIQUE_EVIDENCE'`, `tier = 'SAME_STATION'`, and `evidence_refs` citing the audit row's `reference_id` and the donor's `index_id`. An `APPENDED` record is distinguishable from a `SOURCE` one by `row_kind` alone, which is all the contract requires.

**Closure.** After a row is materialized, its own reference fields are resolved against the audit rows and followed with `walk_closure` bounded by `policy.max_reference_closure_depth`, visited set keyed by `closure_key(target_case_id, source_entity_type, source_id)`. A reference that is already visited, that fails a precondition, or whose depth exceeds the bound becomes an `UNRESOLVED` record with `CLOSURE_DEPTH_EXCEEDED` or the failing precondition's reason, and is counted in the report. Truncation is never silent.

- [ ] **Step 1: Write the failing test**

```python
import pytest


@pytest.mark.parametrize('mutation,reason', [
    ({'classification': 'MULTIPLE_EXTERNAL_MATCH'}, 'MULTIPLE_EXTERNAL_MATCH'),
    ({'external_candidate_count': 2}, 'MULTIPLE_EXTERNAL_MATCH'),
    ({'explicit_voltage_conflict_count': 1}, 'EXPLICIT_VOLTAGE_CONFLICT'),
])
def test_precondition_truth_table_rejects(ledger_fixture, mutation, reason):
    ledger = ledger_fixture.build_cross_case(mutation)
    record, = ledger.unresolved_records
    assert record['reason'] == reason
    assert record['completion_status'] == 'UNRESOLVED'
    assert record['confidence_class'] == 'NONE'
    assert not ledger.completion_records


def test_candidate_identity_and_type_are_required(ledger_fixture):
    assert ('AMBIGUOUS_IDENTITY'
            in ledger_fixture.cross_case_reasons({'identity_status': 'DUPLICATE_IDENTICAL'}))
    assert ('AMBIGUOUS_IDENTITY'
            in ledger_fixture.cross_case_reasons({'identity_status': 'DUPLICATE_CONFLICT'}))
    assert 'TYPE_INCOMPATIBLE' in ledger_fixture.cross_case_reasons({'type_compatible': False})


def test_multiple_candidates_are_recorded_once_not_twice(ledger_fixture):
    ledger = ledger_fixture.build_cross_case(
        {'classification': 'MULTIPLE_EXTERNAL_MATCH', 'external_candidate_count': 3})
    assert len(ledger.unresolved_records) == 1


def test_cross_station_is_not_materialized_under_the_v1_policy(ledger_fixture):
    ledger = ledger_fixture.build_cross_case({'station_relationship': 'CROSS_STATION'})
    assert not ledger.completion_records
    record, = ledger.unresolved_records
    assert record['reason'] == 'TIER_NOT_MATERIALIZED'
    assert record['tier'] == 'CROSS_STATION'


def test_same_station_is_proposed_with_unique_evidence(ledger_fixture):
    ledger = ledger_fixture.build_cross_case({'station_relationship': 'SAME_STATION'})
    record, = ledger.completion_records
    assert record['completion_status'] == 'PROPOSED'
    assert record['confidence_class'] == 'UNIQUE_EVIDENCE'
    assert record['tier'] == 'SAME_STATION'
    assert record['rule_id'] == 'CROSS_CASE_REFERENCE_COPY_V1'
    assert record['donor_source_record_ref'] is not None
    assert record['donor_source_entity_type'] == 'SWITCH'


def test_appended_row_bytes_equal_the_donor_row_bytes(delivery_fixture):
    delivery_fixture.copy_cross_case()
    root = delivery_fixture.write()
    target = (root / 'data' / delivery_fixture.referring_key / '03_Switch.csv').read_bytes()
    appended = target.split(b'\r\n')[-2]
    with ZipFile(delivery_fixture.archive, 'r') as archive:
        donor = archive.read(delivery_fixture.donor_member).split(b'\r\n')
    assert appended == donor[delivery_fixture.donor_data_row]


def test_candidate_input_order_changes_nothing(ledger_fixture):
    assert (ledger_fixture.build_cross_case(candidate_order=[0, 1, 2])
            == ledger_fixture.build_cross_case(candidate_order=[2, 1, 0]))


def test_closure_depth_is_obeyed_and_the_overflow_is_counted(ledger_fixture):
    ledger = ledger_fixture.build_cross_case_chain(depth=4, policy_depth=2)
    assert ledger.counts['materialized_rows'] == 3
    over = [r for r in ledger.unresolved_records if r['reason'] == 'CLOSURE_DEPTH_EXCEEDED']
    assert len(over) == 1
    assert over[0]['closure_depth'] == 3


def test_closure_cycle_terminates(ledger_fixture):
    ledger = ledger_fixture.build_cross_case_cycle()
    assert ledger.counts['materialized_rows'] == 2
    assert not [r for r in ledger.unresolved_records if r['reason'] == 'CLOSURE_DEPTH_EXCEEDED']
```

- [ ] **Step 2: Run** — expect failures.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `feat: materialize same-station cross-case reference completions`.

**Acceptance criteria.** The truth table covers all nine preconditions and records exactly one reason per row; the gate-by-gate counts reproduce 7,818 → 4,410 → 2,954 → 2,544 on the real audit stream; `CROSS_STATION` yields one `TIER_NOT_MATERIALIZED` record and no appended row; appended bytes equal donor row bytes; a member whose source region does not end with a terminator gains exactly one separator and does not concatenate two records; no source region byte is altered; each source member is split at most once per run; the closure is depth-bounded, cycle-safe and every overflow is counted; candidate order changes nothing; `counts['materialized_rows']` equals the number of appended rows and is no longer a hardcoded zero.

---

## 9. Slice 7 — `PLACEMENT_MISSING_ENDPOINT_BUS_V1` materialization

**Goal.** Append one Bus row per distinct unresolved `raw_endpoint_value`, using only source-declared text, with revision 001 §1–§3 rules for `Bus_BaseKV`, `Bus_Station_ID` and the unevidenced fields.

**Files.** Extend `generation/completion_ledger.py`, `io/derived_delivery_artifacts.py`.

**Interfaces.**

```python
PLACEMENT_BUS_COLUMNS = ('Bus_ID', 'Bus_Name', 'Bus_BaseKV', 'Bus_Phase',
                         'Bus_Station_ID', 'Bus_IsSource')
PLACEMENT_ASSUMPTIONS = ('NOT_A_NEW_LINE_DEVICE',)


def placement_bus_records(inputs: CompletionInputs) -> tuple[dict, ...]: ...
def render_bus_row(values: Mapping[str, str | None]) -> bytes: ...
def station_value(bus_member_bytes: bytes) -> str | None: ...
```

**Rule.** Select proposal endpoints where `anchor_origin != 'ACCEPTED_NODE'`. Group by `raw_endpoint_value`; the group is the unit, and the group's single Bus row is emitted once even when several ports or proposals share it (measured: 782 distinct generated ports carry 565 distinct values, because 217 values map to more than one port).

Field values, per revision 001 §3: a field is populated only when it has explicit evidence for that endpoint, and every other field is **`None`**. No field is filled from station context, Case nominal voltage, directory naming, the feeder head, or any default.

| Column | Value |
|---|---|
| `Bus_ID` | the group's `raw_endpoint_value` **verbatim** — the identity the placement rule already determined; never minted, never computed here |
| `Bus_Name`, `Bus_Phase`, `Bus_IsSource` | `None` — no consumed artifact carries evidence for them |
| `Bus_BaseKV` | the joined `endpoint_evidence[(source_line_id, endpoint_side)]['voltage_evidence']` when exactly one distinct non-null value exists across the group; `None` when every occurrence is null (reason `VOLTAGE_EVIDENCE_ABSENT`) or when more than one distinct non-null value exists (reason `VOLTAGE_EVIDENCE_CONFLICT`) |
| `Bus_Station_ID` | `station_value(...)` — the single distinct non-empty `Bus_Station_ID` in the referring Case's `02_Bus.csv`, else `None` with reason `STATION_EVIDENCE_NOT_UNIQUE` |

`None` is preserved as `null` in the ledger and the provenance sidecar, and is rendered as an **empty field** in the CSV, which is the source format's own representation of an absent value. `render_bus_row` maps `None` to `''` at the serialization boundary only.

The join is cross-checked: the endpoint evidence row's `raw_endpoint_value` must equal the proposal endpoint's, else `EVIDENCE_JOIN_MISMATCH` and the record stays `UNRESOLVED`.

`render_bus_row` serializes `PLACEMENT_BUS_COLUMNS` through `csv.writer(io.StringIO(newline=''), lineterminator='\r\n')` in the source header's own column order. Because every emitted value is a digit string or empty, QUOTE_MINIMAL emits the same bytes the source format uses; the test asserts **re-parse equality** rather than byte equality against a hypothetical source row, which is the only honest assertion for a generated row.

- [ ] **Step 1: Write the failing test**

```python
def test_bus_id_is_the_source_declared_endpoint_verbatim(ledger_fixture):
    ledger = ledger_fixture.build_placement()
    record, = [r for r in ledger.completion_records
               if r['rule_id'] == 'PLACEMENT_MISSING_ENDPOINT_BUS_V1']
    assert ledger_fixture.rendered(record)['Bus_ID'] == ledger_fixture.raw_endpoint_value


def test_one_row_per_distinct_raw_value_not_per_port(ledger_fixture):
    ledger = ledger_fixture.build_placement(ports=3, shared_raw_value=True)
    rows = [r for r in ledger.completion_records
            if r['rule_id'] == 'PLACEMENT_MISSING_ENDPOINT_BUS_V1']
    assert len(rows) == 1


def test_distinct_raw_values_get_distinct_rows(ledger_fixture):
    ledger = ledger_fixture.build_placement(ports=3, shared_raw_value=False)
    rows = [r for r in ledger.completion_records
            if r['rule_id'] == 'PLACEMENT_MISSING_ENDPOINT_BUS_V1']
    assert len(rows) == 3
    assert len({ledger_fixture.rendered(r)['Bus_ID'] for r in rows}) == 3


def test_line_csv_receives_no_new_row(delivery_fixture):
    delivery_fixture.placement_bus()
    root = delivery_fixture.write()
    after = (root / 'data' / delivery_fixture.referring_key / '08_Line.csv').read_bytes()
    assert after == delivery_fixture.line_member_bytes


def test_absent_voltage_is_null_not_a_substitute(ledger_fixture):
    ledger = ledger_fixture.build_placement(voltage=None)
    record, = ledger.completion_records
    assert record['confidence_class'] == 'ENGINEERING_DEFAULT'
    assert ledger_fixture.fields(record)['Bus_BaseKV'] is None
    assert ledger_fixture.rendered(record)['Bus_BaseKV'] == ''
    assert 'VOLTAGE_EVIDENCE_ABSENT' in ledger_fixture.assumptions(record)


def test_no_station_context_is_ever_substituted(ledger_fixture):
    ledger = ledger_fixture.build_placement(stations=['1139'], nominal='110')
    record, = ledger.completion_records
    assert ledger_fixture.fields(record)['Bus_Station_ID'] == '1139'
    assert ledger_fixture.fields(record)['Bus_BaseKV'] is None
    assert ledger_fixture.fields(record)['Bus_Name'] is None
    assert ledger_fixture.fields(record)['Bus_Phase'] is None
    assert ledger_fixture.fields(record)['Bus_IsSource'] is None


def test_a_field_without_evidence_is_null_not_derived(ledger_fixture):
    ledger = ledger_fixture.build_placement(voltage='10.5', stations=['1139'])
    fields = ledger_fixture.fields(ledger.completion_records[0])
    assert fields['Bus_BaseKV'] == '10.5'
    assert fields['Bus_Station_ID'] == '1139'
    assert fields['Bus_Name'] is None
    assert fields['Bus_Phase'] is None
    assert fields['Bus_IsSource'] is None


def test_conflicting_voltage_is_never_resolved_by_ordering(ledger_fixture):
    a = ledger_fixture.build_placement(voltage=['10.5', '20'])
    b = ledger_fixture.build_placement(voltage=['20', '10.5'])
    assert a == b
    assert ledger_fixture.rendered(a.completion_records[0])['Bus_BaseKV'] == ''
    assert a.unresolved_records[0]['reason'] == 'VOLTAGE_EVIDENCE_CONFLICT'


def test_ambiguous_station_leaves_the_field_empty(ledger_fixture):
    ledger = ledger_fixture.build_placement(stations=['1139', '3800'])
    assert ledger_fixture.rendered(ledger.completion_records[0])['Bus_Station_ID'] == ''
    assert 'STATION_EVIDENCE_NOT_UNIQUE' in ledger_fixture.assumptions(ledger.completion_records[0])


def test_single_station_is_copied_verbatim(ledger_fixture):
    ledger = ledger_fixture.build_placement(stations=['1139'])
    assert ledger_fixture.rendered(ledger.completion_records[0])['Bus_Station_ID'] == '1139'


def test_evidence_join_mismatch_keeps_the_record_unresolved(ledger_fixture):
    ledger = ledger_fixture.build_placement(join_mismatch=True)
    assert not ledger.completion_records
    assert ledger.unresolved_records[0]['reason'] == 'EVIDENCE_JOIN_MISMATCH'


def test_generated_row_reparses_to_the_intended_values(delivery_fixture):
    delivery_fixture.placement_bus()
    delivery_fixture.write()
    row = delivery_fixture.reparsed_last_bus_row()
    assert row['Bus_ID'] == delivery_fixture.raw_endpoint_value
    assert row['Bus_Name'] == '' and row['Bus_Phase'] == '' and row['Bus_IsSource'] == ''
    assert list(row) == list(delivery_fixture.bus_header)


def test_bus_header_is_never_rewritten(delivery_fixture):
    delivery_fixture.placement_bus()
    root = delivery_fixture.write()
    target = (root / 'data' / delivery_fixture.referring_key / '02_Bus.csv').read_bytes()
    assert target.startswith(delivery_fixture.bus_member_bytes.split(b'\r\n')[0])
```

- [ ] **Step 2: Run** — expect failures.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `feat: materialize placement endpoint bus declarations`.

**Acceptance criteria.** Grouping is by distinct raw endpoint value, never by port or proposal; `08_Line.csv` gains no row; an absent or conflicting voltage and an ambiguous station each yield an empty field plus a recorded reason and never a chosen value; the generated row re-parses to exactly the intended values and the header is untouched.

---

## 10. Slice 8 — Ledger writer

**Goal.** Persist the engine's output as `outputs/nanjing-v1/completion-ledger-v1/` with the house manifest and a replaying verifier.

**Files.** Create `src/grid_case_generator/io/completion_ledger_artifacts.py`, `tests/generation/test_completion_ledger_artifacts.py`.

**Interfaces.**

```python
FILES = ('completion_records.jsonl', 'unresolved_records.jsonl', 'case_summary.jsonl',
         'policy_snapshot.json', 'summary.json', 'report.md')
SCOPE = 'COMPLETION_LEDGER'
INPUTS = frozenset({'source', 'baseline', 'projection', 'feeder', 'recovery', 'd1',
                    'd2', 'frozen', 'd3_analysis', 'accepted_v2', 'd4', 'placement', 'audit'})


def code_hash() -> str: ...
def bindings(roots) -> dict: ...
def inputs_from_artifacts(roots, policy) -> CompletionInputs: ...
def ledger_events(inputs: CompletionInputs): ...
def write_artifact(inputs, output, input_bindings) -> dict: ...
def verify_artifact(output, *, inputs=None, expected_bindings=None) -> dict: ...
def run(roots, policy_path, output, verify=False) -> dict: ...
```

**Follow the newest writer, `io/placement_evidence_artifacts.py`, exactly.** `check_output(output, roots)` from `io/switch_projection_artifacts.py:21` first; then the inline `data/raw` predicate, `raise FileExistsError(output)`, `output.mkdir(parents=True)`; every stream opened `'xb'` inside a single `ExitStack`; `payload(name, row)` returning `row.encode()` for `report.md` and `canonical_json_bytes(row) + b'\n'` otherwise; manifest written last as `canonical_json_bytes(manifest) + b'\n'`; per-file `{'sha256': …, 'record_count': …}` with `record_count` = `len(data.splitlines())` for `report.md` and record count otherwise. All failures raise bare `ValueError` with a `'v1 ledger …'` prefix, matching the `'D4 …'` / `'D4.1 …'` convention.

**Manifest.**

```python
manifest = {'artifact_kind': SCOPE, 'version': VERSION, 'rule_version': VERSION,
            'schema_version': VERSION, 'input_manifest_sha256': input_bindings,
            'policy_sha256': policy_sha256(policy), 'code_sha256': code_hash(),
            'approved': False, 'applied': False, 'canonical_changed': False,
            'accepted_v2_changed': False, 'source_changed': False,
            'e3_ready': False, 'opendss_ready': False,
            'files': {n: {'sha256': hashes[n].hexdigest(), 'record_count': counts[n]}
                      for n in sorted(FILES)}}
```

`bindings` composes the existing chains: `verify_recovery_inputs`-style verification of the eight D3 roots (`source, baseline, projection, feeder, recovery, d1, d2, frozen`), then the D3 analysis manifest, `accepted_v2`, `d4`, `placement` and `audit` manifest digests, exactly as `io/placement_evidence_artifacts.py:56-59` extends `d3_hashes`. `run` follows `io/synthetic_backbone_artifacts.py:163-174`: `before = bindings(roots)`, verify every upstream, write (or verify), self-verify **with the same bindings**, then re-assert `bindings(roots) == before` and raise `ValueError('v1 ledger inputs changed during run')`.

- [ ] **Step 1: Write the failing test**

```python
import json
from hashlib import sha256

import pytest
from test_completion_ledger_artifacts import inputs, make, write


def test_clean_artifact_verifies(tmp_path):
    root, factory = make(tmp_path)
    result = write(root)
    assert result['verified'] is True
    assert result['input_bound'] is True


def test_write_once_and_scope_flags(tmp_path):
    root, factory = make(tmp_path)
    write(root)
    with pytest.raises(FileExistsError):
        write(root)
    manifest = json.loads((root / 'manifest.json').read_text())
    for flag in ('approved', 'applied', 'canonical_changed', 'accepted_v2_changed',
                 'source_changed', 'e3_ready', 'opendss_ready'):
        assert manifest[flag] is False


def test_byte_append_tamper_fails(tmp_path):
    root, factory = make(tmp_path)
    write(root)
    path = root / 'completion_records.jsonl'
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='checksum|count|canonical'):
        verify_artifact(root, inputs=inputs(), expected_bindings=BINDINGS)


def test_extra_file_fails_inventory(tmp_path):
    root, factory = make(tmp_path)
    write(root)
    (root / 'extra.jsonl').write_bytes(b'')
    with pytest.raises(ValueError, match='inventory'):
        verify_artifact(root, inputs=inputs(), expected_bindings=BINDINGS)


def test_flipped_scope_flag_fails(tmp_path):
    root, factory = make(tmp_path)
    write(root)
    mp = root / 'manifest.json'
    m = json.loads(mp.read_text())
    m['applied'] = True
    mp.write_bytes(canonical_json_bytes(m) + b'\n')
    with pytest.raises(ValueError, match='scope violation'):
        verify_artifact(root, inputs=inputs(), expected_bindings=BINDINGS)


def test_stale_policy_hash_fails(tmp_path):
    root, factory = make(tmp_path)
    write(root)
    mp = root / 'manifest.json'
    m = json.loads(mp.read_text())
    m['policy_sha256'] = '0' * 64
    mp.write_bytes(canonical_json_bytes(m) + b'\n')
    with pytest.raises(ValueError, match='policy'):
        verify_artifact(root, inputs=inputs(), expected_bindings=BINDINGS)


def test_rehashed_semantic_tamper_still_fails_replay(tmp_path):
    root, factory = make(tmp_path)
    write(root)
    path = root / 'completion_records.jsonl'
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    rows[0]['completion_status'] = 'CONFIRMED'
    path.write_bytes(b''.join(canonical_json_bytes(r) + b'\n' for r in rows))
    mp = root / 'manifest.json'
    m = json.loads(mp.read_text())
    m['files'][path.name]['sha256'] = sha256(path.read_bytes()).hexdigest()
    mp.write_bytes(canonical_json_bytes(m) + b'\n')
    with pytest.raises(ValueError, match='replay'):
        verify_artifact(root, inputs=inputs(), expected_bindings=BINDINGS)


def test_stale_upstream_binding_fails(tmp_path):
    root, factory = make(tmp_path)
    write(root)
    with pytest.raises(ValueError, match='binding'):
        verify_artifact(root, inputs=inputs(),
                        expected_bindings=dict(BINDINGS, audit='0' * 64))


def test_policy_snapshot_reparses_to_the_consumed_policy(tmp_path):
    root, factory = make(tmp_path)
    write(root)
    snapshot = json.loads((root / 'policy_snapshot.json').read_text())
    assert snapshot == json.loads(Path('configs/nanjing_completion_policy_v1.json').read_text())
    assert sha256(canonical_json_bytes(snapshot) + b'\n').hexdigest() == \
        json.loads((root / 'manifest.json').read_text())['policy_sha256']
```

- [ ] **Step 2: Run** — expect a collection error.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `feat: publish v1 completion ledger artifact`.

**Acceptance criteria.** The artifact replays from its own `policy_snapshot.json` plus bound inputs; a rehashed-semantics tamper still fails; re-writing raises `FileExistsError`; every boundary flag is `False`; the ledger's `policy_sha256` equals the snapshot's canonical hash.

---

## 11. Slice 9 — `row_provenance.jsonl` writer

**Goal.** One provenance record per delivered row, including every source row, with the contract's `SOURCE`/`APPENDED` semantics.

**Files.** Extend `io/derived_delivery_artifacts.py`, `tests/generation/test_derived_delivery_artifacts.py`.

**Interfaces.**

```python
PROVENANCE_KEYS = ('provenance_id', 'case_id', 'source_case_key', 'target_file',
    'row_index', 'row_kind', 'completion_status', 'confidence_class', 'tier', 'rule_id',
    'rule_version', 'source_record_ref', 'donor_source_record_ref', 'raw_field',
    'raw_reference_value', 'evidence_refs', 'policy_id', 'policy_sha256')


def provenance_records(case_rows, ledger, policy) -> Iterator[dict]: ...
```

**Semantics.** `SOURCE` rows carry their own `source_record_ref`, `completion_status='CONFIRMED'`, `confidence_class='EXACT_STRUCTURAL'`, `rule_id=PASSTHROUGH_RULE`, `tier=None`, `donor_source_record_ref=None`, `raw_field=None`, `raw_reference_value=None`, `evidence_refs=[]`. `APPENDED` rows carry the referring Case's `source_record_ref`, the ledger record's status, confidence, tier, rule and `evidence_refs`, and `donor_source_record_ref` set only by `CROSS_CASE_RULE`. `row_index` is 0-based over data rows within the target file, so it aligns with the CSV's own row order. Records are emitted in `(source_case_key, target_file, row_index)` order so the sidecar is stable regardless of which rule produced a row.

- [ ] **Step 1: Write the failing test**

```python
def test_provenance_key_set_is_exact(delivery_fixture):
    delivery_fixture.copy_cross_case().placement_bus()
    delivery_fixture.write()
    rows = delivery_fixture.provenance()
    assert rows
    assert all(set(r) == set(PROVENANCE_KEYS) for r in rows)


def test_source_rows_are_fully_described(delivery_fixture):
    delivery_fixture.write()
    source = [r for r in delivery_fixture.provenance() if r['row_kind'] == 'SOURCE']
    assert len(source) == delivery_fixture.source_row_count
    assert all(r['rule_id'] == 'SOURCE_PASSTHROUGH_V1' for r in source)
    assert all(r['completion_status'] == 'CONFIRMED' for r in source)
    assert all(r['evidence_refs'] == [] for r in source)


def test_donor_ref_is_set_exactly_under_the_cross_case_rule(delivery_fixture):
    delivery_fixture.copy_cross_case().placement_bus()
    delivery_fixture.write()
    for r in delivery_fixture.provenance():
        if r['row_kind'] == 'APPENDED':
            assert (r['donor_source_record_ref'] is not None) == \
                (r['rule_id'] == 'CROSS_CASE_REFERENCE_COPY_V1')


def test_every_appended_row_traces_to_one_ledger_record(delivery_fixture):
    delivery_fixture.copy_cross_case().placement_bus()
    result = delivery_fixture.write()
    ledger_ids = {r['record_id'] for r in result['ledger_records']}
    appended = [r for r in delivery_fixture.provenance() if r['row_kind'] == 'APPENDED']
    assert appended
    for r in appended:
        assert len(set(r['evidence_refs']) & ledger_ids) == 1


def test_row_index_matches_the_csv_row_order(delivery_fixture):
    delivery_fixture.placement_bus()
    root = delivery_fixture.write()
    for r in delivery_fixture.provenance():
        if r['case_id'] != delivery_fixture.referring_case_id:
            continue
        if r['row_kind'] != 'APPENDED':
            continue
        lines = (root / 'data' / delivery_fixture.referring_key / r['target_file']) \
            .read_bytes().split(b'\r\n')
        assert lines[1 + r['row_index']]


def test_policy_hash_agrees_across_artifacts(delivery_fixture):
    root = delivery_fixture.write()
    hashes = {r['policy_sha256'] for r in delivery_fixture.provenance()}
    assert len(hashes) == 1
    ledger_manifest = json.loads(
        (delivery_fixture.ledger_root / 'manifest.json').read_text())
    assert hashes.pop() == ledger_manifest['policy_sha256']


def test_provenance_order_is_stable(delivery_fixture):
    a = delivery_fixture.write(tmp_path_name='a')
    b = delivery_fixture.write(tmp_path_name='b', shuffled_inputs=True)
    assert (a / 'provenance' / 'row_provenance.jsonl').read_bytes() == \
        (b / 'provenance' / 'row_provenance.jsonl').read_bytes()
```

- [ ] **Step 2: Run** — expect failures.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `feat: emit per-row provenance for the v1 delivery`.

**Acceptance criteria.** Provenance is complete for every delivered row; no record omits a key; every appended row traces to exactly one ledger record; the sidecar's `policy_sha256` matches the ledger manifest; the sidecar's order is independent of input order.

---

## 12. Slice 10 — CSV byte-fidelity exporter

**Goal.** The write-through guarantee and the deterministic archive.

**Files.** Extend `io/derived_delivery_artifacts.py`.

**Interfaces.**

```python
def build_archive(root, *, progress=None) -> dict: ...   # {'name', 'sha256', 'entries'}
```

**Write-through.** A member with no appended rows is written by streaming `raw_member_bytes` straight to the destination `'xb'` handle. A member with appended rows is written as the original bytes followed by the appended block, with no added BOM and no terminator translation. No code path decodes a source member and re-encodes it.

**Archive determinism.** `ZipFile(root / ARCHIVE_NAME, 'w', ZIP_DEFLATED)`, each `ZipInfo` built explicitly with `date_time = ARCHIVE_TIMESTAMP`, fixed `external_attr`, fixed `create_system`, and entries added in sorted member-path order. `ZipFile.write` must not be used: it stamps the filesystem mtime, which would make the archive non-reproducible.

**Self-reference carve-out.** Implement exactly as revision 001 §4 specifies: `manifest['files']` inventories every tree file except `manifest.json` and the archive; the archive sha256 is returned by `build_archive` and recorded in the sidecar and the CLI result; the verifier's inventory check is `set(manifest['files']) | {'manifest.json', ARCHIVE_NAME}`. No recursive hashing: the manifest never hashes the archive and the archive hash is never a manifest input.

- [ ] **Step 1: Write the failing test**

```python
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

from grid_case_generator.io.derived_delivery_artifacts import ARCHIVE_NAME


def test_archive_is_byte_identical_across_hash_seeds(tmp_path):
    script = ('from pathlib import Path; '
              'from test_derived_delivery_artifacts import build; '
              'import sys; build(Path(sys.argv[1]))')
    for name, seed in [('a', '1'), ('b', '999'), ('c', '1')]:
        env = dict(os.environ, PYTHONHASHSEED=seed,
                   PYTHONPATH=str(Path(__file__).parent.resolve()))
        subprocess.run([sys.executable, '-c', script, str(tmp_path / name)],
                       env=env, check=True)
    assert ((tmp_path / 'a' / ARCHIVE_NAME).read_bytes()
            == (tmp_path / 'b' / ARCHIVE_NAME).read_bytes()
            == (tmp_path / 'c' / ARCHIVE_NAME).read_bytes())


def test_archive_entries_are_sorted_and_contain_the_manifest(delivery_fixture):
    root = delivery_fixture.write()
    names = ZipFile(root / ARCHIVE_NAME).namelist()
    assert sorted(names) == names
    assert 'manifest.json' in names and 'report.md' in names
    assert not any(n.endswith(ARCHIVE_NAME) for n in names)


def test_archive_csv_entries_match_the_tree(delivery_fixture):
    root = delivery_fixture.write()
    names = set(ZipFile(root / ARCHIVE_NAME).namelist())
    on_disk = {str(p.relative_to(root)) for p in (root / 'data').rglob('*.csv')}
    assert {n for n in names if n.endswith('.csv')} == on_disk


def test_archive_inventory_obeys_the_carve_out(delivery_fixture):
    root = delivery_fixture.write()
    manifest = json.loads((root / 'manifest.json').read_text())
    on_disk = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    assert on_disk == set(manifest['files']) | {'manifest.json', ARCHIVE_NAME}


def test_zip_info_timestamps_are_fixed(delivery_fixture):
    root = delivery_fixture.write()
    infos = ZipFile(root / ARCHIVE_NAME).infolist()
    assert {i.date_time for i in infos} == {(1980, 1, 1, 0, 0, 0)}


def test_archive_sha256_is_reported_not_manifested(delivery_fixture):
    root = delivery_fixture.write()
    result = delivery_fixture.result
    manifest = json.loads((root / 'manifest.json').read_text())
    assert sha256((root / ARCHIVE_NAME).read_bytes()).hexdigest() == result['archive_sha256']
    assert ARCHIVE_NAME not in manifest['files']
```

- [ ] **Step 2: Run** — expect failures.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `feat: add deterministic delivery archive`.

**Acceptance criteria.** The archive is byte-identical across two hash seeds and a same-seed repeat; entry names are sorted; every `ZipInfo.date_time` is the fixed epoch; the carve-out is described in the spec and enforced by the verifier.

---

## 13. Slice 11 — Manifest, report and independent validation

**Goal.** The delivery manifest, the human report, the verification sidecar, and the independent validator.

**Files.** Extend `io/derived_delivery_artifacts.py`; create `src/grid_case_generator/validation/completion_export.py` and its tests in `tests/generation/test_derived_delivery_artifacts.py`.

**Interfaces.**

```python
def render_report(summary, ledger_counts, archive) -> str: ...
def write_sidecar(root, result) -> Path: ...
def validate_delivery(root, *, ledger_root, roots, policy) -> dict: ...
```

**Report content, in this order.** The `approved:false` banner and the PROPOSED-row warning; the measured counts; the `SOURCE_HEAD_CONTEXT` note; the appended-reference note; the generated-Bus-row note; the open-question note. Every count comes from the run.

**Sidecar.** `outputs/nanjing-v1/derived-delivery-v1-verification.json`, shaped like the existing hand-authored sidecars (`json.dumps(..., ensure_ascii=False, sort_keys=True, indent=2)`): `bound_verifier`, `compileall`, `protected_inputs_sha256`, `archive_sha256`, `archive_entries`, `measured`, `changed_protected_files: []`.

**Validator.** A pure function returning `{'reasons': sorted(errors), 'structural_status': 'REJECTED' if errors else 'PASS', ...}` with SCREAMING_SNAKE codes, per the house style in `validation/placement_evidence.py`. Codes and their triggers:

| Code | Trigger |
|---|---|
| `SOURCE_ROW_NOT_VERBATIM` | A source-backed row's bytes differ from `raw_record_bytes(member, data_row)` |
| `APPENDED_ROW_NOT_DONOR_BYTES` | A cross-case row's bytes differ from the donor's row bytes |
| `MINTED_IDENTIFIER` | An appended `Bus_ID` is absent from the source-declared unresolved endpoint value set |
| `TIER_NOT_ENABLED` | An appended row's tier is outside `policy.materialize_tiers` |
| `CLOSURE_NOT_BOUNDED` | Any recorded `closure_depth` exceeds `policy.max_reference_closure_depth` |
| `PROVENANCE_INCOMPLETE` | A delivered row has no sidecar record, or a record omits a key |
| `PROVENANCE_UNKNOWN_ROW` | A sidecar record names a row that does not exist |
| `UNRESOLVED_ROW_WRITTEN` | A CSV contains a row corresponding to an `UNRESOLVED` ledger record |
| `DUPLICATE_APPENDED_ROW` | The same `(case, file, row bytes)` appears twice |
| `CSV_COLUMN_SCHEMA_CHANGED` | A header differs from `NANJING_SOURCE_SCHEMA.for_filename(name).header` |
| `POLICY_HASH_MISMATCH` | Sidecar and ledger manifest `policy_sha256` differ, or disagree with `policy_sha256(policy)` |
| `LEDGER_BINDING_MISMATCH` | The delivery manifest's ledger binding differs from the ledger manifest's hash |
| `STALE_LEDGER_BASE` | The ledger's `accepted_v2` binding is not the current accepted v2 manifest hash |

The validator re-implements its own membership and byte tests and never imports `generation/completion_ledger.py`.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from grid_case_generator.validation.completion_export import validate_delivery


def test_clean_delivery_has_no_reasons(delivery_fixture):
    ledger_root = delivery_fixture.build_ledger()
    root = delivery_fixture.write(ledger_root=ledger_root)
    assert validate_delivery(root, ledger_root=ledger_root,
                             roots=delivery_fixture.roots,
                             policy=delivery_fixture.policy)['reasons'] == []


@pytest.mark.parametrize('mutate,code', [
    (lambda f: f.tamper_source_row(), 'SOURCE_ROW_NOT_VERBATIM'),
    (lambda f: f.tamper_appended_row(), 'APPENDED_ROW_NOT_DONOR_BYTES'),
    (lambda f: f.rename_appended_bus_id(), 'MINTED_IDENTIFIER'),
    (lambda f: f.append_foreign_tier_row(), 'TIER_NOT_ENABLED'),
    (lambda f: f.drop_provenance_row(), 'PROVENANCE_INCOMPLETE'),
    (lambda f: f.add_unknown_provenance_row(), 'PROVENANCE_UNKNOWN_ROW'),
    (lambda f: f.duplicate_appended_row(), 'DUPLICATE_APPENDED_ROW'),
    (lambda f: f.rename_a_column(), 'CSV_COLUMN_SCHEMA_CHANGED'),
    (lambda f: f.change_policy_hash_in_sidecar(), 'POLICY_HASH_MISMATCH'),
    (lambda f: f.stale_ledger_binding(), 'LEDGER_BINDING_MISMATCH'),
])
def test_each_reason_code_is_reachable(delivery_fixture, mutate, code):
    ledger_root = delivery_fixture.build_ledger()
    root = delivery_fixture.write(ledger_root=ledger_root)
    mutate(delivery_fixture)
    verdict = validate_delivery(root, ledger_root=ledger_root,
                                roots=delivery_fixture.roots,
                                policy=delivery_fixture.policy)
    assert code in verdict['reasons']
    assert verdict['structural_status'] == 'REJECTED'


def test_report_states_every_required_fact(delivery_fixture):
    root = delivery_fixture.write()
    text = (root / 'report.md').read_text()
    for phrase in ('approved: false', 'PROPOSED', 'SOURCE_HEAD_CONTEXT',
                   'VOLTAGE_EVIDENCE_ABSENT', 'declaration completion', 'Q-CASE-001'):
        assert phrase in text, phrase


def test_sidecar_records_the_archive_hash(delivery_fixture):
    root = delivery_fixture.write()
    sidecar = json.loads(delivery_fixture.sidecar_path.read_text())
    assert sidecar['bound_verifier'] == 'PASS'
    assert sidecar['archive_sha256'] == sha256(
        (root / 'manifest.json').parent.joinpath(ARCHIVE_NAME).read_bytes()).hexdigest()
    assert sidecar['changed_protected_files'] == []
```

- [ ] **Step 2: Run** — expect failures.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `feat: add delivery manifest, report and independent validation`.

**Acceptance criteria.** Every reason code is reachable and asserted; the report states all six required facts with run-derived counts; the validator shares no code with the engine.

---

## 14. Slice 12 — End-to-end reproducibility

**Goal.** Prove the whole pipeline on a synthetic intake, wire the CLI, and document the slice.

**Files.** Create `src/grid_case_generator/analysis/completion_export_cli.py`, `tests/generation/test_completion_export_e2e.py`, `docs/guides/nanjing_v1_completion_export.md`. Modify `README.md`.

**CLI.** Copy the positional-command shape of `analysis/placement_evidence_cli.py:10-18`:

```python
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('analyze', 'verify'))
    for name in sorted(INPUTS | {'policy', 'output'}):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = run({k: getattr(args, k) for k in INPUTS}, args.policy, args.output,
                 args.command == 'verify')
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
```

Documented invocation:

```bash
PYTHONHASHSEED=1 uv run --frozen python -m grid_case_generator.analysis.completion_export_cli \
  analyze --source outputs/nanjing-e1/source-import-v2 \
  --baseline outputs/nanjing-e2/topology-v1 --projection outputs/nanjing-e2-2/switch-projection-design-v1 \
  --feeder outputs/nanjing-e2-2/feeder-coverage-v1 --recovery outputs/nanjing-e2-3/topology-recovery-evidence-v1 \
  --d1 outputs/nanjing-e2-3/synthetic-completion-contract-v1 \
  --d2 outputs/nanjing-e2-3/synthetic-topology-proposals-v1 \
  --frozen outputs/nanjing-e2/topology-v1 \
  --d3-analysis outputs/nanjing-e2-3/deterministic-topology-recovery-v1 \
  --accepted-v2 outputs/nanjing-e2-3/accepted-topology-v2 \
  --d4 outputs/nanjing-e2-3/synthetic-backbone-proposals-v1 \
  --placement outputs/nanjing-e2-3/placement-evidence-v1-1 \
  --audit outputs/nanjing-e2-3/case-boundary-audit-v1 \
  --policy configs/nanjing_completion_policy_v1.json \
  --output outputs/nanjing-v1/derived-delivery-v1
```

- [ ] **Step 1: Write the failing test**

```python
def test_two_case_pipeline_is_reproducible_and_immutable(tmp_path, e2e_fixture):
    before = {k: snapshot(p) for k, p in e2e_fixture.roots.items()}
    zip_before = e2e_fixture.archive.read_bytes()
    for name in ('out', 'repeat'):
        ledger = e2e_fixture.run_ledger(tmp_path / (name + '-ledger'))
        delivery = e2e_fixture.run_delivery(tmp_path / name, ledger)
        verdict = validate_delivery(tmp_path / name,
                                    ledger_root=tmp_path / (name + '-ledger'),
                                    roots=e2e_fixture.roots,
                                    policy=e2e_fixture.policy)
        assert verdict['reasons'] == []
    assert snapshot_tree(tmp_path / 'out') == snapshot_tree(tmp_path / 'repeat')
    assert before == {k: snapshot(p) for k, p in e2e_fixture.roots.items()}
    assert e2e_fixture.archive.read_bytes() == zip_before
    assert not any(r['approved'] or r['applied'] for r in delivery['ledger_records'])


def test_policy_change_regenerates_without_touching_anything_else(tmp_path, e2e_fixture):
    strict = e2e_fixture.policy_bytes(materialize_tiers=['SAME_STATION'])
    loose = e2e_fixture.policy_bytes(materialize_tiers=['SAME_STATION', 'CROSS_STATION'])
    a = e2e_fixture.run_all(tmp_path / 'a', strict)
    b = e2e_fixture.run_all(tmp_path / 'b', loose)
    assert a['policy_sha256'] != b['policy_sha256']
    assert a['materialized_rows'] < b['materialized_rows']
    assert a['ledger_records'][0]['source_record_ref'] == \
        b['ledger_records'][0]['source_record_ref']


def test_cli_analyze_then_verify_round_trips(tmp_path, e2e_fixture):
    e2e_fixture.run_via_cli(tmp_path / 'out', command='analyze')
    result = json.loads(e2e_fixture.run_via_cli(tmp_path / 'out', command='verify'))
    assert result['verified'] is True
```

- [ ] **Step 2: Run** — expect failures.
- [ ] **Step 3: Implement** the CLI, the guide and the README line.
- [ ] **Step 4: Run** `uv run --frozen python -m pytest` — **expect the full suite green, including the 554 pre-existing tests.**
- [ ] **Step 5: Run** `uv run --frozen python -m compileall -q src tests` — expect silence.
- [ ] **Step 6: Commit** `feat: add v1 completion export CLI and end-to-end reproducibility tests`.

**Acceptance criteria.** Two runs are byte-identical across ledger, delivery and archive; every upstream root and the raw archive are byte-unchanged; no record is approved or applied; a policy change alters the row set and the hash and nothing else; the full suite passes.

---

## 15. The 12 contract test groups

| # | Test group | Fixture / input | Expected artifact | Invariant checked |
|---|---|---|---|---|
| 1 | Deterministic regeneration | `e2e_fixture`; two in-process runs, then `subprocess` runs with `PYTHONHASHSEED` `1`, `999` and a repeat of `1` | `completion-ledger-v1/`, `derived-delivery-v1/`, `nanjing-derived-v1.zip` from each run | All snapshot dicts equal, archive bytes included; no run identity (path, mtime, PID) leaks into any artifact. Slice 10, 12 |
| 2 | Policy hash binding | One valid policy; then unknown field, bad enum, out-of-range depth, non-bool flag; then a policy differing only in `materialize_tiers` | `policy_snapshot.json`, `manifest['policy_sha256']` | Invalid policies raise before any output directory is created; `policy_sha256 == sha256(policy_bytes(policy))`; a policy change alters the hash and the materialized row set and nothing else. Slice 1, 8, 12 |
| 3 | Source byte preservation | 200 sampled real-archive members plus the synthetic fixture | `data/数据/<case>/NN_*.csv` | Every untouched member equals `archive.read(member)` byte-for-byte; BOM, CRLF and trailing CRLF preserved; `10_Load.csv`/`11_DER.csv` stay header-only; `08_Line.csv` gains no row. Slice 3, 4, 7 |
| 4 | No canonical mutation | Verified `source-import-v2` and `accepted-topology-v2` roots | Unchanged roots | `{relpath: bytes}` snapshots equal before and after; `manifest['canonical_changed'] is False`; `git diff --stat` touches no `models/`, `io/nanjing_source/` or `validation/reference_resolution.py`. Slice 4, 12 |
| 5 | No proposal approval or application | Any ledger and delivery build | Ledger and delivery records | No record has `approved` or `applied` truthy; a `PROPOSED` record stays `PROPOSED` regardless of the upstream D1/D2 stage; `manifest['approved'] is False`. Slice 5, 8, 12 |
| 6 | Unresolved taxonomy correctness | Audit rows covering all four D4.2 classes, plus `CROSS_STATION`, plus the placement/backbone/no-line cohorts | `unresolved_records.jsonl` | One record per input row; only the first failing reason in the contract's order is recorded; per-reason counts sum to the input count; cohort overlap is de-duplicated with an explicit overlap count; no `UNRESOLVED` record has a row in any CSV. Slice 5, 6 |
| 7 | Duplicate candidate safety | `classification='MULTIPLE_EXTERNAL_MATCH'`, `external_candidate_count=2`, `identity_status='DUPLICATE_IDENTICAL'`, `'DUPLICATE_CONFLICT'` | `unresolved_records.jsonl` | No row is appended for any of them; no candidate is selected; a row failing two conditions is recorded once; reversing the `candidates` array does not change the output bytes. Slice 6 |
| 8 | Closure depth behaviour | A 4-link chain, a 2-cycle, a self-reference, `max_reference_closure_depth` of `0`, `1`, `2` | Ledger records at each depth | Depth obeys the policy exactly; a cycle terminates at the visited set; an over-deep node is reported with `depth_exceeded` and **not expanded**; the overflow is counted in the report and never silently truncated. Slice 2, 6 |
| 9 | Provenance completeness | A delivery with at least one row from each rule family | `provenance/row_provenance.jsonl` | One record per delivered row; key set exactly `PROVENANCE_KEYS`; `SOURCE` rows carry their own ref and `PASSTHROUGH_RULE` with empty `evidence_refs`; `donor_source_record_ref` non-null exactly under `CROSS_CASE_REFERENCE_COPY_V1`; every appended row traces to exactly one ledger `record_id`; `policy_sha256` matches the ledger manifest. Slice 9 |
| 10 | Manifest verification | A clean build, then five tampered builds | `manifest.json` | Byte-append → checksum/count failure; extra file → inventory failure; flipped boundary flag → scope failure; stale `policy_sha256` → policy failure; a detail row rewritten **with a rehashed manifest** → replay failure. Slice 8, 11 |
| 11 | Full artifact replay | `manifest['input_manifest_sha256']` plus `policy_snapshot.json` | Verifier result | `verify` on a clean artifact returns `{'verified': True}`; a tampered upstream manifest fails the binding check; replay never re-reads `data/raw`; the delivery validator's thirteen reason codes are each reachable. Slice 8, 11 |
| 12 | Protected source SHA unchanged | `data/raw/南京数据.zip` plus all 13 upstream artifact manifests | Protected-input inventory | Whole-ZIP sha256 equals the pinned `7ae1e246…`; every upstream `manifest.json` sha256 unchanged; the sidecar records `changed_protected_files: []`. Slice 11, 12 |

---

## 16. Risk register

| # | Risk | Why it is live here | Mitigation (enforced by) |
|---|---|---|---|
| 1 | **Accidental cross-case topology mutation** | This is the first slice that materializes foreign-Case source rows into a Case, and the first that writes CSV. | Cross-case work lives only in the delivery layer, never in canonical or accepted v2; `CROSS_STATION` is gated off by policy; test group 4 asserts canonical and accepted bytes unchanged; destinations are derived from `source_case_key` only, so an off-by-one Case path is caught by the per-Case provenance check |
| 2 | **Treating `PROPOSED` as `CONFIRMED`** | The delivery ships proposals inside files a consumer reads as data. | `completion_status` is a required sidecar field; the report leads with the warning; test group 5 asserts no record is approved; `CONFIRMED` is reachable only through `SOURCE_PASSTHROUGH_V1` and the D3-accepted rule, so a new rule cannot silently claim it |
| 3 | **Generating new IDs** | Minting an ID is the natural way to write a Bus row. | The contract forbids it; `render_bus_row` receives the value from `raw_endpoint_value` and no ID factory is in scope; `MINTED_IDENTIFIER` fires on any appended `Bus_ID` outside the source-declared unresolved endpoint set |
| 4 | **Changing the CSV schema** | Writing CSV invites header rewriting, reordering, or adding provenance columns. | Passthrough writes raw bytes and never re-serializes; `CSV_COLUMN_SCHEMA_CHANGED` fires on any header differing from `NANJING_SOURCE_SCHEMA.for_filename(name).header`; test group 3 and Slice 7's header test cover it |
| 5 | **Provenance mismatch** | Two artifacts carry overlapping provenance and the delivery copies ledger streams. | The delivery manifest binds the ledger manifest hash; `record_id` excludes `reason` so identity survives a wording change; test group 9 asserts the cross-artifact `policy_sha256` and the one-ledger-record-per-appended-row anchor |
| 6 | **Nondeterministic ordering** | Dict iteration, `set()` iteration, archive entry order, `os.listdir` order. | Every emitted sequence is sorted in exactly one place; the archive is built with explicit `ZipInfo` objects in sorted order; test group 1 runs the real pipeline under two hash seeds in separate processes |
| 7 | **Per-Case archive reopening** | Reopening the 28 MB archive for every Case would multiply failure modes and dominate runtime. | `raw_member_bytes` takes a caller-owned handle and never opens the archive; `write_delivery` opens it once around the whole case loop |
| 8 | **61,908-file manifest bloat** | `manifest['files']` lists every delivered file, following the E1 convention, producing a roughly 10–15 MB manifest. | Accepted deliberately: it is what makes the delivery independently verifiable. Recorded in the guide. If it becomes a problem the fix is a per-Case digest level, which is a contract change, not a plan improvisation |
| 9 | **Generated Bus rows read as modelled buses** | The rows carry an ID and five null attributes. | Revision 001 §3 states they are declaration completions; the report repeats it; `VOLTAGE_EVIDENCE_ABSENT` and `STATION_EVIDENCE_NOT_UNIQUE` sit on every such record; Slice 7's tests assert every unevidenced field is `None` at the ledger level and empty only at the serialization boundary |
| 10 | **A context value substituted for evidence** | `Bus_BaseKV` and `Bus_Station_ID` would each be trivially fillable from station context, and 1.0.0's "derived or left empty" invited it. | Revision 001 §1–§3 forbids substitution explicitly; `station_value` returns `None` rather than a tie-break; `test_no_station_context_is_ever_substituted` and `test_a_field_without_evidence_is_null_not_derived` pin it |
| 11 | **Closure walker silently truncating** | A depth bound that drops work quietly would understate the gap. | An over-deep node is yielded with `depth_exceeded=True`, never expanded, and counted in the report; test group 8 asserts it explicitly |

---

## 17. Definition of done

1. The contract revision is already committed and this plan matches it:
   `docs/spec/nanjing_v1_completion_export.md` reads 1.1.0 and links
   `docs/spec/revisions/nanjing_v1_completion_export_revision_001.md`,
   `configs/nanjing_completion_policy_v1.json` carries `policy_version` `1.1.0`, and the
   implemented constants match Section 0's constant list. No slice edits the spec, and
   Slice 1 Step 5 verifies this rather than performing it.
2. All twelve slices are implemented, one commit each, in the given order — Slice 3 before Slices 4–7, because the delivery depends on it.
3. The full suite passes: the 554 pre-existing tests plus the new ones.
4. `uv run --frozen python -m compileall -q src tests` is silent.
5. Two runs under `PYTHONHASHSEED` `1` and `999`, plus a same-seed repeat, are byte-identical for the ledger, the delivery tree and the archive.
6. `data/raw/南京数据.zip` and all 13 upstream artifact manifests are byte-unchanged, evidenced by a protected-input inventory recording `changed_protected_files: []`.
7. `derived-delivery-v1-verification.json` records `bound_verifier: PASS` and the measured counts.
8. `README.md` and `docs/guides/nanjing_v1_completion_export.md` describe the slice, its policy lever and its explicit limits.
9. **The run stops for review.** No client handoff and no further slice begins from this plan.
