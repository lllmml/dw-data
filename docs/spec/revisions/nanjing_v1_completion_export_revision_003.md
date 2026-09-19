# Revision 003 — `nanjing_v1_completion_export`

| Item | Value |
|---|---|
| Revision id | `nanjing_v1_completion_export_revision_003` |
| Status | Accepted; corrects one materially incomplete rule and one destructive append instruction |
| Date | 2026-09-19 |
| Supersedes | the `CROSS_CASE_REFERENCE_COPY_V1` precondition list and the append instruction of `docs/spec/nanjing_v1_completion_export.md` |
| Contract after this revision | 1.3.0 |
| Policy schema after this revision | `nanjing_completion_policy_v1` (unchanged) |
| Config after this revision | `policy_version` stays `1.1.0` |
| Published artifacts affected | none |

The 1.2.0 contract's `CROSS_CASE_REFERENCE_COPY_V1` precondition list does not select the cohort the same section says it selects, and the excess is not benign. Separately, its append instruction corrupts a member whose final record carries no terminator. Both are corrected here. No tier, state, confidence class, policy field, prohibition or other rule changes.

---

## 1. `CROSS_CASE_REFERENCE_COPY_V1` is missing four preconditions

**Original statement.** The 1.2.0 contract states the rule fires only when **all** of the following hold:

> - `classification == 'UNIQUE_EXTERNAL_MATCH'`;
> - `external_candidate_count == 1`;
> - the single candidate's `identity_status == 'UNIQUE'`;
> - the single candidate's `type_compatible == true`;
> - `explicit_voltage_conflict_count == 0`;
> - the candidate's `station_relationship` is a member of policy `materialize_tiers`.

and, immediately below:

> With the v1 policy `materialize_tiers = ["SAME_STATION"]`, 2,544 rows are materialized.

**Observed evidence.** Applying those six conditions to `case-boundary-audit-v1/cross_case_references.jsonl` under the v1 policy selects **7,818** references, not 2,544. Adding the conditions the artifact itself uses, one at a time:

| Gate | Survivors | Removed |
|---|---:|---:|
| the six stated preconditions | 7,818 | — |
| `+ candidate.voltage_relationship == 'COMPATIBLE'` | 4,410 | 3,408 |
| `+ local_candidate_count == 0` | 4,410 | 0 |
| `+ candidate.canonical_ref` is present | 4,410 | 0 |
| `+ referring Case has no hard_blockers` | 2,954 | 1,456 |
| `+ donor Case has no hard_blockers` | **2,544** | 410 |

The last row reproduces the contract's own stated population exactly. The definition is `src/grid_case_generator/analysis/case_boundary_audit.py:163-168`.

Of the 3,408 references the stated list wrongly admits, **2,993 carry `voltage_relationship == 'CONFLICT'`** — the D4.2 artifact holds explicit counter-evidence against them — and 415 are `UNKNOWN`. A further 1,866 survive the voltage gate but sit on a Case that the audit classifies as carrying `hard_blockers`.

**Problem.** The rule as written would append **three times** the documented row count into the client delivery, and would do so for 2,993 references whose persisted evidence is that the voltage relationship is contradicted. That inverts the rule's purpose: it exists to materialize cross-Case references that the evidence *supports*. A reader checking the contract against the delivery would find neither the population nor the safety property the contract asserts. The inconsistency is not a presentation defect — implementing the contract literally produces a materially different, and worse, artifact than implementing it as described.

**Corrected rule.** The precondition list becomes:

> The rule fires only when **all** of the following hold:
>
> - `classification == 'UNIQUE_EXTERNAL_MATCH'`;
> - `external_candidate_count == 1`;
> - the single candidate's `identity_status == 'UNIQUE'`;
> - the single candidate's `type_compatible == true` and `canonical_ref` is present;
> - the single candidate's `voltage_relationship == 'COMPATIBLE'` — **positive** voltage
>   compatibility, not merely the absence of an explicit conflict;
> - `local_candidate_count == 0` — the reference does not also resolve Case-locally;
> - the referring Case carries no `hard_blockers`;
> - the donor Case carries no `hard_blockers`;
> - the candidate's `station_relationship` is a member of policy `materialize_tiers`.
>
> This is exactly the audit's `strict_candidate` predicate. With the v1 policy
> `materialize_tiers = ["SAME_STATION"]` it selects **2,544** references across **836**
> referring Cases and **778** donor Cases. Candidate order is never used to select.
>
> The two `hard_blockers` gates are deliberately kept even though they are not policy
> fields: a reference whose admitting or receiving Case the audit already flags as hard-
> contradictory is not a reference this rule may act on.

**Compatibility impact.** None for consumers — no artifact has been published. For the
implementation it is decisive: the materialized row count is 2,544 rather than 7,818,
and 2,993 voltage-contradicted references are excluded rather than appended.

---

## 2. The append separator exists to prevent record concatenation, not to normalize source

**Original statement.** In `## Delivery artifact`:

> A CSV with no appended rows is byte-identical to its source member; the exporter writes
> such members through unchanged rather than re-serializing them.

and

> Appended rows are written after the final source row using `\r\n` and no additional BOM.

**Observed evidence.** In the real intake every member ends with a record terminator, so the instruction is harmless there. It is not harmless in general: a member whose final record carries **no** terminator — the synthetic fixture's `06_EarthingSwitch.csv` is exactly this case, and the reader must not assume the intake's uniformity holds for every member it will ever see — would be written as original bytes immediately followed by the appended block, producing `…last_row<donor_row>`. Two logical records silently become one, and the member's row count then disagrees with the provenance sidecar's.

**Problem.** "Using `\r\n`" is stated as a formatting rule. Read as formatting, it invites the writer either to emit a separator unconditionally (harmless) or to treat the existing bytes as already terminated (destructive). Which one is intended is not recoverable from the text, and one of the two readings silently corrupts data.

**Corrected rule.** Appended to `## Delivery artifact`:

> Before writing the appended block, the writer checks whether the source bytes already
> end with a record terminator (`\r\n`, `\n` or `\r`). If they do not, it writes **one**
> `\r\n` before the block.
>
> **That separator exists only to prevent two logical records from concatenating into
> one. It is not source normalization and it is not a claim about the member's format.**
> The writer never rewrites, re-terminates or re-encodes an existing byte: the source
> region of every delivered member remains verbatim, and the separator is added at the
> single point where generated content begins.
>
> A member that receives appended rows and whose existing records use a different
> terminator therefore ends up with mixed terminators. That is accepted and is reported:
> line endings are not semantic in this format, and normalizing them would violate the
> byte-fidelity guarantee that untouched members depend on.

**Compatibility impact.** None for a member that already ends with a terminator — which
is every member in the current intake, so the separator is never emitted today. It
matters for correctness of the guarantee rather than for the current run.

---

## 3. Version transitions

| Artifact | Before | After | Rationale |
|---|---|---|---|
| `docs/spec/nanjing_v1_completion_export.md` | 1.2.0 | **1.3.0** | A rule's precondition set changes and an append instruction is disambiguated. Minor bump: the change narrows `CROSS_CASE_REFERENCE_COPY_V1` to the cohort the contract already claimed, and no tier, state, confidence class, policy field, prohibition or other rule changes. |
| `VERSION` in `models/completion_export.py` | `1.2.0` | **`1.3.0`** | Carries the contract version. |
| `docs/spec/nanjing_completion_policy_v1.schema.json` | `nanjing_completion_policy_v1` | **unchanged** | `materialize_tiers` still gates the tier and the field set is untouched. The two `hard_blocker` gates are rule preconditions over persisted evidence, not policy settings, so they are deliberately not exposed as levers. |
| `configs/nanjing_completion_policy_v1.json` | `policy_version` `1.1.0` | **unchanged** | The policy's content and effect are unchanged; this revision corrects a rule. |
| Rule ids | — | **unchanged** | `CROSS_CASE_REFERENCE_COPY_V1` keeps its id; its `rule_version` becomes `1.1.0`, because a published row count would differ had the rule ever run. It has not. |
| Artifact directories | — | **unchanged** | Nothing published. |

## 4. Clauses of 1.2.0 that this revision does **not** touch

The three completion states; the four confidence classes; the two tiers and the `SAME_STATION` / `CROSS_STATION` materialization split (the policy tier gate is unchanged — the four added preconditions sit *alongside* it, not in place of it); the closure bound and its `max_reference_closure_depth` lever; `SOURCE_PASSTHROUGH_V1` and `ACCEPTED_DETERMINISTIC_RECOVERY_V1`, including the latter's no-appended-row behaviour; `COHORT_TAXONOMY_V1` and the UNRESOLVED taxonomy; the `PLACEMENT_MISSING_ENDPOINT_BUS_V1` field semantics from revision 001; the delivery-manifest carve-out from revision 001; every prohibition, including the blanket prohibition on minting identifiers; and the twelve-group test plan.
