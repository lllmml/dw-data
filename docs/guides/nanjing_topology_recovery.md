# E2.3-A recovery evidence analysis

This command reads verified E1, E2, switch-projection and feeder-coverage artifacts.
It does not open raw ZIP/CSV, apply candidate rules, or publish ElectricalTopology.
Use an absent, independent output directory; existing output is never overwritten.

```bash
PYTHONHASHSEED=1 .venv/bin/python -m grid_case_generator.analysis.topology_recovery_cli analyze \
  --source outputs/nanjing-e1/source-import-v2 \
  --baseline outputs/nanjing-e2/topology-v2 \
  --projection outputs/nanjing-e2-2/switch-projection-design-v1 \
  --feeder outputs/nanjing-e2-2/feeder-coverage-v1 \
  --output outputs/nanjing-e2-3/topology-recovery-evidence-v1

.venv/bin/python -m grid_case_generator.analysis.topology_recovery_cli verify \
  outputs/nanjing-e2-3/topology-recovery-evidence-v1
```

For full reproduction, run analyze again with PYTHONHASHSEED=999 and a different absent
output directory. Compare every relative file's bytes, including manifest.json and report.md.
The code fingerprint binds the Python source tree; artifact paths, timestamps and Git
commit IDs do not affect serialization. Do not edit source code between the two runs.

Both runs execute existing input verifiers before and after analysis. They validate all
four input bindings and case inventories, reproduce S0/S2 graph hashes and coverage,
and verify the new output. The output verifier reaggregates summary/report from details.
Changing any artifact record without updating its manifest checksum fails verification;
a rehashed false summary still fails detail reaggregation.

## Reading the output

- `summary.json`: populations, exclusive evidence/status cross table, readiness,
  Transformer reference composition, candidate impacts, cumulative policies and overlaps.
- `case_details.jsonl`: all source cases, including no-Feeder cases, Transformer file
  accounting, S0/S2 graphs and independent counterfactual metrics.
- `feeder_details.jsonl`: actual source Feeder groups; NO_SOURCE_TARGET is separate
  from legacy FAILED, and every E3 readiness flag remains false.
- `transformer_evidence.jsonl`: source identity groups, complete incoming/outgoing
  declarations, reference ambiguity and S0/S2 projection/reachability.
- `frontier_blockers.jsonl`: per-branch first unresolved boundary for S0 and S2;
  observed tags overlap and are not causal diagnoses.
- `connection_evidence.jsonl`: accepted v1 branch provenance vs unapproved S2 assumptions.
- `candidate_rule_witnesses.jsonl`: full source witnesses and assumptions for three
  narrow candidates plus the explicitly nonrecommended multi-Line risk experiment.
- `recovery_cohorts.jsonl`: A/B/C/D completion-design flags, constraints and readiness.
- `manifest.json`: source bindings, schema/rule versions, code fingerprint and file digests.

Cohort A never licenses duplicate Transformer generation. Cohort B is ROLE_UNDETERMINED.
Cohort C only licenses review. Cohort D prohibits automatic bridging around constraints.
307's meaning is a necessary evidence upper bound, not predicted FULL. Existing synthetic
MV heads remain modeling assumptions; newly generated synthetic connections remain zero.

After this slice, STOP. Next review concerns E2.3-D Synthetic Topology Completion Contract.
B/C implementation, synthetic topology, E3 and OpenDSS need separate authorization.
