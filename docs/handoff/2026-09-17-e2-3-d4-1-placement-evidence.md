# E2.3-D4.1 — Source-constrained placement evidence & Line component recovery

Status: implemented, verified and reproduced. Proposal-only. Nothing approved or applied.
Accepted topology v2, raw source, frozen v1 and every historical D1/D2/D3/D4 artifact are
byte-identical after the run.

## Baseline confirmed before any change

`HEAD = 952065965383c6c75361ee3e18931150ed0f54b3`, worktree clean apart from the known
unrelated untracked `CLAUDE.md`. D3 accepted topology v2 and the D4
`synthetic-backbone-proposals-v1` artifact both re-verify and reproduce at that commit.

## Why the 137 exist

A source Line becomes an accepted LINE edge only when both of its Canonical Terminals map
to an accepted node. In this cohort every Line is excluded with `LINE_ENDPOINT_EXCLUDED`,
and none of the Cases has an accepted edge at all, so no Line has two accepted endpoints.
The measured shape of the cohort: 981 published unique Lines, 1,962 declared endpoints,
778 Lines with exactly one accepted endpoint and 203 with none.

The unresolved endpoint is always mediated by a case-local source entity that E2 and D3
decline to represent:

| unresolved endpoint target | Lines |
|---|---|
| ordinary Switch with explicit endpoint declarations | 356 |
| ordinary Switch with non-series incidence (leaf) | 227 |
| non-exact raw reference | 100 |
| AccessPoint | 77 |
| Transformer with non-single incidence | 18 |

139 Line endpoints (113 distinct texts) do not resolve case-locally, and **every one of
them is defined elsewhere in the intake** — 108 as a `Switch_ID` and 5 as an
`AccessPoint_ID`. The Case directories are partial exports: their declarations point at
sibling folders. Widening the same count to every endpoint-bearing field in the cohort
(Switch, Transformer and AccessPoint declarations as well as Line endpoints) gives 974
unresolved texts, 248 distinct, 210 of them defined elsewhere and 38 defined nowhere.
**No cross-Case reference is ever followed**, and none is counted as a competing
structure.

## Root-cause taxonomy of the 137 Feeder

Overlapping reasons over the 981 Lines, mapped to the requested classes:

- **A. `LINE_ENDPOINT_UNRESOLVED`** — 139 endpoints are `NO_ANCHOR_EVIDENCE`, every one of
  them `EXTERNAL_DEFINED`; 134 Lines are blocked this way, carrying
  `CROSS_CASE_REFERENCE_NOT_FOLLOWED`. No `UNDEFINED_REFERENCE` occurs in this cohort.
- **B. `LINE_ENDPOINT_AMBIGUOUS`** — 24 endpoints name a Transformer whose incidence is not
  single (`TRANSFORMER_INCIDENCE_NOT_UNIQUE`); no arbitrary candidate is picked.
- **C. `SWITCH_MEDIATED_LINE`** — 101 `CONFLICTING_ANCHOR` endpoints: 58 on a tie or
  unknown-state Switch, 43 on a Switch whose outer declaration *is* case-local, which is
  D3's exact-direct contract rather than something D4.1 may take over.
- **D. `ACCESSPOINT_MEDIATED_LINE`** — the enabled cohort; 920
  `ENGINEERING_SHARED_REFERENCE_ANCHOR` endpoints.
- **E. `BUS_REFERENCE_GAP`** — 0. No endpoint in this cohort names a case-local Bus that
  E2 failed to project.
- **F. `ONE_SIDED_LINE_COMPONENT`** — 684 Lines recovered on the accepted endpoint plus a
  generated anchor. This is the class the slice is built for.
- **G. `MULTI_LINE_SHARED_REFERENCE`** — 753 shared-reference reviews. Every one is
  `NEEDS_REVIEW` under the disabled general junction rule; the narrow instances are
  recorded as `NARROW_RULE_ENABLED` inside the same review.
- **H. `HARD_CONTRADICTION`** — 0 in this cohort. The 906 global
  `HARD_SOURCE_CONTRADICTION` Feeder are untouched and no override was applied.
- **I. `INSUFFICIENT_SOURCE_PLACEMENT_EVIDENCE`** — 78 Feeder, all of whose Lines are
  blocked by class A.

Feeder primary status: 51 `PLACEMENT_EVIDENCE_SUFFICIENT`, 78
`INSUFFICIENT_PLACEMENT_EVIDENCE`, 8 `NON_UNIQUE_PLACEMENT`, 0
`ACCESSPOINT_POLICY_REQUIRED`, 0 `REMOTE_SWITCH_POLICY_REQUIRED`, 0
`HARD_SOURCE_CONTRADICTION`. The two policy statuses are zero because no AccessPoint in
the cohort carries a declaration and because every Feeder with a remote-Switch block also
recovered at least one Line, so a stronger status takes priority; 18 Feeder still carry
`LINE_BLOCKED_REMOTE_SWITCH_POLICY` as an overlapping reason.

## Rules enabled, and the one that stays off

`ACCESSPOINT_ENGINEERING_ANCHOR_V1` (74 anchors), `SWITCH_LEAF_PLACEMENT_ANCHOR_V1`
(221) and `SWITCH_SERIES_PLACEMENT_ANCHOR_V1` (270). All are `RULE_INFERRED` and PROPOSED;
no object is ever `SOURCE_CONFIRMED`, because the source fact is that a Line row names an
entity and the derived claim is that the entity is a structural junction.

`DERIVED_SHARED_REFERENCE_JUNCTION_V1` is reviewed but **disabled**: shared raw text proves
the same reference string, not an electrical junction, so no unbounded-degree anchor is
generated and Switch degree >= 3 stays `NON_UNIQUE_PLACEMENT`.

Two Case-level gates fail closed. A group of Lines declaring the identical anchor pair is
withdrawn in full (`PARALLEL_DUPLICATE_DECLARATION_NOT_REPRESENTABLE`, 40 Lines) because
the source never says whether that is one circuit recorded twice or two parallel circuits,
so no representative is chosen. If the survivors would raise the physical or conducting
cycle rank, or reconnect a base non-conducting edge, the whole Case is withdrawn.

## Results

| | count |
|---|---|
| recovered Line components (proposal-only) | 684 |
| new proposed anchors | 565 (74 AccessPoint, 221 leaf Switch, 270 series Switch) |
| parallel duplicate Lines withdrawn | 40 |
| Cases withdrawn by the cycle / open-cut gate | 0 |
| source Lines blocked | 297 (134 no anchor, 105 non-unique, 58 remote-switch policy) |

Downstream validation, `ACCEPTED_V2 + D4.1_PLACEMENT_PROPOSALS + D4_BACKBONE_REPLAY`:

| metric | D4 before | D4.1 after |
|---|---|---|
| physical backbone | 63 | 95 |
| reachable source Lines | 127 | 232 |
| reachable source Line components | 63 | 95 |
| reachable existing Transformers | 13 | 23 |
| attachment eligible Feeder | 20 | 22 |
| eligible Transformer candidates | 301 | 349 |
| missing backbone candidates | 87,154 | 86,289 |
| backbone-required Feeder | 1,401 | 1,369 |

The D4 engine was re-run unchanged on both sides; the graph grows from 70,719 nodes and
32,345 edges to 71,775 and 33,522, with the cycle rank unchanged at 3.

The 30 existing D4 proposals: **30 `STILL_VALID`**, 0 `SUPERSEDED_BY_BETTER_PLACEMENT`,
0 `NOW_AMBIGUOUS`, 0 `INVALID`, plus 2 `NEW_ON_PLACEMENT_COUNTERFACTUAL`. The 30 are
untouched because D4's `HEAD_TO_UNIQUE_COMPONENT_V1` requires an existing disconnected
Line component, which by construction the 137 cohort does not have — the two cohorts are
disjoint. The 2 new proposals are both inside the 137, and they are the answer to
"additional automatic backbone eligible Feeder": **2**.

Other required checks: new cycles 0, OPEN cuts preserved in all 137 Cases, voltage
violations 0, duplicate source Lines 0, generated devices 0, source endpoint text
preserved in all 137 Cases, accepted topology v2 unchanged. The 1,259 no-source-Line
Feeder receive no layout proposal of any kind and are tagged `NO_SOURCE_LINE_LAYOUT_BASIS`.
The 1,713 zero-target Feeder are unchanged.

## Verification performed

- Full suite: 522 tests pass, including 44 new D4.1 tests (27 engine/validator, 17 artifact).
- Independent validator: all 137 Cases PASS with no reason — it re-derives anchors,
  namespace, ownership, voltage, endpoint text, device absence, cycles and OPEN cuts from
  the Case input and the emitted objects, without importing the engine's conclusions.
- Manifest binding tamper, detail tamper with a rehashed manifest, stale accepted/D4
  binding and scope violation all fail as required.
- `PYTHONHASHSEED=999` reproduction into `placement-evidence-v1-reproduction` is
  byte-identical across all 18 files, manifest included.
- Every protected root (`data/raw`, `nanjing-e1`, `nanjing-e2`, `nanjing-e2-1`,
  `nanjing-e2-2`, `nanjing-e2-3-d`) re-hashes identically, and under `nanjing-e2-3` only
  the new `placement-evidence-v1` directory has a new mtime.

## Next slice

Recommended: a **D4.1 delivery review** before anything else, focused on the three enabled
rules' provenance choice and on whether `DERIVED_SHARED_REFERENCE_JUNCTION_V1` should be
narrowed or enabled for degree-2 sources. The 78 `INSUFFICIENT_PLACEMENT_EVIDENCE` Feeder
need an external bus/switch export to move at all — that is a data-procurement question,
not a rule question. The 1,259 no-source-Line Feeder need a separate engineering layout
policy and must not be reached by extending these rules.

Not entered: no-source-Line free layout, D5, E3, OpenDSS, QSTS, zero-Transformer device
generation. Each needs its own authorization.
