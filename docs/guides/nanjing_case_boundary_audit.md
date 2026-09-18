# D4.2 read-only case boundary audit

Contract: [case boundary audit](../spec/nanjing_case_boundary_audit.md).
This command does not change the case-local resolver or emit topology/proposals.

```bash
PYTHONHASHSEED=1 .venv/bin/python -u -m grid_case_generator.analysis.case_boundary_audit_cli analyze \
  --source outputs/nanjing-e1/source-import-v2 \
  --accepted outputs/nanjing-e2-3/accepted-topology-v2 \
  --d3 outputs/nanjing-e2-3/deterministic-topology-recovery-v1 \
  --d4 outputs/nanjing-e2-3/synthetic-backbone-proposals-v1 \
  --placement outputs/nanjing-e2-3/placement-evidence-v1-1 \
  --output outputs/nanjing-e2-3/case-boundary-audit-v1
```

Use `verify` with the same roots for a full source-bound rebuild and byte comparison.
Use `PYTHONHASHSEED=999` and a new `-reproduction` output for independent reproduction.
The destination must not exist; protected input roots cannot be output ancestors or
subdirectories. No new dependency is needed.

`cross_case_references.jsonl` accounts for all nonempty, non-EXACT field occurrences,
including globally undefined and local-only unresolved observations. Its
`external_candidate_count > 0` subset is the cross-case reference total. Classification
labels overlap; primary classifications do not. Candidate counts and reference counts
are distinguished in the summary. Ratio objects carry numerator and denominator;
the decimal ratio is text, and an empty denominator produces null.

`global_reference_index.jsonl` retains every raw definition with a namespaced analysis
ID. The ID identifies an observation; it is not a Canonical ID. `case_reference_edges`
contains all candidate directions, including ambiguity. `case_reference_components`
contains WEAK and STRONG components separately, including isolated inventory cases.
Reciprocal directory references do not prove a reciprocal electrical circuit.

`counterfactual_resolution.jsonl` distinguishes identity matches, unconfirmed ownership,
and existing accepted Bus anchors. `counterfactual_impact.json` reports identity-complete
Line upper bounds separately from calculable placement on existing accepted nodes.
Unrepresented/multi-port foreign entities remain unassessed placement, not recovered
Lines. Reachability uses each object's own Case head and reports physical/conducting
results. No head attachment is invented. `target_78_feeders.jsonl` links every affected
raw endpoint to its candidate details and reports both bounds.

All counterfactual numbers are ANALYSIS_ONLY_CROSS_CASE_COUNTERFACTUAL. No-source-Line
Feeder are counted only. Q-CASE-001 remains OPEN; approval, merger and cross-case follow
need a separate business decision and a separately authorized implementation slice.
