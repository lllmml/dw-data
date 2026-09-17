# E2.3-D1 contract / cohort analysis

D1 reads five verified artifacts, writes eligibility/evidence only, and has no apply
command. The [formal contract](../spec/nanjing_synthetic_topology_completion.md) freezes
cohort priority, prohibitions, operations, readiness and the future candidate lifecycle.

```bash
uv run --frozen python -m grid_case_generator.analysis.completion_cli analyze \
  --source outputs/nanjing-e1/source-import-v2 \
  --baseline outputs/nanjing-e2/topology-v2 \
  --projection outputs/nanjing-e2-2/switch-projection-design-v1 \
  --feeder outputs/nanjing-e2-2/feeder-coverage-v1 \
  --recovery outputs/nanjing-e2-3/topology-recovery-evidence-v1 \
  --output outputs/nanjing-e2-3/synthetic-completion-contract-v1
```

Output must be new and separate from every input and raw. Existing output is rejected.
No seed, force_complete, approval override, S2 acceptance or object generator is exposed.

Verify checksums, canonical bytes, closed profile schema, stream decisions and aggregates:

```bash
uv run --frozen python -m grid_case_generator.analysis.completion_cli verify \
  outputs/nanjing-e2-3/synthetic-completion-contract-v1
```

For acceptance, also bind to authoritative inputs and independently reproduce profiles:

```bash
uv run --frozen python -m grid_case_generator.analysis.completion_cli verify \
  outputs/nanjing-e2-3/synthetic-completion-contract-v1 \
  --source outputs/nanjing-e1/source-import-v2 \
  --baseline outputs/nanjing-e2/topology-v2 \
  --projection outputs/nanjing-e2-2/switch-projection-design-v1 \
  --feeder outputs/nanjing-e2-2/feeder-coverage-v1 \
  --recovery outputs/nanjing-e2-3/topology-recovery-evidence-v1
```

Without input roots, verifier establishes internal consistency only, not the truth of
copied source facts. With roots, changed/rehashed profiles fail input reconstruction.
Five input verifiers run before/after analysis. Use a distinct output path and different
PYTHONHASHSEED for independent byte reproduction; seed is a test environment variable,
not a generation configuration.

`case_profiles.jsonl` retains every case including 25 without Feeders. Join all detail
streams by case_id/feeder_id/case_profile_ref. Primary action is mutually exclusive;
original A/B/C/D and all operation-specific rejection reasons remain independent.
`prohibitions.jsonl` includes both explicit source constraints and unmet preconditions;
its union is not a count of erroneous source data. Whole-case OPEN and closed earthing
switch declarations are conservative vetoes; the latter does not prove the source
EarthingSwitch_Bus location or modify its state.

`ALREADY_TARGET_COMPLETE` means accepted S0 target coverage only. Unaccepted S2 FULL
never receives that primary class. B role distributions use all 1,713 B Feeders, even
when blocked takes primary precedence. The 13/113/93 historical feasibility numbers
are retained as counterfactual evidence, never permission or a completion promise.

D review's prototype is archived under docs/analysis; formal D1 recomputes from verified
inputs and never copies prototype JSON. Only the directory with a verified manifest is
the formal D1 result. `*-initial-audit` is a development analysis, not the delivery.
STOP after review: D2, synthetic topology implementation, E3 and OpenDSS remain unauthorized.
