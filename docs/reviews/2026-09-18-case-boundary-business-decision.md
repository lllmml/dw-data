# Q-CASE-001：Case boundary 业务确认阶段

状态：**REQUIRES_BUSINESS_CONFIRMATION / 待甲方确认**。Q-CASE-001 保持 **OPEN**。
本文是业务确认问题单，不是甲方已作出的决定，也不构成规则批准或实施授权。
当前仍按 source directory = GridCase 处理，禁止实际 cross-case follow 或合并。

## 1. 证据依据与当前发现

依据已交付的 [D4.2 case boundary review](2026-09-18-nanjing-case-boundary-review.md)
和 [D4.2 handoff](../handoff/2026-09-18-e2-3-d4-2-case-boundary-audit.md)。
审计覆盖全部 5,159 个 source case directory；正式只读产物为
`outputs/nanjing-e2-3/case-boundary-audit-v1/`，manifest SHA256：
`d8c1b78017e328e73444fd57f823892d4985e0fcef6b596147a86d2286562144`。

| 发现 | 数量与口径 |
|---|---|
| Cross-case reference | 98,954 个非空、case-local 未解析的原始字段引用，在其他目录找到定义 |
| Affected Cases / Feeders | 3,220 个引用方 Case / 3,219 个已发布 source Feeder |
| Unique / multiple external match | 97,293 / 1,661 个字段引用 |
| Reciprocal reference | 5,273 个字段引用，占 cross-case reference 的 5.3287% |
| POSSIBLE_EXPORT_PARTITION_CLUSTER | 174 个唯一、同站、电压兼容且双向引用子图中的候选 cluster |
| 同站 / 跨站 external reference | 8,103 / 90,848 个字段引用；存在多候选时两个标签可以重叠 |

Reciprocal 仅表示目录 A 引用了 B 的实体，且 B 存在指向 A 的引用，不证明同一电气
回路双向连通。候选 cluster 也不证明多个目录属于同一 feeder。完整候选引用图最大
弱连通分量包含 3,698 个 Case，不应将其直接视为一个可合并电网。
本次没有观察到跨目录候选与引用方共享精确 Feeder_ID 或非空 Feeder_Name 的情况；
相似线路名称、同站和唯一 ID 匹配均不能单独确认 ownership。

D4.1 的 78 条 `INSUFFICIENT_PLACEMENT_EVIDENCE` Feeder 分类如下：

| 分类 | Feeder 数 |
|---|---:|
| LIKELY_EXPORT_PARTITION | 11 |
| UNIQUE_EXTERNAL_BUT_OWNERSHIP_UNCONFIRMED | 43 |
| AMBIGUOUS_EXTERNAL_REFERENCE | 0 |
| CROSS_STATION_OR_VOLTAGE_CONFLICT | 24 |
| TRULY_MISSING_GLOBAL_REFERENCE | 0 |
| 合计 | 78 |

这 78 条 Feeder 的 96 个 case-local unresolved Line endpoint 均有唯一外部定义；
其中 69 个同站、38 个存在反向目录引用、96 个电压 context 兼容。因此不应统一要求
甲方补交“缺失 sibling export”。应先确认已有外部定义与引用方的业务归属关系。
该结论仅适用于这批 endpoint，并不代表全数据集不存在缺失、占位或错误引用。

## 2. 三类工作的边界

| 工作类别 | 要回答的问题 | 当前证据支持范围 | 不代表什么 |
|---|---|---|---|
| Identity completion（身份补足） | 原始 ID 是否在 intake 中有定义，候选是什么类型、位于哪个目录？ | 在独立分析索引中补足定义定位、原始记录出处、唯一性及歧义证据 | 不证明 ID 全局唯一，不建立跨目录实体同一性，不确认 feeder ownership |
| Reference completion（引用证据补足） | 某个原始引用有哪些可追溯的目标候选及上下文？ | 在只读 audit 中记录 raw field → 外部候选定义及类型、station、voltage、reciprocal 证据，保留未确认状态 | 不回写 Canonical resolved reference，不改变 resolver，不赋予电气连通语义 |
| Topology reconstruction（拓扑重建） | 实体具体通过哪个端口连接，属于哪个 feeder，如何处理开关状态和边界？ | 当前分析不足以授权或完成此类工作；需要另行确认业务语义与拓扑规则 | 不能由唯一 ID、同站、双向引用或候选 cluster 自动推出连接、合并或可达性 |

**当前分析只能支持前两类的只读证据补足，不应自动进入 topology reconstruction。**
这里的 reference completion 不是改变现有解析结果；即使身份和引用候选均唯一，
具体 attachment port、OPEN cut、跨 feeder ownership 等问题仍可能未解决。

在 `ANALYSIS_ONLY_CROSS_CASE_COUNTERFACTUAL` 下，唯一、同站、电压兼容且通过
类型/身份及已知硬矛盾检查的候选为 2,544 个引用身份，包含 1,252 个 Line endpoint；
1,251 条 Line 可达到两端身份有据可查的上界。它们不是已恢复的拓扑线路。
仅使用已有 accepted anchor 计算时，新增 Line representation、backbone-eligible
Feeder、reachable Line delta 和 reachable Transformer delta 均为 0。
更广泛的 placement / reachability 影响仍为 **undetermined**，不能把这个受限计算的
零增量解读为全局 follow 没有影响，也不能擅自生成锚点使其变成非零。

## 3. 请甲方确认的 Q-CASE-001 问题

以下四项均为 **待确认**，不预填肯定答案。请按适用的数据版本、目录和实体类型
给出答复、例外及可追溯的源系统或导出规则依据。

| 编号 | 需要确认的问题 | 请提供的依据或明确范围 |
|---|---|---|
| BC-01：导出分片 | 不同 Case 是否来自同一个 feeder export partition？目录代表独立 feeder、station/network 分片，还是其他导出单元？ | 给出 source_case_key → 实际 feeder / station / export partition 的权威映射；确认同站不同线路与同一 feeder 多分片的区别。不能把 174 个候选 cluster 整体默认认可。 |
| BC-02：标识符范围 | source_id 是否全局唯一？唯一性范围是整个源系统、同一实体类型、某次导出，还是单个目录？ | 说明是否必须使用 `(entity type, source_id)` 或额外命名空间；重复记录是否为同一设备副本，是否存在 ID 重用及跨版本变化，并提供重复/冲突样例的解释。 |
| BC-03：归属与合并 | feeder ownership 是否允许跨 Case 合并？若允许，是确认同一 feeder 的导出片段，还是表达不同 feeder 的边界关系？ | 指定可合并和不可合并的目录、权威 feeder identity、设备归属及多 head/联络设备处理原则；明确跨 Case 引用不等于自动合并 feeder。业务意见不直接授权当前代码执行合并。 |
| BC-04：引用语义 | cross-case reference 是否表示真实电气连接，还是设备关联、导出定位、边界占位或其他语义？ | 按实际字段说明目标类型、端口/端点含义、方向、电压侧与开关状态语义；解释 reciprocal、单向引用及跨站样例，指出判断真实连接所需的额外证据。 |

建议先核对以下可追溯样本，再决定是否存在可推广的规则：

- 同站 reciprocal cluster：例如西岗变新锦城、夹河变华城相关目录。完整成员和方向见
  `case_reference_components.jsonl`，具体字段及原始记录见 `cross_case_references.jsonl`。
- 78 条 insufficient Feeder：逐条依据 `target_78_feeders.jsonl` 的 reference IDs，
  确认 11 条 likely partition、43 条 ownership unconfirmed 和 24 条冲突分类的业务解释。
- 唯一但跨站的引用：核对是否为真实联络、错误归属或导出问题，不能用“唯一”跳过归属确认。

请在每项答复中记录：问题编号、确认人及职责、确认日期、源数据/导出版本、适用目录
或实体范围、原始记录证据、确认结论、例外和未决项。无答复、部分答复和缺乏证据均
不视为批准；本文件目前不包含任何已签署业务决定。

## 4. 确认阶段的操作约束与结束条件

本阶段仅新增业务确认文档并运行测试验证，不发送或代替甲方作出业务答复。
保持以下状态：

- 不新增 synthetic topology、锚点、设备或拓扑 proposal，不 APPROVE / APPLY。
- 不修改 raw/source facts、Canonical model、Canonical reference 或 resolver。
- 不修改 accepted topology v2，不修改 GridCase contract，不执行 cross-case follow/merge。
- 不进入 E3 / OpenDSS / QSTS，不生成 OpenDSS 数据，不开展 no-source-Line layout 或 D5。
- Q-CASE-001 保持 OPEN，建议状态保持 REQUIRES_BUSINESS_CONFIRMATION。

收到业务答复后，先整理适用范围、证据与未决冲突，形成独立 review。
即使甲方确认存在分片或真实连接，也必须另行确认相应规范并取得明确实施授权，
才可讨论 resolver、GridCase boundary 或拓扑重建的变更；不由本文件自动启动下一阶段。
