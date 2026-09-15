# E2.2 Switch Projection Design

只读数据实验，状态 **PROPOSED / NOT ACCEPTED / NOT IMPLEMENTED**。
分析规范见 [switch_projection_analysis.md](../spec/switch_projection_analysis.md)。

## 运行

使用现有锁定环境，无新增依赖，无 random sampling：

```bash
uv run --frozen python -m grid_case_generator.analysis.switch_projection_cli \
  --source outputs/nanjing-e1/source-import-v2 \
  --baseline outputs/nanjing-e2/topology-v2 \
  --output outputs/nanjing-e2-2/switch-projection-design-v1
```

输出必须不存在，与所有输入目录分离；重复实验使用新目录。
先完整 checksum 校验 E1/E2 及 manifest 关联、case inventory，然后逐 case typed
reload。E2.1 的候选识别代码从 E1 重建全部 motif，不读取 raw ZIP，不改 resolver。
E1/E2 输入在验证至运行结束期间须保持不变。程序每 100 cases 报告进度。

## 产物

- `strategy_comparison.json`：输入 manifest SHA256、语义三分类、结构排除、相对 S0 的 coverage 差值。
- `coverage_by_strategy.json`：S0/S1/S2/S3_A/S3_B 的完整覆盖率及 published Transformer 分母。
- `risk_analysis.json`：结构与导通 multigraph 的 cycle basis、degree、unsupported、source-region 指标与 witness。
- `tie_switch_analysis.json`：normal/tie/unknown_type × NormalState、仅该组/移除该组的独立图覆盖实验。
- `representative_examples.json`：每策略/类别按 `(case_id, switch_id)` 取前三个；无实例则空数组。
- `candidate_decisions.jsonl`：每个候选的全部 source endpoint 证据、安全判定和每策略 decision。
- `case_results.jsonl`：每 case 的策略指标、风险、分组实验与 deterministic graph SHA256。
- `proposal.md`：从实测统计生成的 review-only 提案，待审版本同步至 docs/decisions。
- `manifest.json`：版本、状态、输入/输出 SHA256、record counts。

图 SHA256 对 sorted nodes/edge-ID multigraph 的 canonical JSON 计算。
Line 按 source owner 去重，平行 Line 仍是不同边；没有额外依赖或全局 mutable state。
UNKNOWN Option A/B 不通过默认闭合来比较；任何策略仅 CLOSED 导通。
S1/S2 已要求 known state，S3_B 等于 S2 是有意的控制结果。

## 验证

```python
from grid_case_generator.io.switch_projection_artifacts import verify_projection_analysis
verify_projection_analysis('outputs/nanjing-e2-2/switch-projection-design-v1')
```

```bash
uv run --frozen python -m pytest
uv run --frozen python -m compileall -q src tests
```

不要将 coverage 提升解释为 source 语义已确认或 OpenDSS Ready。环不自动删除，
高 degree 不自动修复；EXACT source region 也不是已确认的全局 feeder ownership。
本阶段不发布 V2 topology，不进入 E3。
