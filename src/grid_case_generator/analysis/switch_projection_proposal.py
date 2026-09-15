"""Render the review-only design proposal from measured experiment results."""


def render_proposal(reports):
    coverage = reports['coverage_by_strategy']['strategies']
    risks = reports['risk_analysis']['strategies']
    ties = reports['tie_switch_analysis']['strategies']
    rows = []
    for name, c in coverage.items():
        rows.append(f"| {name} | {c['switch_projected_count']} | {c['switch_conducting_count']} | {c['switch_excluded_count']} | {c['cases_with_feeder_head']} | {c['cases_with_usable_subgraph']} | {c['reachable_transformers']} | {c['cases_with_reachable_transformers']} | {c['reachable_transformer_ratio']} |")
    risk_rows = []
    for name, r in risks.items():
        s, c = r['structural'], r['conducting']
        risk_rows.append(f"| {name} | {r['projected_semantic_unknown_count']} | {r['projected_endpoint_conflict_count']} | {s['new_cycles_count']} / {c['new_cycles_count']} | {s['isolated_new_cycles_count']} / {c['isolated_new_cycles_count']} | {c['cross_feeder_projection_count']} | {c['unsupported_path_count']} | {r['blocked_unsupported_path_count']} |")
    base, s1, s2 = coverage['S0'], coverage['S1'], coverage['S2']
    normal = ties['S2']['normal']['only_group_coverage']
    tie = ties['S2']['tie']
    return f'''# SERIES_SWITCH_V2 — E2.2 数据实验提案

**PROPOSED / NOT ACCEPTED / NOT IMPLEMENTED**

本文件由 E2.2 测量结果生成，仅实现独立分析框架，不实现 accepted topology rule。
取代 E2.1 的 EXACT DIRECT 窄提案作为当前待审设计；旧提案仍可在 git 历史查阅。
完整证据见 outputs/nanjing-e2-2/switch-projection-design-v1/。

## Evidence 与候选 rule

1. UNIQUE Switch、完整源 Line incidence 恰好两条不同的 UNIQUE 已发布 Line；
   一条 Line_ToBus == Switch_ID，另一条 Line_FromBus == Switch_ID；内端均 EXACT。
2. 建议以 S2 / S3_B 为状态与安全核心：NormalState 必须 known，CLOSED 导通，
   OPEN 保留结构边但不用于 reachability。UNKNOWN 两方案本阶段分别测量，不决定。
3. 显式 X/Y 不删除：完整记录 raw 值、SourceReference、resolved target、证据 locators。
   unresolved/ambiguous/missing/不同 ID 均不能单独成为 conflict。
4. 安全否决仅为同侧 A/X 或 B/Y 都 EXACT 指向 UNIQUE Bus，且已声明有限正电压
   不兼容；使用 E2 的 10/10.5 kV 兼容域。完整 direct/reverse 或严格 membership
   兼容证据优先。不同实体抽象层、共享 Station、图距离不作为否决或 ID repair。
   此安全条件只检测可证的电压域矛盾；不是完整语义冲突检测器。
5. 普通 series 规则候选范围建议 IsTie == FALSE；IsTie TRUE 留给独立
   TIE_SWITCH_V1 设计，IsTie unknown 继续等待类型证据。分组覆盖损失公开列出。
6. 非 Switch 的 feeder head、Bus 电压、Transformer、unsupported entity 排除不变。
   proposal 经另行明确接受后才可实现派生规则；本阶段所有边只在临时分析图内。

## Coverage（counterfactual）

| 策略 | projected | conducting | excluded | head cases | usable cases | reachable Transformer | reachable cases | ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

ratio 分母为全部 published Transformer，不是本地 projected Transformer。
S1/S2 已要求 known state，所以 S3_B 与 S2 等价；S3_A 额外投影 UNKNOWN 但不导通。

建议普通 Switch 范围（S2 仅 normal；其它保留 S0）独立重建结果：
usable {normal['cases_with_usable_subgraph']}、reachable Transformer {normal['reachable_transformers']}、
reachable cases {normal['cases_with_reachable_transformers']}。
这才是普通 SERIES_SWITCH_V2 建议范围的收益，不能拿全类别 S2 收益代替。

## Risk analysis

| 策略 | projected unknown semantics | endpoint conflicts accepted | 新环 structural / conducting | 孤立新环 structural / conducting | conducting 跨 region switch | actual unsupported | blocked unsupported evidence |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(risk_rows)}

环为确定性 fundamental cycle basis（边数含 Switch 内边，保留平行边与 self-loop）；
不是枚举所有 simple cycles，也不是自动认定错误。degree 的角色分布与审查阈值详见
risk_analysis.json；Bus/head >4 仅供审查，没有已确认物理上限。
actual unsupported 是临时图实际接到不支持实体的边数；blocked evidence 是因冻结
规则未进入图的候选外侧路径数，不可混为已建立连接。

跨 feeder 检查以 EXACT Feeder_SourceBus 的 raw Bus ID 作为 source region 线索，
检查新增 switch 是否连接不同 region；另外报告新可达的外部 region。case 不合并，
同 Bus 多 Feeder 单列歧义。source regions 映射不完整且全局 ownership 未确认，
因此真实跨 feeder 风险为 NOT ASSESSABLE；0 不能解释为真实电网无跨 feeder 连接。

## 必答问题与推荐理由

### Q1：S1 提升与风险

相对 S0，S1 增加 {s1['reachable_transformers'] - base['reachable_transformers']} 个可达 Transformer、
{s1['cases_with_reachable_transformers'] - base['cases_with_reachable_transformers']} 个可达 case、
{s1['cases_with_usable_subgraph'] - base['cases_with_usable_subgraph']} 个 usable case。
代价是接受大量语义 unknown 的结构解释，新增环与高 degree 要作为 review 证据。
这不是对实际电气连接的确认，源事实相容性与覆盖改善是两件事。

### Q2：S1 是否产生明显错误连接模式

表中报告可检测的电压冲突、闭环、隔离环和 unsupported 路径；闭环本身不是错误。
没有全局 feeder ownership，不能从这些检查推断真实电网连接正确。
需联合 representative_examples.json 的确定性样例审查 source 字段层级。

### Q3：S2 是否更合理

S2 比 S1 少 {s1['reachable_transformers'] - s2['reachable_transformers']} 个可达 Transformer、
{s1['cases_with_reachable_transformers'] - s2['cases_with_reachable_transformers']} 个可达 case、
{s1['cases_with_usable_subgraph'] - s2['cases_with_usable_subgraph']} 个 usable case；
排除 {risks['S2']['endpoint_conflicts_excluded_count']} 个有明确同侧电压矛盾的候选。
推荐保留这一有证据的安全否决。若实测排除为 0，仅证明本数据无命中，
不能声称已经降低了可量化的真实错误率，也不能因此取消安全条件。

### Q4：Tie 是否单独处理

建议单独处理。S2 tie candidate {tie['candidate_count']}、projected {tie['projected_count']}。
从完整 S2 移除 tie 的可达 Transformer 损失 {tie['remove_group_loss']['reachable_transformers']}、
可达 case 损失 {tie['remove_group_loss']['cases_with_reachable_transformers']}、
usable case 损失 {tie['remove_group_loss']['cases_with_usable_subgraph']}。
这些是重建图的边际差值，不是可加贡献。IsTie 不直接决定开闭状态；
联络设备还需要独立的两侧 feeder ownership/边界语义，当前证据不能确认。

### Q5：推荐

推荐 **S2/S3_B 的已知状态、安全过滤核心 + IsTie FALSE 普通 Switch 范围**，
作为待审 SERIES_SWITCH_V2 proposal。UNKNOWN A/B 保留为实验选项，tie 与 unknown
类型单列后续设计。覆盖率并非唯一依据；此提案明确承担未解析显式字段的解释风险，
必须通过用户 review 才能成为规则，不能据本报告自动发布 topology。

## Why source facts unchanged

输入只使用已验证的 E1 source artifact 与 E2 topology-v2；记录两个 manifest SHA256。
不读取或改写 raw import，不改 SourceReference、Terminal connectivity，不覆盖 E2。
分析使用独立 analysis-only namespace 和按源 Line ID 去重的临时 multigraph，
不会把诊断匹配写回 resolver。产物目录独立且拒绝覆盖；没有 accepted rule 注册。
E1 冻结、E2-v1 不变，Q-CONN-001 / Q-TRANSFORMER-001 仍 OPEN；不进入 E3。
'''
