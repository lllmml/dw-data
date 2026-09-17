# E2.3-D1 Synthetic Topology Completion Contract

Version `synthetic-completion-contract-v1 / 1.0.0`. D review accepted; D1 implements
contract/read-only eligibility analysis only. No synthetic node, device, edge, accepted
graph writer, S2 acceptance, E3 or OpenDSS. Rationale: [D review](../reviews/2026-09-16-e2-3-d-synthetic-topology-design.md).

## Evidence and stages

Reuse EvidenceClass: SOURCE_CONFIRMED requires genuine source evidence AND approved
semantics; RULE_INFERRED requires an approved deterministic proof; RULE_GENERATED
(SYNTHETIC) describes engineering-created nodes/connections/devices/attachments, never
recovered real topology. UNRESOLVED covers unproved/unapproved semantics. Reachability
never promotes a class. All D1 eligibility decisions remain UNRESOLVED, not generated
objects. Existing S0/S2 evidence classes and inherited synthetic heads are preserved.

CandidateStage: OBSERVED → ELIGIBLE → PROPOSED → VALIDATED → APPROVED → APPLIED.
Each transition requires a nonempty reason and evidence/provenance refs; no skip or
reverse transition. D1's executable transition validator permits only the first two
transitions; later transitions fail closed. D1 emits OBSERVED or ELIGIBLE assessments,
never topology proposals with chosen endpoints, never VALIDATED/APPROVED/APPLIED.
Future validation binds proposal/base/config hashes; approval requires the applicable
rule/profile/business semantics review; apply requires separate authorization and
immutable overlay output, followed by independent verifier. No stage implies E3-ready.

## Primary action cohort (ordered, mutually exclusive)

Preserve A/B/C/D exactly from E2.3-A, and independently record accepted S0 and
counterfactual S2 target coverage. One primary action per source Feeder identity group:

1. BLOCKED_BY_SOURCE_CONFLICT: existing D flag OR explicit identity/voltage/ownership
   conflict OR source OPEN Switch/Disconnector OR explicit closed earthing switch.
   OPEN is an operating constraint, not an assertion that source facts are erroneous.
   This whole-case conservative exclusion does not assert an actual bypass was attempted.
2. ROLE_CONFIRMATION_REQUIRED: B / zero or undetermined source target inventory.
3. ALREADY_TARGET_COMPLETE: nonempty targets FULL in accepted S0, not S2; still not
   case topology complete, E3 or simulation ready.
4. DETERMINISTIC_RULE_REVIEW: C or S2 target FULL, or no accepted usable backbone
   while S2 has one. Unapproved S2 cannot be used to grant synthetic eligibility.
5. INSUFFICIENT_STRUCTURE: missing valid head, no source Line, or no S0/S2 usable
   backbone; also no accepted junction region for otherwise usable A.
6. AUTO_SYNTHETIC_ELIGIBLE: A with an allowed attachment operation, all gates passed.
7. ROLE_CONFIRMATION_REQUIRED: remaining A requires engineering owner/MV/voltage/
   region/cap confirmation. Other referenced cases require deterministic rule review.

This is an action priority, not a mutually exclusive diagnosis. All prohibition and
missing-prerequisite reasons remain; especially blocked B retains role-undetermined.
Source-file-undetermined never becomes confirmed zero-row. A case-unique Feeder is
accounting scope only, not equipment ownership. No implicit approval is inferred from
D review, names, directory membership, empty source fields or generic SimConfig.

## Readiness

CompletionReadiness: NOT_ELIGIBLE, RULE_REVIEW_REQUIRED, SYNTHETIC_ELIGIBLE,
ROLE_CONFIRMATION_REQUIRED, BLOCKED, READY_FOR_SYNTHETIC_PROPOSAL.
AUTO_SYNTHETIC_ELIGIBLE assessments emit SYNTHETIC_ELIGIBLE; proposal readiness also
requires a separately approved concrete selection policy/config. D1 does not emit
READY_FOR_SYNTHETIC_PROPOSAL automatically. Other primary classes map respectively to
BLOCKED, ROLE_CONFIRMATION_REQUIRED, NOT_ELIGIBLE, RULE_REVIEW_REQUIRED.
Target FULL, topology completion, synthetic eligibility, E3 and adapter readiness are
independent. D1 e3_ready and opendss_ready always false.

## Operation contract

All generated objects in future have RULE_GENERATED evidence; D1 emits no such object.
All operations require case-local owner evidence, compatible positive finite voltage
in kV, all negative evidence assessed, versioned approved policy/config, full provenance.
Unknown is not compatible. Known OPEN/UNKNOWN cannot be silently closed or bypassed.

| Operation | Allowed cohort and positive evidence | Additional exclusions / risk gates |
|---|---|---|
| SYNTHETIC_ATTACHMENT_EDGE | A: unique existing unreferenced T, accepted head/Line backbone and exactly one compatible approved MV junction region, confirmed owner/MV side, approved placement/cap | Existing declaration/attachment cannot be replaced; no winding merge, duplicate, parallel/self edge, shortcut or component bridge; batch degree/density cap |
| SYNTHETIC_JUNCTION | A under separately approved ENGINEERING_LAYOUT; declared region, model need and owner/voltage | No automatic co-location inference or merging components; high-risk policy absent in D1 |
| SYNTHETIC_LV_BUS | Existing located T with accepted reachable MV side, confirmed LV side/voltage and approved one-to-one LV policy | No duplicate LV bus; does not solve MV reachability; later authorized completion slice only |
| SYNTHETIC_TRANSFORMER | B with confirmed distribution supply role, demand evidence, zero existing T, MV voltage, LV voltage policy, device-count determination, capacity-source policy, owner, explicit high-risk authorization | Never in A; no default device count; AP ID alone insufficient; no source contradiction |
| SYNTHETIC_BACKBONE_EDGE | No D1 enabled cohort; future separate engineered route/port/owner/voltage/state design | Explicit high-risk approval; cannot use disconnectedness as positive evidence |
| SYNTHETIC_COMPONENT_BRIDGE | No D1 enabled cohort | UNSAFE_COMPONENT_BRIDGE, requires future separate contract; not a profile override |

No operation is enabled just by defining its enum. Current source schema and reviewed
inputs do not certify the missing owner/MV side/placement/count approvals. Production
D1 reader records these gates false with explicit reasons, never guesses permission.
Typed evaluator supports independently evidenced gate facts for tests/future adapters;
this slice has no CLI switch that supplies approvals or forces completion.

## Machine prohibitions (pre-generation evaluation)

AMBIGUOUS_IDENTITY, OWNERSHIP_UNRESOLVED, CROSS_CASE_CONNECTION,
INCOMPATIBLE_VOLTAGE, KNOWN_OPEN_BYPASS, UNKNOWN_TRANSFORMER_SIDE,
DUPLICATE_GENERATION, EXISTING_NEGATIVE_SOURCE_EVIDENCE, UNSAFE_COMPONENT_BRIDGE.
Additional closed codes: KNOWN_OPEN_PRESENT, STATE_UNDETERMINED,
VOLTAGE_UNDETERMINED, POLICY_APPROVAL_REQUIRED, HIGH_RISK_AUTHORIZATION_REQUIRED,
NO_ACCEPTED_BACKBONE, ATTACHMENT_REGION_UNDETERMINED, ROLE_UNDETERMINED,
DEMAND_EVIDENCE_MISSING, DEVICE_COUNT_POLICY_REQUIRED, NO_UNREFERENCED_TARGET,
NO_LOCATED_TRANSFORMER, EXISTING_REFERENCE_REQUIRES_REVIEW.

Codes distinguish explicit contradiction/operating constraint from missing evidence.
KNOWN_OPEN_BYPASS describes a requested forbidden operation; merely observing an OPEN
uses KNOWN_OPEN_PRESENT (or a source frontier witness), not a fabricated bypass claim.
EarthingSwitch OPEN is not treated as an open series switch; CLOSED is a conservative
whole-case veto, not proof of actual grounding connectivity when its Bus is missing. Raw state value and source locator are retained. Unknown switching state is a
missing precondition. Duplicate Transformer permission is forbidden when count > 0.
Every operation runs the prohibition evaluator before any future generator. No force,
ignore-conflicts, name inference or evidence-class override configuration exists.

## Selection and risk boundary

Allowed features: approved graph role, head reachability, voltage, hop position (hops,
not km), multigraph incident degree, region/branch structure, previously placed assets
in an approved immutable input, approved deterministic rule configuration and strong
source hints. Forbidden: numeric/lexical ID proximity, sorted-first, random nearest,
cross-case nearest or convenience connection to increase coverage. Strong evidence may
justify INFERRED_LOCATION only after rule approval; engineering placement always bears
ENGINEERING_PLACEMENT. Multiple unranked regions are SELECTION_UNDETERMINED. No selection
is executed in D1. Seed is not accepted by this contract.

Future risk checks: connectivity and scope, voltage/port/owner, source OPEN isolation,
structural/conducting components and cycle rank m-n+c (including isolates and parallel
edges), self-loops, parallel branches, degree/density, duplicates and shortcuts. New leaf
attachments may not alter distances/connectivity between existing nodes. Do not delete
source edges for radiality; operating-state radiality belongs to a separate scenario.
No engineering degree/count cap is invented in D1; unapproved policy remains a blocker.

## Models, identity, provenance and nullability

CompletionFacts is an immutable typed contract: case_id and feeder_id nonempty strings;
A/B/C/D tuple preserves original flags; counts are nonnegative integers in devices,
source rows or regions as named; graph/full/head flags and confirmation flags are bool.
Prohibition enums distinguish explicit conflicts from missing confirmations. No source
identifier is repaired. Feeder ownership remains case-scoped evidence until confirmed.

Assessment records use independent `completion-evidence:` SHA256 IDs over canonical
[contract version, stream kind, case_id, feeder_id, semantic key]. Sorting affects only
serialization. Every assessment has case/Feeder refs, supporting source locators,
E2.3-A evidence refs, conflict refs, rule_id/version, decision reason, input binding,
evidence_class=UNRESOLVED, stage and generated_object_count=0. Empty evidence arrays mean
no such evidence, not assumed compatibility. Nominal voltage may be null (unknown),
otherwise canonical positive finite Decimal string in kV; hop/degree integer counts.

Future synthetic-object provenance additionally requires object ID/kind, owner case and
Feeder, related source refs, supporting/conflict evidence, rule/version/config hash,
policy profile, decision reason, deterministic inputs, software/artifact version, seed
only for explicitly approved future random rules. No fake source_record_ref/source_id.
IDs use a separate generated namespace, not this assessment namespace or source factory.

## Formal D1 artifact

Independent new directory `outputs/nanjing-e2-3/synthetic-completion-contract-v1/`.
Required files: summary.json, case_profiles.jsonl, feeder_completion_cohorts.jsonl,
synthetic_eligibility.jsonl, prohibitions.jsonl, role_evidence.jsonl,
operation_eligibility.jsonl, report.md, manifest.json. No topology file is permitted.

Case profile includes all 5,159 cases, raw source counts/field availability/station/
SimConfig/state observations, S0/S2 graph diagnostics, source/evidence refs and typed
facts for each source feeder. No-Feeder cases remain profiles, not invented Feeder rows.
Graph diagnostics derive solely from persisted baseline nodes and S0/S2 connection
evidence; retain separate structural/conducting components, degree, cycles, reachable
Line/Transformer counts, candidate junction IDs/hops and head voltage. Region candidates
are existing accepted junction/bus nodes reachable on the named graph, not chosen points.
S0 reachability must equal persisted topology; S0/S2 target/Line counts must equal E2.3-A.
The copied historical 13/113/93 numbers are explicitly counterfactual, never eligibility.

One feeder/cohort/eligibility/role/prohibition record per Feeder, six operation rows per
Feeder (including rejected). Prohibition row groups codes by operation; every missing
confirmation and original A/B/C/D flag survives. B role candidate enums are
NO_TRANSFORMER_REQUIRED_CANDIDATE / SYNTHETIC_TRANSFORMER_ROLE_CANDIDATE /
ROLE_UNDETERMINED; the current reader never uses weak names/AP IDs to assign the first two.

Manifest binds all five input manifests, source-tree fingerprint, schema/rule versions,
file inventory/hash/count and analysis-only flags. No absolute paths/timestamps/random
seed. Canonical UTF-8 JSON, stable case/Feeder/operation ordering. Input verifiers run
before and after analysis; output isolation and existing-output checks fail closed.
Verifier checks canonical bytes/inventory/hash/count, recomputes every derived decision
from persisted typed facts, cross-checks each stream with profiles and reaggregates all
counts/report. With input roots supplied, also validates five manifests/bindings and
recomputes profiles from authoritative input streams, preventing rehashed invented facts.

## Acceptance and stop

Tests precede implementation: primary exclusivity/overlap, role handling, no duplicate T,
voltage/OPEN/ownership/identity/cross-case, stage limits/no evidence promotion, source
ordering/hash-seed determinism, checksum and semantic tamper, output isolation and input
immutability. Full data reproduction must be byte identical. All primary counts sum to
5,134; B role cohorts sum to 1,713, regardless of primary conflict precedence.
Full tests, compile/static, all input/output verifiers, immutable accepted/frozen/raw,
independent commit and handoff. D1 completion does not authorize D2, E3 or OpenDSS.

## D2 superseding scope

The separately authorized [D2 proposal-only contract](nanjing_synthetic_topology_proposals.md)
reclassifies D1 whole-case operating-state vetoes and permits explicit engineering
assumptions for derived proposals. This D1 specification and its artifacts retain their
historical interpretation. D2 does not accept S2, apply proposals or authorize E3.
