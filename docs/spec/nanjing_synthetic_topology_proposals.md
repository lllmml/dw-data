# E2.3-D2 — Synthetic topology proposals only

Version `synthetic-topology-proposals-v1 / 1.0.0`. User authorizes proposal generation,
validation and counterfactual analysis, not APPROVED/APPLIED, accepted graph mutation,
E3, parameters or OpenDSS. D1 remains a historical contract/artifact; its whole-case
state veto is superseded only in D2. Frozen v1/source resolver semantics are unchanged.
Q-CONN/Q-TRANSFORMER remain OPEN: new engineering ports do not reinterpret source Terminals.

## Blocker refinement

Three independent categories with reason codes and source witnesses:

- HARD_SOURCE_CONTRADICTION: unresolved/nonunique Feeder ownership; published/rejected
  identity conflicts and incompatible explicit voltage projections affecting case model
  interpretation; individual target ambiguity, contradicting endpoints or cross-case
  references. Source identity/voltage inventory conflicts block automatic case proposals
  until resolved; no ID repair or arbitrary representative. Individual target/region
  conflicts reject that candidate, not unrelated state-bearing devices.
- OPERATING_STATE_CONSTRAINT: preserve every raw Switch/Disconnector/EarthingSwitch
  state and endpoint declaration. OPEN is a nonconducting branch in a modeled source
  scenario, still a physical branch. CLOSED earthing with a uniquely resolved region
  rejects attachment at that region; unknown earthing location is UNRESOLVED scenario
  evidence, never whole-case structural veto. Unsupported device connectivity is not
  silently modeled. No inferred closure or override is allowed.
- MODELING_GAP: absent attachment, MV-side evidence, LV voltage, route/region ambiguity,
  role/count policy, absent backbone. Missing is not a contradiction. Empty source data
  can be supplemented only by named engineering assumptions or a bound business input.

Primary priority (mutually exclusive; all reasons retained): hard contradiction;
zero-target unknown role; eligible existing attachment; eligible new
Transformer; candidate hard contradiction when no bundle survives; accepted S0 FULL; C/referenced-incomplete or S2-only usable backbone needing deterministic
review; no accepted physical backbone → SYNTHETIC_BACKBONE_REQUIRED; otherwise
INSUFFICIENT_FOR_AUTOMATIC_PROPOSAL. Known-no-transformer role uses role-specific scope,
never converts NO_SOURCE_TARGET to target FULL. All 5,159 cases are retained.

## D2 engineering assumptions and selection

`CASE_LOCAL_EXISTING_T_LEAF_V1`: a unique case Feeder and unique unreferenced existing
Transformer may be modeled as belonging together within a derived case. This is explicit
ENGINEERING_CASE_OWNERSHIP, not source-confirmed ownership. New synthetic MV attachment
port has the existing head/region voltage when source HV is empty (ASSUMED_MV_SIDE).
No source Terminal number or winding is assigned; all source declarations are retained.
Nonempty incompatible HV/endpoint evidence rejects, not overwritten.

Base is accepted S0 only. Physical reachability uses all existing S0 branches, including
OPEN; conducting view uses their unchanged conducting flags. S2 is comparison/review
context only, never imported to the proposal base. Source devices not projected by S0
remain unresolved even if their states are known.

Eligible attachment regions are existing accepted junction/bus nodes on a physical
head-reachable backbone containing at least one source Line. Exclude feeder-head,
Transformer port, unknown switch port and upstream station Bus. Exactly one compatible
region → ENGINEERING_PLACEMENT. Multiple regions require a business-selected existing
region, otherwise reject; no ID/lexical/hop tie-break, random tree or cross-case nearest.
Head reachability, roles, voltage, graph hops and degree are diagnostics, not proof of GIS.
No numerical electrical/degree cap is invented: degree increase/density are reported as
ENGINEERING_LIMITS_NOT_ASSESSED; engineering adequacy and simulation readiness stay false.

Every unique NO_REFERENCE T receives at most one proposed MV-port node and attachment
edge; source Transformers are never duplicated. Any referenced-but-unmodeled T remains
for deterministic review. A new leaf cannot connect two existing components, bypass an
OPEN cut or shorten paths between existing nodes. No new source Line parameters exist.

LV bus: optional, only when positive explicit source LV or bound business LV policy is
available, compatible with source and lower than MV. Bind it to the same Transformer
bundle and an explicit transformer-transfer relation (not a same-voltage wire).
Missing LV yields a retained rejection/gap, not a guessed default. This is topology only.

New Transformer: only confirmed DISTRIBUTION_WITH_TRANSFORMER,
transformer_required=true, synthetic_transformer_allowed=true, zero source targets,
explicit positive device count and demand_basis, MV/LV policy and unique accepted region.
Each device plan slot has stable derived identity, MV port and LV bus. No default count,
capacity, Load or DER. Without confirmation official output has zero new Transformers.

Junction/backbone/component bridge: types and validation contracts are defined, but no
free-layout rule is enabled in v1. A synthetic junction needs a versioned region/route
plan, backbone needs explicit engineered route and permission. `synthetic_backbone_allowed`
alone does not define a route. Return BACKBONE_LAYOUT_RULE_REQUIRED / JUNCTION_LAYOUT_RULE_REQUIRED;
no random or convenient component bridging. This narrow rule deliberately leaves broad
layout cohorts unresolved rather than imposing unsupported topology.

## Business confirmation input

`nanjing_completion_decisions_v1` schema in `docs/spec/nanjing_completion_decisions_v1.schema.json`.
Official config: `configs/nanjing_completion_decisions_v1.json`, initially empty decisions.
It is derived-model policy provenance, not a source fact or proof of actual network role.

Root fields: schema_version (exact ID), decision_version (nonempty), input_manifest_sha256
(source and D1 hashes), decisions (unique case_id/feeder_id pairs). Each decision:
case_id, feeder_id, decision_version, role (UNKNOWN/DISTRIBUTION_WITH_TRANSFORMER/
NO_TRANSFORMER_REQUIRED), transformer_required (bool/null), synthetic_transformer_allowed
and synthetic_backbone_allowed (bool), nominal_voltage_kv/lv_voltage_kv (positive finite
Decimal strings or null; kV), transformer_count (positive int/null), demand_basis,
attachment_node_id, confirmation_ref, comment (strings/null).
Unknown entries cannot grant permissions or supply engineering values. Any confirmation
requires nonempty confirmation_ref; distribution role requires transformer_required=true;
no-transformer role requires false and forbids new T/count. New T permission requires
role, positive count/demand and LV/MV values. Entries must match known case/Feeder pair;
unknown/duplicate keys, floats/bools-as-count, duplicate JSON keys and stale bindings fail.
Serialize canonically with decisions ordered by case/Feeder; no timestamps/implicit seed.
Template includes all actual feeder IDs but UNKNOWN/null/false values, never fabricated
confirmations. Parser validates semantic constraints beyond the JSON shape schema.

## Bundle model and validation

Independent `proposal:` namespace SHA256 of canonical [version, case, feeder, kind,
semantic key/endpoints, business-input hash]. No Python hash(), iteration or ID-distance
selection. Every object: owning case/Feeder, kind, evidence_class=RULE_GENERATED,
source refs (empty only for new device, then business refs required), rule/version,
config/input binding, assumptions, proposal ID, semantic endpoints/port role and voltage.
Source-related refs refer to existing entities, never generated source IDs.

Lifecycle per bundle: OBSERVED → ELIGIBLE → PROPOSED; structural validator can record
VALIDATED only within declared scope when no unresolved assumptions remain. Each step
has reason and evidence refs. With engineering/scenario gaps, stage remains PROPOSED,
structural checks can PASS while electrical_sanity=ASSUMPTION/UNRESOLVED. No APPROVED or
APPLIED enum is accepted by D2 artifact verifier. Graph impact is not semantic validation.

Validator rechecks unique generated IDs/semantic edges/devices, no existing source T
duplication, all endpoints existing in same base/bundle, node/Feeder/case ownership,
finite voltages, direct-edge voltage compatibility, MV→LV only through Transformer,
self loops/parallel duplicates, no changed source edges or state declarations, and
candidate-local closed-earthing/OPEN-bypass constraints. Any rejection retains reason
and witness; invalid objects are excluded from the counterfactual accepted-proposal set.
Independently recompute physical AND conducting m-n+c, components, reachable Lines and
Transformers, degree, new cycles, disconnected synthetic nodes and target coverage.
Report original-source target coverage separately from model target inventory when new
Transformers are proposed; empty source targets remain NO_SOURCE_TARGET in that axis.

## Artifact and acceptance

New directory `outputs/nanjing-e2-3/synthetic-topology-proposals-v1/` only. Required:
case_inputs.jsonl (immutable analysis view), feeder_eligibility.jsonl,
blocker_reclassification.jsonl, business_confirmation_template.json,
business_confirmation_snapshot.json, proposal_bundles.jsonl, proposal_edges.jsonl,
proposal_devices.jsonl, proposal_validation.jsonl, rejected_candidates.jsonl,
case_coverage.jsonl, coverage_impact.json, summary.json, report.md, manifest.json.

Nine proposal/report streams are derived from case inputs + decision snapshot; no
accepted graph file. All claims bear PROPOSAL_ONLY_COUNTERFACTUAL. Manifest binds six
artifacts (E1/E2/E2.2 projection/feeder/E2.3-A/D1), policy hash, code/rule/schema version,
file SHA256/count; no timestamp-dependent bytes. Verifier checks inventory/canonical
bytes, reconstructs bundles, revalidates objects and recomputes all detail/coverage.
Input-bound mode independently reconstructs case inputs from verified authoritative
artifacts; rehashed fabricated facts fail. Before/after input verifiers and immutable
raw/accepted/frozen/D1 hashes required. Independent hash-seed reproduction, full tests,
compile/static and commit, then STOP. No E3 or apply capability.
