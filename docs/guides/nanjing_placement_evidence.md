# D4.1 source-constrained placement evidence

Contract: [placement-evidence specification](../spec/nanjing_placement_evidence.md).
Accepted v2 is the deterministic base and stays immutable. Nothing in this command
approves or applies a proposal. Formal output is separate from source, historical
artifacts, accepted v2 and the D4 artifact. Runtime is stdlib; no new dependencies.

```bash
PYTHONHASHSEED=1 .venv/bin/python -u -m grid_case_generator.analysis.placement_evidence_cli analyze \
  --source outputs/nanjing-e1/source-import-v2 \
  --baseline outputs/nanjing-e2/topology-v2 \
  --projection outputs/nanjing-e2-2/switch-projection-design-v1 \
  --feeder outputs/nanjing-e2-2/feeder-coverage-v1 \
  --recovery outputs/nanjing-e2-3/topology-recovery-evidence-v1 \
  --d1 outputs/nanjing-e2-3/synthetic-completion-contract-v1 \
  --d2 outputs/nanjing-e2-3/synthetic-topology-proposals-v1 \
  --frozen outputs/nanjing-e2/topology-v1 \
  --analysis outputs/nanjing-e2-3/deterministic-topology-recovery-v1 \
  --accepted outputs/nanjing-e2-3/accepted-topology-v2 \
  --d4 outputs/nanjing-e2-3/synthetic-backbone-proposals-v1 \
  --output outputs/nanjing-e2-3/placement-evidence-v1-1
```

Output must not exist. Verification uses `verify` in place of `analyze`, all the same
roots, and requires the existing output. Both commands verify the authoritative D3
chain, bind the D4 artifact manifest, compare source and accepted case evidence, replay
every D4.1 detail and summary stream from authoritative inputs, and recompute the whole
D4 backbone counterfactual instead of reading it back.

The D3 chain verification dominates the runtime; it re-derives all 5,159 Cases. Budget
roughly a quarter of an hour per command.

For independent reproduction use `PYTHONHASHSEED=999` and a new output directory ending
in `-reproduction`. Compare all 17 files including the manifest. No timestamps, GIS,
random seeds or ordering-based selection are used; the hash seed only tests independence
from Python hash iteration.

## Cohort and scope

The target cohort is the D3-after `SYNTHETIC_BACKBONE_REQUIRED` Feeder that own source
Line rows but no accepted Line component. It is derived from the D4 engine's own
taxonomy inside the same run, so the cohort definition cannot drift from D4's.

The 1,259 backbone-required Feeder with no source Line at all are out of scope; they are
tagged `NO_SOURCE_LINE_LAYOUT_BASIS` and receive no layout proposal of any kind. The
1,713 zero-target Feeder stay unchanged. No Transformer, LV Bus, Load or DER is ever
generated, and no D2 hard contradiction is bypassed.

## What is recovered

`ACCESSPOINT_ENGINEERING_ANCHOR_V1` turns a case-local unique AccessPoint into one
junction node. `SWITCH_LEAF_PLACEMENT_ANCHOR_V1` and `SWITCH_SERIES_PLACEMENT_ANCHOR_V1`
turn an ordinary case-local Switch whose own outer declarations carry no case-local
anchor into an `ATTACH`/`UNBOUND` or `IN`/`OUT` port pair joined by an internal Switch
branch whose `conducting` follows the recorded state. A Line is then represented only
when every declared endpoint reaches an anchor — an accepted node or one of those
generated ports. The Line keeps its own source identity: no second Line device exists.

Every generated object is `UNRESOLVED` and PROPOSED. An AccessPoint is never labelled
`SOURCE_CONFIRMED`: the source fact is that a Line row names it; the derived claim is
that it is a structural junction.

## Gates to read before trusting a proposal

`PARALLEL_DUPLICATE_DECLARATION_NOT_REPRESENTABLE` withdraws every member of a group of
Lines that declare the identical anchor pair — the source never says whether that is one
circuit recorded twice or two parallel circuits, so no representative is chosen.

`PLACEMENT_WOULD_CREATE_CYCLE` and `PLACEMENT_WOULD_BYPASS_OPEN_CUT` withdraw the whole
Case when the surviving proposals would increase the physical or conducting cycle rank,
or would reconnect the two sides of a base non-conducting edge. Both are reported with
their before/after ranks in `rejected_candidates`.

`DERIVED_SHARED_REFERENCE_JUNCTION_V1` is reviewed but disabled. Shared raw text proves
the same reference string, not an electrical junction, so no unbounded-degree anchor is
generated; Switch degree >= 3 stays `NON_UNIQUE_PLACEMENT`.

## Reading the output

`target_feeders.jsonl` gives one primary status per cohort Feeder plus overlapping
outcomes and reasons. Primary priority is `HARD_SOURCE_CONTRADICTION`,
`PLACEMENT_EVIDENCE_SUFFICIENT`, `NON_UNIQUE_PLACEMENT`, `ACCESSPOINT_POLICY_REQUIRED`,
`REMOTE_SWITCH_POLICY_REQUIRED`, `INSUFFICIENT_PLACEMENT_EVIDENCE`. Overlapping reasons
must not be summed with the primary counts.

`line_endpoint_evidence.jsonl` carries one record per declared endpoint with its verbatim
text, resolver status, evidence class and conflicting witnesses. `line_component_proposals.jsonl`
holds the recoverable Lines; `rejected_candidates.jsonl` holds the rest with reasons.
`counterfactual_coverage.json` is the
`ACCEPTED_V2 + D4.1_PLACEMENT_PROPOSALS + D4_BACKBONE_REPLAY` composition, with the D4
engine re-run unchanged on both sides.

`d4_replay.jsonl` has one row per D4 backbone proposal: `origin: BEFORE` rows are the D4
proposals reclassified on the placement counterfactual as `STILL_VALID`,
`SUPERSEDED_BY_BETTER_PLACEMENT`, `NOW_AMBIGUOUS` or `INVALID`; `origin: NEW` rows are
the proposals the placement newly makes eligible. None is approved or applied.

All coverage numbers are `PROPOSAL_ONLY_COUNTERFACTUAL`. `accepted_physical_backbone` in
the `after` column is the D4 predicate on the proposal graph, not accepted topology.

STOP after delivery review. Approval/apply, no-source-Line free layout, D5, E3, OpenDSS
and QSTS need separate authorization.
