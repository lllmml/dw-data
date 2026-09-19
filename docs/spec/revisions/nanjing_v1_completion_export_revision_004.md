# Revision 004 — `nanjing_v1_completion_export`

| Item | Value |
|---|---|
| Revision id | `nanjing_v1_completion_export_revision_004` |
| Status | Accepted; splits one ambiguous count into two |
| Date | 2026-09-19 |
| Extends | `docs/spec/nanjing_v1_completion_export.md` 1.3.0 |
| Contract after this revision | 1.4.0 |
| Policy schema after this revision | `nanjing_completion_policy_v1` (unchanged) |
| Config after this revision | `policy_version` stays `1.1.0` |
| Published artifacts affected | none |

---

## 1. `materialized_rows` measured two different things

**Original statement.** Revision 002 added, in the `COHORT_TAXONOMY_V1` subsection:

> It is **classification-only** … `counts['materialized_rows']` is unaffected by it.

The name `materialized_rows` was otherwise undefined. It was introduced as a placeholder in the ledger scaffold, where it was `0`, and revision 002 relied on it without fixing its meaning.

**Observed evidence.** For the v1 policy `CROSS_CASE_REFERENCE_COPY_V1` cohort:

| Measure | Value |
|---|---:|
| audit references passing all nine preconditions | **2,544** |
| distinct `(destination member, donor member, donor row)` triples | **1,476** |
| triples reached by more than one reference | 199, covering **1,267** references |
| distinct destination members that receive rows | 887 |

1,267 references target a triple another reference already covers. Appending one row per reference would write the same donor row into the same destination file twice, so the append set is de-duplicated and only 1,476 rows are written.

**Problem.** `materialized_rows` can be read as either number, and they differ by 1,068 — 41% of the cohort. A reader who takes it as "references the rule acted on" under-reports the evidence trail; a reader who takes it as "rows written" and finds the CSVs disagreeing has no way to tell which was meant. Worse, the de-duplication itself is invisible under a single name: 1,068 references are served by rows they did not individually create, and nothing states that this is intended rather than a lost write.

**Corrected rule.** `materialized_rows` is **removed** in favour of two counts, both required, never conflated:

> - `counts['addition_count']` — materialized rule matches. One per audit reference that
>   passed every precondition, and equal to the number of `PROPOSED` completion records
>   the rule contributed to the ledger. This is the evidence trail: every reference the
>   rule acted on stays individually accounted for.
> - `counts['appended_row_count']` — rows actually written into delivered CSVs.
>   Always `<= addition_count`, and strictly less whenever several references share a
>   donor row. This is what makes the delivery's row arithmetic reconcile against its
>   own CSVs.
>
> The append set is de-duplicated on `(destination member, donor member, donor row)`,
> first occurrence winning. A reference that is served by a row another reference caused
> to be written is **not** omitted from the ledger: it keeps its own completion record,
> and the delivered row's `evidence_refs` carries **every** contributing ledger
> `record_id`, sorted. Collapsing 2,544 additions into 1,476 rows therefore loses no
> evidence, and a row backed by three references lists three ids.
>
> A rule that materializes nothing sets both counts to `0`.

Revision 002's sentence remains accurate in substance — the classification-only rule
contributes to neither count — and its wording is superseded by this revision without
being rewritten, since revisions are records of their time.

**Compatibility impact.** None for consumers; no artifact has been published. The
delivery manifest and report gain both counts, and the report must state the
de-duplication explicitly so that 1,476 written rows beside 2,544 ledger records reads as
intended rather than as data loss.

---

## 2. Version transitions

| Artifact | Before | After | Rationale |
|---|---|---|---|
| `docs/spec/nanjing_v1_completion_export.md` | 1.3.0 | **1.4.0** | One count is replaced by two. Minor bump: no rule precondition, tier, state, confidence class, policy field or prohibition changes. |
| `VERSION` in `models/completion_export.py` | `1.3.0` | **`1.4.0`** | Carries the contract version. |
| `counts` key set | `completion_records`, `unresolved_records`, `materialized_rows`, `cohort_overlap_members` | `completion_records`, `unresolved_records`, `addition_count`, `appended_row_count`, `cohort_overlap_members` | The split above. |
| Policy schema and `policy_version` | — | **unchanged** | Not a policy concern. |

## 3. Clauses that this revision does **not** touch

Everything else, and in particular: the three completion states; the four confidence
classes; the two tiers; all nine `CROSS_CASE_REFERENCE_COPY_V1` preconditions from
revision 003; its closure bound and `max_reference_closure_depth`; `SOURCE_PASSTHROUGH_V1`
and `ACCEPTED_DETERMINISTIC_RECOVERY_V1`; `COHORT_TAXONOMY_V1` and the UNRESOLVED
taxonomy, including revision 002's overlap quantification; the append separator rule from
revision 003; the revision 001 manifest carve-out and generated-Bus-row field semantics;
every prohibition; and the twelve-group test plan.
