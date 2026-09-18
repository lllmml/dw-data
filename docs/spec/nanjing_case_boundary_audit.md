# D4.2 case boundary audit / 1.0.0

Analysis only. Q-CASE-001 remains OPEN and directory = GridCase remains the operational
contract. No resolver, mapper, Canonical reference, accepted graph or proposal is changed.
No synthetic object, device, layout, approval or apply is produced.

## Source and identity

Rebuild from all cases in the source inventory and manifest-bound row_accountability.
GlobalSourceReferenceIndex keys are (source entity type, verbatim raw ID); retain every
row including duplicate identities. Each entry carries case/key, source record/file type,
identity status, Canonical ref (nullable), feeder IDs/names, station context and voltage
witnesses. IDs and references are never normalized. Empty references are counted separately.
Fields come from the registered CSV schema: all FromBus/ToBus/Bus fields, Bus_Station_ID,
Feeder_SourceBus, and SimConfig SourceBus/OutputVoltageBus values. Load/DER header-only
files remain zero rows, not inferred devices. Persisted EXACT case-local resolutions are
excluded; local ambiguity is retained as an explicit diagnostic, never overwritten.

## Classification and context

Primary external classification counts raw field occurrences, not distinct strings:
UNIQUE_EXTERNAL_MATCH (one foreign row), MULTIPLE_EXTERNAL_MATCH (more than one),
UNDEFINED_GLOBAL (no local or foreign row), LOCAL_UNRESOLVED_ONLY (local candidates only).
CROSS_TYPE_EXTERNAL_MATCH is an overlapping flag for more than one external source type.
Candidate context flags also overlap; denominators and unknowns must be explicit.
An external lookup is an observation, not a change to the local resolution status.

Station context uses exact Feeder_SourceBus -> case-local unique Bus -> Bus_Station_ID
source fields. Missing or contradictory context stays UNKNOWN; a shared distribution
station elsewhere in the directory does not establish a shared feeder station.
Feeder family observations use exact raw Feeder_ID or exact nonempty Feeder_Name;
no fuzzy names, stripped suffixes or inferred ownership. All comparisons have witnesses.
Voltage is in kV as decimal text: Bus_BaseKV and the endpoint-specific Transformer
HV/LV declaration take precedence; otherwise the unique source-head Bus voltage is a
context observation. Compatibility is exact or the existing 10/10.5 kV equivalence.
Missing or multi-domain evidence is UNKNOWN, never compatible by default.
Transformer candidates carry both domains and cannot provide a unique terminal voltage
without side evidence. Station nameplate voltage is not a bus voltage.

Reciprocity means a witnessed directory pair A->B and B->A, not proof that the same
terminal pair or electric circuit connects. All candidate directories contribute graph
edges; ambiguous edges are explicitly counted and must not be treated as resolved.
CaseReferenceGraph has all inventory cases, directed edges with complete raw-ID/type
sets and reference witnesses, in/out degree, WCC (also called undirected connected
components), SCC, ratios and isolated nodes. A POSSIBLE_EXPORT_PARTITION_CLUSTER is a
nontrivial component of the unique, same-station, compatible reciprocal subgraph;
these are reported separately from the full WCC, which may span many stations. It is an
observation, never a merger. Report station/feeder/voltage sets and ownership conflicts.

## Counterfactual

All results are ANALYSIS_ONLY_CROSS_CASE_COUNTERFACTUAL. Unique, type-compatible,
identity-unique, voltage-compatible candidates with no known hard contradiction are
safe-looking identity candidates only. Ownership remains unconfirmed even for equal
station context. Strict impact also requires same-station context. Identity resolution
counts and representable accepted anchors are separate: an external Switch identity
without a uniquely evidenced attachment port does not resolve placement.

Structural impact uses a transient connectivity calculation over existing accepted
nodes/edges and source Lines only when both endpoints already have unique accepted
anchors (local endpoint projections or unique target Bus junction). It emits counts
and witnesses, no topology, proposals, or connection objects. No new Switch ports,
AccessPoint junctions, head links, Transformer or devices are synthesized. A Switch
with multiple ports is not collapsed. Both physical/conducting reachability are checked;
existing OPEN cuts, cycles, station/voltage conflict, cross-feeder bridges and multiple
heads are diagnosed. Backbone eligibility is an analytical upper bound: source-Line
components with a unique same-case Bus anchor; it does not authorize head attachment.
Unknown placement is reported separately rather than assumed reachable.

The 78 historical INSUFFICIENT_PLACEMENT_EVIDENCE Feeder receive per-endpoint witnesses
and counts. Primary priority: explicit station/voltage conflict, ambiguity, globally
missing, likely partition (same-station compatible reciprocal evidence), otherwise
unique external but ownership unconfirmed. Missing, external, ambiguous and ownership
labels are reported separately and may overlap. No probability scores.

## Artifacts and verification

Write a new nonexisting directory. JSON/JSONL are canonical sorted serialization;
arrays use stable semantic ordering. Manifest binds all consumed source files, inventory,
accepted v2, corrected D4.1, D4, and audit code. Verification checks hashes then rebuilds
index, graph, classifications, impact and summary from authoritative inputs and compares
every byte. Independent hash-seed reproduction must match every file. Protected inputs
and resolver hashes are compared before and after. Unknown metrics are explicit null with
reasons; zero is reserved for a computed zero. No new dependency.

Voltage conflicts derived from head context are reported separately from conflicts
where both sides have direct source voltage fields. Neither licenses connection.
