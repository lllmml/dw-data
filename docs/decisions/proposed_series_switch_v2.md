# SERIES_SWITCH_V2：完整 EXACT DIRECT 声明子集

**PROPOSED / NOT ACCEPTED / NOT IMPLEMENTED**

本文件仅供 review，不修改 accepted v1 contract 或任何 E2 topology artifact。
基线为 `6019befa35579b4a08f51bac8c1d9d0989999bc8`。
证据与复现见 [E2.1 调查报告](../handoff/2026-09-15-e2-1-switch-semantics.md)。

## Evidence

从 verified E1 重建 60,960 个 UNIQUE、一入一出候选。111 个字面 DIRECT 中只有
80 个（60 cases）具备完整 EXACT 引用，其余 30 个 unresolved、1 个 ambiguous。
这 80 个同时声明 X=A、Y=B，是兼容且重复的端点证据，足以提出窄的模型规则供审查。
未发现完整 reverse-compatible 实例，也未发现满足严格 membership 判据的不同层级子集。
因此不提议全局忽略 Switch 显式字段，不把部分相等或图距离短视为兼容。

## Rule conditions

未来如另行批准，应以新版本派生规则表达，并同时满足：

1. Switch source identity UNIQUE；完整 source Line incidence 恰好两条不同 Line，
   两条 Line 各自唯一且有可追溯的 published source entity。
2. 一条 Line_ToBus 等于 Switch_ID，另一条 Line_FromBus 等于 Switch_ID；
   两个内端 SourceReference 均 EXACT 指向该 Switch，不隐藏额外 incident evidence。
3. A/B 为两条 Line 的外端，X/Y 为 Switch 的 FromBus/ToBus；四个原始引用全部
   EXACT，指向唯一且存在的 source entity；raw X=A、raw Y=B，并逐对确认 resolved target 一致。
4. 延续现有非 Switch 端点投影、Bus/电压和 Transformer 规则；不会因满足 Switch
   条件就救回其他被排除的端点。派生端口保留完整 source refs 与规则版本。
5. CLOSED 才允许导通；OPEN/UNKNOWN 保持阻断。保留 IsTie、HasMeasurement 和
   原始状态，不从 flag 推断状态，不额外强制径向化或合并 source entities。

这是条件驱动的版本化子模式，不是将当前 80 个 ID 硬编码为白名单。

## Exclusion conditions

排除非唯一、额外或不完整 incidence、同一条 Line 重复、非一入一出、内端不 EXACT、
任一外端或显式引用 missing/unresolved/ambiguous、对应 target 不一致。
部分兼容、双端不同、未获证明的 collapsed X=Y、单纯同 Station 或 source graph 接近
不获得额外放行。反向声明暂不纳入本提案，因为本批数据没有完整正例。
数字接近、共同前缀、后缀规律、科学计数形式不得成为匹配或修复规则。

## Expected coverage impact

**COUNTERFACTUAL ONLY / NOT ACCEPTED TOPOLOGY**

当前数据的 Scenario B 恰为这 80 个 DIRECT 候选：reachable Transformers 5→5，
reachable Transformer cases 4→4，usable subgraph cases 17→37。
80 个中 CLOSED 76、OPEN 4；非 tie CLOSED/OPEN 为 74/2，tie 为 2/2。
Scenario A 忽略全部 60,960 个显式字段得到的 1,042 reachable cases 不属于本提案收益。

## Risks and review needs

完整 source 声明一致仍不是实际电气连接的独立确认；后续接受意味着批准该派生解释。
需核实 Switch 字段方向含义及这 4 个 tie 的处理，保留状态与角色；不能将普通 series
样本的解释自动推广到所有 tie。当前仅 60 cases 提供正例，不能外推未解析的大多数。
反向、不同抽象层、collapsed 端点需要独立证据和另行版本化 review。
Q-CONN-001、Q-TRANSFORMER-001 继续 OPEN。

## Source Facts remain unchanged

未来规则也只能创建独立版本的派生端口、连接与 provenance，不修改 raw data、E1
实体、SourceReference、Terminal connectivity 或 baseline E2 输出。
本次实现只有只读诊断与临时 counterfactual adjacency，没有实现该 topology rule。
须用户 review 并另行批准后才可实施；本阶段到此停止，不进入 E3。
