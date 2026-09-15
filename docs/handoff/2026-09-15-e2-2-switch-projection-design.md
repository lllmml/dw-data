# E2.2 — Switch Projection Design

**PROPOSED / NOT ACCEPTED / NOT IMPLEMENTED**

交付完成：只读 candidate framework、全量 counterfactual graph 实验、coverage/risk/tie
分析、确定性样例、待审提案。E1 冻结、E2-v1 及 accepted contract 保持不变。
没有实现 SERIES_SWITCH_V2 topology rule，没有 E3、Load/PV 或 OpenDSS。

## Commit、测试与复现

- 输入代码基线：`c1ca4235ce2073faba9eabf681c38892ce888c2e`。
- 交付 commit：本文件所在独立提交；`git log -1 --format=%H -- docs/handoff/2026-09-15-e2-2-switch-projection-design.md`。
- 指定 commit message：`analysis: design switch projection v2 proposal`。
- `.venv/bin/python -m pytest`：**303 passed**（273 原有 + 30 E2.2）。
- `.venv/bin/python -m compileall -q src tests`、`git diff --check`：通过。
- 测试包括结构/状态/同侧电压正反例，未知/歧义保持 unknown，非 Switch 排除，
  OPEN 的结构环与导通阻断、平行边/self-loop、degree、unsupported、共享 source
  region 不误报、head source region、Tie 移除、顺序稳定、源输入不变、checksum tamper。
- 两个独立 Python 进程，PYTHONHASHSEED=1/999，测试 fixture 全部产物逐字节相同；
  source records/accounting 顺序反转仍得相同完整结果及 graph hash，多 case 汇总顺序稳定。
- **全量 5159 cases、60960 candidates**：从输出明细重新汇总
  全部五份 JSON 报告与 proposal，逐字节相同。全量图运行一次；确定性验证由上述
  多进程测试与全量汇总复现共同支撑。
- 运行后完整 verify E1、E2、E2.1 和本次 artifact 通过，输入 manifest SHA256 未改变。
- 核验摘要：`outputs/nanjing-e2-2/switch-projection-design-v1-verification.json`。
- 使用方法：[E2.2 guide](../guides/nanjing_switch_projection_design.md)。无新依赖、无随机抽样。

## 输入与产物

- E1：`outputs/nanjing-e1/source-import-v2/`；manifest SHA256 `9d244c812bae8f5f9b1f5e6e1aca8d7bda13fde4b31da9f2ec6ad044f6e135a3`。
- E2：`outputs/nanjing-e2/topology-v2/`；manifest SHA256 `40f4bb350e33415306d80e6c7436cddff8d72a2294e0261d0beac3063477bd55`。
- 本次从 verified E1 重建 E2.1 motif，复用 E2.1 分析代码；不读取 raw ZIP。
- 正式 artifact：`outputs/nanjing-e2-2/switch-projection-design-v1/`。
- 输出 manifest SHA256：`581ab83e6d610191b47ae30b2d48b4b6ab186a4c1cec980a3ee5fa79324ab8e2`。
- 包含 strategy_comparison、coverage_by_strategy、risk_analysis、tie_switch_analysis、
  representative_examples、proposal，以及 candidate_decisions/case_results 明细与 manifest。
- [待审 proposal](../decisions/proposed_series_switch_v2.md) 与 artifact proposal.md 字节相同。
- [分析规范](../spec/switch_projection_analysis.md) 仅定义本次实验，没有修改 accepted rules。

## 策略与 coverage

S0 原 SERIES_SWITCH_V1；S1 结构 + known state；S2 额外同侧 EXACT UNIQUE Bus 的
明确电压矛盾安全否决；S3_A 允许 UNKNOWN 非导通投影；S3_B 排除 UNKNOWN。
所有策略只让 CLOSED 导通。非 Switch 决策、source references、Terminal 全部沿用。

| 策略 | Switch projected | conducting | excluded | head cases | usable cases | reachable Transformer | reachable cases | ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| S0 | 0 | 0 | 271461 | 5134 | 17 | 5 | 4 | 0.000045 |
| S1 | 60960 | 54824 | 210501 | 5134 | 2496 | 7024 | 1042 | 0.063659 |
| S2 | 60960 | 54824 | 210501 | 5134 | 2496 | 7024 | 1042 | 0.063659 |
| S3_A | 60960 | 54824 | 210501 | 5134 | 2496 | 7024 | 1042 | 0.063659 |
| S3_B | 60960 | 54824 | 210501 | 5134 | 2496 | 7024 | 1042 | 0.063659 |

ratio 分母为 110,338 个 published Transformer。usable 不等于 OpenDSS Ready。
S0 与持久化 E2 baseline 全 case 核对通过；S1 与 E2.1 Scenario A 完全一致。
本批没有 UNKNOWN NormalState；S2 没有命中明确电压否决，因此 S1/S2/S3_A/S3_B
覆盖一致是实测结果，不是省略图重建。合成测试证明策略在相应输入下确实不同。

## Risk comparison

以下“环”均是 deterministic fundamental cycle basis，不是所有 simple cycles；
cycle size 是边数，含 Switch 内边。structural / conducting 分开统计。

| 策略 | projected semantic unknown | accepted endpoint conflict | 新环 S/C | 孤立新环 S/C | conducting degree 审查节点 | conducting cross-region Switch | actual unsupported | blocked unsupported evidence |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| S0 | 0 | 0 | 0/0 | 0/0 | 2 | 0 | 0 | 0 |
| S1 | 60880 | 0 | 0/0 | 0/0 | 2342 | 0 | 0 | 6881 |
| S2 | 60880 | 0 | 0/0 | 0/0 | 2342 | 0 | 0 | 6881 |
| S3_A | 60880 | 0 | 0/0 | 0/0 | 2342 | 0 | 0 | 6881 |
| S3_B | 60880 | 0 | 0/0 | 0/0 | 2342 | 0 | 0 | 6881 |

导通图各角色 maximum degree：`{"feeder-head/mv": 2, "junction/bus": 13, "switch-port/in": 2, "switch-port/out": 2, "transformer-mv/mv": 1}`。
超审查阈值分组：`{"junction/bus": 2342}`。
Switch port 阈值 2、Transformer 1；Bus/head >4 只是审查启发值，未获得物理上限确认。
新增高 degree 是投影后的 Bus 分支汇集证据，不能直接称为错误，更不能自动修复。
S0 与各策略均保留 3 个长度为 2 的平行 Line 基础环；新增环为 0，没有删除既有环。
完整 degree/cycle size distributions 在 risk_analysis.json 中，包括基线。

source-region 可映射 5134 cases、不可映射
25 cases。region 为 E1 EXACT Feeder_SourceBus 的原始 Bus ID，
head 携带同一锚点，不使用共享 Station 猜 feeder ownership。
S0 已有 114,014 个 case-region 标签接触，来自共享 source Bus；S1 数量相同。
这些标签不表示已建立全局馈线连接。新增 source-reachable foreign-region contacts
（相对 S0 的 case-region 总数差）为 0。
共享同一 Bus 的多个 Feeder 只列为歧义；GridCase 不合并。**真实跨 feeder 风险
NOT ASSESSABLE**：缺少已确认全局设备身份/ownership，且高压/unsupported 路径仍被
冻结规则隔离。cross-region=0 只对本次可构建的分析图成立，不能证明真实连接安全。

actual unsupported 为图中实际 unsupported 连接；blocked evidence 是候选外端指向
unsupported entity、被原有规则挡住的路径证据，两者分开。未删除环或修复节点。

## Tie 分组

下表中的 triples 为 Transformer / reachable cases / usable cases；only-group 与
remove-group 都重新构造图，不能把不同组贡献直接相加。完整五策略分组见 artifact。

| IsTie 分组 | candidates | S2 projected | CLOSED / OPEN / UNKNOWN | only-group coverage T/C/U | remove-group loss T/C/U |
|---|---:|---:|---:|---:|---:|
| normal | 56621 | 56621 | 54136 / 2485 / 0 | 6898 / 1042 / 2486 | 7019 / 1038 / 2469 |
| tie | 4339 | 4339 | 688 / 3651 / 0 | 5 / 4 / 27 | 126 / 0 / 10 |
| unknown_type | 0 | 0 | 0 / 0 / 0 | 5 / 4 / 17 | 0 / 0 / 0 |

S1/S2/S3 本批投影数量一致；未知 IsTie 没有真实 candidate。
联络开关 IsTie 不等于 OPEN；其 CLOSED 数量与边际 reachability 收益均保留，
不把“单独处理”写成已证明 Tie 不导通或无价值。

## 必答问题

### Q1：采用 S1 coverage 提升多少，新增风险是什么？

Transformer 5→7,024（+7,019），reachable cases 4→1,042（+1,038），
usable cases 17→2,496（+2,479）。主要新增风险是允许
60880 个显式端点语义仍 unknown 的结构解释，
以及 Bus degree 审查项增加；coverage 不能证明 source 声明已解释正确。

### Q2：S1 是否产生明显错误连接模式？

本次可构建图未观察到新增环、孤立环、Switch/Transformer 超预期 degree 或 actual
unsupported 路径；source-region 检查也未发现新增跨区 Switch。高 degree Bus 要审查，
不能据阈值认定错误。没有全局 feeder ownership，所以不能得出“无错误连接”的结论。
每策略真实样例按 `(case_id, switch_id)` 前三条确定性选择，包含原始 A/B/X/Y、两条
Line、NormalState、IsTie、decision 和 reason；没有人工挑样例。

### Q3：S2 是否比 S1 更合理，损失/避免多少？

建议保留 S2 安全否决，因为它只拒绝可证明的同侧电压域矛盾，不把 unresolved 或
不同 ID 当 conflict。本批命中 0 个，coverage 损失 0，
可量化被避免的风险也是 0。不能把未来过滤能力说成本批已验证的错误率改善。
不存在真实 S2 排除样例，因此 examples 对应数组为空；合成测试提供明确冲突正例。
更广泛的“conflicting entity”仍需要新证据，不用图距离或文本差异补造冲突。

### Q4：Tie switch 是否需要单独规则？

**建议需要。** Tie 为 688 CLOSED / 3,651 OPEN，普通 Switch 为
54,136 CLOSED / 2,485 OPEN，状态分布明显不同。联络语义依赖两侧 feeder 边界，
当前数据没有完整 ownership。
表中给出 CLOSED/OPEN 和真实边际覆盖代价；单独处理是对证据范围的限制，不是自动
改变状态。未来另做 TIE_SWITCH_V1；unknown type 不归入普通 Switch。

### Q5：推荐哪个 SERIES_SWITCH_V2 proposal，为什么？

推荐 **S2 的 known-state + endpoint safety 核心，限定 IsTie == FALSE**，
作为普通 SERIES_SWITCH_V2 待审规则。对应普通范围 coverage 是
6898 Transformer / 1042 reachable cases /
2486 usable cases，不能引用全类别 S2 的收益冒充。
UNKNOWN 的 Option A/B 未决定：本批没有真实 UNKNOWN 候选，仅有测试验证；
Tie/unknown type 暂不属于普通规则提案。结构解释仍需用户接受，不能自动发布 V2。

## Source facts 与停止边界

没有修改 raw、E1 SourceReference、Source Terminal connectivity、raw import、E2 artifact
或 docs/spec/nanjing_topology_interpretation.md 的 accepted rules。临时 graph 使用
analysis-only namespace、保留独立 Line owner；不生成 accepted ElectricalTopology。
待用户 review；Q-CONN-001 / Q-TRANSFORMER-001 继续 OPEN。本交付到此停止，不进入 E3。
