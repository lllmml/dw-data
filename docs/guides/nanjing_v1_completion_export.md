# Nanjing v1 completion export

Turns the frozen source intake plus the published D-series evidence chain into a
completion ledger and a source-shaped delivery, exactly as frozen in
`docs/spec/nanjing_v1_completion_export.md`.

**No completion decision is made here.** Every rule ran against persisted evidence
before this step; this layer makes those decisions deliverable and auditable.

## Invocation

```bash
bash scripts/run_completion_export.sh [OUTPUT_ROOT]     # default outputs/nanjing-v1
```

or directly:

```bash
PYTHONHASHSEED=1 python -m grid_case_generator.analysis.completion_export_cli analyze \
  --source outputs/nanjing-e1/source-import-v2 \
  --baseline outputs/nanjing-e2/topology-v1 \
  --projection outputs/nanjing-e2-2/switch-projection-design-v1 \
  --feeder outputs/nanjing-e2-2/feeder-coverage-v1 \
  --recovery outputs/nanjing-e2-3/topology-recovery-evidence-v1 \
  --d1 outputs/nanjing-e2-3/synthetic-completion-contract-v1 \
  --d2 outputs/nanjing-e2-3/synthetic-topology-proposals-v1 \
  --frozen outputs/nanjing-e2/topology-v1 \
  --d3-analysis outputs/nanjing-e2-3/deterministic-topology-recovery-v1 \
  --accepted-v2 outputs/nanjing-e2-3/accepted-topology-v2 \
  --d4 outputs/nanjing-e2-3/synthetic-backbone-proposals-v1 \
  --placement outputs/nanjing-e2-3/placement-evidence-v1-1 \
  --audit outputs/nanjing-e2-3/case-boundary-audit-v1 \
  --policy configs/nanjing_completion_policy_v1.json \
  --ledger outputs/nanjing-v1/completion-ledger-v1 \
  --output outputs/nanjing-v1/derived-delivery-v1
```

Re-check an existing export without writing anything:

```bash
... completion_export_cli verify --source ... --ledger ... --output ...
```

## Why thirteen roots and not just the archive

The obvious interface would be `--input nanjing.zip --output delivery.zip`. It cannot
work: the completion rules decide from persisted evidence, and **none of the evidence is
derivable from the source archive**. Cross-case references come from the D4.2 audit's
136,852-row counterfactual resolution; placement endpoints come from the D4.1 proposal
artifact; the recovery additions come from D3; the cohort taxonomy comes from D2 and D4.
Re-deriving any of them here would duplicate a different slice's analysis and let the
two disagree. The command therefore takes each artifact as a verified input and binds
its manifest digest into both outputs.

## Outputs

`<root>/completion-ledger-v1/` — write-once, canonical, no timestamps:

| File | Content |
|---|---|
| `completion_records.jsonl` | one record per completion event of the three inference rules |
| `unresolved_records.jsonl` | the UNRESOLVED taxonomy, one record per entry, per reason |
| `case_summary.jsonl` | per-Case counts by state, rule and tier |
| `policy_snapshot.json` | the policy verbatim as consumed |
| `summary.json`, `report.md`, `manifest.json` | aggregate, human report, bindings |

`<root>/derived-delivery-v1/`:

```
data/数据/<source_case_key>/01_Station.csv … 12_SimConfig.csv
provenance/row_provenance.jsonl          one record per delivered row
provenance/completion_records.jsonl      verbatim copy of the ledger stream
provenance/unresolved_records.jsonl      verbatim copy of the ledger stream
manifest.json
report.md
nanjing-derived-v1.zip
```

`<root>/derived-delivery-v1-verification.json` carries the archive sha256, the
provenance and manifest digests, the protected input digests and the validator verdict.
The archive digest lives only here: the archive contains the manifest, so a manifest
that hashed the archive could not be hashed by it.

## What a consumer must know

1. **The delivery contains `PROPOSED` rows.** No completion is approved or applied.
   `manifest.json` and `report.md` state `approved:false`; every row's status is in the
   sidecar. A consumer that ignores the sidecar can read a proposal as an assertion.
2. **Generated Bus rows are declaration completions, not modelled buses.** Each carries
   `Bus_ID` — the source-declared endpoint text, verbatim, never minted — and five null
   attributes, because no consumed artifact carries voltage or an unambiguous station for
   these endpoints. Their empty fields are not zero and not a measured absence.
3. **`SOURCE_HEAD_CONTEXT` is an evidence tier, not a proven voltage equivalence.** The
   `SAME_STATION` voltage check compares a station-head context, not terminal voltages.
4. Untouched members are byte-identical to source: same BOM, quoting, line endings and
   trailing terminator. `10_Load.csv` and `11_DER.csv` are header-only; `08_Line.csv`
   gains no row.

## Policy lever

`configs/nanjing_completion_policy_v1.json` is the only supported lever for regenerating
against client feedback. Its canonical bytes are SHA256-bound into both manifests, so a
regeneration proves which policy produced it. `materialize_tiers` gates the tier;
`CROSS_STATION` stays off until the export-partition and ownership question is answered.

## Verification

`verify` re-derives every materialized row from the persisted artifacts and re-checks:
row byte fidelity against the source archive, donor-row identity, no minted identifier,
tier membership, closure bound, the provenance joins, the delivery manifest's own
per-file digests and boundary flags, the archive inventory and the `policy_sha256`
chain.

A provenance record may not choose its own test: a row that claims `SOURCE`, or an
appended row that names a rule which never appends or omits the donor ref it is checked
against, is rejected rather than checked cheaply. A SOURCE row must mirror its own
position in its own member, so it cannot call itself a verbatim copy of some other
matching row. `closure_depth` bounds are checked on every record, but see the known gap
below — no rule currently walks a closure, so that check is inert on this artifact.

The validator shares no code with the engine, so a defect the engine and the writer
agree on is still caught. Every check it could not run — because a root was not supplied
— is named in `measured['checks_skipped']` rather than reported as a pass.

Two runs over identical inputs are byte-identical for the ledger, the delivery tree, the
provenance sidecar and the archive.

## Known gaps against the contract

These are open, and a reader should not infer them as done.

1. **Reference closure is not exercised.** The contract specifies that a copied row's own
   references are followed recursively under `max_reference_closure_depth`, with
   `CLOSURE_DEPTH_EXCEEDED` / `CLOSURE_PRECONDITION_FAILED` recorded on overflow.
   `walk_closure` is implemented and unit-tested, but no rule calls it: every record in
   the current artifact has `closure_depth` 0 or null, and no closure reason is ever
   emitted. The validator's `CLOSURE_NOT_BOUNDED` is a real check but is inert on this
   artifact. Either the rule must follow references or the contract must say it does not.
2. **The recovery population's source stream is ambiguous.** `ACCEPTED_DETERMINISTIC_RECOVERY_V1`
   records are read from the D3 analysis stream `accepted_connections.jsonl` — 29,528
   edge additions. The contract names `accepted-topology-v2/additions.jsonl`, which holds
   59,354 rows: the same 29,528 edge rows byte-for-byte, plus 29,826 node additions that
   carry no `edge_id` and so cannot produce a record in the current shape. The materialized
   content is identical either way, but the contract needs to say whether node additions
   are completion events and how they would be identified.
3. **`COHORT_TAXONOMY_V1` names two different populations.** The contract describes it as
   a feeder classification rule. In the artifact, 2,746 of its 137,054 records are those
   feeder cohorts; the other 134,308 are `CROSS_CASE_REFERENCE_COPY_V1` precondition
   failures, which reuse the rule id. Pre-existing engine behaviour, now published as a
   headline aggregate.

## Spec measurements that no longer reproduce

The code matches revision 003's own gate table exactly (7,818 → 4,410 → 2,954 → 2,544).
Several figures in `docs/spec/nanjing_v1_completion_export.md` predate that revision and
do not reproduce against the published artifacts. The artifact is right in each case.

| Spec | Says | Artifact | Why |
|---|---:|---:|---|
| `TIER_NOT_MATERIALIZED` | 89,472 | **12,106** | 89,472 is the 1.0.0 reading (CROSS_STATION with no *explicit* conflict). Revision 003 made the gate positive `voltage_relationship == 'COMPATIBLE'` plus two hard-blocker gates, which reclassifies the rest into `VOLTAGE_NOT_COMPATIBLE`, `REFERRING_CASE_HARD_BLOCKER` and `DONOR_CASE_HARD_BLOCKER` — three reasons the taxonomy table does not list. |
| `cohort_overlap_members` | 1,259 | **1,345** | 1,259 counts only `NO_SOURCE_LINE_LAYOUT_BASIS ⊂ MANUAL_LAYOUT_REQUIRED`. 86 further feeders are in both a placement cohort and `MANUAL_LAYOUT_REQUIRED`. The definition is right; the predicted total ignored that pair. |
| Cases with a `02_Bus.csv` | 4,951 | **5,159** | All 5,159 Cases have one; 495 / 4,644 / 20 sum to 5,159, not 4,951. |
| Values mapping to >1 port | 217 | **248** | Same class: the description holds, the number does not. |
| "2,544 rows are materialized" | 2,544 rows | 2,544 records → **1,476 rows** | The record-vs-row conflation revision 004 (→1.4.0) exists to forbid. The artifact reports both: `addition_count` 3,109, `appended_row_count` 2,041. |

## Boundaries

- `data/raw/` is opened read-only; no source byte, ID or reference is modified.
- No canonical record, accepted topology v2 object or GridCase boundary is touched.
- No electrical parameter, Load row, DER row, Transformer, LV Bus, 8760 profile or
  simulation configuration is generated.
- No fuzzy, nearest-neighbour, ordering-based or random selection anywhere.
- The open question set is unchanged: Q-CONN-001, Q-PHASE-001, Q-TRANSFORMER-001,
  Q-SIMCONFIG-001 and Q-CASE-001 remain `OPEN`.

## Where the runtime goes

The export reads roughly 1.9 GB of upstream streams and writes about 1.3 GB. Most of the
wall clock is upstream manifest verification (`verify_manifests` re-hashes every file of
all thirteen roots) and the delivery's per-row provenance. The upstream *semantic*
replays are deliberately not run here — each has its own `verify` command — because
re-running D4.2's 1.4 GB counterfactual build inside every export would cost hours and
prove nothing the manifest binding does not.
