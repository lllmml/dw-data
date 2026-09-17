# D4 synthetic backbone proposal-only generation

Contract: [D4 specification](../spec/nanjing_synthetic_backbone.md).
Accepted v2 is the deterministic base. Nothing in this command approves or applies
proposals. Formal output is separate from source, historical artifacts and accepted v2.
Runtime is stdlib; no new dependencies or lockfile changes.

```bash
PYTHONHASHSEED=1 .venv/bin/python -u -m grid_case_generator.analysis.synthetic_backbone_cli analyze \
  --source outputs/nanjing-e1/source-import-v2 \
  --baseline outputs/nanjing-e2/topology-v2 \
  --projection outputs/nanjing-e2-2/switch-projection-design-v1 \
  --feeder outputs/nanjing-e2-2/feeder-coverage-v1 \
  --recovery outputs/nanjing-e2-3/topology-recovery-evidence-v1 \
  --d1 outputs/nanjing-e2-3/synthetic-completion-contract-v1 \
  --d2 outputs/nanjing-e2-3/synthetic-topology-proposals-v1 \
  --frozen outputs/nanjing-e2/topology-v1 \
  --analysis outputs/nanjing-e2-3/deterministic-topology-recovery-v1 \
  --accepted outputs/nanjing-e2-3/accepted-topology-v2 \
  --output outputs/nanjing-e2-3/synthetic-backbone-proposals-v1
```

Output must not exist. Verification uses `verify` in place of `analyze`, all the same
roots, and requires the existing output. Both commands verify the authoritative D3
chain, compare source and accepted case evidence, replay the D4 detail streams and
summaries, and independently compare counterfactual eligibility with the original D2
engine. D2's temporary objects used for that check are discarded; D4 publishes no
attachment or device proposal. The Python `verify_artifact(output)` API alone checks
internal replay; only the CLI/full authoritative case iterator certifies source truth.
A saved `input_bound` result is not a substitute for rechecking changed inputs.

For independent reproduction, use `PYTHONHASHSEED=999` and a new output directory
ending in `-reproduction`. Compare all 16 files including the manifest. No timestamps,
GIS, random seeds for topology or sorting-based anchor selection are used. Hash seed
only tests independence from Python hash iteration.

The 1,402 D3 backbone-required cohort is identified in every Feeder taxonomy record.
The overall proposal run also evaluates other source Feeders, including zero-target
Feeders with existing Line structure. Overall and cohort counts must not be confused.
Gap tags overlap and must not be summed. `taxonomy_primary` is a display priority,
not a statement of causation or automatic recoverability.

All coverage is PROPOSAL_ONLY_COUNTERFACTUAL. `accepted_physical_backbone` in the
reused D2 output means the evaluator's backbone predicate on its input graph; in the
`after` column this is the proposal graph, **not accepted topology**. Source-target
status counts source Feeders (5,134); graph counts include all 5,159 cases. Existing
Transformer reachability measures physical/conducting representation, not electrical
adequacy. NO_SOURCE_TARGET stays unchanged even if a backbone is proposed.

Files contain case snapshots, gap/component witnesses, all engineering anchors,
candidate edges, bundles, edges, empty junction stream, rejections, independent
validation, before/after coverage, recomputed D2 eligibility, engineering metrics,
summary, report and SHA256 manifest. All generation IDs are separate RULE_GENERATED
identities. The accepted graph, raw endpoints and historical D2 objects are unchanged.

Rules 2–4 (component bridges, unbound extensions, intermediate junctions) remain
reviewed but disabled in version 1 because their unique placement contract is not
established. Review their recorded source evidence before introducing another rule
version. D4 does not expand deterministic Switch semantics or accept S2 as a whole.

STOP after delivery review. Approval/apply, zero-Transformer device generation,
Load/DER, E3, OpenDSS and QSTS need separate authorization.
