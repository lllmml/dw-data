#!/usr/bin/env bash
# Build the v1 completion export from the published D-series artifacts.
#
#   bash scripts/run_completion_export.sh [OUTPUT_ROOT]
#
# Thirteen verified upstream roots are required: the completion rules decide from
# persisted evidence and none of it is derivable from the source archive alone.
# The two outputs must not exist; both are write-once and the run self-verifies.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-outputs/nanjing-v1}"
exec python -u -m grid_case_generator.analysis.completion_export_cli analyze \
  --source outputs/nanjing-e1/source-import-v2 \
  --baseline outputs/nanjing-e2/topology-v1 \
  --projection outputs/nanjing-e2-2/switch-projection-design-v1 \
  --feeder outputs/nanjing-e2-2/feeder-coverage-v1 \
  --recovery outputs/nanjing-e2-3/topology-recovery-evidence-v1 \
  --d1 outputs/nanjing-e2-3/synthetic-completion-contract-v1 \
  --d2 outputs/nanjing-e2-3/synthetic-topology-proposals-v1 \
  --frozen outputs/nanjing-e2/topology-v1 \
  --d3-analysis outputs/nanjing-e2-3/deterministic-topology-recovery-v1 \
  --accepted-v2 outputs/nanjing-e2-3/accepted-topology-v2 \
  --d4 outputs/nanjing-e2-3/synthetic-backbone-proposals-v1 \
  --placement outputs/nanjing-e2-3/placement-evidence-v1-1 \
  --audit outputs/nanjing-e2-3/case-boundary-audit-v1 \
  --policy configs/nanjing_completion_policy_v1.json \
  --ledger "$OUT/completion-ledger-v1" \
  --output "$OUT/derived-delivery-v1"
