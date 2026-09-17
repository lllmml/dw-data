# E2.3-D4 synthetic physical backbone proposals / 1.0.0

D4 uses immutable accepted topology v2, source-bound D3 evidence and the unchanged
D2 business snapshot. All effects are PROPOSAL_ONLY_COUNTERFACTUAL. No approval,
apply, source edit, accepted edit, device generation, electrical parameters or E3.

## Structural evidence and gap taxonomy

Inventory every source Feeder; separately aggregate the 1,402 whose D3-after primary
is SYNTHETIC_BACKBONE_REQUIRED. Components are maximal undirected accepted physical
components. A source-supported Line component contains an accepted source LINE edge;
unrepresented raw Lines are separately counted and never assumed connected.
Tags overlap: DISCONNECTED_SOURCE_LINE_COMPONENTS (multiple Line components),
HEAD_TO_SOURCE_COMPONENT_GAP (unreachable Line component), INTER_COMPONENT_GAP
(multiple disconnected Line components), REMOTE_SWITCH_PORT_GAP (D3 UNBOUND port),
ACCESS_POINT_GAP (source AccessPoint), TRANSFORMER_REGION_GAP (existing target and
not exactly one reachable accepted Bus), INSUFFICIENT_STRUCTURE (no Line component).
The exclusive display priority is the order above. Tags do not authorize placement.
Every raw AccessPoint remains an unreviewed ENGINEERING_PLACEMENT_ANCHOR candidate;
no source junction or accepted connection is inferred from its existence.

## Rules and anchor selection

HEAD_TO_UNIQUE_COMPONENT_V1: exactly one feeder, known compatible MV voltage, no
D3/D2 hard contradiction, exactly one disconnected accepted source-Line component,
no already reachable source-Line component, and exactly one accepted Bus junction
inside that component. A Bus is the engineering distribution attachment boundary;
Transformer MV ports are not generic junctions and Switch ports need explicit
upstream/downstream placement evidence. Multiple Bus anchors remain NON_UNIQUE_ANCHOR.
This is an explicit engineering assumption, not recovered source direction. Isolated
Bus nodes outside the component are reported but do not qualify without a source Line.
If any explicit OPEN source reference involves the selected Bus, or any unresolved
OPEN declaration has nonempty endpoints, placement requires review; it may not silently
bypass an unrepresented cut. Closed earthing at either endpoint also forbids placement.
One generated edge joins the existing derived head to this unique Bus. No new node
is necessary. Neither coverage nor ID/iteration order selects the target.

UNIQUE_COMPONENT_BRIDGE_V1 requires a unique source-evidenced pair of attachment
ports in two different components and continuity evidence beyond common feeder or
voltage. Current source reference semantics do not establish that port-pair contract;
retain MANUAL_LAYOUT_REQUIRED, with component and raw reference witnesses.
UNBOUND_SWITCH_EXTENSION_V1 requires unique downstream placement evidence independent
of the empty remote declaration. UNBOUND alone is not evidence; retain review with
source references. ENGINEERING_JUNCTION_V1 requires reviewed multi-component placement
and proof that an intermediate node is necessary; absent that evidence emit no node.
These three rule families are explicitly reviewed but not enabled for automatic
placement in v1. This is not acceptance of S2. Future enabling requires a rule version.

## EngineeringAttachmentAnchor contract

All IDs are opaque case-local identifiers, exact-match only. Each record contains
case_id, feeder_id, node_id (nullable only for unreviewed AccessPoints), source_refs,
voltage_kv (decimal-string kV or null), anchor_type, physical_reachable,
conducting_reachable, ambiguity_status and exclusion_reasons. Accepted Bus, head,
Switch ports, Line endpoints and raw AccessPoints are inventoried. Source refs refer
to immutable rows. Unrepresented/unbound ports cannot automatically establish route.

## Safety, metrics and artifact

Generated IDs use `d4-generated:<kind>:<sha256>` over version, case, feeder, rule and
semantic endpoints; ordering is only serialization. Objects are RULE_GENERATED,
PROPOSED and neither approved nor applied. No new Transformer or LV Bus is allowed.
Independent validation checks exact base hash, case/feeder ownership, namespace,
voltage, evidence-backed unique selection, cycles, state/cut preservation and absence
of disconnected generated nodes. Both physical and conducting graphs are rebuilt.
OPEN edges persist physically and remain excluded from conducting paths. Zero-target
status stays NO_SOURCE_TARGET. The D3 read-only D2 eligibility evaluator is rerun.

Artifacts have canonical JSON/JSONL, SHA256 inventories, no timestamps, source/D3/v2
manifest bindings and rule/schema/code bindings. Full verification checks authoritative
D3 inputs and replays all detail and summary streams. Separate hash-seed reproduction
must be byte-identical. Inputs and outputs must be disjoint, output must not exist,
and data/raw is prohibited. Summary distinguishes overlapping taxonomy, exclusive
outcomes, all-case graph sums and source-Feeder coverage counts. Ratios with zero
synthetic edges are null. Original cycles remain; new cycles are prohibited.

The raw reference incidence graph (Line endpoints, explicit Switch endpoints and
AccessPoint_Bus) is an additional competing-structure veto. Its connected groups are
not accepted physical components and cannot certify conducting paths. Multiple raw
Line-bearing reference groups forbid automatic head placement even if only one group
has accepted Lines. Raw reference witnesses are persisted per Feeder. No GIS is used.
Automatic review includes all source Feeders with existing structure (including
zero-target Feeders); the 1,402 primary cohort is separately identified and counted.

Engineering degree covers inherited generated feeder heads and any newly generated
junctions; maximum_new_synthetic_node_degree separately counts new nodes only.
Unresolved-anchor count means inventory anchors with nonempty exclusion reasons;
ambiguous placement counts Feeders with multiple components or multiple Bus anchors.
Source:synth ratio is an exact {source, synthetic} integer pair, not a binary float.
Per-Feeder impact is case-local (current accepted input has unique feeder ownership);
zero/multiple-Feeder cases receive no proposal.

A sole source-Line component already connected to the head is classified
NO_BACKBONE_ACTION_REQUIRED (unless a hard exclusion applies). It does not count as
manual layout simply because this construction rule has nothing to add. Device
attachment/business readiness remains independently evaluated by D2.
