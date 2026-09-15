# Feeder coverage 与 switch policy 敏感性分析

这是 E2.2 的独立只读分析，不改变补全逻辑或 accepted topology。
主指标由用户选择：全部源 Transformer 可达；全部源 Line/Switch/Transformer
可达作为辅助严格质量指标。[完整口径](../spec/feeder_coverage_analysis.md)。

## 全量运行

```bash
uv run --frozen python -m grid_case_generator.analysis.feeder_coverage_cli \
  --source outputs/nanjing-e1/source-import-v2 \
  --baseline outputs/nanjing-e2/topology-v2 \
  --projection outputs/nanjing-e2-2/switch-projection-design-v1 \
  --output outputs/nanjing-e2-2/feeder-coverage-v1
```

输出目录须不存在，并与三个输入分离。程序先完整校验所有输入及 checksum 关联，
然后 typed reload E1/E2、流式读取 E2.2 候选，重建每个 policy 的分析图。
每 case 的 S0/S2 graph SHA256 和覆盖指标必须与已验证 E2.2 产物一致。
输入从校验开始至分析结束期间须保持不变。无 raw ZIP 读取、无新依赖、无随机抽样。

## 先看哪些文件

- `report.md`：主/辅 coverage、失败分类、两种 UNKNOWN 的恢复量与结论。
- `feeder_switch_counts.csv`：每 Feeder identity group 一行，含原始 ID、case、
  Switch group/raw/published/candidate 数与每政策的主/辅状态。
- `feeder_details.jsonl`：每 Feeder 完整明细，包括 NormalState/IsTie 分布、
  每政策 graph hash、Transformer 目标/可达数、失败证据与假设导通的 Switch IDs。
- `case_details.jsonl`：全部 case，包括没有 Feeder 的 case。
- `feeder_coverage.json`：原始分母、每政策 FULL/PARTIAL/FAILED、严格完整性、
  两种完整性差异矩阵；无 Transformer 目标的失败另列计数。
- `failure_analysis.json`：当前 S2 及其他政策的互斥 primary 分组与可重叠 observed tags。
- `policy_recovery.json`：semantic conservative→optimistic 的失败恢复、全部不完整
  feeder 新达到 FULL、严格完整性变化；NormalState 敏感性实验相对 S2 单列。
- `manifest.json`：版本、输入/输出 checksum 与 record counts。

```python
from grid_case_generator.io.feeder_coverage_artifacts import verify_feeder_analysis
verify_feeder_analysis('outputs/nanjing-e2-2/feeder-coverage-v1')
```

## 两种 UNKNOWN 与两种分母

Semantic UNKNOWN 是 Switch 显式端点的拓扑语义未确认；conservative 阻断这些新增
Switch，optimistic 按已知 NormalState 允许 CLOSED 导通。当前 S2 已采用这一
optimistic 解释。NormalState UNKNOWN 是状态本身未知，额外比较非导通投影与
假设导通；不能把前一种放宽的收益再叠加到 S2，或自动闭合已知 OPEN。
未满足结构/安全条件的设备不能因“optimistic”而获得臆造的连接。

真实 Feeder 按源 identity group 计；case directory 是另一个 cohort。没有 Feeder
记录的 case 不伪造 ID。有多个 Feeder 的 case 不断言设备属于哪一条，专属
switch_count 为 null；对应 case_scope_switch_count 仍可用于源数据审计。

FULL 是当前拓扑规则下的目标覆盖计数；最终 E3 参数、负荷、时序、OpenDSS readiness
尚须后续规范和实现。全部源 Transformer 可达但严格完整性未通过的 feeder 必须
保留其未覆盖源设备证据，不能悄悄删除资产或声称已经完整补全。
