# D3 deterministic recovery and accepted topology v2

D3 reviews source evidence under the [D3 contract](../spec/nanjing_deterministic_topology_recovery.md).
It publishes a new immutable accepted overlay; the historical `topology-v2` directory
contains **v1 rules** and remains an input. S2 as a whole remains unaccepted. No new
synthetic proposal, junction, device, LV bus, E3 parameter or simulation is produced.

```bash
PYTHONHASHSEED=1 .venv/bin/python -u -m grid_case_generator.analysis.deterministic_recovery_cli analyze \
  --source outputs/nanjing-e1/source-import-v2 \
  --baseline outputs/nanjing-e2/topology-v2 \
  --projection outputs/nanjing-e2-2/switch-projection-design-v1 \
  --feeder outputs/nanjing-e2-2/feeder-coverage-v1 \
  --recovery outputs/nanjing-e2-3/topology-recovery-evidence-v1 \
  --d1 outputs/nanjing-e2-3/synthetic-completion-contract-v1 \
  --d2 outputs/nanjing-e2-3/synthetic-topology-proposals-v1 \
  --frozen outputs/nanjing-e2/topology-v1 \
  --output outputs/nanjing-e2-3/deterministic-topology-recovery-v1 \
  --accepted-output outputs/nanjing-e2-3/accepted-topology-v2
```

Both output directories must be new and disjoint from every input, one another and
`data/raw`. Do not delete a formal artifact to reuse its name. Development runs without
a manifest are incomplete and cannot be consumed as accepted results.

For independent reproduction, use `PYTHONHASHSEED=999` and append `-reproduction` to
both output directory names. Compare every file including both manifests. All eight
input verifiers/bindings run before and after an analysis, and output replay rebuilds
all decisions, topology, coverage, eligibility, summaries and report from case evidence.

For authoritative verification, use the same command and roots with `verify` in place
of `analyze` (the hash seed is immaterial). The CLI requires every root. It reconstructs
case evidence from the verified source/E2/D2 inputs and then replays all output streams.
The Python `verify_artifacts(analysis, accepted)` API without input roots only verifies
internal consistency; it does not certify the source truth of a replaced case snapshot.

Analysis files:

- `case_inputs.jsonl`: unchanged compact S0 base, raw row accountability, source Terminals,
  original topology and projections, all case-bound and input-hash-bound.
- `rule_review.jsonl`: formal rule acceptance and evidence/safety contract; broad S2,
  tie/reverse/unknown interpretations and Transformer port collapse are separately reviewed.
- `candidate_connections.jsonl`: all Switch/AccessPoint identity groups and referenced
  Transformer groups, with raw evidence, state, conflict refs, status and rule variant.
- `accepted_connections.jsonl`: only the newly accepted deterministic **edges**.
- `rejected_connections.jsonl`: rejected and still-unresolved candidate interpretations;
  these are not automatically real physical branches that were removed.
- `feeder_recovery.jsonl`: all Feeders, original D2 primary, taxonomy, overlapping families,
  candidate IDs/counts and before/after metrics. Filter original D2 primary to obtain 1,383.
- `case_coverage.jsonl`: all cases, physical/conducting before/after and single-family deltas.
- `d2_eligibility.jsonl`: independently evaluated before/after; no proposal is instantiated.
- `summary.json`, `rule_summary.json`, `coverage_impact.json`, `d2_reclassification.json`,
  `report.md`, `manifest.json`: detail-derived aggregates and input/output bindings.

Accepted artifact is separate:

- `case_topologies.jsonl`: materialized S0 + deterministic additions, one case per row.
- `additions.jsonl`: new derived ports and edges with RULE_INFERRED evidence and rule/source
  provenance. Existing source devices are referenced, never copied as generated devices.
- `manifest.json`: source/v1/E2.2/D2 and analysis bindings, file counts and SHA256.

Every OPEN branch exists in the physical graph but is excluded from the conducting
graph. A leaf Switch's remote port is UNBOUND and supplies no attachment region. D2
regions remain existing reachable accepted Bus junctions; a reachable Line ending at
an unbound Switch port does not by itself make a Transformer proposal eligible.

Coverage denominators: target status and topology-status histograms count the 5,134
source Feeders; graph metrics sum all 5,159 cases. `topology_coverage` is explicitly
scoped to source Line/Switch/Transformer groups, not a claim that AccessPoint, business
roles, remote leaf connections, E3 or all source entity semantics are complete.
`active_edge_count` uses only conducting edges in that view, and verifies m-n+c.
Single-family deltas are independent experiments on S0 and are not additive in general.

`missing_backbone_or_region_count` is comparable to D2's 87,293 combined rejection
metric. `missing_backbone_count` and `missing_region_count` separately expose each reason;
their overlap must not be summed. Synthetic candidate count means eligible existing
Transformer targets, not newly instantiated RULE_GENERATED objects (D3 creates zero).

Stop after D3 delivery review. Broader Switch semantics, synthetic backbone/layout,
zero-Transformer device generation and E3/OpenDSS each require separate authorization.
