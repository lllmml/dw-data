# E2.3-D3 deterministic recovery / accepted topology v2

Version `deterministic-topology-recovery-v1 / 1.0.0`. The D3 user request authorizes
review and acceptance of individually justified deterministic rules and publication
of a new immutable overlay. Historical S0/v1, source facts, and D2 artifacts are inputs,
never rewritten. This is not blanket S2 acceptance. E3/OpenDSS/QSTS remain unauthorized.

## Acceptance rationale and rules

`SERIES_EXACT_DIRECT_V2` is ACCEPTED only for a unique case-local ordinary Switch,
complete two-distinct-unique-Line incidence with one incoming and one outgoing Line,
EXACT inner references, all four A/B/X/Y EXACT unique source targets, X=A and Y=B
in both raw text and resolved identity. Direct consistent declarations extend the
already accepted series interpretation without ignoring explicit evidence. Reverse,
membership-only, partial matches, unresolved declarations and tie devices remain
NEEDS_REVIEW. A/B may be Bus, Station, Switch or Transformer, but no new mapping of
those outer entities is implied. Only already accepted terminal mappings or separately
accepted Switch ports may complete a Line. AccessPoint/other types remain unsupported.
An endpoint cannot refer to the same Switch; A=B is excluded. Every explicitly declared
Bus voltage must agree with the existing MV model, except an existing approved
Station-to-head projection (the upstream Bus is not rewired). No lexical selection.

`LEAF_SWITCH_REPRESENTATION_V2` is ACCEPTED only for one unique incoming source Line,
a unique ordinary known-state Switch, EXACT inner reference, empty Switch_ToBus and
EXACT Switch_FromBus equal to the Line outer endpoint in raw text AND resolved identity.
The incoming side is attached to a derived switch port; the second port is explicitly
UNBOUND. This represents the existing device without claiming its remote connection.
It cannot bridge components through an invented remote connection. No junction or
source device is generated. An outer endpoint projection is still required for a Line.

Both rules require a valid existing head/MV voltage, no D2 hard identity/ownership/
voltage contradiction, full incidence evidence, and finite compatible explicit voltage.
They preserve raw endpoints and raw state, use two derived ports and an internal
physical branch, and conduct exactly when source state is CLOSED. OPEN remains physical
and nonconducting; UNKNOWN fails the known-state prerequisite. All new nodes/edges are
RULE_INFERRED, never SOURCE_CONFIRMED or RULE_GENERATED. Source terminal numbering is
not repurposed as Transformer winding semantics. Existing synthetic heads are inherited
model assumptions, separately counted; D3 creates none.

Other rule families: broad S2 semantic relaxation NEEDS_REVIEW (absence of conflict is
not a proof); tie/reverse/membership NEEDS_REVIEW; referenced Transformer with an existing
v1 attachment is BASELINE_PRESERVED, otherwise NEEDS_REVIEW; Switch-declared Transformer
NEEDS_REVIEW because two-level endpoint semantics/port placement are not proven;
multi-incidence Transformer NEEDS_REVIEW, and collapsing it into a junction REJECTED;
AccessPoint NEEDS_REVIEW without an approved unique port contract. Source ID alone or a
single incoming declaration does not prove the physical role of AccessPoint. No missing
Transformer is created. Hard conflicts reject additions throughout their affected case;
all original conflicting rows survive. No disambiguation rule is introduced.

Each rule review records input evidence, possible interpretations, state, case/type,
identity, voltage, component-bridge checks, preconditions/exclusions and acceptance result.
Candidate statuses are ACCEPTED / REJECTED / NEEDS_REVIEW / BASELINE_PRESERVED. Family
status describes the rule, not a blanket acceptance of every candidate. Candidate counts
and distinct Feeder counts by status/reason overlap across families and across status
subsets; a Feeder may have both accepted and rejected candidates.

## Data / graph contract

Independent SHA256 IDs hash canonical JSON `[version, rule_version, kind, case_id,
source_owner, role]`, prefix `deterministic-v2:`. Sorting only serializes output.
Case/Feeder/source identifiers are existing strings, never repaired. Evidence locators
are sorted unique lists; source row fields preserve text and field order. Missing
endpoint/identity/voltage values are null or original empty text, never filled in source.
Derived voltage is a positive finite Decimal string in kV inherited from the approved
MV domain. Counts (candidates, feeders, nodes, edges, components, cycle rank) are integers.
Port roles IN/OUT/UNBOUND explicitly exclude winding/HV/LV assignments.

Accepted artifact stores a full materialized graph in `case_topologies.jsonl`, plus
`additions.jsonl` with per-object source refs, rule/version, candidate ID and evidence
class. Base nodes/edges are byte-equivalent JSON records from D2's accepted S0 graph;
all additions carry provenance. The overlay never drops a base node or edge. Line
addition requires two accepted endpoint mappings, exact local source Line identity,
and voltage compatibility. Cycles are retained and reported, never repaired for radiality.
Physical graph includes all branches; conducting graph uses original conducting flags.
Components include isolates; cycle rank is m-n+c with parallel edges and self-loops.

## Taxonomy, coverage and eligibility

All 5,159 cases remain represented. Every source Switch/AccessPoint and referenced
Transformer gets a candidate review, including nonunique/unpublished groups. Every
D2 DETERMINISTIC_RECOVERY Feeder gets overlapping taxonomy and one display primary:
accepted series; multi-incidence T; unprojected referenced T; leaf representation;
AccessPoint; known OPEN series; S2-only backbone; other deterministic review. The
priority is descriptive, not a claim of recoverability or causal attribution.
Full candidate lists and source/conflict witnesses support these categories.

Report before/after physical AND conducting target coverage FULL/PARTIAL/FAILED/
NO_SOURCE_TARGET using unchanged source target inventory. Independently report topology
coverage FULL only when all source Line/Switch/T identity groups are represented and
reachable; PARTIAL requires a head-reachable Line, otherwise FAILED. All no-Feeder cases
are retained but excluded from Feeder denominators. Report all transitions, reachable
Line/T, component/cycle deltas, new branches and state preservation.

Recompute D2 eligibility without creating any synthetic object. Reuse D2 region and
voltage definitions, source hard conflicts, business snapshot and primary priority.
Unique region/voltage/identity/grounding checks assess a hypothetical attachment; no
bundle, node, edge or proposal is instantiated. Before results MUST reproduce D2
feeder primary, backbone, eligible target and missing-backbone-or-region candidate
counts before reporting after. Missing-backbone-or-region retains D2's combined 87,293
metric; absent physical backbone and absent/nonunique region are also separate metrics.

## Artifact / verification

Analysis directory: `outputs/nanjing-e2-3/deterministic-topology-recovery-v1/`.
Accepted directory: `outputs/nanjing-e2-3/accepted-topology-v2/`.
Manifest binds source/E2/E2.2/feeder/E2.3-A/D1/D2/frozen-v1 hashes, rule/code versions,
canonical file SHA256/counts; accepted manifest binds analysis manifest. Separate directories
must be new, outside data/raw and outside every input/output. No overwrite option.
Analysis persists case evidence inputs, candidate/accepted/rejected connections,
rule_review, feeder_recovery, case_coverage, eligibility before/after, rule_summary,
coverage_impact, d2_reclassification, report. Verifier rejects extra/missing files and
noncanonical bytes, rebuilds decisions/graphs/summary from details, compares accepted
materialization, and in bound mode reconstructs evidence from all authoritative inputs.
Input bindings are required for authoritative verification. A self-consistency check
alone cannot certify source truth. Full reproduction uses independent processes and
hash seeds; protected-file SHA256 inventory proves source/v1 unchanged. Full suite,
compileall and whitespace checks precede commit; then STOP at D3.

## Reporting refinements

Series candidate review variants distinguish exact direct, exact reverse,
tie/unknown type, invalid incidence, unresolved endpoint and different/partial endpoint.
Variant counts are a secondary partition of the series family; they do not double the
source candidate denominator. Family and variant acceptance still require all gates.
Single-family graph deltas include only source Line edges whose added endpoint mappings
are wholly supplied by that family; cumulative deltas may differ and are reported too.

`topology_coverage_scope=SOURCE_LINE_SWITCH_TRANSFORMER_ONLY` accompanies the topology
status. It must not be read as completion of AccessPoint semantics or remote leaf ports.
`active_edge_count` counts all physical branches or only conducting branches, respectively,
and satisfies `cycle_rank = active_edge_count - node_count + components` in each view.
New Switch ports bind their voltage to the inherited accepted feeder-head node. Explicit
Transformer HV declarations, when present on an outer endpoint, must also agree with
that inherited domain; absence does not assign winding numbers or create a new MV rule.

Candidate `structural_inclusion` / `conducting` describe **new D3 candidate branch
inclusion**, not whether an inherited S0 Transformer node is present. In particular,
BASELINE_PRESERVED makes no new connection. A hard-case rejection forbids a new
interpretation but does not delete an already inherited v1 attachment. Materialized
before/after topology and coverage are authoritative for inherited graph membership.
