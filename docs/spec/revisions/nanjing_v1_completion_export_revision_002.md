# Revision 002 — `nanjing_v1_completion_export`

| Item | Value |
|---|---|
| Revision id | `nanjing_v1_completion_export_revision_002` |
| Status | Accepted; adds one classification-only rule and one quantified clarification |
| Date | 2026-09-19 |
| Supersedes | none — this revision adds and clarifies rather than replacing |
| Extends | `docs/spec/nanjing_v1_completion_export.md` 1.1.0 |
| Contract after this revision | 1.2.0 |
| Policy schema after this revision | `nanjing_completion_policy_v1` (unchanged) |
| Config after this revision | `policy_version` stays `1.1.0` — see §3 |
| Published artifacts affected | none |

This revision does two things. It **quantifies** an overlap the 1.1.0 contract asserted existed but never measured, and it **names** the rule that produces the UNRESOLVED taxonomy, which the 1.1.0 contract required every record to carry but never defined for that family. It does not change any existing rule's preconditions, any tier, any state, any confidence class, the policy field set, or any prohibition.

---

## 1. The UNRESOLVED taxonomy overlap is 1,259 Feeders

**Original statement.** In `## UNRESOLVED taxonomy`, the 1.1.0 contract lists four reasons with their populations and states:

> Every entry is one ledger record with its own `reason` … `TIER_NOT_MATERIALIZED` … is a subset of the 136,852 published cross-case references and overlaps none of the other reasons.

The overlap clause was written for `TIER_NOT_MATERIALIZED` only. Nothing in the section said whether the four **cohort** reasons overlap each other, or by how much.

**Observed evidence.** Measured against the persisted artifacts:

- `synthetic-backbone-proposals-v1/feeder_gap_taxonomy.jsonl` filtered to `d3_primary == 'SYNTHETIC_BACKBONE_REQUIRED'` yields **1,402** rows.
- Of those, `outcome == 'MANUAL_LAYOUT_REQUIRED'` yields **1,401** — the `MANUAL_LAYOUT_REQUIRED` population.
- Of those 1,401, `source_line_count == 0` yields **1,259** — the `NO_SOURCE_LINE_LAYOUT_BASIS` population.
- The split of the 1,402 is exact: 1,259 with no source Line, 142 with source Lines, and 1 `AUTOMATIC_PROPOSAL_ELIGIBLE`.

So `NO_SOURCE_LINE_LAYOUT_BASIS` is a **strict subset** of `MANUAL_LAYOUT_REQUIRED`, not a sibling of it.

**Problem.** A reader of `unresolved_records.jsonl` sees 1,401 records carrying `MANUAL_LAYOUT_REQUIRED` and 1,259 carrying `NO_SOURCE_LINE_LAYOUT_BASIS`, and has no way to tell from the contract that 1,259 Feeders appear in both. A reader who assumed the four reasons partition the affected Feeders would over-count the distinct Feeders by 1,259 — reporting 2,660 where the true distinct count is 1,401. The contract's own instruction not to sum silently has no force if the magnitude it protects against is unstated.

**Corrected rule.** Appended to `## UNRESOLVED taxonomy`:

> The four cohort reasons are **not** mutually exclusive. `NO_SOURCE_LINE_LAYOUT_BASIS`
> (1,259 Feeders) is a strict subset of `MANUAL_LAYOUT_REQUIRED` (1,401 Feeders): the
> `SYNTHETIC_BACKBONE_REQUIRED` cohort is 1,402 Feeders, of which 1,259 have no source
> Line, 142 have source Lines, and 1 is `AUTOMATIC_PROPOSAL_ELIGIBLE`. The 1,259
> Feeders in both cohorts therefore carry **two** `UNRESOLVED` records, one per reason,
> because the two reasons describe genuinely distinct problems and both are reported.
>
> `counts['cohort_overlap_members']` reports the overlap explicitly: it counts distinct
> `(case_id, feeder_id)` identities that appear under more than one reason, so a full
> run reports **1,259**. The overlap key is deliberately **not** `source_record_ref`,
> which embeds the reason and would therefore never show an overlap. Consumers must use
> this count rather than summing the per-reason populations.
>
> `TIER_NOT_MATERIALIZED` remains disjoint from all four cohort reasons.

**Compatibility impact.** None for the artifact's contents — the records and their
populations are unchanged, because the implementation already keyed the overlap on
Feeder identity. What changes is that a consumer can now interpret the taxonomy
correctly from the contract alone.

---

## 2. `COHORT_TAXONOMY_V1` / 1.0.0 — the taxonomy's rule identity

**Original statement.** In `## Ledger artifact`, the 1.1.0 contract states:

> Required in every record: `record_id`, `completion_status`, `confidence_class`,
> `rule_id`, `rule_version`, `case_id`, `source_case_key`, `evidence_refs`,
> `policy_version`, `policy_sha256`.

Meanwhile `## Rules` defines exactly four rules, all of which *materialize* something,
and `## UNRESOLVED taxonomy` describes the cohort reasons without naming any rule:

> Every entry is one ledger record with its own `reason`, and the report aggregates by
> reason.

**Observed evidence.** The two sections cannot both be satisfied. Every `UNRESOLVED`
cohort record is required to carry a non-null `rule_id`, and no rule id exists for the
family that produces it. Measured `unresolved_records.jsonl` populations: 78 + 8 + 1,401
+ 1,259 = 2,746 records with no defined `rule_id`.

**Problem.** Three resolutions were available and only one is honest. Leaving `rule_id`
null violates an explicit contract statement. Reusing an existing rule id misattributes
the record to a rule that did not produce it — the cohort taxonomy is precisely the
*absence* of an applicable materializing rule, so citing one would be false provenance.
The remaining option is to name what actually produces these records: a classification
rule over persisted evidence.

**Added rule.**

> ### `COHORT_TAXONOMY_V1` / 1.0.0 — classification only
>
> The cohort taxonomy is a rule with its own identity, because it produces ledger
> records and those records must cite what produced them.
>
> It is **classification-only**. It evaluates the four cohort predicates against the
> persisted placement and backbone artifacts, emits one `UNRESOLVED` / `NONE` record per
> matching identity, and **never materializes anything**: it appends no CSV row, creates
> no entity, mints no identifier, and produces no object that any other rule may consume
> as a topological input. `counts['materialized_rows']` is unaffected by it.
>
> Its records carry `rule_id = 'COHORT_TAXONOMY_V1'` and `rule_version = '1.0.0'`,
> `source_entity_type = 'FEEDER'`, `confidence_class = 'NONE'`, and
> `source_record_ref = 'cohort:<reason>:<case_id>:<feeder_id>'`. That last value is a
> ledger-level identifier, not a source locator: the streams' own `feeder_id` is a
> Canonical id and is not passed off as a source row. It is never routed through
> `SourceRecordRef`, which validates the `zip-member:…` form.
>
> Predicates and supports:
>
> | Reason | Stream | Predicate | Population |
> |---|---|---|---:|
> | `INSUFFICIENT_PLACEMENT_EVIDENCE` | `feeder_classification.jsonl` | `primary_status == 'INSUFFICIENT_PLACEMENT_EVIDENCE'` | 78 |
> | `NON_UNIQUE_PLACEMENT` | `feeder_classification.jsonl` | `primary_status == 'NON_UNIQUE_PLACEMENT'` | 8 |
> | `MANUAL_LAYOUT_REQUIRED` | `feeder_gap_taxonomy.jsonl` | `d3_primary == 'SYNTHETIC_BACKBONE_REQUIRED'` and `outcome == 'MANUAL_LAYOUT_REQUIRED'` | 1,401 |
> | `NO_SOURCE_LINE_LAYOUT_BASIS` | `feeder_gap_taxonomy.jsonl` | the same, and `source_line_count == 0` | 1,259 |
>
> The rule is **not** a policy lever. Unlike the three inference rules, it is absent
> from `enabled_rules`: the taxonomy is a report of what the evidence already shows, and
> suppressing it would make the delivery's UNRESOLVED section a policy artefact rather
> than an evidence artefact. `configs/nanjing_completion_policy_v1.schema.json` is
> therefore **unchanged** by this revision.
>
> The rule performs no IO; its streams arrive as already-loaded rows on
> `CompletionInputs`.

**Compatibility impact.** Additive. Every artifact this project has produced so far
predates the completion layer, so no published record carries a `rule_id` for this
family. A consumer that switches on `rule_id` will now see a fifth value; one that
ignores `rule_id` for `UNRESOLVED` records is unaffected. The rule cannot change any
topology, because it materializes nothing.

---

## 3. Version transitions

| Artifact | Before | After | Rationale |
|---|---|---|---|
| `docs/spec/nanjing_v1_completion_export.md` | 1.1.0 | **1.2.0** | Adds one classification-only rule and quantifies a taxonomy overlap. Minor bump: no existing rule's preconditions, no tier, no state, no confidence class, no policy field and no prohibition changes. |
| `VERSION` in `models/completion_export.py` | `1.1.0` | **`1.2.0`** | The module constant carries the contract and rule-analysis version; it must track the contract. |
| `docs/spec/nanjing_completion_policy_v1.schema.json` | `nanjing_completion_policy_v1` | **unchanged** | The taxonomy is explicitly not a policy lever, so the policy field set, enums and ranges are untouched. Its `description` gains a pointer to this revision. |
| `configs/nanjing_completion_policy_v1.json` | `policy_version` `1.1.0` | **unchanged at `1.1.0`** | Deliberately not bumped, and this differs from revision 001. Revision 001 changed what the *policy* does — the generated Bus row's field semantics are governed by `placement_endpoint_bus`. This revision adds an unconditional classification that no policy field controls, so the policy's own content and effect are unchanged. `policy_version` identifies the policy, not the contract; the contract version is carried separately by the artifact manifest's `version`. |
| Artifact directories `completion-ledger-v1`, `derived-delivery-v1` | — | **unchanged** | Neither has been published. |
| Rule ids of the four existing rules | — | **unchanged** | No existing rule's behaviour changes. |

## 4. Clauses of the 1.1.0 contract that this revision does **not** touch

The three completion states and their boundary; the four confidence classes; the two
tiers and the `SAME_STATION` / `CROSS_STATION` materialization split; the four existing
rules and all their preconditions, including the `CROSS_CASE_REFERENCE_COPY_V1` closure
bound; the delivery-manifest carve-out from revision 001; the generated Bus row's
field semantics from revision 001; the policy field set and its validation rules; every
item under `## Boundaries and prohibitions`, including the blanket prohibition on minting
identifiers; and the twelve-group test plan.
