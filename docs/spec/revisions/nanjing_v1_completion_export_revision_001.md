# Revision 001 — `nanjing_v1_completion_export`

| Item | Value |
|---|---|
| Revision id | `nanjing_v1_completion_export_revision_001` |
| Status | Accepted; supersedes the affected clauses of the 1.0.0 contract |
| Date | 2026-09-18 |
| Supersedes | `docs/spec/nanjing_v1_completion_export.md` 1.0.0, clauses listed below |
| Superseded by | — |
| Contract after this revision | 1.1.0 |
| Policy schema after this revision | `nanjing_completion_policy_v1` (unchanged identity; see §5) |
| Config after this revision | `configs/nanjing_completion_policy_v1.json` `policy_version` `1.0.0` → `1.1.0` |
| Published artifacts affected | none — no artifact has been produced under 1.0.0 |

This revision replaces four statements in the 1.0.0 contract that the persisted evidence
contradicts. It does not change any rule precondition, any tier, any state, any
confidence class, the policy field set, or any prohibition. It changes only where three
generated fields get their values from, and how the delivery manifest relates to its own
archive.

Nothing here was edited silently: the 1.0.0 clauses are quoted verbatim below and
superseded explicitly. Every measurement is reproducible from the artifacts named in
`Observed evidence`.

---

## 1. `Bus_BaseKV` — the field is not where the contract said it is

**Original statement.** In `PLACEMENT_MISSING_ENDPOINT_BUS_V1`:

> `Bus_BaseKV` is derived from the proposal's `voltage_evidence`;

**Observed evidence.**

- `outputs/nanjing-e2-3/placement-evidence-v1-1/line_component_proposals.jsonl` carries
  **no** `voltage_evidence` field. Its complete key set is `applied, approved,
  assumptions, base_graph_sha256, case_id, conducting, edge_id, endpoint_evidence_class,
  endpoint_values, endpoints, evidence_class, feeder_id, kind, outcome, proposal_id,
  reasons, rule_id, rule_version, scope, source_line_id, source_line_record_ref,
  source_line_ref, stage`.
- The field lives on `placement-evidence-v1-1/line_endpoint_evidence.jsonl`, joinable on
  `(source_line_id, endpoint_side)`.
- Across the 684 consumed proposals there are 815 unresolved endpoint occurrences (those
  whose `anchor_origin != 'ACCEPTED_NODE'`). **All 815 carry `voltage_evidence == null`.**
- Those 815 occurrences carry 565 distinct `raw_endpoint_value`s. **565 of 565 have no
  non-null voltage at all, and 0 have more than one distinct non-null voltage.**

**Problem.** The clause names a field that does not exist on the named input. Read
literally it is unimplementable; read charitably it invites an implementer to reach for
another voltage source — the station head context, the Case nominal voltage, or the
accepted node's voltage — none of which is evidence about *this* endpoint. That is
exactly the substitution the contract's prohibition on filling from station context
exists to prevent. The measurement also shows the fallback would have fired on 100% of
rows, so any substitute value would have been pure invention presented as derivation.

**Corrected rule.**

> `Bus_BaseKV` is taken from the endpoint's own voltage evidence, joined from
> `placement-evidence-v1-1/line_endpoint_evidence.jsonl` on
> `(source_line_id, endpoint_side)` and cross-checked against the endpoint's
> `raw_endpoint_value`. The joined value must equal the proposal endpoint's
> `raw_endpoint_value`; a mismatch is `EVIDENCE_JOIN_MISMATCH` and leaves the record
> `UNRESOLVED`.
>
> If the endpoint's `voltage_evidence` is non-null and every occurrence contributing to
> the same `raw_endpoint_value` agrees on a single distinct non-null value, that value is
> copied verbatim.
>
> If it is null, `Bus_BaseKV` is **null** and the `VOLTAGE_EVIDENCE_ABSENT` reason is
> recorded.
>
> If one `raw_endpoint_value` carries more than one distinct non-null value,
> `Bus_BaseKV` is **null** and `VOLTAGE_EVIDENCE_CONFLICT` is recorded. The conflict is
> never resolved by ordering, and no representative is selected.
>
> No other voltage source — station head context, Case nominal voltage, accepted node
> voltage, or any default — may be substituted.

**Compatibility impact.** None for consumers: no artifact has been published, so no
downstream reader has ever seen a derived `Bus_BaseKV`. After this revision every
generated Bus row carries a null `Bus_BaseKV`. A consumer that needs bus voltage must
either obtain it from the endpoint evidence directly or from a later slice that
establishes voltage evidence; this contract does not supply one.

---

## 2. `Bus_Station_ID` — there is no Case-local station identity to assume

**Original statement.** In `PLACEMENT_MISSING_ENDPOINT_BUS_V1`:

> `Bus_Station_ID` is the Case-local station;

**Observed evidence.** Across all 4,951 Cases that have a `02_Bus.csv`, grouped by the
distinct non-empty `Bus_Station_ID` values in that file:

| Distinct non-empty `Bus_Station_ID` in the Case | Cases |
|---|---:|
| exactly one | 495 |
| more than one | 4,644 |
| none | 20 |

**Problem.** "The Case-local station" presumes a Case has one station identity. It has
one only 10% of the time. The clause as written forces the implementer to pick among
several stations on 4,644 Cases, and every available tie-break — first row, lowest ID,
the station named by the Feeder head — is a selection the contract elsewhere forbids.
`02_Bus.csv` uses more than one `Bus_Station_ID` space within a single Case, so the
ambiguity is structural, not dirty data.

**Corrected rule.**

> `Bus_Station_ID` is filled only when the referring Case's `02_Bus.csv` carries exactly
> one distinct non-empty `Bus_Station_ID`; that value is copied verbatim. Otherwise
> `Bus_Station_ID` is **null** and the `STATION_EVIDENCE_NOT_UNIQUE` reason is recorded.
>
> No station is chosen by ordering, proximity, name similarity, feeder-head association
> or any other tie-break, and no station context is inherited from the feeder, the
> accepted topology or the case directory name.

**Compatibility impact.** None for consumers. After this revision every generated Bus row
carries a null `Bus_Station_ID`, because the 51 target Cases are not among the 495
single-station Cases in any guaranteed way; the measured count per run is reported, not
assumed.

---

## 3. `PLACEMENT_MISSING_ENDPOINT_BUS_V1` — generated rows carry evidence only

**Original statement.** In `PLACEMENT_MISSING_ENDPOINT_BUS_V1`, the field-derivation
sentence read as a group:

> `Bus_BaseKV` is derived from the proposal's `voltage_evidence`; `Bus_Station_ID` is the
> Case-local station; `Bus_Name`, `Bus_Phase` and `Bus_IsSource` are derived or left empty.

**Observed evidence.** Consequences of §1 and §2 combined: of the six `02_Bus.csv`
columns, exactly one — `Bus_ID` — has evidence for these endpoints.

- `Bus_ID`: the raw endpoint value is a declaration the source itself made. It appears in
  the source `08_Line.csv` `Line_FromBus`/`Line_ToBus` text, and it is the identity the
  D4.1 `PLACEMENT_LINE_REPRESENTATION_V1` rule already determined when it proposed the
  Line representation. Measured: 565 distinct values.
- `Bus_BaseKV`: no evidence. §1.
- `Bus_Station_ID`: no unambiguous evidence. §2.
- `Bus_Name`, `Bus_Phase`, `Bus_IsSource`: no evidence anywhere in the consumed
  artifacts. The proposal rows carry no name, no phase and no source flag, and no
  upstream artifact does either.

**Problem.** "Derived or left empty" is a discretionary clause: it lets an implementer
choose per field whether to derive. Combined with the two clauses above it, the natural
reading produced a row where four of six columns are filled from context rather than
evidence. That is the failure mode the project's source-versus-derived separation exists
to prevent, and it would be invisible downstream because the row parses as a normal Bus.

**Corrected rule.**

> A generated Bus row materializes a field only when that field has explicit evidence
> for that endpoint.
>
> - `Bus_ID` carries the endpoint identity the existing placement rule already
>   determined: the `raw_endpoint_value` verbatim. This layer does not mint an
>   identifier and does not compute one; it consumes the identity the placement rule
>   established. `Bus_ID` remains subject to the existing prohibition — no identifier
>   is ever minted for a delivered row, and any completion that would require a new
>   entity identifier is downgraded to `UNRESOLVED`.
> - `Bus_BaseKV` follows §1.
> - `Bus_Station_ID` follows §2.
> - `Bus_Name`, `Bus_Phase` and `Bus_IsSource` are **null**.
>
> The fields are not "derived or left empty"; they are null unless evidence exists. No
> attribute is filled from station context, Case nominal voltage, directory naming, the
> feeder head, or any default.
>
> In CSV materialization a null field is written as an empty field, which is the source
> format's own representation of an absent value; the null is preserved as `null` in the
> ledger and the provenance sidecar.

**Compatibility impact.** No published artifact exists. The delivered row becomes
`Bus_ID` plus five empty fields. This is a materially thinner object than 1.0.0
described, and the contract's `Known limitations` must say so: these are **declaration
completions**, not modelled buses. Consumers that need bus attributes must treat the
appended rows as declaring that an identifier exists, and must not read their empty
fields as zero or as a measured absence of the attribute.

---

## 4. Manifest self-reference — the archive cannot hash itself

**Original statement.** In `## Delivery artifact`, the delivery tree was given as:

> ```
> data/数据/<source_case_key>/01_Station.csv … 12_SimConfig.csv
> provenance/row_provenance.jsonl
> provenance/completion_records.jsonl
> provenance/unresolved_records.jsonl
> manifest.json
> report.md
> nanjing-derived-v1.zip
> ```

together with:

> The zip is deterministic: fixed timestamp `1980-01-01T00:00:00`, fixed compression
> level, entries sorted by path, entries exactly `data/数据/**` + `provenance/**` +
> `manifest.json` + `report.md`.

**Observed evidence.** This is a specification-internal contradiction, not a data
finding: `manifest.json` is listed as a member of the delivery directory **and** as an
entry inside the archive, while `manifest['files']` is defined to inventory every
delivered file with its sha256. If `manifest['files']` also covered the archive, the
manifest's bytes would depend on the archive's hash, which depends on the manifest's
bytes.

**Problem.** Recursive hashing has no fixed point. Any implementation either loops,
omits a file without saying so, or emits a manifest whose inventory silently disagrees
with the directory — and the last of these breaks the very verifier the manifest exists
to enable. The 1.0.0 text did not state which resolution was intended.

**Corrected rule.**

> `manifest['files']` inventories every delivered file **except** `manifest.json`
> itself and except `nanjing-derived-v1.zip`.
>
> The archive contains the full delivery tree including `manifest.json`, built after the
> manifest is final. The archive's sha256 is therefore stored **externally**, in
> `outputs/nanjing-v1/derived-delivery-v1-verification.json` as `archive_sha256`, and is
> returned by the CLI result. It is never written into the manifest.
>
> The delivery verifier's inventory check is exactly
> `set(manifest['files']) | {'manifest.json', 'nanjing-derived-v1.zip'}`.
>
> No recursive hashing is performed anywhere: the manifest never hashes the archive, and
> the archive's hash is never a manifest input.

**Compatibility impact.** No published artifact exists. A consumer verifying the
delivery must read the sidecar to obtain the archive hash; it cannot obtain it from
inside the archive. This is inherent to a self-describing archive and is now stated
rather than implied.

---

## 5. Version transitions

| Artifact | Before | After | Rationale |
|---|---|---|---|
| `docs/spec/nanjing_v1_completion_export.md` | 1.0.0 | **1.1.0** | Generated-row field semantics change and a delivery-inventory rule is added. Minor bump: no rule precondition, tier, state, confidence class, policy field or prohibition changes, and no consumer of 1.0.0 exists. |
| `docs/spec/nanjing_completion_policy_v1.schema.json` | `nanjing_completion_policy_v1` | **unchanged** | The policy field set, enums and ranges are untouched by this revision. Bumping the schema identity would force a config rename for no semantic change. The schema's `description` gains a pointer to this revision so the change is not silent. |
| `configs/nanjing_completion_policy_v1.json` | `policy_version` `1.0.0` | **`1.1.0`** | `policy_version` is recorded verbatim in every ledger record and bound through `policy_sha256`. Bumping it makes "which contract produced this row" answerable from the artifacts alone. |
| Artifact directories `completion-ledger-v1`, `derived-delivery-v1` | — | **unchanged** | Never published under 1.0.0, so there is no superseded artifact to keep apart. The `-v1` suffix denotes the first published generation of this contract family, not its contract version. |
| Rule ids `SOURCE_PASSTHROUGH_V1`, `ACCEPTED_DETERMINISTIC_RECOVERY_V1`, `CROSS_CASE_REFERENCE_COPY_V1`, `PLACEMENT_MISSING_ENDPOINT_BUS_V1` | — | **unchanged** | The D3 precedent (`SERIES_EXACT_DIRECT_V1` → `_V2`) applied to a rule whose V1 had been published and reviewed. These have not. Renaming now would create two names for one unbuilt rule. `PLACEMENT_MISSING_ENDPOINT_BUS_V1`'s semantics are narrowed by §3 and its `rule_version` becomes `1.1.0`. |
| Generated-ID namespaces `v1-completion:ledger:`, `v1-completion:provenance:` | — | **unchanged** | No identifier has been emitted under 1.0.0. The namespace string is a contract constant, not a version. |

If a future revision changes a precondition, a tier or a prohibition, that is a major
bump and, at that point, a rule-id rename for any rule whose published output would
differ.

## 6. Clauses of 1.0.0 that this revision does **not** touch

For avoidance of doubt, the following remain exactly as frozen in 1.0.0 and are not
reinterpreted here: the three completion states and their boundary; the four confidence
classes; the two tiers and the `SAME_STATION` / `CROSS_STATION` materialization split;
all `CROSS_CASE_REFERENCE_COPY_V1` preconditions and its closure bound; the
`ACCEPTED_DETERMINISTIC_RECOVERY_V1` scope and its no-appended-row behaviour; the
UNRESOLVED taxonomy and its populations; the policy field set and its validation rules;
every item under `## Boundaries and prohibitions`, including the blanket prohibition on
minting identifiers; and the twelve-group test plan.
