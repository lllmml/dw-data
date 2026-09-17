# E2.3-D3 — Deterministic recovery and accepted topology v2

D3 implements two individually reviewed deterministic Switch rules in a new accepted
artifact. **Accepted physical backbone Feeders: 17 → 33.** Source-target coverage does
not improve: reachable Transformers remain 5, target FULL remains 0. Broad S2 remains
unaccepted; synthetic completion/E3/OpenDSS/QSTS are not entered.

Starting HEAD was `8807e46283c8c403747650484144ed3a69f97040`, with a clean worktree.
Delivery SHA: `git log -1 --format=%H -- docs/handoff/2026-09-17-e2-3-d3-deterministic-recovery.md`.
No dependency or lockfile change; runtime remains stdlib.

## Delivered files and immutable outputs

- [D3 specification](../spec/nanjing_deterministic_topology_recovery.md),
  [rule decision](../decisions/nanjing_derived_topology_v2.md),
  [run/verify guide](../guides/nanjing_deterministic_topology_recovery.md).
- `generation/deterministic_recovery.py`: complete raw incidence, exact declaration,
  state/identity/type/voltage gates and deterministic overlay; no synthetic placement.
- `analysis/deterministic_recovery.py`: taxonomy, rule reviews, independent eligibility
  evaluator and detail aggregation; `analysis/deterministic_recovery_cli.py`: CLI.
- `io/deterministic_recovery_artifacts.py`: separate artifact writer, input bindings,
  stream replay and independently reconstructed authoritative case evidence.
- `tests/generation/test_deterministic_recovery.py` and
  `tests/generation/test_deterministic_recovery_artifacts.py`: 33 new tests.
- README, AGENTS and gated slices now identify the D3 delivery review boundary.

Formal analysis: `outputs/nanjing-e2-3/deterministic-topology-recovery-v1/` (14 files).
Formal accepted graph: `outputs/nanjing-e2-3/accepted-topology-v2/` (3 files).
Independent reproduction uses the same two names with `-reproduction` suffix.
Development directories are not formal evidence. Generated files stay in ignored outputs.
Verification and protected SHA256 inventory are siblings named
`deterministic-topology-recovery-v1-verification.json` and
`deterministic-topology-recovery-v1-input-sha256.json`.

Analysis manifest SHA256: `3c72061c0882709422717a74be042af086517d7dc19f3181e995f2c6d195c1f6`.
Accepted manifest SHA256: `072c43663425dcb3ecf09053c166c9359e4defc13a069f679e87fefd06dbed1e`.

## Rule acceptance and candidate populations

Accept `SERIES_EXACT_DIRECT_V2 / 1.0.0` only when all exact direct declaration,
unique full incidence, ordinary known-state Switch, case-local identity, inherited MV
voltage and no-hard-conflict prerequisites hold. Accept
`LEAF_SWITCH_REPRESENTATION_V2 / 1.0.0` only for the separately proven unique incoming
Line and matching explicit local declaration; the remote port stays **UNBOUND**.
No external route, connection, junction or Transformer port is invented.

Source rows, endpoint text and state remain unchanged. OPEN is physical and nonconducting;
CLOSED conducts. All additions are RULE_INFERRED, zero are SOURCE_CONFIRMED or RULE_GENERATED.
Keep broad S2 unresolved declarations, reverse/tie semantics, unproved Transformer ports
and AccessPoint physical roles NEEDS_REVIEW. Reject collapsing a multi-incidence
Transformer into an MV junction. Q-CONN-001 and Q-TRANSFORMER-001 remain OPEN.

Candidate records (all cases, not just the original 1,383 cohort):

| Family | Candidate | Accepted | Rejected | Needs review | Baseline preserved |
|---|---:|---:|---:|---:|---:|
| ACCESS_POINT_RECOVERY | 34,661 | 0 | 6,636 | 28,025 | 0 |
| MULTI_INCOMING_TRANSFORMER_REVIEW | 26 | 0 | 5 | 21 | 0 |
| OTHER_DETERMINISTIC_REVIEW | 164,631 | 0 | 164,631 | 0 | 0 |
| REFERENCED_TRANSFORMER_RECOVERY | 14,271 | 0 | 4,786 | 20 | 9,465 |
| SERIES_SWITCH_RECOVERY | 60,997 | 45 | 19,076 | 41,876 | 0 |
| SWITCH_TERMINAL_REPRESENTATION | 45,833 | 14,868 | 14,604 | 16,361 | 0 |

Distinct Feeders by family/status (columns and families can overlap):

| Family | Candidate Feeders | Accepted | Rejected | Needs review | Baseline preserved |
|---|---:|---:|---:|---:|---:|
| ACCESS_POINT_RECOVERY | 4,868 | 0 | 887 | 3,981 | 0 |
| MULTI_INCOMING_TRANSFORMER_REVIEW | 17 | 0 | 4 | 13 | 0 |
| OTHER_DETERMINISTIC_REVIEW | 3,739 | 0 | 3,739 | 0 | 0 |
| REFERENCED_TRANSFORMER_RECOVERY | 1,491 | 0 | 465 | 20 | 1,026 |
| SERIES_SWITCH_RECOVERY | 2,938 | 40 | 766 | 2,171 | 0 |
| SWITCH_TERMINAL_REPRESENTATION | 2,492 | 907 | 688 | 1,200 | 0 |

The 60,997 series inventory includes 37 nonunique two-Line groups; the historical
60,960 E2.2 structural candidates excluded them. The complete candidate stream has
320,419 records: 271,461 Switch groups, 34,661 AccessPoints, 14,297 referenced Transformers.
The 96,041 unreferenced Transformers across all cases remain in source/D2 case inputs;
none receives an invented deterministic connection.

A candidate REJECTED in a hard-conflict case forbids a new interpretation; it does not
remove an inherited v1 attachment. Thus the 9,465 BASELINE_PRESERVED Transformer records
are the conflict-free subset, while all 14,245 original v1 Transformer nodes remain.
Every status retains source/conflict witnesses. `rule_variant_summary` separately splits
series direct, partial/different, unresolved and tie candidates; 76 ordinary exact-direct
candidates yield 45 accepted, 13 rejected and 18 still unresolved (including unsupported
outer entity types). The other 4 exact-compatible E2.2 candidates are tie devices.

New accepted deterministic edges: **29,528**, comprising **14,913 Switch branches** and
**14,615 source Line edges**. New derived Switch ports: **29,826**; no physical device is
created. Of accepted Switch branches, 10,430 are CLOSED and 4,483 OPEN. Rejected Switch
candidate interpretations: 198,311; unresolved: 58,237. These candidate counts are not
physical edges deleted from source. The existing 5,134 synthetic feeder-head nodes are
inherited assumptions, not new D3 generation.

## Original 1,383 deterministic recovery Feeders

Mutually exclusive display taxonomy (fixed priority, not a recoverability promise):

| Taxonomy | Feeders |
|---|---:|
| ACCESS_POINT_RECOVERY | 301 |
| KNOWN_OPEN_STRUCTURAL_RECOVERY | 1 |
| MULTI_INCOMING_TRANSFORMER_REVIEW | 0 |
| OTHER_DETERMINISTIC_REVIEW | 0 |
| REFERENCED_TRANSFORMER_RECOVERY | 19 |
| S2_ONLY_BACKBONE_RECOVERY | 1 |
| SERIES_SWITCH_RECOVERY | 23 |
| SWITCH_TERMINAL_REPRESENTATION | 1,038 |

Every Feeder also retains all overlapping rule families and candidate IDs. For example,
1,383 have series candidates, 1,380 are S2-only backbone cases, 1,344 have AccessPoints,
1,323 have source OPEN Switches, 1,072 have one-incidence Switch candidates, and 986 have
referenced Transformers. These numbers must not be summed. Multi-incidence review has
17 Feeders in the full source population but none in this original D2-primary cohort.

## Three coverage axes

The target denominator is unchanged: 5,134 source Feeders; 25 no-Feeder cases remain
in case artifacts and in all-case graph metrics. Physical and conducting target
histograms are identical here, but are independently recomputed:

| Source-target status | Before | After |
|---|---:|---:|
| FULL | 0 | 0 |
| PARTIAL | 4 | 4 |
| FAILED | 3,417 | 3,417 |
| NO_SOURCE_TARGET | 1,713 | 1,713 |

FAILED→PARTIAL = 0, FAILED→FULL = 0, PARTIAL→FULL = 0; unchanged = 5,134.
Reachable source Transformers **5 → 5**. Reachable Lines **25 → 68 (+43)** in both views.
Many accepted local Switch representations remain disconnected from the head, so new
edge counts must not be mistaken for target reachability or backbone gain.

Accepted topology status below is explicitly scoped to **source Line/Switch/Transformer
identity groups**, as in the prior strict topology metric; it does not certify unknown
AccessPoint roles, unbound remote connections or simulation readiness:

| View / status | FULL before→after | PARTIAL before→after | FAILED before→after |
|---|---:|---:|---:|
| Physical | 0 → 2 | 17 → 31 | 5,117 → 5,101 |
| Conducting | 0 → 1 | 17 → 32 | 5,117 → 5,101 |

All-case physical components: 38,109 → 38,407 (+298).
All-case conducting components: 38,109 → 42,890 (+4,781).
The increase includes newly represented local/OPEN/unbound ports, not invented bridges.
Cycle rank is **3 → 3 in each view**, retaining the original cycles; no new cycle.
Every case also checks `m - n + c` with the correct physical/conducting active edge count.
Single-family deltas are separately measured: series alone +33 reachable Lines, leaf
alone +3; cumulative +43 includes interaction, so family effects are not added naively.

## D2 eligibility after accepted v2

No synthetic proposal object is instantiated. The independent eligibility evaluator
reproduces D2 **per Feeder**, including primary class, region count, usable backbone,
eligible target count and the original missing-backbone/region rejection count, before
it evaluates the accepted v2 graph.

| Measure | Before | After |
|---|---:|---:|
| Accepted physical backbone Feeders | 17 | 33 |
| DETERMINISTIC_RECOVERY | 1,383 | 1,380 |
| SYNTHETIC_ATTACHMENT_ELIGIBLE | 11 | 12 |
| SYNTHETIC_DEVICE_ELIGIBLE | 0 | 0 |
| SYNTHETIC_BACKBONE_REQUIRED | 1,402 | 1,402 |
| ROLE_CONFIRMATION_REQUIRED | 1,432 | 1,432 |
| HARD_SOURCE_CONTRADICTION | 906 | 906 |
| INSUFFICIENT_FOR_AUTOMATIC_PROPOSAL | 0 | 2 |
| Eligible existing Transformer target candidates | 177 | 179 |
| Missing backbone **or** region candidates (D2 comparable metric) | 87,293 | 87,291 |
| Missing physical backbone candidates alone | 87,293 | 87,276 |
| Missing/nonunique region candidates alone | 87,293 | 87,291 |

Of the 16 newly backbone-bearing Feeders, 11 were role-confirmation cases and 5 were
deterministic-review cases. One former deterministic Feeder becomes attachment-eligible
for 2 existing Transformers.
Two others have a physical backbone but 0 or 3 eligible regions, respectively; neither
gets an arbitrary attachment node. Backbone expansion alone therefore cannot remove
most of the candidate rejection count. Hard contradiction Feeders remain 906; no
identity disambiguation, voltage override or operating-state closure was introduced.

## Validation and next minimum slice

Full suite: **442 passed** (409 baseline + 33 D3). Compileall and Git whitespace checks
PASS. D2 was verified against its six authoritative inputs and reproduced from the
original baseline code: all 15 files byte-identical, including its historical manifest.
D3 independent PYTHONHASHSEED=1/999 runs reproduce all **17 files byte-identically**,
including both manifests. Each run checks all eight input bindings/verifiers before
and after, replays every output stream, and checks the independent D2 baseline result.
Final authoritative verification additionally reconstructs every persisted case input
from the verified source/E2/D2 inputs. Protected inventory: **263,826 files**, all SHA256
unchanged; raw file inventory unchanged; frozen topology-v1 verifier PASS.

Tests cover known OPEN/CLOSED and exact prerequisites, identity/voltage/cross-case,
source/raw endpoint immutability, unbound leaf ports, no multi-T arbitrary selection,
cycle detection/retention, no generated objects, region ties, input ordering/hash seeds,
empty/no-Feeder pipeline, no-overwrite/isolation, rehashed detail/summary/accepted-graph
and manifest/input-evidence tampering, independent eligibility, and source/v1 byte safety.

Next minimum slice recommendation: review the one newly eligible Feeder's two existing
Transformer attachment candidates and collect a bound business/engineering decision;
any actual proposal generation needs separate authorization. Broader S2 endpoint
semantics need new exact source evidence, not coverage-driven acceptance.
**D3 delivered; STOP.** No synthetic backbone/junction/LV/new Transformer, E3, OpenDSS or QSTS.
