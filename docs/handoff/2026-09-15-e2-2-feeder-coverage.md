# E2.2 — Feeder-level coverage analysis

**COUNTERFACTUAL ANALYSIS ONLY。补全逻辑、accepted topology 和 Switch proposal 保持不变。**

## 结论

在用户选定的主口径“全部源 Transformer 可达”下，当前 S2 为：
**80 完整 / 962 部分 / 4092 失败 feeder**，
分母为 **5134 条真实源 Feeder identity groups**。
原 E2.2 的 1,042 个可达 case 是 FULL+PARTIAL，不能当作 1,042 条完整 feeder。

Semantic conservative→optimistic 使 80 条失败 feeder 达到主 FULL、
958 条失败 feeder 达到 PARTIAL；新 FULL 总计 80。
当前 S2 已等同 semantic optimistic，因此这是相对 conservative 的收益，不是 S2
之上的增益。NormalState UNKNOWN 的非导通/假设导通实验另列，未自动闭合已知 OPEN。

这回答的是**本轮 switch policies、冻结的非 Switch 规则下，多少 feeder 的全部源
Transformer 可以到达**；尚不能据此宣称参数/负荷/时序补全或 OpenDSS 已成功。
辅助严格质量指标要求所有源 Line/Switch/Transformer 都唯一且可达，不用于替代主指标。

## 原始分母与逐 feeder Switch 数量

- Feeder 原始行 = identity groups = published = distinct raw IDs = 5134。
- 原始 source case directories = 5159，其中 25 个没有 Feeder。
  后者在 case cohort 单列，不伪造 Feeder，不计入 5134 的分母。
- 本批一条 Feeder 对应一个 source case，case directory 是设备分析范围；没有假装
  所有 source entities 都有已确认的 feeder ownership。
- 全数据 Switch identity groups 271461；有 Feeder 的 case 内
  271406，无 Feeder case 内 55。
- 每条 Feeder 的 switch_count、raw rows、published/candidate 数、两种 UNKNOWN、
  NormalState/IsTie 分布及每政策状态均已输出，未只给 Transformer/case 总计。
- 直接查看 `outputs/nanjing-e2-2/feeder-coverage-v1/feeder_switch_counts.csv`；
  完整证据位于同目录 `feeder_details.jsonl`，case 层明细含无 Feeder 的 25 个 case。

## Coverage 与两种完整性的差异

| Policy | 主 FULL | 主 PARTIAL | 主 FAILED | 严格 FULL | 主 FULL 但严格未完整 |
|---|---:|---:|---:|---:|---:|
| SEMANTIC_CONSERVATIVE | 0 | 4 | 5130 | 0 | 0 |
| SEMANTIC_OPTIMISTIC | 80 | 962 | 4092 | 0 | 80 |
| S2_NORMAL_ONLY | 78 | 964 | 4092 | 0 | 78 |
| S2_UNKNOWN_NONCONDUCTING | 80 | 962 | 4092 | 0 | 80 |
| S2_UNKNOWN_CONDUCTING | 80 | 962 | 4092 | 0 | 80 |

S2 的主完整率为 0.015582（ratio，分母 5134）；
没有源 Transformer 目标的 feeder 为 1713，单列为失败中的
NO_SOURCE_TRANSFORMER_TARGETS，避免空集合虚增 FULL。
普通 Switch 范围的完整 feeder 比全类别 S2 少
2 条；这是 feeder 完整性差，
不能用“reachable cases 没下降”来掩盖。各政策的严格 FULL/PARTIAL/FAILED 与双状态
交叉表都在 feeder_coverage.json 中。

## 失败分类与恢复

主分类按 missing_source→switch_unknown→tie_unresolved→topology_disconnected→
transformer_unreachable 的顺序进行互斥归类，仅为统计归类，不声称已证明根因。
Observed tags 可以重叠；例如未覆盖 Tie 可能是已知 OPEN 的正常隔离，也可能是
不满足投影条件。必须结合该 feeder 的 blocker_evidence，不把存在当作可恢复证明。

以下 S2 列以**当前 S2 的 FAILED feeder**为 cohort；semantic 列以**conservative
的 FAILED feeder**为 cohort。恢复数通过实际图重建计算，不能混用分母。

| 类别 | S2 主分类失败 | S2 重叠 tag | conservative 主分类失败 | semantic 放宽→FULL | semantic 放宽→PARTIAL | 相对 S2 放宽状态→FULL/PARTIAL |
|---|---:|---:|---:|---:|---:|---:|
| missing_source | 0 | 0 | 0 | 0 | 0 | 0 / 0 |
| switch_unknown | 0 | 0 | 2919 | 80 | 958 | 0 / 0 |
| tie_unresolved | 2357 | 2357 | 1203 | 0 | 0 | 0 / 0 |
| topology_disconnected | 1735 | 4092 | 1008 | 0 | 0 | 0 / 0 |
| transformer_unreachable | 0 | 4092 | 0 | 0 | 0 | 0 / 0 |

完整 failed / not_full、primary / overlapping 分类与恢复见 failure_analysis.json /
policy_recovery.json。逐 feeder 保留 raw IDs、source locators、假设导通 owner IDs、
未覆盖目标数及 anchor reason。缺少 Feeder 的 25 个 case 在 case_details 单列。

## 两种 UNKNOWN 的边界

- **拓扑语义 UNKNOWN**：对有合法结构与 EXACT inner references 的 S2 候选，
  conservative 保留结构但阻断导通；optimistic 允许按原 NormalState 导通（仅 CLOSED）。
  当前 S2 已允许它，不能再叠加一次这部分收益。
- **NormalState UNKNOWN**：另做非导通投影 / 假设导通的乐观敏感性实验。本批满足
  结构与安全条件的未知状态候选为 0；不能让其他不满足结构
  条件的 Switch 因“unknown”获得臆造的连接。
- 两种实验都没有闭合已知 OPEN，没有改 SourceReference/Terminal/raw/E2.2 输出，
  没有更改 accepted contract 或普通 Switch proposal。

## 验证与复现

- 代码输入基线：`df8795db5fbd89afefad4bdae1fd9d26d6dfbbf8`。
- `.venv/bin/python -m pytest`：**326 passed**（303 原有 + 23 本次）。
- `.venv/bin/python -m compileall -q src tests`、`git diff --check`：通过。
- 测试覆盖主/辅完整性、原始分母、无/多 Feeder、空目标、源身份不唯一、known OPEN、
  semantic UNKNOWN 与 state UNKNOWN、非结构候选不得越权、失败分类与实际恢复、
  原输入不变、CSV 引号/换行、checksum tamper、输出隔离。
- 三次 fixture 写出（PYTHONHASHSEED=1/999/1_repeat）全部产物字节一致；source
  records/accounting 顺序反转仍得到相同完整结果。无 random sampling，无新依赖。
- 全量 5159 case 的 S0/S2 graph SHA256 与 coverage 均与原 E2.2 逐项相同。
- 全部报告从 case 明细重新汇总，逐字节相同；CSV 与每个 feeder_details 逐条核对。
- 运行后完整 verify E1、E2、E2.2；输入 manifest SHA256 不变。
- 输出 manifest SHA256：`fd3c1f0bff34afa203f202148060941822198548669aa3f3594b16fbdca72a48`。
- 验证摘要：`outputs/nanjing-e2-2/feeder-coverage-v1-verification.json`。
- [分析规范](../spec/feeder_coverage_analysis.md)、[复现指南](../guides/nanjing_feeder_coverage.md)。

正式 artifact：`outputs/nanjing-e2-2/feeder-coverage-v1/`。到此停止，没有进入 E3。
