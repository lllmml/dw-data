# E2.1 Switch semantics diagnostic contract v1

Status: ANALYSIS ONLY. No accepted topology contract is changed. Inputs are verified
E1 and baseline E2 artifacts from the same source manifest. Output is a separate,
new directory. Neither source values/references nor baseline graphs are modified.

## Populations and identity

Report all inventory cases. Count source Switch rows, published Switch entities and
raw Switch identity groups separately. Degree means distinct raw source Line IDs
incident through either endpoint, before excluding any Line. Missing Line IDs use
row locators for degree accounting but cannot certify a candidate. Duplicate Line
identities and malformed Line rows prevent candidate certification; no representative
is selected to recover a connection. Candidate: one UNIQUE published Switch/one raw
row, two distinct UNIQUE published Lines/one raw row each, one incoming and one
outgoing occurrence. Persist whether the two inner E1 references are EXACT to Switch.
Baseline SWITCH_DEGREE and EXPLICIT_ENDPOINT_EVIDENCE counts select device mappings,
not repeated Line endpoint projection records.

## Diagnostic records

`switch_candidates.jsonl` has one row per candidate, sorted by case_id and Switch
source_record_ref. Fields: case_id/source_case_key; switch_id (raw), source_entity_ref,
source_record_ref; raw Switch_FromBus/ToBus/NormalState/IsTie/HasMeasurement;
canonical normal_state (CLOSED/OPEN/UNKNOWN), is_tie and has_measurement (bool/null);
incoming/outgoing Line IDs and locators; A/B/X/Y and both inner Line endpoints;
source reference statuses and exact source entity types; diagnostic literal identity
lookups; motif, semantic assessment, graph relations, ID-pattern diagnostics;
complete ordered/deduplicated supporting_source_refs. IDs remain exact text.
All fields are required, except nullable targets, flags and source_case_key. Counts
are integers, graph distance is a categorical value, ratios/percentages are Decimal
strings (six decimal places), and no field is an electrical parameter.

E1 SourceReference status/target is preserved verbatim. A separate
`diagnostic_status/type/target` is a case-local exact-text lookup over all source
identity types, including unpublished/duplicate evidence. This does NOT alter or
replace the frozen Candidate Matrix. Multiple rows/types are AMBIGUOUS; absent IDs
UNRESOLVED; empty IDs MISSING. Lookup uses no normalization, prefix/nearest search,
scientific notation expansion or ID repair.

## Motifs and semantics

Nonempty equality flags independently cover direct (X=A,Y=B), reverse (X=B,Y=A),
each single equality, X=Y, both/one missing and both different from A/B. Exclusive
literal motifs prioritize missing fields, direct, reverse, collapsed X=Y, exactly
one equality, other partial equality and both different. Flags may overlap; exclusive
motif counts sum to the candidate population.

Explicit breakdown is exclusive: preserved EXACT direct/reverse compatible evidence,
demonstrated different source layer, endpoint ambiguous, endpoint unresolved, both/one
missing, partial compatible, both different, other. Extra diagnostic matches outside
the frozen Candidate Matrix never override an existing EXACT source reference. Additional literal motifs are retained so
unresolved lookups never hide string patterns. "Compatible" here means redundant,
consistent *source endpoint evidence*, not confirmed real-world connectivity.
Confirmed conflict is not inferred merely from nonempty/different values or a missing
local path. Without a frozen endpoint abstraction, such records remain semantics
unknown. A different-layer classification requires explicit Bus→Station membership
on a differing pair, with the other pair equal or supported the same way; proximity
alone is insufficient.

## Source-reference graph

Vertices are existing Canonical source entities. Undirected edges are existing EXACT
Terminal owner→target references, Bus→Station membership, and Feeder→source Bus;
owning/target identity must be UNIQUE. Line is a vertex, so one intervening Line is
two reference hops. No raw textual lookup is inserted as a graph edge. Distances for
A-X, B-Y and reverse pairs are 0, 1, 2, GT2, DISCONNECTED, or UNRESOLVED.
Use a preserved EXACT source target when present, otherwise only a unique diagnostic
lookup target. This does not add an edge for the lookup itself. A resolved
same-component pair beyond two hops is GT2; no unbounded shortest-path search is
needed. Deterministic witness paths and their source locators are retained for ≤2.
Station affinity uses explicit source paths only, and is not physical ownership.

ID diagnostics compare only the given endpoint pair: exact text, decimal-digit text,
common prefix length, first differing suffix width, suffix equality at 1/2/3/6 digits,
scientific-notation flag, and leading-zero-only difference. These features are never
used for identity lookup, topology, or counterfactual acceptance.

## Aggregation and examples

All cases have candidate count, dominant motif(s), purity=max motif count/total,
minority motif count (not a quality defect), and group distributions. No candidates:
purity=null, dominant motifs=empty. Preserve ties instead of choosing one. NormalState,
IsTie, HasMeasurement and source A/B entity-type pairs are separate stratifications.
Representative examples: first three sorted (case_id, source_record_ref) per motif
and breakdown bucket, never selected for apparent plausibility.

## Counterfactuals

Every scenario is COUNTERFACTUAL ONLY / NOT ACCEPTED TOPOLOGY. Persist metrics only,
never a replacement topology. Baseline is loaded unchanged. Scenario A ignores only
Switch explicit fields and uses certified one-in-one-out incidence with EXACT inner
references. Scenario B accepts only literal direct/reverse compatible unique endpoint
evidence. Scenario C adds demonstrated Bus/Station layer relations if any exist.
OPEN/UNKNOWN remain non-conducting. Non-Switch endpoint mappings, feeder heads,
BUS voltage exclusions, Transformer attachments and all other E2 decisions are reused
from the baseline. Source Line identity and both accepted endpoint requirements remain.
Temporary analysis ports have no Source identity and are not emitted as topology.
