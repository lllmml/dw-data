# E2.3-D4 — Synthetic Backbone Construction Proposal

D4 proposes **30 RULE_GENERATED backbone edges in 30 bundles across 30 Feeders**,
with **zero new junctions or devices**. All effects below are
**PROPOSAL_ONLY_COUNTERFACTUAL**. Accepted v2, source facts and historical artifacts
remain unchanged. No proposal is APPROVED or APPLIED.

Baseline HEAD was `47f8d22861112fd6b5a0730eecb898293560b4b4`, initially clean.
After session resumption an unrelated untracked `CLAUDE.md` appeared and was preserved.
Delivery SHA: `git log -1 --format=%H -- docs/handoff/2026-09-17-e2-3-d4-synthetic-backbone.md`.

## Evidence and generation boundary

The 1,402 SYNTHETIC_BACKBONE_REQUIRED Feeders are not 1,402 already routable Line
components: **1,259 have no source Line**, and another **137 have source Lines but
no accepted Line component**. Only six have any accepted Line component. This limits
minimal structural completion without introducing unreviewed endpoint semantics.

HEAD_TO_UNIQUE_COMPONENT_V1 requires unique feeder scope, compatible MV voltage,
a unique disconnected accepted source-Line component and its unique accepted Bus
engineering boundary. The raw reference incidence graph supplies an additional veto
for competing source structure. Explicit unresolved OPEN declarations and grounded
attachment points are excluded. Placement is an explicit engineering assumption,
not a claim to recover a real Nanjing connection. Source Line and Bus witnesses are
bound alongside the existing derived-head evidence.

UNIQUE_COMPONENT_BRIDGE_V1, UNBOUND_SWITCH_EXTENSION_V1 and ENGINEERING_JUNCTION_V1
are documented and assessed but **not enabled for automatic placement**: shared
ownership/voltage, AccessPoint existence or an empty remote Switch declaration do not
prove a unique port pair or necessary junction. Full per-Feeder component/anchor and
raw-reference witnesses remain available for review. No S2 blanket acceptance, GIS,
lexical tie breaker, random tree, device generation or impedance assumption is used.

## The 1,402-Feeder cohort

Overlapping gap tags (do not sum):

| Gap | Feeders |
|---|---:|
| DISCONNECTED_SOURCE_LINE_COMPONENTS | 4 |
| HEAD_TO_SOURCE_COMPONENT_GAP | 6 |
| INTER_COMPONENT_GAP | 4 |
| REMOTE_SWITCH_PORT_GAP | 2 |
| ACCESS_POINT_GAP | 1,361 |
| TRANSFORMER_REGION_GAP | 1,402 |
| INSUFFICIENT_STRUCTURE | 1,396 |

Exclusive display taxonomy uses the documented priority: disconnected components 4,
head-to-component 2, AccessPoint 1,355, Transformer region 41 (total 1,402).
These are display labels, not recovery claims.

**Automatic proposal eligible: 1; ambiguous/manual layout: 1,401; rejected: 0.**
The eligible cohort Feeder is 集庆变_10kV弓箭坊#1线113. Four Feeders have nonunique
components/Bus anchors, 1,396 lack accepted Line structure, and 16 have an unresolved
explicit OPEN-cut veto; these reason counts overlap. All 906 hard-contradiction
Feeders outside this cohort remain excluded from automatic proposals.

The full run also considers existing source structure in other cohorts, including
zero-target Feeders. Of 30 proposals, one is from the required cohort, nine from
DETERMINISTIC_RECOVERY and 20 from ROLE_CONFIRMATION_REQUIRED. The latter receive
only topology proposals; no business role or Transformer count is inferred.

## Counterfactual coverage and D2 eligibility

Counts of backbone/target statuses use 5,134 source Feeders; graph totals include all
5,159 cases. Physical and conducting reachability are separately recomputed.

| Measure | Accepted v2 before | Proposal after |
|---|---:|---:|
| Physical backbone Feeders | 33 | 63 |
| Reachable source Lines (both views) | 68 | 127 |
| Reachable existing Transformers (both views) | 5 | 13 |
| Synthetic attachment eligible Feeders | 12 | 20 |
| Eligible existing Transformer candidates | 179 | 301 |
| Missing backbone candidates | 87,276 | 87,154 |
| Missing region candidates | 87,291 | 87,169 |
| Missing backbone or region candidates | 87,291 | 87,169 |
| DETERMINISTIC_RECOVERY | 1,380 | 1,373 |
| SYNTHETIC_BACKBONE_REQUIRED | 1,402 | 1,401 |
| ROLE_CONFIRMATION_REQUIRED | 1,432 | 1,432 |
| HARD_SOURCE_CONTRADICTION | 906 | 906 |

D2's original proposal engine independently confirms the read-only evaluator's
per-Feeder primary class, region count, backbone predicate, eligible target count,
and missing-backbone/region counts on the counterfactual graph. Temporary D2 objects
used for this comparison are discarded, not published or applied.

| Source-target status, both views | Before | Proposal after |
|---|---:|---:|
| FULL | 0 | 0 |
| PARTIAL | 4 | 11 |
| FAILED | 3,417 | 3,410 |
| NO_SOURCE_TARGET | 1,713 | 1,713 |

FAILED→PARTIAL: 7; FAILED→FULL: 0; PARTIAL→FULL: 0.

| Structural measure | Before | Proposal after |
|---|---:|---:|
| Reachable source-Line components, both views | 33 | 63 |
| Reachable Switch groups, physical | 28 | 79 |
| Reachable Switch groups, conducting | 25 | 76 |
| Physical components | 38,407 | 38,377 |
| Conducting components | 42,890 | 42,860 |
| Cycle rank, each view | 3 | 3 |

## Engineering metrics

- One edge per proposed Feeder; zero junctions per Feeder; 30 components attached.
- RULE_GENERATED edges/junctions: **30 / 0**. Source-supported accepted:synth edges:
  **32,315:30**. No source identity is assigned to a generated object.
- Maximum degree of synthetic nodes including inherited feeder heads: **2**;
  maximum degree of newly generated nodes: **0**, because no node is created.
- New physical/conducting cycles: **0 / 0**; existing cycles remain three in each view.
- All **4,483 represented OPEN Switch branches** remain physical and nonconducting;
  original source states and endpoint declarations remain unchanged. Unrepresented
  OPEN references are retained as constraints, not claimed as recovered branches.
- Voltage violations: **0**. Unresolved/excluded inventory anchors: **87,119**.
- Ambiguous placement Feeders across the full population: **1,001**;
  manual-layout Feeders across the full population: **4,175**. Another 23 already
  have the sole Line component connected and need no backbone action.
- Per-Feeder edge/junction counts, component reduction, Line and Transformer deltas
  are persisted in `engineering_metrics.json`.

## Implementation and reproduction

New [specification](../spec/nanjing_synthetic_backbone.md) and
[run/verify guide](../guides/nanjing_synthetic_backbone.md); generation,
independent validation, canonical artifact/replay and CLI modules named
`synthetic_backbone.py`, `synthetic_backbone_artifacts.py`, and
`synthetic_backbone_cli.py`. No dependency changes. Existing source/E2/D1/D2/D3
implementation and contracts remain unchanged.

Formal artifact: `outputs/nanjing-e2-3/synthetic-backbone-proposals-v1/` (16 files).
Independent reproduction: same path with `-reproduction`. Development directories
are not formal evidence. All snapshots, decisions, assumptions and metrics use
canonical serialization, SHA256 bindings and no timestamps. Accepted-v2/source
bindings are checked before case replay. Summary and report are regenerated from
all detail; rehashed semantic tampering is detected.

Full suite: **478 passed** (442 baseline + 36 D4). Compileall and whitespace checks
pass. Tests were written before the corresponding engine/artifact and validator
changes and include red/green checks. Coverage includes unique/tied components and
anchors, raw competing components, case/ownership/hard-conflict/voltage restrictions,
OPEN/CLOSED paths and bypass attempts, cycles, independent generated namespaces,
input immutability, zero-target status, ordering/hash seeds, stale bindings,
source/detail/summary tampering, disconnected/unreviewed generated nodes, independent
D2 eligibility and source-side validator gates.

D3 authoritative verifier passed with its original source/E2/D2/frozen inputs.
Independent D3 replay from baseline code under PYTHONHASHSEED=999 reproduces all
**17 files byte-identically**, including both original manifests. The dedicated
D3 reproduction directories end in `-d4-reproduction`. Accepted manifest SHA256
remains `072c43663425dcb3ecf09053c166c9359e4defc13a069f679e87fefd06dbed1e`.
D4 independent PYTHONHASHSEED=1/999 runs reproduce all **16 files byte-identically**,
including manifest SHA256
`c157b1a7080e709422a522e8bc3bf0bb76220a0edabda55aa0203cba2205f6b2`.
Protected inventory contains **263,843 files** (the existing inventory plus D3/v2);
all SHA256 values and the raw file inventory remain unchanged after generation.
Verification certificates are sibling files prefixed `synthetic-backbone-proposals-v1-`
for D3 authority, protected inputs, independent reproduction and final replay.

## Next slice and stop

Review these 30 backbone proposals and the 1,401 unresolved cohort layouts. The
smallest next design task is an explicit source-constrained placement-evidence
contract for the 137 source-Line Feeders lacking accepted Line representation,
including AccessPoint and remote Switch-port semantics. Feeders without source Lines
need a separately reviewed layout basis; D4 does not manufacture one.

**D4 STOP.** No approval/apply, D5 device generation, E3, OpenDSS or QSTS is authorized
by this delivery. Accepted topology v2 has not changed.
