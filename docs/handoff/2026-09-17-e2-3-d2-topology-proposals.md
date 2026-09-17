# E2.3-D2 — Synthetic Topology Proposal Only

D2 delivers a proposal engine, bound business decisions, structural/electrical-scope
validation and independently rebuilt physical/conducting counterfactual artifacts.
**11 Feeders, 177 existing Transformer attachment bundles, all PROPOSED.**
Accepted S0 remains **0 target FULL**. No accepted/frozen graph, source fact or source
state is changed; S2 remains unaccepted. APPROVED/APPLIED = 0; E3/OpenDSS/QSTS unstarted.

## Baseline and files

The requested starting HEAD was `5db5c10c93f1d5d78f2a613daf0e69b143e94ee4`, with a clean
worktree before D2 work. The interrupted implementation was resumed without discarding it.
Delivery commit: `git log -1 --format=%H -- docs/handoff/2026-09-17-e2-3-d2-topology-proposals.md`.
No new dependency; runtime remains stdlib, existing uv.lock unchanged.

- Contract: [D2 spec](../spec/nanjing_synthetic_topology_proposals.md),
  [business JSON schema](../spec/nanjing_completion_decisions_v1.schema.json).
- Official unconfirmed policy: `configs/nanjing_completion_decisions_v1.json`.
- Models/parser: `src/grid_case_generator/models/proposals.py`.
- Analysis: `analysis/proposal_inputs.py`, `analysis/topology_proposals.py`,
  `analysis/proposal_summary.py`, `analysis/proposal_cli.py` under `src/grid_case_generator/`.
- IO/verifier: `src/grid_case_generator/io/proposal_artifacts.py`.
- Graph/structural validator: `src/grid_case_generator/validation/topology_proposals.py`.
- Tests: `tests/models/test_completion_decisions.py`, `tests/analysis/test_topology_proposals.py`,
  `tests/analysis/test_proposal_artifacts.py`, `tests/generation/test_proposal_inputs.py`,
  `tests/generation/test_proposal_pipeline.py`.
- Documentation: this handoff, [run guide](../guides/nanjing_synthetic_topology_proposals.md),
  README, AGENTS, gated slices and an explicit D2 superseding note in the historical D1 spec.

Formal output: `outputs/nanjing-e2-3/synthetic-topology-proposals-v1/`.
Independent run: `outputs/nanjing-e2-3/synthetic-topology-proposals-v1-reproduction/`.
Verification: `outputs/nanjing-e2-3/synthetic-topology-proposals-v1-verification.json`.
Protected SHA256 inventory: `outputs/nanjing-e2-3/synthetic-topology-proposals-v1-input-sha256.json`.
All generated artifacts remain ignored local outputs, not Git contents.

## Blocker reclassification

| Mutually exclusive primary | Feeders |
|---|---:|
| DETERMINISTIC_RECOVERY | 1,383 |
| SYNTHETIC_ATTACHMENT_ELIGIBLE | 11 |
| SYNTHETIC_DEVICE_ELIGIBLE | 0 |
| SYNTHETIC_BACKBONE_REQUIRED | 1,402 |
| ROLE_CONFIRMATION_REQUIRED | 1,432 |
| HARD_SOURCE_CONTRADICTION | 906 |
| INSUFFICIENT_FOR_AUTOMATIC_PROPOSAL | 0 |
| ALREADY_COMPLETE | 0 |
| **Total** | **5,134** |

All 5,159 cases remain represented, including 25 without a Feeder. Hard contradictions
are witnessed identity ambiguity (607 Feeders) and explicit voltage incompatibility
(325), with overlap: their union is 906. Case ownership, cross-case and candidate target
voltage/identity checks remain enabled. No identity repair or arbitrary entity selection.

D1's 4,614 blocked Feeders split into 906 hard contradiction, 1,331 deterministic review,
1,084 role confirmation, 1,282 backbone required and 11 attachment eligible. This is a
semantic reclassification, not correction of raw records or deletion of operating constraints.
The other D1 cohorts retain 52 deterministic, 348 role and 120 backbone cases.

Operating constraints remain separate: source OPEN Switch in 4,496 Feeders; CLOSED
EarthingSwitch in 2,381. Presence alone is not a whole-case veto. All 11 eligible Feeders
were D1-blocked; 10 of them have source OPEN switching devices. Exact mapped closed-ground
attachment locations are locally rejected; unresolved locations remain scenario assumptions.
No cut is bypassed and no existing switch is closed by a proposal.

Only 17 Feeders have the required accepted S0 physical backbone: 11 become eligible,
3 retain witnessed identity conflicts, and 3 have referenced targets requiring deterministic
review instead of a missing-attachment rule. All 17 have one candidate region. Thus the low
proposal count follows accepted-base availability and target evidence, not D1's state veto.
The 87,293 missing-backbone target candidates cannot use S2 as an accepted base.

## Proposals and coverage

| Proposed object | Count |
|---|---:|
| Existing Transformer attachment edge | 177 |
| Derived MV attachment port | 177 |
| Junction / LV bus / new Transformer / backbone / transfer | 0 each |

177 bundles attempted and structurally retained; 0 validator-rejected bundles.
92,816 rejected candidate/gap records also remain, including 177 optional LV gaps.
This count includes unconstructible candidates; it is not the number of generated bundles
failing validation. Reasons overlap: 87,293 missing-region / missing-accepted-backbone
candidate records, 2,782 backbone-rule gaps, 1,432 role gaps, 226 deterministic-reference
reviews, plus hard conflict records. No assumed LV voltage or source Transformer duplicate.

Eligibility uses the unique physically reachable accepted S0 junction region and a source
Line backbone. Case-local ownership, missing source MV side and placement are explicitly
engineering assumptions (`RULE_GENERATED`). S2 regions are not imported. Engineering degree,
capacity and scenario adequacy remain unassessed; structural PASS does not certify a
simulation-ready case. Every retained bundle stays PROPOSED, electrical sanity ASSUMPTION.

**PROPOSAL_ONLY_COUNTERFACTUAL**, original source-target coverage:

| Status | Physical before | Physical after | Conducting before | Conducting after |
|---|---:|---:|---:|---:|
| FULL | 0 | 2 | 0 | 2 |
| PARTIAL | 4 | 10 | 4 | 10 |
| FAILED | 3,417 | 3,409 | 3,417 | 3,409 |
| NO_SOURCE_TARGET | 1,713 | 1,713 | 1,713 | 1,713 |

11 Feeders gain reachable Transformers; 5,123 unchanged in target reachability.
FAILED→FULL 2; FAILED→PARTIAL 6; PARTIAL→FULL 0; another 3 improve within PARTIAL.
Reachable existing Transformers: 5→182 in both views. New cycles 0; disconnected synthetic
nodes 0. Graph components, degree, lines and per-case deltas are in `case_coverage.jsonl`.

Identical aggregate physical/conducting numbers reflect this accepted S0 base and selected
leaf proposals; they do not mean all raw OPEN devices conduct. Unprojected operating devices
remain unresolved. Dedicated OPEN-branch tests establish different physical/conducting
reachability when such a branch is present in the modeled base.

All 1,713 zero-Transformer Feeders remain UNKNOWN, including 281 with hard-primary status.
The business template includes all 5,134 actual Feeder identities with UNKNOWN/null/false.
The official bound input grants no device permission. Confirmed fixture tests demonstrate
new Transformer plans only with role, permission, count, demand basis and MV/LV declarations.

## Verification and next gate

Full suite: **409 passed** (381 baseline + 28 new). Compileall src/tests and Git whitespace
checks pass. Tests cover OPEN physical/conducting separation, local grounding, real hard
conflicts, missing evidence eligibility, no duplicate source Transformer, confirmed-only
new devices, isolation, cross-case/dangling/self-loop rejection, stable IDs/order/hash seeds,
rehashed detail/summary/input-schema tampering, six bound inputs and raw ZIP immutability.

Full all-data runs with PYTHONHASHSEED 1 and 999: PASS; all **15 files byte-identical**,
including manifest and report. Input-bound verifier: PASS; all six authoritative input
bindings, reconstructed input facts/proposal details, summary and physical/conducting
graph recomputation agree. Protected raw/source/accepted/frozen/D1 inventory: **263,811
files, all SHA256 unchanged**. Frozen topology-v1 verifier: PASS. Input verifiers before
and after each full run also pass.

Formal manifest SHA256:
`fba84c2cd3982b1724317990369366a17ccf8b14dbfe5a2848a7b3b6c16cbdd7`.
Source-tree fingerprint:
`bd9f453cc67461b3627541e1ec13ce1582e5a4e56c9431d75a40de10ba6afd7a`.
Verification JSON records the six input hashes, business-input hash, reproduction file
hashes and the independently stored protected-file inventory digest.

Remaining primary cohorts: 1,383 deterministic recovery review (including S2-only backbones),
1,402 missing accepted backbone/layout, 1,432 business role confirmation and 906 hard
contradictions. These overlap with 1,713 total unresolved zero-target roles. Junction/backbone
layout has no enabled free-layout generator; a permission flag alone cannot invent routes.

Next minimum slice: review the 11 concrete Feeder proposal bundles, engineering limits and
scenario assumptions, and collect a small bound business decision cohort. This recommendation
does not approve/apply any proposal or authorize E3. **D2 delivered; STOP for review.**
