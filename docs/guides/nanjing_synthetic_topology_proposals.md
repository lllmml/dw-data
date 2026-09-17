# E2.3-D2 proposal-only workflow

D2 reads six verified artifacts and a bound business policy. It generates engineering
proposals, validation and counterfactual coverage. It has no apply command.
The official policy remains unconfirmed: no default new Transformer or LV voltage.

```bash
PYTHONHASHSEED=1 .venv/bin/python -m grid_case_generator.analysis.proposal_cli analyze \
  --source outputs/nanjing-e1/source-import-v2 \
  --baseline outputs/nanjing-e2/topology-v2 \
  --projection outputs/nanjing-e2-2/switch-projection-design-v1 \
  --feeder outputs/nanjing-e2-2/feeder-coverage-v1 \
  --recovery outputs/nanjing-e2-3/topology-recovery-evidence-v1 \
  --d1 outputs/nanjing-e2-3/synthetic-completion-contract-v1 \
  --decisions configs/nanjing_completion_decisions_v1.json \
  --output outputs/nanjing-e2-3/synthetic-topology-proposals-v1
```

The output directory must not exist and cannot overlap any input. For independent
reproduction run with `PYTHONHASHSEED=999` and a separate `-reproduction` directory.
Compare every artifact file, including the manifest. Outputs are local generated
artifacts and are not tracked in Git.

```bash
.venv/bin/python -m grid_case_generator.analysis.proposal_cli verify \
  --output outputs/nanjing-e2-3/synthetic-topology-proposals-v1 \
  --source outputs/nanjing-e1/source-import-v2 \
  --baseline outputs/nanjing-e2/topology-v2 \
  --projection outputs/nanjing-e2-2/switch-projection-design-v1 \
  --feeder outputs/nanjing-e2-2/feeder-coverage-v1 \
  --recovery outputs/nanjing-e2-3/topology-recovery-evidence-v1 \
  --d1 outputs/nanjing-e2-3/synthetic-completion-contract-v1
```

Bound verification rebuilds input facts from all six verified artifacts, then rebuilds
bundles and both graph views, validates the proposals and checks all detail, summary
and report bytes. Omitting all six roots checks internal consistency only; it cannot
establish that input facts match authoritative artifacts. Partial root sets fail.

`business_confirmation_template.json` lists every source Feeder with UNKNOWN/null/false
values. A separately reviewed decision file must preserve the source/D1 manifest binding,
provide a confirmation reference, and satisfy the
[business contract](../spec/nanjing_synthetic_topology_proposals.md). It is derived policy,
never a replacement for source CSV evidence. New Transformer permission also requires an
explicit count, demand basis and MV/LV plan. Permission alone does not define backbone layout.

Inspect `feeder_eligibility.jsonl` and `blocker_reclassification.jsonl` for separate hard
contradictions, preserved operating states and modeling gaps. Inspect `proposal_bundles.jsonl`
for lifecycle, source/business provenance and assumptions; `proposal_validation.jsonl`
records structural checks without asserting electrical adequacy. `case_coverage.jsonl`
contains physical and conducting before/after graph metrics. All after values are
`PROPOSAL_ONLY_COUNTERFACTUAL`; accepted S0 and unaccepted S2 retain their prior status.

Stop at D2 delivery review. APPROVED/APPLIED, E3, OpenDSS and QSTS require later explicit authorization.
