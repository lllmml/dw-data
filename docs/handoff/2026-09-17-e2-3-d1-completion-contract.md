# E2.3-D1 — Synthetic Completion Contract & Cohort Refinement

D1 completed: formal contract, typed facts/enums, prohibition/eligibility evaluator,
read-only profiles/action cohorts, isolated versioned artifact, CLI and verifier.
Synthetic topology implementation has **not** started. Generated connections/nodes/devices
= **0**. Accepted topology, frozen v1, raw/source facts and E2.3-A artifacts unchanged.
S2 is not accepted. E3/OpenDSS/Load/PV/8760 are not authorized.

## Baseline and delivered scope

Input HEAD: `a066e2761e86f71adbf178ebe6f10ff9350cdb01`.
Before D1, `docs/analysis/` and `docs/reviews/` were untracked from the accepted D review;
no tracked files were modified. This was reported before implementation. They are
preserved and included in this independent D1 commit, with review status updated.
Delivery SHA: obtain with `git log -1 --format=%H -- docs/handoff/2026-09-17-e2-3-d1-completion-contract.md`.
No new dependency; existing stdlib runtime and uv.lock remain unchanged.

- [Formal spec](../spec/nanjing_synthetic_topology_completion.md)
- [Run / verification guide](../guides/nanjing_synthetic_completion_contract.md)
- [Accepted design rationale](../reviews/2026-09-16-e2-3-d-synthetic-topology-design.md)
- Formal artifact: `outputs/nanjing-e2-3/synthetic-completion-contract-v1/`
- Independent repeat: `outputs/nanjing-e2-3/synthetic-completion-contract-v1-reproduction/`
- Verification evidence: `outputs/nanjing-e2-3/synthetic-completion-contract-v1-verification.json`

The `*-initial-audit` directory is a development analysis, not the formal delivery.
D1 independently recomputes from five verified inputs; it does not copy D review's
prototype JSON. Large artifacts stay in ignored outputs, not in the commit.

## Primary action cohorts

| Primary action | Feeder count |
|---|---:|
| AUTO_SYNTHETIC_ELIGIBLE | 0 |
| DETERMINISTIC_RULE_REVIEW | 52 |
| ROLE_CONFIRMATION_REQUIRED | 348 |
| BLOCKED_BY_SOURCE_CONFLICT | 4,614 |
| INSUFFICIENT_STRUCTURE | 120 |
| ALREADY_TARGET_COMPLETE | 0 |
| **Total** | **5,134** |

All 5,159 cases retained, including 25 with no Feeder. Original overlapping flags remain
A=3,114 / B=1,713 / C=227 / D=1,884. Primary action is a fixed priority, not an assertion
that all secondary issues disappear. Every operation has its own complete reason list.

Why blocked increased: source D alone covers 1,884; D ∪ any source OPEN Switch/Disconnector
covers 4,557. Conservative whole-case rejection of closed EarthingSwitch declarations
adds 57 more, giving 4,614. The 2,730 newly blocked non-D cases are **not newly declared
source errors**. OPEN is an operating constraint; closed earthing declarations are a
conservative veto even when Bus/location is unproved, not proof of actual grounding.
No source state is changed, and no bypass is claimed to have been attempted.

Known OPEN presence affects 4,496 Feeders; closed earthing declarations affect 2,381
(overlap allowed). Identity 607 and voltage 325 are separately retained. Missing owner,
MV side, voltage and approved placement/count policy are independent unmet gates, not
silently accepted compatibility. The union of all prohibition codes must not be read
as a count of contradictory source records.

## Existing Transformer (A)

All 3,114 A have a valid modeled head, but only 1,819 have source Line rows. Accepted S0
has usable backbone in 14 A; S2 has one in 1,348. S0 has 14 unique reachable junction
regions and no multi-region A; S2 has 160 unique and 817 multiple unranked region cases.
96,038 unreferenced existing Transformer groups remain; no duplicate Transformer is allowed.

Primary A split: blocked 2,945; deterministic review 49; insufficient structure 120;
automatic attachment eligibility 0. The 120 are the remaining unblocked structurally
insufficient cases, not the total number of A with structural gaps. Components, cycles,
self-loops, parallel edges, degree, hops, reachable targets, region inventory, voltage and
source state/field evidence are persisted separately for every case and both graph views.

**Existing Transformer attachment proposal eligibility: 0 Feeders.** Source does not
confirm equipment ownership/MV side; no approved numeric placement/cap policy is invented.
Even without these semantic gaps, any S2-only backbone must first pass its own review.

## Zero Transformer (B)

| Source-evidence role assessment | B Feeders |
|---|---:|
| NO_TRANSFORMER_REQUIRED_CANDIDATE | 0 |
| SYNTHETIC_TRANSFORMER_ROLE_CANDIDATE | 0 |
| ROLE_UNDETERMINED | 1,713 |

Of all B, primary blocked=1,365 and primary role-confirmation=348. **All 1,713 still need
business role confirmation**, regardless of primary class. Synthetic Transformer proposal
eligibility=0. Source AP presence does not establish demand or a device count.

B has Line in 1,128 cases / no Line in 585; accepted usable=0, S2 usable=886. AP occurs
in 1,535 B cases; Load/DER rows=0. Profiles and summary include Switch/state inventory,
Station types, head voltage, SimConfig, component/region distributions and source-row
histograms, alongside the 3,421 cases with Transformer. Generic SimConfig is identical
across the two populations, and AP fields beyond ID are empty. Names are persisted only
as weak evidence, never a business-role classifier. Need client role/demand/owner/count
confirmation; do not invent one Transformer per feeder or turn zero targets into FULL.

## Historical counterfactual and new eligibility

Accepted S0 remains 0 target FULL; unaccepted S2 remains 80 target FULL.
13 Feeders / 113 hypothetical connections / prior conditional target FULL upper bound 93
remain explicitly historical evidence. The 13 split under D1 into deterministic review
11 and source-constraint blocked 2. None becomes eligible; no new FULL is promised.
S2 FULL is never ALREADY_TARGET_COMPLETE. Target FULL is not topology complete or E3-ready.
All six operation eligible counts are zero on current inputs, including LV bus, which
still needs later approved LV/completion semantics.

## Gates and outstanding work

| DoD question | Answer |
|---|---|
| Automatic synthetic candidates? | None on current evidence; future A needs accepted region/backbone, owner/MV/voltage, approved placement and all prohibition checks |
| Deterministic recovery priority? | 52 primary; original C=227 retained with constraints; deterministic review does not promise success |
| Business roles? | B all 1,713 unresolved; primary role cohort 348 because explicit constraints take priority |
| Explicit automatic prohibition? | 4,614 primary under frozen whole-case conservative policy; all operation-specific missing gates also retained |
| Existing T attachment proposal? | 0; preserve 96,038 unreferenced existing targets |
| Future new T? | No current B eligible; require distribution role, demand, zero inventory, MV/LV, owner, count/capacity-source policy and separate high-risk authorization |
| Principally allowed operations? | Conditional A attachment, engineering junction and located T LV bus; new T/backbone separately high risk; component bridge disabled |
| Non-overridable prohibitions? | Identity, ownership/cross-case, voltage, OPEN bypass, unknown side, duplication, explicit negative evidence, unsafe bridge; no force override |
| Candidate to accepted result? | Observe → eligible → propose → validate hashes/risk → approve business/rule/profile → separately authorized apply/verify immutable overlay; D1 stops before applying |
| What remains for engineering cases? | Owner/role/MV-side evidence, approved region/cap/count policy, S2/B/C reviews, some backbone designs; then separately authorized parameters/completion/simulation validation |

Recommended next minimal slice: a versioned business-confirmation input for the smallest
A/role cohort and eligibility re-evaluation; only after prerequisites and separate approval
should D2 produce candidate proposals. Do not start a generator that merely masks missing
positive evidence or tries to preserve 93.

## Validation and reproducibility

- Full pytest: **381 passed** (348 existing + 33 new).
- Compileall for src/tests and staged git diff whitespace/static check: PASS.
- All five input verifiers and manifest bindings before/after both analyses: PASS.
- Frozen topology-v1 verifier: PASS.
- Output checksum/canonical/schema verifier independently regenerates each decision stream
  from typed profile facts and reaggregates summary/report: PASS.
- Input-bound output verification rebuilds profiles from authoritative source/baseline/
  recovery streams and checks graph bindings against E2.2: PASS.
- Full independent runs with PYTHONHASHSEED=1 / 999: all nine artifact files byte-identical,
  including manifest/report. Source record reversal and hash-seed tests also pass.
- Original protected files: **263,774**, all SHA256 unchanged (raw + pre-existing outputs).
- Tests cover mutually exclusive primary actions, overlap preservation, zero-target role,
  duplicate T permission, identity/ownership/voltage/OPEN/cross-case, stage no-apply,
  no evidence promotion, input/output isolation, immutable inputs, multigraph risks,
  reordered records, checksum/rehashed decision/profile tamper, extra topology payload
  rejection and authoritative input binding.

Formal manifest SHA256:
`64b87920d7320a6593a39a96d1f32461bce665462b147693e3a8d61494dc8b0e`.
Source-tree fingerprint:
`75eb0470e65547306a1af07a4096b6e861b3e6ffc6b584e50b2de544dc2c686d`.
Five input manifest hashes are recorded in manifest and the verification evidence file.

D1 delivered, STOP for review. D2 and synthetic topology implementation remain unstarted;
E3 and OpenDSS remain unauthorized.
