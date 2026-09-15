# Feeder-level coverage analysis v1

状态：COUNTERFACTUAL ANALYSIS ONLY。扩展 E2.2 观测，不修改 source、accepted topology、
Switch proposal、补全逻辑或参数，不进入 E3。使用已校验的 E1、E2、E2.2 产物。

## 分母与归属

分别统计 source case directories、Feeder 原始行、case-local Feeder identity groups、
published Feeder 和 distinct raw Feeder_ID；跨 case 不合并 ID。
无 Feeder 的 case 单列，不能伪造 Feeder；同时给出包含它们的 case-directory cohort。
同一个 case 恰好一个唯一 Feeder 时，采用 source case directory 作为设备分析范围，
不是声称每台设备已有明确 feeder ownership。多 Feeder/歧义 case 无法分配设备，
feeder 专属 switch_count 为 null，case_scope_switch_count 仍公开，不重复声称独占归属。
所有 Feeder identity groups 均保留原始 ID、name、case、source locators 与可空 canonical ID。

Switch 数量以 case-local identity group 为主，另列 raw rows、published entities、
结构 candidates、known/UNKNOWN NormalState、IsTie normal/tie/unknown_type。
Line、Switch、Transformer 三类 identity groups 为严格范围；malformed/rejected/duplicate
身份证据不得因未发布而从分母消失。计数单位均为个；ratio 六位小数、零分母 null。

## 双重完整性口径

辅助质量口径 `strict_topology_status`：

- FULL：有效 feeder head、至少一条 source-reachable conducting Line；全部源 Line、
  Switch、Transformer identity groups 均唯一、可投影并从 head 可达。
  Line 两端均可达，Switch 两个端口均可达，Transformer MV attachment 节点可达。
  OPEN 不被自动闭合；若两端经别的路径可达，可计为已覆盖设备。
- PARTIAL：有 head-reachable conducting Line，但不满足 FULL。
- FAILED：没有有效 head，或没有 head-reachable conducting Line。

主口径 `transformer_goal_status`：非空源 Transformer target set 全部可达为 FULL，
可达一部分为 PARTIAL，零个可达为 FAILED；没有源 Transformer 时也计 FAILED，
另标 no_transformer_targets，明确失败是缺少目标证据，不将空集合算成功。
所有目标以 source identity groups 计，不只以 projected 子集计。
两种口径分别汇总，不用 1,042 个“至少一个 Transformer 可达”的 case 冒充完整 feeder。
这些指标是拓扑覆盖/后续补全的候选范围，不能宣称 E3 参数、负荷、时序或仿真已完成。

## Policies

复用 E2.2 `build_graph`，保留所有非 Switch 决策及 baseline 已投影对象。

- S0：冻结 SERIES_SWITCH_V1 图。
- SEMANTIC_CONSERVATIVE：保留 S2 结构投影，但新增 semantic UNKNOWN Switch 不导通。
  既有 v1 已确认投影保留；不冒充 S2。
- SEMANTIC_OPTIMISTIC：S2 的 semantic UNKNOWN 允许按已知 NormalState 导通（仅 CLOSED）；
  与当前 S2 相同。未知拓扑语义与未知状态不混淆，不自动闭合已知 OPEN。
- S2：原 E2.2 S2，已允许显式 endpoint semantic UNKNOWN；known NormalState，CLOSED 导通。
- S2_NORMAL_ONLY：S2 新增投影限定 IsTie FALSE（现有 proposal 的普通范围）。
- S2_UNKNOWN_NONCONDUCTING：S3_A，只对满足结构/安全条件的未知状态 Switch 增加
  非导通投影，不自动闭合 OPEN。
- S2_UNKNOWN_CONDUCTING：同上，但未知状态 Switch 在临时图中假设导通，仅为乐观
  敏感性实验；同时处理 baseline 已投影的 UNKNOWN。原始 NormalState 完整保留，
  记录所有被假设导通的 owner IDs，不改变 source 或 accepted rule。

结构不合格、内端不 EXACT、明确安全冲突的 UNKNOWN 不能仅因放宽状态得到投影。
所有政策都保留已知 OPEN。两个 UNKNOWN 含义分开：NormalState UNKNOWN 与 endpoint
semantic UNKNOWN；前者没有结构候选时，放宽它恢复 0 个 feeder 是实测结论。
每 case 重建图并记录 canonical graph SHA256；相同候选/假设集合可共享结果。
S0/S2 的图 SHA256、coverage 与既有 E2.2 case_results 逐 case 核对，否则 fail fast。

## 失败分类与恢复

五类 observation tags：

1. missing_source：没有有效 head，另保留 anchor reason；无 Feeder case 单列。
2. switch_unknown：有未覆盖且可按结构/安全规则投影的 NormalState UNKNOWN，
   或被 SEMANTIC_CONSERVATIVE 阻断的 semantic UNKNOWN。另列非结构候选 UNKNOWN 数，
   不把这些计为单纯放宽状态可修复。
3. tie_unresolved：IsTie TRUE 的源 Switch group 未投影或其端口未完整可达；
   已知 OPEN 的正常隔离也可能落在此 observation 中，不能因此声称 source 有错。
4. topology_disconnected：没有 Line，或存在未完整可达的源 Line/Switch。
5. transformer_unreachable：存在未完整可达的源 Transformer，或没有源 Transformer
   目标（单列 NO_SOURCE_TRANSFORMER_TARGETS subreason，不声称空集合中的设备不可达）。

同一 feeder 可有多个 tags，报告各类重叠 counts，不作为可加根因。为方便总量核对，
另按上述顺序赋予唯一 primary_failure_reason；该优先级仅为统计归类，不声称因果。
PARTIAL 也输出 blocker tags；失败表按主口径，明确区分 FAILED 与全部 not-FULL。
同时汇总 strict/transformer 双状态交叉表、目标完整但严格不完整的数量。

按 S2 失败 primary class 与 overlapping tags，分别计算 UNKNOWN 非导通/假设导通：
主口径 FAILED→FULL、FAILED→PARTIAL、仍 FAILED；对全部 not-FULL 再统计新达到 FULL 的 feeder。
同样统计严格完整性的变化，避免只报主指标收益。
另报告 Transformer goal 的变化及每 feeder 状态转移。所有恢复数来自重建图，
不是“出现一个 UNKNOWN 就可以恢复”的数量猜测。SEMANTIC_CONSERVATIVE→
SEMANTIC_OPTIMISTIC 的拓扑语义放宽收益单独按失败类别输出；当前 S2 已是这一
optimistic policy，不能把此收益当作在 S2 之上的未来增益。

## 输出与验收

独立不可覆盖目录 outputs/nanjing-e2-2/feeder-coverage-v1/：
feeder_coverage.json、failure_analysis.json、policy_recovery.json、feeder_details.jsonl、
case_details.jsonl、feeder_switch_counts.csv、report.md、manifest.json。
CSV 每 Feeder identity group 一行，包含源 ID、scope、switch counts、各 policy 双状态。
manifest 绑定三个输入和全部输出 SHA256/count；没有伪造 source refs。

先测试再实现：完整/部分/失败/空目标、原始分母、未发布身份、无/多 Feeder、OPEN 不变、
两种 UNKNOWN 差异、unknown 状态不能越过结构约束、baseline UNKNOWN、分类重叠、
恢复实际依赖图、确定性/哈希种子、产物隔离及输入不变。无新依赖、无随机采样。
