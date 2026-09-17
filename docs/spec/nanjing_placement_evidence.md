# E2.3-D4.1 source-constrained placement evidence / 1.0.0

D4.1 works on immutable accepted topology v2 plus the immutable D3/D2/source chain.
It studies the 137 D3-after `SYNTHETIC_BACKBONE_REQUIRED` Feeder that own source Line
rows but no accepted Line component. All effects are PROPOSAL_ONLY_COUNTERFACTUAL.
No approval, no apply, no source edit, no accepted edit, no device generation, no
electrical parameters, no E3/OpenDSS/QSTS. This is not acceptance of S2.

## Why the cohort exists

D4 proved `HEAD_TO_UNIQUE_COMPONENT_V1` cannot scale. D4.1 first answers a narrower
question: why does a Feeder with source Lines still have no accepted Line component?

A source Line becomes an accepted LINE edge only when both Canonical Terminals map to
an accepted node. In this cohort every Line is excluded with `LINE_ENDPOINT_EXCLUDED`.
Measured over the 137 Feeder: 981 published unique Lines, 1962 declared endpoints,
of which 778 Lines have exactly one accepted endpoint and 203 have none. The accepted
endpoint count is zero for every Line, because none of these Cases has an accepted
edge. The unresolved endpoint is mediated by a case-local source entity that E2/D3
decline to represent:

| unresolved endpoint target | Lines |
|---|---|
| ordinary Switch with explicit endpoint declarations | 356 |
| ordinary Switch with non-series incidence | 227 |
| non-exact raw reference | 100 |
| AccessPoint | 77 |
| Transformer with non-single incidence | 18 |

The raw declarations of those entities point outside the Case. Over the 137 Case,
974 endpoint texts do not resolve case-locally; 248 are distinct, 217 of which are
defined as `Switch_ID` (156), `AccessPoint_ID` (24), `Transformer_ID` (20) or
`Bus_ID` (17) in a *different* Case directory, and 31 are defined nowhere in the
intake. Those references are cross-Case and are never followed (see Boundaries).

## Root-cause taxonomy

Every one of the 137 Feeder receives exactly one primary status and a set of
overlapping reasons. The classes are:

- `PLACEMENT_EVIDENCE_SUFFICIENT` — at least one Line component proposal was produced.
- `ACCESSPOINT_POLICY_REQUIRED` — the only remaining blocker is an AccessPoint anchor
  that the enabled narrow rule declines.
- `REMOTE_SWITCH_POLICY_REQUIRED` — the only remaining blocker is a Switch anchor the
  enabled narrow rules decline.
- `NON_UNIQUE_PLACEMENT` — a blocker is genuine placement ambiguity (competing entity
  type, non-exact reference, series incidence that does not pair, Switch degree >= 3).
- `HARD_SOURCE_CONTRADICTION` — the Case carries a D2 hard blocker.
- `INSUFFICIENT_PLACEMENT_EVIDENCE` — source Lines exist but no anchor is reachable.

Primary priority is the order above. Overlapping reasons are reported separately and
must not be summed with the primary counts. The 1,259 backbone-required Feeder with no
source Line at all are out of scope and are only tagged `NO_SOURCE_LINE_LAYOUT_BASIS`.

## PlacementEvidence contract

One immutable record per declared endpoint of every published unique source Line in a
target Case. Fields: `case_id`, `feeder_id`, `source_line_id`, `source_line_record_ref`,
`endpoint_side` (1 = `Line_FromBus`, 2 = `Line_ToBus`), `raw_endpoint_value` (verbatim
source text, never normalized), `terminal_ref_status` (persisted Canonical Terminal
status), `resolver_status`, `resolved_source_kind`, `resolved_source_id`,
`candidate_anchor_ids` (accepted node ids already mapped to this terminal),
`source_incidence_witnesses`, `voltage_evidence`, `switch_witnesses`,
`accesspoint_witnesses`, `identity_status`, `ownership_status`,
`operating_state_constraint`, `competing_evidence`, `contradiction_refs` and
`placement_evidence_class`.

`resolver_status` is one of `NO_DECLARATION`, `EXACT_CASE_LOCAL`,
`CASE_LOCAL_AMBIGUOUS`, `EXTERNAL_DEFINED` (defined only outside this Case),
`UNDEFINED_REFERENCE`. `placement_evidence_class` is a discrete contract class and
there is no numeric confidence anywhere:

- `EXACT_STRUCTURAL_ANCHOR` — the persisted endpoint projection already maps the
  Terminal to an accepted node.
- `ENGINEERING_SHARED_REFERENCE_ANCHOR` — the endpoint names a case-local unique
  entity that carries no accepted structural representation and that an enabled narrow
  rule may propose as an engineering anchor.
- `AMBIGUOUS_ANCHOR` — several case-local entities match the raw text.
- `CONFLICTING_ANCHOR` — a case-local target exists but a hard gate forbids it.
- `NO_ANCHOR_EVIDENCE` — no declaration, external reference or undefined reference.

`DERIVED_LOCAL_ANCHOR` is reserved for endpoints already mapped to an accepted D3
Switch port; the D3 cohort already covers that case and it is counted separately.

## Anchors and rules

All generated anchors are `RULE_INFERRED` and PROPOSED. Nothing is ever marked
`SOURCE_CONFIRMED`: the source fact is that a Line row names an entity; the derived
claim is that the entity is a structural junction or attachment point. Generated ids
are `d4.1-generated:<kind>:<sha256>` over version, case, feeder, rule and semantic
endpoints; ordering is serialization only and never selects an anchor.

`ACCESSPOINT_ENGINEERING_ANCHOR_V1` creates one junction node for a case-local unique
AccessPoint, with the Case nominal MV voltage, when all hold: exactly one raw row for
that `AccessPoint_ID`; no case-local entity of another type shares that raw id; every
declared AccessPoint field other than the id is empty; at least one published unique
Line references it through an exact Terminal; all referencing Lines are case-local and
belong to the single Case feeder; no D2 hard blocker; no CLOSED `EARTHING_SWITCH` or
OPEN state constraint names that raw id. AccessPoint degree 1, 2 or 3 all take the same
junction form because an AccessPoint carries no state and therefore no cut.

`SWITCH_LEAF_PLACEMENT_ANCHOR_V1` covers an ordinary case-local Switch with exactly one
incident published Line. It creates an `ATTACH` port, an `UNBOUND` port and an internal
`SWITCH` edge whose `conducting` equals `state == 'CLOSED'`. The incident Line attaches
to `ATTACH` regardless of its endpoint side: with a single Line and no case-local outer
declaration the orientation is not source-evidenced, so no orientation is claimed.

`SWITCH_SERIES_PLACEMENT_ANCHOR_V1` covers an ordinary case-local Switch with exactly
two incident published Lines, one declared on side 2 and one on side 1. It creates
`IN`/`OUT` ports joined by an internal `SWITCH` edge with `conducting == (state ==
'CLOSED')`, and attaches the side-2 Line to `IN` and the side-1 Line to `OUT`. This is
D3's frozen orientation convention; with two Lines the pairing is evidenced by both
declarations.

Both Switch rules additionally require: unique published identity, exactly one raw row,
`Switch_IsTie` exactly `False`, `Switch_NormalState` in {`Open`, `Closed`}, the Switch
not already represented in accepted v2, and — the complement of D3's exact-direct rule —
**neither `Switch_FromBus` nor `Switch_ToBus` may resolve to a case-local entity**. If an
outer declaration is case-local, the Switch belongs to D3's exact-direct contract or is a
genuine conflict, and D4.1 declines it.

`DERIVED_SHARED_REFERENCE_JUNCTION_V1` is reviewed but **disabled**. It would join an
arbitrary number of Lines that share one unresolved raw text, or an entity of degree
>= 3. Source evidence proves the same string, not an electrical junction, so no
unbounded-degree anchor is generated. Switch degree >= 3 is `NON_UNIQUE_PLACEMENT`.

OPEN semantics: a Switch anchor always keeps its state. An OPEN Switch produces a
non-conducting internal edge, so the two sides stay separated in the conducting graph.
Placement must never close a cut, and must never create a conducting path between the
endpoints of any existing non-conducting edge that was separated before.

## Line component representation

A `LineComponentProposal` is emitted only when every declared endpoint of a published
unique source Line resolves to an anchor — either an accepted node or a proposed
engineering anchor. It reuses the source Line's own identity: no second Line device is
generated, the original `Line_ID`, endpoint text and record provenance are preserved,
and the proposal carries `source_entity_ref` of the real Line plus the anchor provenance.
A Line already represented by an accepted LINE edge is `LINE_ALREADY_REPRESENTED`.
Line edges are conducting; cuts live in Switch internal edges only.

## Two Case-level gates and one pruning rule

The derived representation must never invent connectivity the source does not certify,
and it must never choose between competing source readings.

`PARALLEL_DUPLICATE_DECLARATION_NOT_REPRESENTABLE`: two distinct source Line identities
can declare the identical anchor pair. That is either one circuit recorded twice or two
parallel circuits, and the source does not say which, so **every member of such a group
is withdrawn** and no ordering ever selects a representative. The groups are recorded in
`rejected_candidates`. This is the only reason a source Line that is otherwise fully
evidenced is not represented.

`PLACEMENT_WOULD_CREATE_CYCLE` / `PLACEMENT_WOULD_BYPASS_OPEN_CUT`: after the parallel
gate, the surviving proposals are placed on a copy of accepted v2 and both the physical
and the conducting cycle rank are recomputed, together with the conducting connectivity
of every base edge that was separated before. If either changes, the whole Case is
withdrawn — anchors, ports, branches and proposals — because the source declarations
cannot be represented simultaneously without inventing a topology. A bypass always also
raises the physical rank, so the cycle check normally reports first; both are kept
because they are independent assertions.

Pruning keeps generated objects only for anchors a surviving Line still attaches to, so
the counterfactual never contains a disconnected generated port. Every port of a kept
anchor is retained, including a series Switch's unattached side and a leaf Switch's
`UNBOUND` port: those are the represented boundary, not stray nodes.

## Composition, replay and metrics

The downstream counterfactual is named
`ACCEPTED_V2 + D4.1_PLACEMENT_PROPOSALS + D4_BACKBONE_REPLAY`. The D4 engine is
re-invoked unchanged on the placement counterfactual; D4 objects are never confused
with accepted topology. Each of the 30 D4 proposals is replayed and classified
`STILL_VALID`, `SUPERSEDED_BY_BETTER_PLACEMENT`, `NOW_AMBIGUOUS` or `INVALID`, and
none is approved or applied.

Reported after the replay: recovered/proposed Line components, additional automatic
backbone-eligible Feeder, physical backbone proposal-after, reachable source Lines,
reachable Transformers, attachment-eligible Feeder, eligible Transformer candidates and
missing backbone candidates, each against the D4 before-value.

## Boundaries

`NO_SOURCE_LINE_LAYOUT_BASIS` is emitted and nothing else for the 1,259 backbone-required
Feeder without source Lines: no random tree, no arbitrary feeder route, no synthetic
source-like Line. No Transformer, LV Bus, Load or DER is ever generated; the 1,713
zero-target Feeder stay unchanged. A D2 `HARD_SOURCE_CONTRADICTION` is never bypassed;
where an existing hard classification looks too strict, only a review note is recorded.

Cross-Case reference is never followed, even when the id is defined elsewhere in the
intake: identity, ownership and placement stay case-local. No normalization is applied
to raw text, and no GIS, nearest-neighbour, min-id or random selection is used.

## Validation and artifact

An independent validator re-derives every proposal from the persisted evidence and
checks: exact accepted base hash, case and feeder ownership, generated namespace,
voltage compatibility, evidence-backed uniqueness, absence of new cycles, preservation
of OPEN cuts, no duplicate source Line, no device generation, and source endpoint text
unchanged. Artifacts are canonical JSON/JSONL with SHA256 inventories, no timestamps,
source/D3/v2 manifest bindings and rule/schema/code bindings; verification replays every
detail and summary stream against authoritative inputs, a tampered manifest fails, and a
separate `PYTHONHASHSEED` reproduction must be byte-identical.
