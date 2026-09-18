# Nanjing v1 completion and export / 1.1.0

Revision history: 1.0.0 froze this contract. **1.1.0** incorporates
[revision 001](revisions/nanjing_v1_completion_export_revision_001.md), which replaces
four clauses the persisted evidence contradicts: the source of `Bus_BaseKV`, the
`Bus_Station_ID` inference, the discretionary "derived or left empty" field rule for
generated Bus rows, and the delivery manifest's relation to its own archive. No rule
precondition, tier, state, confidence class, policy field or prohibition changed.

This contract defines an independent completion/export layer that produces a
deliverable v1 derived dataset from the frozen source facts plus the already
published evidence chain. It is authorized as a standalone slice. It does **not**
enter E3, does not generate electrical parameters, Load, DER or 8760 profiles, does
not produce an OpenDSS model or run QSTS, does not APPROVE or APPLY any D1/D2/D4/D4.1
proposal, and does not change canonical records, the reference resolver, the GridCase
boundary or accepted topology v2.

## Authorization and relation to prior gates

`nanjing_gated_slices.md` gates E5 behind E3/E4 and `docs/reviews/2026-09-18-nanjing-case-boundary-review.md`
leaves Q-CASE-001 OPEN with `REQUIRES_BUSINESS_CONFIRMATION`. The delivery goal for v1
is explicitly decoupled from that business confirmation: the export ships every
inferred object under an explicit, machine-readable `PROPOSED` status and never claims
a business decision was obtained. The slice is therefore named `nanjing-v1` and not
`E5`; the E3/E4 gates remain untouched and unentered.

Case-local isolation remains the operational contract for canonical resolution. This
slice does not relax it. Cross-case materialization is a *derived delivery* decision
taken in a separate layer, recorded per row, and reversible through policy.

## Completion states

Exactly one of three states is assigned to every completion record.

| State | Meaning |
|---|---|
| `CONFIRMED` | The row is copied verbatim from source, **or** the completion is the product of a deterministic rule that has already been `ACCEPTED` in the D3 rule review. |
| `PROPOSED` | The completion is produced by an enabled completion rule whose rule has *not* been accepted. It is materialized into the delivery only when policy permits its tier. |
| `UNRESOLVED` | No enabled rule's preconditions are satisfied, or a precondition fails. Nothing is written to the delivered CSV; the record is reported in the provenance sidecar. |

`CONFIRMED` is not a claim of electrical truth. `SOURCE_PASSTHROUGH_V1` confirms only
that the row is a source fact; `ACCEPTED_DETERMINISTIC_RECOVERY_V1` confirms only that
an accepted deterministic rule represents an existing source row. Neither asserts
connectivity beyond what the licensing source row and the accepted rule already state.

The business decision file `configs/nanjing_completion_decisions_v1.json` currently
carries an empty `decisions` array. It does **not** participate in state assignment for
v1: a business decision would be required to promote a `PROPOSED` completion to an
accepted one, and no such promotion exists in this contract. `PROPOSED` is terminal for
v1.

## Confidence classes

Confidence is a discrete class. There is no numeric confidence and no probability
anywhere in this contract, consistent with `nanjing_placement_evidence.md`.

- `EXACT_STRUCTURAL` — verbatim source row, or an accepted deterministic rule over
  persisted structure.
- `UNIQUE_EVIDENCE` — the cross-case rule's full precondition set held: unique
  external match, single candidate, unique identity, type compatible, no explicit
  voltage conflict.
- `ENGINEERING_DEFAULT` — a derived field whose value is chosen by an enabled
  engineering rule rather than read from a source declaration.
- `NONE` — no basis; always paired with `UNRESOLVED`.

## Tiers

Tier is the D4.2 candidate's `station_relationship`, carried through unmodified.

| Tier | Population | v1 materialization |
|---|---:|---|
| `SAME_STATION` | 2,544 references across 836 referring and 778 donor Cases | materialized when policy enables it |
| `CROSS_STATION` | 89,472 references; the full candidate graph reaches a largest weakly connected component of 3,698 Cases | **not materialized**; ledger-only |

The 2,544 D4.2 `strict_candidate` / `safe_looking_candidate` population is entirely
`SAME_STATION`; there is no strict cross-station subpopulation. `CROSS_STATION` is
recorded because D4.2 published it and because the client may later decide to enable
it through policy, but materializing it in v1 would perform the unrestricted global
follow that D4.2 documents as unsafe.

## Rules

### `SOURCE_PASSTHROUGH_V1` — CONFIRMED, `EXACT_STRUCTURAL`

Every source row of every one of the 5,159 Cases is copied to the delivery verbatim.
The row's original bytes, file, and row index are preserved. If a Case receives no
appended rows, all twelve of its delivered CSV files are byte-identical to the source
member.

This rule is unconditional and emits no ledger record of its own: one record per source
row would place 1,007,354 entries in the ledger for no review value. Its per-row
evidence lives in the delivery's `provenance/row_provenance.jsonl`.

### `ACCEPTED_DETERMINISTIC_RECOVERY_V1` — CONFIRMED, `EXACT_STRUCTURAL`

Consumes `accepted-topology-v2/additions.jsonl` (59,354 records, rules
`SERIES_EXACT_DIRECT_V2` and `LEAF_SWITCH_REPRESENTATION_V2`, both `ACCEPTED`). It
appends **no** CSV row: the recovered representation joins source rows that already
exist. The ledger records that the cited source row is confirmed as represented by an
accepted deterministic rule.

### `CROSS_CASE_REFERENCE_COPY_V1` — PROPOSED, `UNIQUE_EVIDENCE`

Consumes `case-boundary-audit-v1/cross_case_references.jsonl`. The rule fires only when
**all** of the following hold:

- `classification == 'UNIQUE_EXTERNAL_MATCH'`;
- `external_candidate_count == 1`;
- the single candidate's `identity_status == 'UNIQUE'`;
- the single candidate's `type_compatible == true`;
- `explicit_voltage_conflict_count == 0`;
- the candidate's `station_relationship` is a member of policy `materialize_tiers`.

Action: copy the donor Case's source row for the candidate's `source_entity_type`
verbatim into the referring Case's CSV for that entity type. The row is appended; the
donor row is never edited and never moved. Ordering is never used to select a
candidate.

Tier is the candidate's `station_relationship`. With the v1 policy
`materialize_tiers = ["SAME_STATION"]`, 2,544 rows are materialized.

Type pairs materialized under v1 policy, by owner → donor source entity type:

| owner | donor | rows |
|---|---|---:|
| `SWITCH` | `SWITCH` | 1,113 |
| `LINE` | `SWITCH` | 895 |
| `LINE` | `ACCESS_POINT` | 357 |
| `SWITCH` | `ACCESS_POINT` | 179 |

### `CROSS_CASE_REFERENCE_COPY_V1` closure

A copied row may itself declare references on other fields. Those are followed by the
same rule, recursively, subject to `max_reference_closure_depth` in policy (default 2),
with a visited set keyed by `(target_case_id, source_entity_type, source_id)`. A
reference that exceeds the depth bound, that fails any precondition, or that is already
visited becomes an `UNRESOLVED` record and is counted in the report. Truncation is
never silent.

### `PLACEMENT_MISSING_ENDPOINT_BUS_V1` — PROPOSED, `ENGINEERING_DEFAULT`

Consumes `placement-evidence-v1-1/line_component_proposals.jsonl`: 684 records across 51
Cases, all with `outcome == 'LINE_PLACEMENT_PROPOSED'`. All 684 have at least one endpoint
anchored on a rule-generated port; 553 have at least one endpoint on an accepted node
and 0 have both endpoints on accepted nodes.

This rule does not re-derive placement and does not re-run the D4.1 rules. D4.1's
`PLACEMENT_LINE_REPRESENTATION_V1` decision is consumed as an input and cited in
`evidence_refs` through the proposal's `proposal_id`, `anchor_id` and `anchor_origin`. The
export rule is a distinct rule because materializing an endpoint declaration into a CSV
row is a different act from proposing a placement.

An endpoint is unresolved when its `anchor_origin` is not `ACCEPTED_NODE`. Every such
endpoint needs the Bus row that its source declaration names but no Case-local row
supplies.

Action: append one Bus row per **distinct unresolved `raw_endpoint_value`** of the
consumed proposals to the referring Case's `02_Bus.csv`. Measured: 782 distinct generated
ports carry 565 distinct unresolved raw endpoint values, because 217 raw values map to
more than one port. The port count and the row count are different measures and must not
be conflated; 565 Bus rows result, and the measured value is reported rather than
assumed.

A generated Bus row materializes a field only when that field has explicit evidence for
that endpoint. No attribute is filled from station context, Case nominal voltage,
directory naming, the feeder head, or any default.

`Bus_ID` carries the endpoint identity the existing placement rule already determined:
the `raw_endpoint_value` **verbatim**. This layer consumes that identity and never mints
or computes one; the blanket prohibition on minting identifiers still applies.

`Bus_BaseKV` comes from the endpoint's own voltage evidence, joined from
`placement-evidence-v1-1/line_endpoint_evidence.jsonl` on
`(source_line_id, endpoint_side)` and cross-checked against the endpoint's
`raw_endpoint_value`; a mismatch is `EVIDENCE_JOIN_MISMATCH` and leaves the record
`UNRESOLVED`. A non-null value is copied verbatim when every occurrence contributing to
the same `raw_endpoint_value` agrees on one distinct non-null value. When the evidence is
absent the value is **null** with reason `VOLTAGE_EVIDENCE_ABSENT`; when occurrences
disagree it is **null** with reason `VOLTAGE_EVIDENCE_CONFLICT` and no representative is
selected. Measured: all 815 unresolved endpoint occurrences carry
`voltage_evidence == null`, and none of the 565 distinct raw values has a non-null
voltage, so every generated row leaves this field null.

`Bus_Station_ID` is filled only when the referring Case's `02_Bus.csv` carries exactly
one distinct non-empty `Bus_Station_ID`, and that value is copied verbatim. Otherwise it
is **null** with reason `STATION_EVIDENCE_NOT_UNIQUE`. Measured over the 4,951 Cases with
a `02_Bus.csv`: 495 have exactly one distinct non-empty value, 4,644 have more than one,
and 20 have none. No station is chosen by ordering, proximity, name similarity or any
other tie-break.

`Bus_Name`, `Bus_Phase` and `Bus_IsSource` have no evidence in any consumed artifact and
are **null**.

In CSV materialization a null field is written as an empty field, the source format's own
representation of an absent value; the null is preserved as `null` in the ledger and the
provenance sidecar.

`08_Line.csv` receives **no** new row: the source Line row already exists and the proposal
is a placement representation of it, carrying `NOT_A_NEW_LINE_DEVICE`.

## UNRESOLVED taxonomy

Nothing in this section is written to a delivered CSV. Every entry is one ledger record
with its own `reason`, and the report aggregates by reason.

| Reason | Population |
|---|---:|
| `MULTIPLE_EXTERNAL_MATCH` | 1,661 |
| `UNDEFINED_GLOBAL` | 34,750 |
| `LOCAL_UNRESOLVED_ONLY` | 3,148 |
| `TIER_NOT_MATERIALIZED` (tier `CROSS_STATION`) | 89,472 |
| `INSUFFICIENT_PLACEMENT_EVIDENCE` | 78 Feeders |
| `NON_UNIQUE_PLACEMENT` | 8 Feeders |
| `MANUAL_LAYOUT_REQUIRED` | 1,401 Feeders |
| `NO_SOURCE_LINE_LAYOUT_BASIS` | 1,259 Feeders |
| `CLOSURE_DEPTH_EXCEEDED` / `CLOSURE_PRECONDITION_FAILED` | measured |

`TIER_NOT_MATERIALIZED` is the population that satisfies every
`CROSS_CASE_REFERENCE_COPY_V1` precondition except the tier gate: unique external match,
single candidate, unique identity, type compatible, no explicit voltage conflict, and a
`CROSS_STATION` candidate. It is a subset of the 136,852 published cross-case references
and overlaps none of the other reasons.

The 25 Cases with `GRID_CASE_FEEDER_MISSING` are still delivered with all twelve CSV
files. Missing Feeder rows are not completion targets of this contract.

## Completion policy

Policy is `configs/nanjing_completion_policy_v1.json`, validated against
`docs/spec/nanjing_completion_policy_v1.schema.json`. Recognized fields:

- `schema_version` — const `nanjing_completion_policy_v1`;
- `policy_version` — free string, recorded in every ledger record;
- `materialize_tiers` — non-empty subset of `["SAME_STATION", "CROSS_STATION"]`;
- `enabled_rules` — non-empty subset of the three inference rule ids
  (`ACCEPTED_DETERMINISTIC_RECOVERY_V1`, `CROSS_CASE_REFERENCE_COPY_V1`,
  `PLACEMENT_MISSING_ENDPOINT_BUS_V1`). `SOURCE_PASSTHROUGH_V1` is unconditional and is
  not a lever: a delivery without its source rows is not a delivery;
- `max_reference_closure_depth` — integer 0..8;
- `placement_endpoint_bus` — boolean, enables `PLACEMENT_MISSING_ENDPOINT_BUS_V1`.

Policy is the only supported lever for regenerating v1 against new client feedback.
The policy's canonical JSON bytes are SHA256-bound into both artifacts' manifests, so a
regeneration proves which policy produced it. No rule may read configuration from
anywhere else.

## Ledger artifact

`outputs/nanjing-v1/completion-ledger-v1/`, write-once, canonical JSON/JSONL, no
timestamps:

| File | Content |
|---|---|
| `completion_records.jsonl` | one record per completion event of the three inference rules, in states `CONFIRMED` and `PROPOSED` |
| `unresolved_records.jsonl` | the UNRESOLVED taxonomy, one record per entry |
| `case_summary.jsonl` | per-Case counts by state, rule and tier |
| `policy_snapshot.json` | the policy verbatim as consumed |
| `summary.json`, `report.md`, `manifest.json` | aggregate, human report, bindings |

Ledger record fields: `record_id` (`v1-completion:ledger:<sha256>`), `completion_status`,
`confidence_class`, `tier`, `rule_id`, `rule_version`, `case_id`, `source_case_key`,
`source_entity_type`, `donor_source_entity_type`, `source_record_ref`,
`donor_source_record_ref`, `raw_field`, `raw_reference_value`, `evidence_refs`
(D4.2 `index_id`/`reference_id`, D4.1 `proposal_id`/`anchor_id`, D3 `edge_id`),
`closure_depth`, `policy_version`, `policy_sha256`, `reason`.

Required in every record: `record_id`, `completion_status`, `confidence_class`,
`rule_id`, `rule_version`, `case_id`, `source_case_key`, `evidence_refs`, `policy_version`,
`policy_sha256`. Nullable: `tier` (null when the rule assigns no tier),
`donor_source_entity_type`, `donor_source_record_ref` (null except under
`CROSS_CASE_REFERENCE_COPY_V1`), `raw_field` and `raw_reference_value` (null when the
completion is not licensed by a single raw reference), `closure_depth` (null at depth 0)
and `reason` (null for materialized records, required for `UNRESOLVED`). No field is
absent; a nullable field is present and null rather than omitted.

The ledger carries no per-source-row record, as stated under `SOURCE_PASSTHROUGH_V1`.
`SOURCE_PASSTHROUGH_V1` is absent from `completion_records.jsonl`; every delivered source
row's provenance is in the delivery sidecar instead.

`manifest.json` carries `artifact_kind`, `version`, `rule_version`, `schema_version`,
`policy_sha256`, `code_sha256`, `input_manifest_sha256` for every verified upstream,
and the boundary flags `approved:false`, `applied:false`, `canonical_changed:false`,
`accepted_v2_changed:false`, `source_changed:false`, `e3_ready:false`,
`opendss_ready:false`.

## Delivery artifact

`outputs/nanjing-v1/derived-delivery-v1/`:

```
data/数据/<source_case_key>/01_Station.csv … 12_SimConfig.csv
provenance/row_provenance.jsonl
provenance/completion_records.jsonl
provenance/unresolved_records.jsonl
manifest.json
report.md
nanjing-derived-v1.zip
```

`source_case_key` is preserved exactly as the source directory relative path. All 5,159
Cases are delivered, including the 25 without a published Feeder.

**Manifest scope and the archive.** `manifest['files']` inventories every delivered file
**except** `manifest.json` itself and except `nanjing-derived-v1.zip`. The archive is
built after the manifest is final and contains the full delivery tree including
`manifest.json`, so the archive's sha256 is stored **externally**: in
`outputs/nanjing-v1/derived-delivery-v1-verification.json` as `archive_sha256`, and in
the CLI result. It is never written into the manifest. No recursive hashing is performed:
the manifest never hashes the archive, and the archive hash is never a manifest input.
The delivery verifier's inventory check is exactly
`set(manifest['files']) | {'manifest.json', 'nanjing-derived-v1.zip'}`.

Byte fidelity: header bytes, column order, column count, quoting and BOM are identical
to source (`utf-8-sig`, CRLF line endings, trailing CRLF). No CSV column is added,
renamed or reordered. Appended rows are written after the final source row using `\r\n`
and no additional BOM. A CSV with no appended rows is byte-identical to its source
member; the exporter writes such members through unchanged rather than re-serializing
them.

Appended rows are ordered by `(rule_id, provenance_id)` so ordering is a stable
serialization, never a selection.

`row_provenance.jsonl` carries one record per delivered row:

`provenance_id` (`v1-completion:provenance:<sha256>`), `case_id`, `source_case_key`,
`target_file`, `row_index`, `row_kind` (`SOURCE`|`APPENDED`), `completion_status`,
`confidence_class`, `tier`, `rule_id`, `rule_version`, `source_record_ref`,
`donor_source_record_ref`, `raw_field`, `raw_reference_value`, `evidence_refs`,
`policy_id`, `policy_sha256`.

For a `SOURCE` row, `source_record_ref` is the row's own source locator,
`completion_status` is `CONFIRMED`, `rule_id` is `SOURCE_PASSTHROUGH_V1` and
`donor_source_record_ref` is null. For an `APPENDED` row, `source_record_ref` is the
referring Case's record locator that carried the raw reference, and
`donor_source_record_ref` is set only by `CROSS_CASE_REFERENCE_COPY_V1`.

`provenance/` also contains `unresolved_records.jsonl` and `completion_records.jsonl` as
verbatim copies of the two ledger streams, so the recipient can locate every gap and
every inference from the delivery alone without re-running the pipeline.

The zip is deterministic: fixed timestamp `1980-01-01T00:00:00`, fixed compression
level, entries sorted by path, entries exactly `data/数据/**` + `provenance/**` +
`manifest.json` + `report.md`. Identical inputs produce a byte-identical archive.

## Boundaries and prohibitions

- `data/raw/` is opened read-only. No source member, `RawCsvRecord`, source ID,
  reference literal or Decimal is modified, normalized, trimmed or repaired.
- No canonical record, canonical ID, `EntityRef`, resolver result, GridCase boundary or
  accepted topology v2 object is created, edited or deleted by this slice.
- No electrical parameter, Load row, DER row, Transformer, LV Bus, 8760 profile, or
  simulation configuration is generated. Source `10_Load.csv` and `11_DER.csv` remain
  header-only and `12_SimConfig.csv` remains source-verbatim.
- No APPROVE, APPLY or promotion of any prior proposal. Every proposed completion stays
  `PROPOSED` regardless of the D2/D4/D4.1 lifecycle.
- No fuzzy, nearest-neighbour, min-`source_record_ref`, ordering-based or random
  selection. Candidate selection is preconditions plus policy, nothing else.
- No unbounded reference following: the closure depth bound is enforced and every
  truncated or failed branch is recorded.
- **No identifier is ever minted for a delivered row.** `PLACEMENT_MISSING_ENDPOINT_BUS_V1`
  reuses the source-declared endpoint text. Any completion that would require a new
  entity ID is downgraded to `UNRESOLVED` instead.
- A `CROSS_STATION` reference is never materialized under the v1 policy. Enabling it is
  a policy revision requiring the client's export-partition and ownership decision.

## Known limitations

1. The D4.2 `voltage_relationship == 'COMPATIBLE'` check on `SAME_STATION` candidates
   rests on `voltage_basis == 'SOURCE_HEAD_CONTEXT'`, comparing a station-head context
   rather than terminal voltages. It is an evidence tier, not a proven voltage
   equivalence, and the report must say so.
2. An appended row can introduce a reference that resolves neither in the referring
   Case nor within the closure bound. Such references are recorded as `UNRESOLVED` and
   are not resolved by this slice.
3. `PLACEMENT_MISSING_ENDPOINT_BUS_V1` is the only rule that produces a row for an
   entity that has no source row of its own. Because no voltage evidence and no
   unambiguous station evidence exists for these endpoints, a generated row carries
   `Bus_ID` and five null attributes. These are **declaration completions**, not modelled
   buses, and are the highest-scrutiny object in the delivery. A consumer must not read
   their empty fields as zero, as a measured absence of the attribute, or as an
   implication about the bus's voltage or station.
4. The delivery contains `PROPOSED` rows. `manifest.json` and `report.md` state
   `approved:false` prominently, and every row's `completion_status` is available in
   the sidecar, but a consumer that ignores the sidecar can still read a proposal as an
   assertion.
5. This slice does not reduce the open question set. Q-CONN-001, Q-PHASE-001,
   Q-TRANSFORMER-001, Q-SIMCONFIG-001 and Q-CASE-001 remain `OPEN`.

## Validation and verification

An independent validator under `src/grid_case_generator/validation/completion_export.py`
re-derives every materialized row and every UNRESOLVED record from the persisted
upstream artifacts and the policy, without calling the engine's internal helpers. It
asserts: upstream manifest SHA256 chain intact; every appended row traces to exactly one
ledger record; every appended row's bytes equal the donor source row's bytes for
`CROSS_CASE_REFERENCE_COPY_V1`; every `PLACEMENT_MISSING_ENDPOINT_BUS_V1` `Bus_ID`
equals its `raw_endpoint_value`; tier membership obeys `materialize_tiers`; closure
depth obeyed; no new identifier minted; CSV byte fidelity for untouched Cases; and
`data/raw/` plus every upstream artifact unchanged before and after.

The artifact verifier rejects a tampered manifest, a non-canonical JSON line, an
uninventoried file, a flipped boundary flag, and a `policy_sha256` mismatch. A separate
`PYTHONHASHSEED` reproduction must be byte-identical for the CSV tree, the sidecar and
the zip.

## Test plan

The contract test plan is written before implementation:

1. policy schema: version pin, unknown-field rejection, enum and range validation;
2. `CROSS_CASE_REFERENCE_COPY_V1` truth table: unique / multiple candidate / type
   incompatible / explicit voltage conflict / tier not enabled — one case each;
3. tier gating: with `materialize_tiers = ["SAME_STATION"]`, no `CROSS_STATION` row is
   written and every one is recorded as `TIER_NOT_MATERIALIZED`;
4. verbatim copy: an appended `SWITCH` row's bytes equal the donor Case's source row
   bytes;
5. closure: a two-level chain, a cycle, and a depth-bound exceedance — the last
   recorded as `UNRESOLVED` and counted in the report;
6. placement rule: appended `Bus_ID` equals `raw_endpoint_value`; `08_Line.csv` row
   count unchanged;
7. CSV fidelity: a Case with no completions has twelve byte-identical files;
8. determinism: `PYTHONHASHSEED` 1 and 999 subprocess runs plus a same-seed repeat are
   byte-identical across CSV, sidecar and zip;
9. verifier: tampered sidecar row, flipped manifest flag and altered `policy_sha256`
   each raise;
10. input immutability: `data/raw/`, `source-import-v2` and `accepted-topology-v2`
    snapshots unchanged;
11. boundary: the 25 Cases without a published Feeder still deliver twelve CSVs;
12. zip: entry set equals `manifest.files` plus the archive metadata, and a repeated
    deterministic build is byte-identical.

Measured values — Case count, CSV count, materialized row counts per rule and tier,
appended Bus row count, and the UNRESOLVED breakdown — are reported from the run. They
are not asserted as literals in tests.

## Versioning

Contract and rule-analysis version `1.1.0`, incorporating revision 001. Artifact
directories `completion-ledger-v1` and `derived-delivery-v1` — the `-v1` suffix denotes
the first published generation of this contract family, not the contract version, and no
artifact was ever published under 1.0.0. Generated-ID namespaces
`v1-completion:ledger:<sha256>` and `v1-completion:provenance:<sha256>` over canonical
ordered UTF-8 JSON. Archive name `nanjing-derived-v1.zip`.

`PLACEMENT_MISSING_ENDPOINT_BUS_V1` carries `rule_version` `1.1.0`; the other three rules
remain at `1.0.0`. Rule ids are unchanged: the D3 precedent for renaming
(`SERIES_EXACT_DIRECT_V1` → `_V2`) applied to a rule whose V1 had already been published
and reviewed, which these have not.

A policy-only change regenerates both artifacts under the same version with a new
`policy_sha256`. A revision that changes a rule precondition, a tier or a prohibition is a
major bump and then requires a rule-id rename for any rule whose published output would
differ. See [revision 001](revisions/nanjing_v1_completion_export_revision_001.md) §5.
