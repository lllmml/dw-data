# E2.3-A — Topology Recovery Evidence & Readiness Foundation

Version `topology-recovery-evidence-v1 / 1.0.0`. Analysis only. User review authorizes
this evidence foundation, not new electrical rules, S2 acceptance, synthetic topology,
E2.3-B/C, E3, or OpenDSS. Frozen topology v1 and source facts retain their meanings.

## Evidence classes and provenance

- SOURCE_CONFIRMED: exact unique source evidence AND approved equipment connectivity
  semantics. EXACT resolver status alone never grants this class. No new source-confirmed
  rule is introduced here.
- RULE_INFERRED: approved deterministic versioned electrical rule, with source case,
  entity/terminal refs, supporting and conflict locators, derived IDs and decision reason.
- RULE_GENERATED: SYNTHETIC alias; source cannot prove a generated connection/device.
  This slice defines the boundary only; newly generated connections always number zero.
- UNRESOLVED: insufficient/conflicting evidence or an unapproved interpretation.
  S2-only connections and all recovery candidates remain UNRESOLVED, even if reachable.

Connection evidence is reported for S0 and S2 separately. Preserved S0 branches are
RULE_INFERRED. S2 additions are unapproved counterfactual assumptions, not accepted rules.
Existing synthetic MV head *nodes* are separately counted as modeling assumptions, not
new synthetic connections. This accounting does not change their original provenance.

Provenance fields: evidence_id (analysis-only SHA256 ID), case_id/source_case_ref,
source_entity_ref (nullable for unpublished identities), source_terminal_refs,
supporting_source_refs, conflict_refs, rule_id/version, derived_ids, decision_reason,
evidence_class, approved. Null source refs never mean fabricated Canonical identities.
IDs hash canonical [version, kind, case_id, semantic key]; sort order never selects a
physical connection. Counts are integers in devices/identity groups/feeders/boundaries,
not raw-row counts unless explicitly named. No random generation or seed configuration.

## Source evidence cohorts and Transformer audit

Scope is case-local source identity groups, including rejected/duplicate identities.
A single unique source Feeder permits case-scoped accounting, not proven asset ownership.
No-Feeder cases remain in case details. Multiple/nonunique Feeder cases carry unresolved
ownership; case evidence is not presented as uniquely assigned feeder equipment.

Mutually exclusive source-evidence cohorts:
1. ZERO_TRANSFORMER_ROWS: recognized Transformer file(s), zero source rows and zero
   target groups; distinguish missing file and malformed/nonpublished records.
2. HAS_UNREFERENCED_TRANSFORMER: nonempty targets, at least one target with no incoming
   equipment connection declaration and no own nonempty connection declaration.
3. ALL_TARGETS_HAVE_REFERENCE: nonempty targets, every target has some declaration.
   Label **necessary evidence upper-bound cohort** only, never recoverable/expected FULL.
4. SOURCE_FILE_UNDETERMINED for absent file/target evidence; do not silently call it empty.

Connection declarations use exact raw text from the explicit equipment endpoint columns
(Line, Switch, Disconnector, EarthingSwitch, Transformer, AccessPoint, Load, DER), not
names, IDs guessed from prefixes, Bus station membership or numeric proximity. Raw
references count as *evidence*, independently of identity/resolution validity. Every
incoming declaration retains the row, field, raw value, source resolver status and target.
Transformer records retain outgoing declarations, identity statuses, raw row refs,
NO_REFERENCE / LINE_ONLY / SWITCH_ONLY / LINE_AND_SWITCH / OTHER reference composition,
ambiguous/unresolved flags, S0/S2 projected/reachable attachment separately. Missing
source Transformer IDs are not matched to empty endpoint strings. No outlier removal.

## Graph frontier and primary observations

Rebuild S0/S2 with the existing E2.2 graph builder; bind graph hashes/coverage to verified
E2.2 and feeder artifacts. For every reachable Line side whose opposite endpoint has no
projection, report the first unexplainable boundary, with source Line/Terminal/target
and exclusion evidence. A projected OPEN Switch with exactly one reachable port is a
KNOWN_OPEN boundary; state is never overridden. Branch frontiers overlap and do not
prove global causality. Missing head, no Line, no reachable Line, and reachable Line
but no reachable Transformer are separate case observations. Preserve accepted and S2
views, not just a single coarse failure tag.

Primary observation priority: MISSING_HEAD, NO_LINE, NO_HEAD_REACHABLE_LINE,
REACHABLE_LINE_NO_TRANSFORMER, then IDENTITY_CONFLICT, ENDPOINT_AMBIGUOUS,
VOLTAGE_CONFLICT, KNOWN_OPEN, SWITCH_DEGREE_RULE, ACCESS_POINT_UNSUPPORTED,
ENDPOINT_UNRESOLVED, TRANSFORMER_MULTI_INCIDENCE, OTHER_BOUNDARY, NONE.
Exactly one primary per graph/feeder; all overlapping observations also reported.

## Readiness and future completion cohorts

Target coverage: FULL, PARTIAL, FAILED, NO_SOURCE_TARGET. Preserve legacy FAILED for
zero targets independently for baseline comparisons. FULL != E3_READY: every case in
this slice has e3_ready=false, reason E3_NOT_AUTHORIZED_AND_CONTRACT_NOT_ASSESSED.
Evidence composition counts approved/source/pending connections and unresolved frontier
boundaries separately; no candidate promotes a connection evidence class.

Recovery readiness has overlapping reasons and one primary, in this order:
ROLE_UNDETERMINED (zero/unknown targets or ownership), BLOCKED_BY_CONFLICT,
NEEDS_SYNTHETIC_COMPLETION, NEEDS_RULE_REVIEW, SOURCE_EVIDENCE_SUFFICIENT.
The last means S0 target-full with approved graph and no blocking evidence, not E3 ready.

Future completion cohorts are flags, not falsely exclusive root causes:
A existing unreferenced Transformer: needs connection/attachment/ownership, never duplicate
  Transformer generation; new source evidence is the non-synthetic alternative.
B zero source rows: ROLE_UNDETERMINED; never automatically generate a Transformer.
C all targets referenced but S2 not FULL: deterministic rule review candidates, not a
  promise of recoverability. Referenced FULL cases remain in the upper-bound cohort.
D identity, voltage, known OPEN frontier or unresolved case ownership: no automatic
  synthetic bridging around these constraints. Known OPEN is a state constraint, not an
  assertion that source data is erroneous. D may overlap A/B/C.

## Candidate evidence and experiments (not applied)

- LEAF_SWITCH_TERMINAL_REPRESENTATION_V1: unique Switch, one unique incoming Line,
  exact inner ref, Switch_FromBus and Line outer endpoint exact and equal, empty ToBus,
  known state. Model two analysis ports with unbound remote connection; never certify
  the unknown external connection. Preserve OPEN.
- UNIQUE_SWITCH_DECLARED_T_ATTACHMENT_V1: existing S2 candidate Switch ToBus EXACT to
  unique Transformer with zero Line incidence, no own endpoint fields, exactly one
  referencing source Switch row. Explicit Switch vs Line outer endpoint semantics
  remain unknown; connection is hypothetical. Never join several Switches via one target.
- MULTI_INCOMING_T_ATTACHMENT_V1: unique Transformer, exactly two unique incoming Lines,
  exact inner refs, no own endpoints or malformed Line evidence. Same MV winding is an
  unapproved assumption. Report source voltage/port evidence and unresolved semantics.
- MULTI_LINE_T_AS_MV_JUNCTION: all unique multi-incidence Transformer Lines mapped to
  one MV attachment, including mixed direction. RISK_EXPERIMENT_ONLY, NOT_RECOMMENDED.

Witnesses retain full incident rows/terminals, own explicit endpoint declarations,
negative/conflict evidence and assumption reasons. Single-rule and cumulative actual
multigraph rebuilds report hashes, target/Line counts, transitions, overlaps, structural
and conducting cycle-rank changes. Risk metrics are diagnostics, not safety certification.
No known OPEN closure, ID repair, case merging, synthetic physical device or accepted
ElectricalTopology is emitted. Hypothetical graph IDs use a separate analysis namespace.

## Artifact and verification contract

Independent non-overwriting output: outputs/nanjing-e2-3/topology-recovery-evidence-v1/.
Required: summary.json, case_details.jsonl, feeder_details.jsonl,
transformer_evidence.jsonl, frontier_blockers.jsonl, connection_evidence.jsonl,
candidate_rule_witnesses.jsonl, recovery_cohorts.jsonl, report.md, manifest.json.
Each case and nested record has stable ordering, canonical UTF-8 JSON, SHA256/count.
Manifest binds four input manifests, schema/analysis/rule versions and a deterministic
Python source-tree fingerprint (code identity independent of commit self-reference),
with no timestamps or absolute paths. Existing verifiers run before and after full
analysis; mismatched input bindings/case inventory/graph hashes fail closed.
Output verifier verifies inventory, canonical bytes, checksums/counts, schema flags and
reaggregates summary from detail streams. Reproduction reruns the analysis, not /tmp
JSON copying. Same inputs/code yield byte-identical outputs across hash seeds.

Tests precede implementation: zero-row/zero-target, all reference compositions,
ambiguous/unresolved/duplicate evidence, OPEN, voltage, AccessPoint, multi-Line,
overlapping blockers, no evidence promotion, candidate immutability, ordering and
hash-seed determinism, checksum tamper, input binding and output isolation.

After full acceptance STOP. Next major review is E2.3-D Synthetic Topology Completion
Contract; B/C require separate review because their observed gains do not add safe FULL.

## Detail field contract

All JSONL records are case-local. `case_id` is the existing non-null Canonical case ID.
`source_case_key` preserves the nullable source value. Entity refs retain their original
Canonical type and ID; `source_terminal_refs` is an ordered array of existing Terminal
ID strings. An empty array means no such evidence, not a generated Terminal. Raw IDs
remain strings, with missing Transformer ID represented by null. `source_records.fields`
is the original ordered source field/value list (nullable for malformed rows), not a
repaired dictionary. Evidence IDs belong only to this analysis, never SourceImport IDs.

| Detail | Fields and interpretation |
|---|---|
| Transformer | `raw_row_count`, `line_incidence_count`: integer rows/distinct source Line groups; `reference_composition`: closed audit category; identity/resolution flags are independent booleans; `incoming_references`/`outgoing_references` preserve raw values and resolution statuses; `attachment.S0/S2`: projected/reachable booleans and derived ID lists |
| Frontier | `policy`: S0 or S2; `tag` and `decision_reason`: stable observation codes; `raw_endpoint`/`resolved_source_ref`: nullable for case-level observations; `reached_node_id`: nullable if no head; one record per branch boundary or case-level observation |
| Connection | `policy`, `conducting`, `approved`: explicit; `derived_ids`: branch and its two node IDs; `approved_rule_refs`: existing v1 rule/version strings, empty for S2 assumptions; `evidence_class`: never inferred from reachability |
| Candidate | `rule_id/version`, `approved=false`, `evidence_class=UNRESOLVED`; `assumptions`: nonempty semantic gaps; `source_records`: supporting raw records; `source_exclusions`: existing E2 exclusions; `recommended=false` for risk experiment, null for undecided candidates |
| Feeder | `target_coverage` and `legacy_target_status` are separate; `evidence_composition` counts connections/boundaries/head nodes in separate integer fields; `recovery_readiness` plus all `readiness_reasons`; `completion_cohorts` A/B/C/D may overlap; `e3_ready=false` with explicit reason |
| Graph/experiment | SHA256 of the actual temporary multigraph; integer reachable Transformer/Line counts and structural/conducting cycle ranks; target status uses the complete source target group denominator |
| File accounting | Original Transformer file path/header/diagnostics and row count; `recognized_headers` requires exact registered header equality; missing/unrecognized files never become confirmed zero-row files |

Artifact case streams are ordered by `case_id`; evidence streams within a case by
`evidence_id`; Feeder groups retain deterministic source identity-group order. Raw field
order is preserved; supporting/conflict locator arrays are sorted and unique. Primary
readiness does not erase other reasons: for example, an A+D case still exposes both its
missing attachment and the prohibition on bridging around a known constraint.
