# v1 `CROSS_CASE_REFERENCE_COPY_V1` closure — decision paper

| Item | Value |
|---|---|
| Status | **OPEN — not implemented.** Three clauses are underdetermined by the shipped artifacts |
| Date | 2026-09-19 |
| Contract | `docs/spec/nanjing_v1_completion_export.md` §"`CROSS_CASE_REFERENCE_COPY_V1` closure" |
| Measurement | `scripts/analysis/closure_probe*.py`, results below |

**The closure is not implemented, and this paper does not claim the contract is
satisfied.** `walk_closure` exists and is unit-tested but no rule calls it: every record
in the shipped ledger carries `closure_depth` `0` (materialized) or `null` (unresolved),
and `CLOSURE_DEPTH_EXCEEDED` / `CLOSURE_PRECONDITION_FAILED` are never emitted.

## What the measurement establishes

Run against the thirteen published roots with `configs/nanjing_completion_policy_v1.json`
(`materialize_tiers = ["SAME_STATION"]`):

| Measure | Value |
|---|---:|
| `append_plan` entries | 1,476 |
| `CROSS_CASE_REFERENCE_COPY_V1` records | 2,544 |
| Placement Bus rows | 565 |
| Distinct donor rows | 1,364 |
| Donor rows declaring references the audit also indexed | 326 |
| Audit rows sitting on those donor rows | 342 |
| …of those, passing `eligible()` | **1** |

The one survivor (`数据/上新河变_10kV渔人#2线256/03_Switch.csv#data-row=18`,
`Switch_ToBus = 3801038085500745728`) resolves to a donor row that is **already in the
plan**, with six contributing `record_ids`. Wiring the closure under this policy would
therefore add **one ledger record and zero CSV bytes** (`addition_count` 3,109 → 3,110;
`appended_row_count` unchanged at 2,041).

That is a measurement of *this input under this policy*. It is **not** evidence the
closure semantics are settled, and it is not stable under a policy change: with both
tiers enabled the level-0 population grows to 14,650 rows, 546 level-1 rows are reached,
18 are eligible — and still zero need a new CSV row. Level-2 eligible: 0.

## The three undetermined clauses

### a. What can check a donor-local reference in the destination?

`case_boundary_audit.py:109-111` **excludes** references whose
`local_resolution_status == 'EXACT'` before emitting any row (summary:
`case_local_exact_excluded = 432,008`, `empty_references_excluded = 890,285`). So a
reference that resolved exactly inside the donor's own Case has **no row** in
`cross_case_references.jsonl`. Copied into a different Case it may not resolve at all,
and no published stream says whether it does.

Available evidence, and what each would license:

| Option | Uses | Authorised? |
|---|---|---|
| A. Treat "no audit row" as "no reference" | — | **No.** It asserts a resolution that was never computed, and would silently drop a real dangling reference. |
| B. Re-resolve against `global_reference_index.jsonl` (950,605 rows) in the destination Case | audit artifact only | **No, not as written.** That index is an audit-side view of *declarations*; re-resolving with it is a new computation the contract does not specify, and doing it in the export layer duplicates D4.2's resolver. |
| C. Treat the reference as `CLOSURE_PRECONDITION_FAILED` with the destination Case as context | audit artifact only | **Plausible, needs confirmation.** It never asserts a resolution; it records that the evidence to decide was never published. |
| D. Re-run the D4.2 audit with copied rows included | the audit's own code | **Out of scope for v1.** It changes a published analysis artifact. |

**Recommendation: C.** It is the only option that neither invents a resolution nor
re-derives D4.2, and it fails closed. **Needs your confirmation**, because it makes the
closure's record count depend on an absence of evidence rather than on evidence.

### b. Per level, which Case is the destination, donor, tier and blocker context?

The contract says "followed by the same rule" but not *in which Case's context* the
followed reference is judged. A copied row physically lands in the referring Case `C`,
while the reference it declares was audited in the donor Case `D`.

| Option | Level-1 eligibility judged in | Destination member | Tier / blockers from |
|---|---|---|---|
| E. Donor context | `D` (the audit row's own `case_id`) | `C` | `D` ↔ candidate |
| F. Destination context | `C` | `C` | `C` ↔ candidate |
| G. Both must hold | `D` and `C` | `C` | both |

Measured: of the 342 candidate rows, all 342 have `case_id` equal to the donor row's own
Case, so E is the only option the current audit can evaluate without new resolution work.
Under F, the eligibility of all 342 is unknowable from the published streams — which is
clause (a) again.

**Recommendation: E**, and **this needs your confirmation**: it means a row copied into
`C` can be licensed by evidence about `D`, so `C`'s own blocker status does not gate its
own copies. **Note the prohibition this must not break:** the review already flagged that
donor-context `eligible()` must **not** be reused as if it were a destination-context
verdict. E is only safe if the record states which Case it was judged in.

### c. Dedup keys, depth, truncation and failure reporting

| Question | Options | Recommendation |
|---|---|---|
| Completion-event dedup key | contract's `(target_case_id, source_entity_type, source_id)`; or `(destination_member, donor_ref)` as the plan uses | **Both, for different things**: the visited set uses the contract's key; the row plan keeps `(destination_member, donor_source_record_ref)`. |
| Appended-row dedup key | unchanged — revision 004's `(destination, donor member, donor row)` | unchanged |
| `depth` of a row reached by several seeds | shortest; first-found; max | **Shortest**, so depth is a property of the graph rather than of seed order |
| Multiple seeds reaching one node | one record listing all seeds in `evidence_refs`; or one record per seed | **One record, all seeds sorted** — matching revision 004's "a row backed by three references lists three ids" |
| Depth-exceeded nodes | emit a record per node; or one summary record | **One record per node** with `CLOSURE_DEPTH_EXCEEDED` |
| `closure_depth` on materialized records | contract says **null at depth 0**; the code writes `0` | **Fix the code and bump the artifact version** — see below |

**Needs your confirmation:** the depth of a multiply-reached node and the seed-merging
rule are not stated anywhere; both change the record count and therefore every digest.

## Consequential, already-determined work

`closure_depth` is a contract violation independent of the above: the contract says
"null at depth 0" (`:347`) and `completion_ledger.py` writes `0` on all 32,637
materialized records. Fixing it changes **every `record_id`** and therefore every
published artifact, so it requires a contract revision and a new artifact version rather
than an edit in place. It is **not** done.
