# E2.1 — Switch Connectivity Semantics Investigation

状态：分析完成后提交 review；没有修改 accepted topology。
E2 基线 commit：`6019befa35579b4a08f51bac8c1d9d0989999bc8`。
本次独立 commit 的完整 SHA 在交付回复中给出，也可用
`git log -1 --format=%H -- docs/handoff/2026-09-15-e2-1-switch-semantics.md` 获取。

## 范围与复现

本阶段新增独立 analysis package、诊断 artifact writer、测试与报告。没有修改
E2 interpreter、accepted v1 contract、SourceReference 或 Terminal connectivity。
没有实施 SERIES_SWITCH_V2、Transformer 规则变更、E3、Load/PV、OpenDSS 或 QSTS。

- E1 输入：`outputs/nanjing-e1/source-import-v2/`。
- E1 manifest SHA256：`9d244c812bae8f5f9b1f5e6e1aca8d7bda13fde4b31da9f2ec6ad044f6e135a3`。
- E2 baseline：`outputs/nanjing-e2/topology-v2/`（v1 规则的 artifact 修订 v2）。
- Baseline manifest SHA256：`40f4bb350e33415306d80e6c7436cddff8d72a2294e0261d0beac3063477bd55`。
- 独立诊断：`outputs/nanjing-e2-1/switch-semantics-v1/`。
- 分析版本：`switch-semantics-investigation-v1`；没有随机采样或 seed。
- [运行指南](../guides/nanjing_switch_semantics.md)；[诊断合同](../spec/switch_semantics_investigation.md)。

## 测试与验证

- `.venv/bin/python -m pytest`：**273 passed**，其中 E2.1 为 **34 项测试**。
- `.venv/bin/python -m compileall -q src tests`：通过。
- Git whitespace 检查：通过。
- 跨 PYTHONHASHSEED=1/999、输入 records/accountability 顺序变化，全部诊断文件逐字节相同。
- 覆盖 literal motif、原始/额外查询类型、0/1/2/GT2/disconnected/unresolved 图关系、
  degree/direction、case aggregation、状态/flag 分组、counterfactual 和源数据不变。
- 端到端测试移除测试 ZIP 后仍能分析 persisted E1/E2，两个输入逐字节不变。
- Counterfactual 不放行 OPEN/UNKNOWN，也不绕过 Transformer 或 Bus 电压排除。

全量 artifact 校验通过：5,159 cases、60,960 条唯一候选记录，逐条重算 motif、
类型、分桶、case 汇总和图距离 witness；counterfactual baseline 与 E2 coverage 一致。
诊断 manifest SHA256：`91e3489d5ee2f893c006124c2582f5e80ace22a4aac455a6c4039c854611b6c3`。
复核摘要：`outputs/nanjing-e2-1/switch-semantics-v1-verification.json`。
运行后再次完成 E1/E2 全文件 hash 验证，两个 manifest SHA 与上列值相同。

## 解释原则

A/B 是相邻 Line 的外侧端点，X/Y 是 Switch 自己的 FromBus/ToBus 声明。
原始 SourceReference 与额外 case-local 精确查询并列保存；后者不覆盖 Candidate Matrix。
特别是额外类型中的同文本 ID，不会推翻已有 EXACT 引用。

所有数量区分 source rows、published entities、identity groups、候选与 mapping records。
Baseline 的 EXPLICIT_ENDPOINT_EVIDENCE/SWITCH_DEGREE 只选择设备映射，不把同一设备的
Line endpoint 映射重复计数。未解析、不同文本、同 Station、数字接近或没有局部路径，
都不能单独证明字段冲突或电气兼容。

Source-reference graph 的顶点包含 Line，本图的一条 EXACT owner→target 引用是一跳；
经一条 Line 从外侧端点到 Switch 是两跳。图距离不是电气距离。未解析的声明没有
偷偷加入图中。明确的 Bus→Station membership 可作为不同 source layer 的证据，
仅有距离接近不够。ID 特征永不用于检索、repair 或 scenario 接受。

## 六个问题的正式回答

1. **Q1：不能认定通常属于同一抽象层。** A/B 常命中 Bus，也大量命中 Switch，
   B 还包括 Transformer/AccessPoint；X/Y 分别有 34,620/57,031 个未解析。
   因此类型分布不能支持全局同层或全局不同层结论。严格的 Bus→Station membership
   判据没有找到两端完整成立的不同层级子集；这不证明源系统没有其他抽象层。
2. **Q2：明确完整兼容 80；已证实冲突 0；语义未知但满足结构筛选 60,880。**
   已证实冲突为零表示没有足够独立语义证据，不表示保证无冲突。
   1,838 个部分兼容、296 个双端不同仍属于未知。字面 DIRECT 共 111 个，
   其中 30 个未解析、1 个有歧义，只有 80 个具有完整 EXACT 证据。
3. **Q3：non-empty == conflict 不被支持。** 80 个完整一致声明构成反例，
   可视为兼容且重复表达 Line 外端点；其他非空字段多为语义未决。
   E2 的 EXPLICIT_ENDPOINT_EVIDENCE 应继续解释为保守排除原因，不能改称已证实冲突。
4. **Q4：Scenario A 从 4 增至 1,042 个 reachable Transformer cases。**
   仅忽略 Switch 显式端点，保留 NormalState、所有非 Switch 投影和 Transformer 规则。
   这是 COUNTERFACTUAL ONLY / NOT ACCEPTED TOPOLOGY；不能当作验收结果。
5. **Q5：建议提出窄 V2，但只限完整 EXACT DIRECT 子集。** 当前证据支持为 80 个
   明确一致声明提出可审查规则，不支持全局忽略字段。Scenario B 的 reachable cases
   仍为 4，不能用 Scenario A 的提升替窄提案背书。
6. **Q6：最小规则为 UNIQUE、两条不同且唯一的 source Lines、严格一入一出、
   内端引用 EXACT 指向该 Switch，A/B/X/Y 全部 EXACT 且唯一，X=A、Y=B，
   对应 resolved targets 也一致。** OPEN/UNKNOWN 不导通，保留 IsTie/HasMeasurement，
   不放宽其他规则。没有反向兼容实例，暂不提议反向扩展。
   详见 [SERIES_SWITCH_V2 proposal](../decisions/proposed_series_switch_v2.md)。

## 全量统计

### 总体与显式证据

5,159 cases 中有 2,936 cases 含候选。Switch source rows 272,716；published entities
270,972；identity groups 271,461；其中 UNIQUE 270,642。重新认证的一入一出候选
60,960，全部 inner reference EXACT，恰与 baseline 显式端点排除设备集合一致。
非候选为 209,682 个非一入一出 UNIQUE 和 819 个非唯一 identity groups。

|显式证据桶|Switch 数|Case 数|候选占比 %|
|---|---:|---:|---:|
|EXACT_COMPATIBLE|80|60|0.131234|
|REVERSE_COMPATIBLE|0|0|0|
|PARTIAL_COMPATIBLE|1,838|118|3.015092|
|BOTH_ENDPOINTS_DIFFERENT|296|43|0.485564|
|ENDPOINT_UNRESOLVED|58,223|2,869|95.510171|
|ENDPOINT_AMBIGUOUS|523|318|0.857940|
|ONE_ENDPOINT_MISSING|0|0|0|
|BOTH_ENDPOINTS_MISSING|0|0|0|
|DIFFERENT_SOURCE_LAYER|0|0|0|
|OTHER|0|0|0|

Switch 分桶互斥，Case 可以跨桶。完整兼容覆盖 60 cases；未知语义覆盖 2,931 cases。
判定优先级见诊断合同；unresolved/ambiguous 优先于 partial/different。

### 端点类型

|类型|A|B|X|Y|
|---|---:|---:|---:|---:|
|BUS|41,776|21,613|17,815|789|
|SWITCH|16,151|17,057|7,216|2,115|
|STATION|2,488|0|1,236|0|
|TRANSFORMER|6|12,466|1|914|
|ACCESS_POINT|122|6,759|10|111|
|UNRESOLVED|16|2,939|34,620|57,031|
|AMBIGUOUS|401|126|62|0|
|MISSING|0|0|0|0|

每列 60,960。保留 E1 类型与全量 case-local diagnostic lookup 在本数据逐端点一致，
交叉表没有类型变化，扩大精确查找并未救回缺失引用。两个 Line 内端均为 EXACT SWITCH。
A/B 大量指向 Switch，确有设备链声明；不能把所有外端都假定为 Bus。

### Literal motif 与 degree

|互斥 motif|Switch 数|Case 数|占比 %|
|---|---:|---:|---:|
|BOTH_DIFFERENT|33,074|1,730|54.255249|
|X_A_ONLY|24,346|1,344|39.937664|
|X_EQUALS_Y|3,356|742|5.505249|
|DIRECT|111|68|0.182087|
|Y_B_ONLY|73|67|0.119751|

其余 reverse、交叉单端、missing 等模式为零；artifact 另保留可重叠 equality flags，
因此 X_EQUALS_Y 优先分类不会丢失其与 A/B 的等值关系。

|degree|全部 identity groups|UNIQUE Switch|baseline SWITCH_DEGREE 独立设备|
|---|---:|---:|---:|
|0|163,849|163,849|163,849|
|1|45,833|45,833|45,833|
|2|60,997|60,960|0|
|3|596|0|0|
|>3|186|0|0|

Degree 2 为一入一出 60,960、两入 37、两出/其他 0；两入 37 和 degree≥3 的 782
均为非唯一 identity groups。Baseline SWITCH_DEGREE 为 **209,682 独立设备**，
不能与此前 255,515 条 mapping records 混用。一入一出是主要可解释 degree-2 结构，
仍不能仅凭数量授予电气语义。

### Source graph 与 ID 模式

|端点对|distance 0|1|2|>2|disconnected|unresolved|
|---|---:|---:|---:|---:|---:|---:|
|A–X|24,403|733|29|1,097|0|34,698|
|B–Y|160|774|1,115|1,802|0|57,109|
|A–Y|12|379|1,953|1,573|0|57,043|
|B–X|6|316|7,041|17,473|0|36,124|

A–X/B–Y 分别有 24,281/141 对具备共同 Station affinity；直接 Bus–Station membership
均为 0。两对都处于 0–2 跳的候选 1,220。此图包含被调查的 source declarations，
接近或共同 Station 不构成独立的连接证明，因此这些候选不能自动升级兼容。

|给定 ID 对|完全相同|数字形式但不同|科学计数形式|仅前导零不同|
|---|---:|---:|---:|---:|
|A–X|24,469|36,491|0|0|
|B–Y|190|60,770|0|0|

不同 ID 的首次差异均在末 1–6 位内。A–X 末差异宽度 1/2/3/4/5/6 的数量分别为
1,443/6,606/23,927/4,105/339/71；B–Y 为 1,159/11,036/41,038/6,786/691/60。
共同前缀和 suffix equality 的完整直方图见 endpoint_type_distribution.json。
这提示可进一步向源系统核实编码/导出表示模式，不能据此断言具体原因，
更不能执行数值就近、前缀匹配、科学计数展开或 ID repair。

### 状态、flag 与 case 一致性

|分组|候选|完整兼容|BOTH_DIFFERENT|DIRECT|X_A_ONLY|X_EQUALS_Y|Y_B_ONLY|
|---|---:|---:|---:|---:|---:|---:|---:|
|CLOSED|54,824|76|30,227|106|21,358|3,066|67|
|OPEN|6,136|4|2,847|5|2,988|290|6|
|IsTie FALSE|56,621|76|31,259|106|22,061|3,125|70|
|IsTie TRUE|4,339|4|1,815|5|2,285|231|3|
|HasMeasurement FALSE|57,686|71|31,299|98|22,930|3,286|73|
|HasMeasurement TRUE|3,274|9|1,775|13|1,416|70|0|

各属性 UNKNOWN 均为 0。Tie 的 X_A_ONLY 比例高于非 tie，不能预先假定所有类型同规则。
80 个完整兼容中非 tie CLOSED/OPEN 为 74/2，tie CLOSED/OPEN 为 2/2；
提案须明确保留此差异并 review 这 4 个 tie，不从 IsTie 推导 NormalState 或径向性。

Case purity：无候选 2,223；单一 motif 2,074；混合但主导占比 ≥0.9 的 318；
主导占比 <0.9 的 544。每 case 候选数、主导 motif、purity 和 minority 数量见
case_pattern_summary.jsonl。局部一致性支持继续研究版本化子模式，不支持全局忽略字段。

### Counterfactual reachability

**COUNTERFACTUAL ONLY / NOT ACCEPTED TOPOLOGY**

|场景|选中候选 Switch|Reachable Transformers|含 reachable Transformer 的 cases|Usable subgraph cases|
|---|---:|---:|---:|---:|
|E2-v1 baseline|0|5|4|17|
|A：忽略显式字段，保留状态|60,960|7,024|1,042|2,496|
|B：完整兼容子集|80|5|4|37|
|C：兼容 + 明确不同层级|未评估|—|—|—|

A 增加 1,038 个 reachable cases、7,019 个 Transformers 和 2,479 个 usable cases。
B 仅增加 20 个 usable cases，没有新增 reachable Transformer case。
不存在满足本次严格判据的不同层级子集，所以不构造 C。其他 v1 排除和状态均保留，
不追求先前非正式探索约 1,440 的数值，也没有证据逐项归因该差值。

### 真实例子与追溯

representative_examples.json 对每个非空 motif/证据桶按
`(case_id, source_record_ref)` 取前三条，包含完整 Switch、两条 Line、六个端点的
原始引用与类型、状态、IsTie 和 supporting source refs。以下为便于阅读的摘录；
完整 case ID/locator 以 artifact 为准，未人工替换选样。

|源 case|Switch ID|incoming / outgoing Line|观察|
|---|---|---|---|
|双闸变_10kV富春江#1线111|3800475135547508630|2126444 / 2126437|X、Y 未解析；不能称冲突|
|荣盛变_10kV听涛#1线|3800475135547859602|2243800 / 2243785|A=X=3800475135547872870（Switch），B=Y=3801601035454291968（Bus），全部 EXACT|
|荣盛变_10kV听涛#1线|3800475135547859537|2243647 / 2243644|X=A；B=3801601035454291953，Y=3801601035454291968 都为 EXACT Bus；仅部分兼容，IsTie TRUE|
|桠溪变_10kV桠顾线122|3800475135547542486|2610549 / 2610545|X=Y=3800475135547542528（Switch），不同于 A/B；语义仍未决|

这些摘录均为 CLOSED。完整 unresolved 示例 A=3801601035454212297（Bus）、
B=3800475135547508631（Switch）、X=3801601035454212096、Y=3800475135547508736。
双端不同示例 A=3800475135547542591、B=3800475135547542487，均 EXACT Switch。


## 局限与下一步

候选全部是一入一出，是筛选条件本身，不能再当作独立的电气语义证明。
Case purity 描述 X/Y 对 A/B 的字面 motif 一致性；minority motif 不是源数据错误。
COMPATIBLE_SOURCE_EVIDENCE 表示完整声明一致，不表示真实连接已确认；没有已证实冲突
也不等于保证无冲突。Counterfactual 仅量化假设影响，不能当成已接受 coverage。

原 E2-v1 报告仍为基线。任何 V2 proposal 仅供 review，须另行批准才能实现。
Q-CONN-001、Q-TRANSFORMER-001 保持 OPEN；本阶段结束后 STOP，不进入 E3。
