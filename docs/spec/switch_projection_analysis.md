# E2.2 Switch projection design analysis v1

本规范只授权只读实验。候选规则状态：**PROPOSED / NOT ACCEPTED / NOT IMPLEMENTED**。
不修改 accepted topology contract、E1 或 E2，不进入 E3。

## 输入、身份及策略

读取完整校验的 E1 与 E2 topology-v2，并校验 manifest 关联及全量 case inventory。
复用 E2.1 SourceMotifIndex / investigate_case 重建候选及原始 A/B/X/Y 证据。
候选要求 UNIQUE Switch、恰好两条 UNIQUE 已发布 Line、一入一出、内端 EXACT、
完整 incidence；不补 ID、不重写引用。非 Switch 投影完全沿用 E2。
所有 case（含 canonical-invalid、无 Line、无 head）纳入分母。

- S0：原 SERIES_SWITCH_V1 图，重算指标并核对持久化 coverage。
- S1：结构候选且 NormalState 为 CLOSED/OPEN，显式端点仅作诊断。
- S2：S1 加明确同侧电压冲突过滤。对应 A/X 或 B/Y 都是 source EXACT、UNIQUE
  BUS，且两者有有限正电压、不满足 E2 电压容差时，标记 CONFLICTING。
  这是“同侧无变压器的 Bus 电压域不能相同”的安全否决证据；不是任意 ID 不等。
  直接/反向一致或已证明 Bus–Station membership 是 COMPATIBLE；其他 UNKNOWN。
  不以 source graph 距离、未解析、缺失、歧义或不同 Bus ID 证明电气冲突。
  反向完整兼容优先，避免未经确认的方向解释导致误拒绝。
- S3_A：S2 的结构与安全条件，UNKNOWN 也投影但不导通。
- S3_B：UNKNOWN 排除，因此与 S2 相同。

所有实验仅 CLOSED 导通；OPEN 始终保留结构边、阻断 reachability。
S1/S2 已要求 known state，故它们与 S3_B 的电气结果本应相同；不能为了制造
对比而闭合 OPEN。S3_A 额外 UNKNOWN 端口可能让邻接 Line 成为可达末端，须重算图。
原 baseline 已投影 Switch 在各策略保持；新增策略条件仅控制新增投影。

## 分析图契约

临时图是 multigraph，节点含 baseline 全部节点与新增 Switch 两个端口；边包含
baseline 全部边及新 Switch 和新获得完整端点的 Line。按 source entity ID 去重 Line。
分析端口/边使用 `analysis-only:` namespace，不生成 ElectricalTopology 或 accepted artifact。
每条分析边记录 id、两个 node ID、kind、conducting、source owner；source IDs 原样保留。
图摘要 sha256 对节点与边排序后的 canonical JSON 计算；case、Switch 示例按
(case_id, switch_id) 排序，每策略全部/接受/排除/OPEN/UNKNOWN/冲突各取前三个。
无真实示例时输出空列表，不人为构造或抽样。

## Coverage 与分组

每策略统计 projected/conducting/excluded Switch（分母为 source identity groups）、
head cases、usable subgraph cases、reachable Transformers、reachable Transformer cases。
ratio 分母为全部 published Transformers，六位小数；零分母为 null，计数单位均为个。
每 case 输出图摘要及 coverage；S0 与持久化报告逐项一致，否则失败。
IsTie FALSE/TRUE/null 分为 normal/tie/unknown_type，再按 CLOSED/OPEN/UNKNOWN 分层。
每类报告 candidate、projection 及两种图实验：仅添加该类、移除该类；报告相对 S0
和完整策略的 reachability 差，不把非可加的组贡献强行相加。

## 风险（只报告，不自动修复）

结构图与 conducting 图分别检查：

- 以 source Line/branch ID 为边身份，先处理 baseline，再按边 ID 插入新增边，
  确定性 spanning forest 的非树边给出 fundamental cycle basis。new cycles 为新增
  边闭环数；cycle size 为边数（含 Switch 内边），self-loop=1、parallel edges=2。
  报告总数、大小分布、与 head 不连通的新环数及确定性 witness。
  不是所有 simple cycles 的枚举，也不能据此认定实际错误。
- 所有节点 degree 分布及按角色分布；Switch 端口预期 <=2，Transformer <=1，
  Bus/head >4 仅为审查阈值，没有已确认的硬性上限。
- unsupported_path_count：分析图中实际连接到 unsupported source entity 的边数；
  另报告 candidate 外端指向 AccessPoint/Disconnector/EarthingSwitch 等的 blocked
  path evidence 数。计数是候选侧路径证据，不枚举无穷 walk。保留证据 refs。
- cross_feeder_projection_count：新增 conducting Switch 两端去除此边后连接不同
  已知 feeder source regions 的数量。region 仅取 E1 EXACT Feeder_SourceBus 的 Bus
  原始 ID，在各 case 内按 EXACT Bus ID 查找，synthetic head 携带其 Feeder_SourceBus。
  region 标签为 case_id + feeder_id；不把 Station 当 feeder，也不合并 case。
  外部 case 的相同 Bus ID 只是 potential contact，不证明 ownership 或真实跨馈线。
  同 Bus 多 Feeder 为共享/歧义 region，单列；记录 assessed、无可映射 region 的 case。
  另外报告新增 source-reachable foreign region contacts。0 不证明无跨 feeder 风险，
  source region 不完整且没有已确认全局设备身份或 feeder ownership。

所有风险保留 S0 数量、每策略总量与新增量。没有观测依据时说明 NOT ASSESSABLE，
禁止以空图/隔离 GridCase 得出真实电网无风险。

## Artifact 与验收

输出独立且不存在的目录，禁止与任何输入重叠或写入 data/raw。
strategy_comparison.json、coverage_by_strategy.json、risk_analysis.json、
tie_switch_analysis.json、representative_examples.json、proposal.md，另含
case_results.jsonl、candidate_decisions.jsonl 和绑定输入/输出 checksum 的 manifest。
所有结果明确 counterfactual；proposal.md 与 docs/decisions 的提案相同。
测试先于实现：正反策略、状态、电压证据、非 Switch 排除、平行边/环/degree/
unsupported/region、输入不变、顺序不变、重复运行、PYTHONHASHSEED=1/999
产物字节一致，以及完整 E1→E2→E2.2 验证。无新依赖、无 random sampling。
