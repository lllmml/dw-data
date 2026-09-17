# E2.3-D — Synthetic Topology Completion Contract Design Review

状态：**DESIGN REVIEW ACCEPTED**（用户于后续请求明确通过）。分析日期：2026-09-16；D1 正式合同见 [spec](../spec/nanjing_synthetic_topology_completion.md)。
以下为获批的历史设计分析；其中停止边界指 D review 当时的状态，D1 不因此获得 topology apply 授权。
本文件是设计提案，不冻结新规则、不授权实现、不接受 S2。新增 synthetic connection、Transformer、completed topology 均为 **0**；E3-ready 仍为 **0**。

## 1. Baseline 与结论

开始时 HEAD 为 `a066e2761e86f71adbf178ebe6f10ff9350cdb01`，`git status --porcelain` 为空。
已阅读 intent、data completion、topology interpretation、topology recovery、gated slices、E2.3-A handoff，以及全量正式 evidence 的七个 JSONL/JSON 统计与 report。全量计算以逐 Feeder、Transformer、connection、frontier、candidate witness 和 E1 原字段为依据，不用 handoff 的摘要代替明细。

正式输入与 verifier：

| 输入 | 路径 | 结果 |
|---|---|---|
| E1 | `outputs/nanjing-e1/source-import-v2` | `verify_source_artifact` PASS |
| E2 accepted baseline | `outputs/nanjing-e2/topology-v2` | `verify_topology_artifact` PASS |
| E2.2 projection | `outputs/nanjing-e2-2/switch-projection-design-v1` | `verify_projection_analysis` PASS |
| E2.2 feeder | `outputs/nanjing-e2-2/feeder-coverage-v1` | `verify_feeder_analysis` PASS |
| E2.3-A | `outputs/nanjing-e2-3/topology-recovery-evidence-v1` | `verify_recovery_artifact` PASS；重新汇总明细 |
| frozen E2 artifact | `outputs/nanjing-e2/topology-v1` | `verify_topology_artifact` PASS |

四输入 manifest 与 E2.3-A 绑定一致。E2.3-A manifest SHA256 为
`b088c5567362b6ae39caf2ed3bf56069e63ff3ac6cbe138d9ee347a7f432fe52`。
具体输入哈希和复现材料见第 13 节。

分母保留 5,159 source cases / 5,134 真实 Feeder；另 25 无 Feeder cases 不补造 ownership。
S2 反事实为 FULL 80、PARTIAL 962、legacy FAILED 4,092；拆分后 FAILED 2,379、NO_SOURCE_TARGET 1,713。
**accepted S0 target FULL 为 0，reachable Transformer 为 5；S2 的 80 不能写成 accepted FULL。**
S0 有 usable backbone 的 Feeder 为 17，S2 为 2,496。两者的 FULL 都只是既有 Transformer target coverage，不等于整个 case 拓扑完整。

结论：当前没有已证明安全的自动全覆盖路径。保守规则在已批准语义下的新增 FULL 为 0。
附加 ownership/MV role 等业务假设、独立通过 S2 review 后，最窄结构筛选有 13 条 Feeder、113 条假想叶连接，目标覆盖上界从 80 到 93；这不是安全完成预测。
只要求 A、非 D、S2 usable 的宽松算术包络为 650 条 Feeder、11,835 条假想连接、目标 FULL 上界 697；其中 attachment location、OPEN 区域和设备角色尚未通过验证，不能称为 conservative。
**不建议为达到 100% 绕过 evidence boundary。**

## 2. Evidence-driven findings

### 2.1 A：已有设备，缺 attachment

| A subdivision | Feeder 数 |
|---|---:|
| A 总数 | 3,114 |
| A ∩ D | 1,065 |
| A 非 D | 2,049 |
| 没有 source Line | 1,295 |
| 有 Line，但 S2 没有 usable backbone | 471 |
| S2 usable backbone | 1,348 |
| S2 usable 且非 D | 650 |
| 上项有至少一个 head-reachable `junction/bus` | 351 |
| 上项恰好一个这样的 junction | 115 |
| 恰好一个 junction、非 D、全 case 无 source OPEN Switch | 13 |
| S0 usable、非 D、恰好一个 junction | 7 |
| 上项再要求全 case 无 source OPEN Switch | 1 |

usable 定义沿用正式合同：head 存在且至少一条 accepted/counterfactual conducting Line 从 head 可达，不以单独 head 节点代替 backbone。
候选 junction 仅为已投影的 `junction/bus` 且在相应 policy 图上可达；不把 Transformer MV node、未知 switch 外端口、上游 110kV Bus 或 head 本身伪装成 attachment region。

A 中无引用 Transformer 共 96,038 个；按 feeder 的 经验分位分布为 median 11、P90 39、P99 78、max 44,596（分位算法为排序后 `floor((n-1)*q)`）。
最大 case `数据/113997367245538568_lzwtest22278` 完整保留，不能把 44,596 个设备一并挂在 head 上。
A 中 2,905 个 case 存在 source OPEN Switch，远多于 frontier 的 OPEN 计数；**非 D 不等于已证明不存在 OPEN 风险**。

全体有 Feeder case 的 110,335 个 Transformer source rows，非空字段只有 ID 和部分额定容量（15,474 条）；FromBus、ToBus、HV/LV voltage、phase、winding connection 等字段均为空。
因此不能用“没有电压冲突”代替“已证实 MV 兼容”，更不能凭空声称 transformer port 已定位。
E2.3-A Transformer identity ambiguous 为 0；全量无引用组均缺连接声明。身份唯一不能证明 ownership。
Transformer schema 没有 station/name/feeder 字段可关联。Station 名称、Bus station membership、同目录以及 AccessPoint_ID 是弱上下文，不足以唯一恢复真实连接。

S0 七条结构筛选中的唯一算术新增 FULL 是 `数据/东坝变_10kV青工线133`：20 个 target 全部无引用，但有 5 个 source OPEN Switch，因此不进入最窄无 OPEN 策略。
S0 无 OPEN 的唯一候选 `数据/凤凰变_10kV万科#2线123` 有 12 个 target，其中 6 个无引用、另外 6 个引用目标仍不可达；补这 6 个叶 attachment 仍不是 FULL。
这两个逐例反证说明不能把“有唯一节点”直接升级成安全 completion。

### 2.2 B：零 Transformer rows 的进一步划分

| B source/graph subdivision（互斥） | Feeder |
|---|---:|
| 无 Line、无 AccessPoint | 106 |
| 无 Line、有 AccessPoint | 479 |
| 有 Line、无 S2 usable backbone、无 AccessPoint | 31 |
| 有 Line、无 S2 usable backbone、有 AccessPoint | 211 |
| 有 S2 usable backbone、无 AccessPoint | 41 |
| 有 S2 usable backbone、有 AccessPoint | 845 |
| 合计 | 1,713 |

B 中有 Line 1,128、无 Line 585；S2 usable 886，其中非 D 459；S0 usable 为 0。
B ∩ D 为 546。AccessPoint 存在于 1,535 个 case，但共 5,275 条 AP 记录只有 ID 非空，Bus、UserType、ContractCapacity 全空；不能把 AP 数当负荷数或配变数。
Load/DER 在 B 以及有 Transformer case 均为零 source rows，缺数据不是无需求证明。

B 名称含 10kV 1,186、20kV 210、联络 2、test 2。两个“联络”分别是高淳变联络线117和凤山变凤双联络线111，均无 Line；前者有 Disconnector，后者有一个 AP。这是人工角色审查线索，不是可执行的 NO_TRANSFORMER_REQUIRED 分类器。
B 的 Station 源记录具体包括 1,713 条 110kV 变电站、3,933 条 10kV 环网柜、282 条 10kV 箱式变电站、70 条 10kV 配电室、108 条开关站和 105 条电缆分支箱。存在箱式变电站/配电室是配电用途的人工核查线索，但没有 Transformer 对应关系、需求或数量语义。Station 类型/电压和 Bus 所属 station 描述位置或电压上下文，不足以认证 feeder 业务角色；不得从 station 行数反推配变数。

所有 1,713 个 B 与另外 3,421 个有 Transformer case 的 SimConfig **11 项值完全相同**：包括 BaseVoltage_kV=10.5、SourceBus/OutputVoltageBus=SUB_10KV、Snapshot、50Hz、Newton-Raphson、MVAsc1=450、MVAsc3=500、MaxIterations=100、Tolerance=0.0001、Metric。
这组重复声明没有角色区分能力，也不构成真实仿真参数的证据。20kV 名称不能被默认 10.5 覆盖。

结构比较：B / 有 Transformer case 的 source Line 行数中位数为 7 / 4，AP 行数中位数为 2 / 6；有 Line 比例为 1,128/1,713 / 2,126/3,421；S2 usable 为 886/1,713 / 1,610/3,421。
B 并非普遍更“空”，仅凭 Line 数不能判定应该新增 Transformer。

**当前可认证分类：SYNTHETIC_TRANSFORMER_ALLOWED=0；NO_TRANSFORMER_REQUIRED=0；ROLE_UNDETERMINED=1,713。**
后续只有经过带引用的角色确认，才能将某个 case 归为无需配变的联络/转供网络，或允许 synthetic Transformer 的配电算例；保持原始 zero-row 事实。
需要甲方业务确认：用途、边界、需求及设备数量依据。不能默认“一 feeder 一配变”。

### 2.3 C：deterministic 优先，但不能承诺收益

227 条 C 全部有 Line，其中 S2 usable 182、无 usable 45；223 条与 D 重叠。
非 D 的 4 条为桥东变桥东线、南湖变盛香1号线11E、永阳变湖韵线162、铁心桥变景家村线117。
它们分别仍有 multi-incidence、unresolved/AccessPoint/switch-degree 或 no-head-reachable-line 等问题。

C 内 170 个 feeder 有 leaf-switch witness，0 个有 unique-switch-T witness，0 个有 multi-incoming-T witness；2 个有宽松 multi-line 风险 witness。
全量窄候选累计只增加 19 个可达 Transformer，3 条 FAILED→PARTIAL，**不新增 FULL**；leaf-switch representation 本身增加可达 Transformer 为 0。
宽松 multi-line 得到 81 FULL，但 cycle rank 增加 13 且 winding 语义未证，不推荐。
上述“零收益”限于当前候选与当前证据，不证明未来所有 deterministic 规则都无收益。

优先提交 B/C 独立语义 review：switch 端口表示、EXACT 声明如何解释、multi-incoming 是否同 MV winding、AccessPoint 端点语义。未通过的候选不得换个 synthetic 名称自动落地。
仅在 deterministic review 留下明确“无相矛盾但确实缺失的 attachment”、ownership/voltage/port 已确认时，才可转 synthetic 候选；已有冲突或显式引用不能抹除重接。

### 2.4 D：约束是独立维度

D 共 1,884：A 1,065、B 546、C 223，另有 S2 FULL 50。
因此即使 target FULL 也可能存在显式约束；剩余 30 个 S2 FULL 非 D 也尚未完成 S2 语义验收。
E2.3-A constraint_tags 中 identity 607、voltage 325；known OPEN frontier 涉及 1,074 个 feeder，与前两者重叠，不能求和。
25 个无 Feeder case 的 ownership unresolved 另列，不混入 5,134 分母。

## 3. 原则与政策系统

目标是可解释的工程算例，不是恢复真实南京缺失接线，也不是无条件 graph repair。
记录四类证据：SOURCE_CONFIRMED、RULE_INFERRED、RULE_GENERATED（SYNTHETIC alias）、UNRESOLVED。
SOURCE_CONFIRMED 需要 source evidence 和已批准设备语义；EXACT resolver、唯一候选或算法 deterministic 均不足以自动获得此类。

采用命名 profile 加独立 gate，不用一个高 level 覆盖低 level 的禁令：

| Profile | 范围 | 默认与审批 |
|---|---|---|
| EVIDENCE_ONLY | 无新 synthetic，对应 Level 0 | 当前唯一启用 |
| CONSERVATIVE_ATTACHMENT | existing T 的单点叶 attachment；不建 backbone/Transformer | 拟议 Level 1；业务语义与风险上限冻结后逐批 review |
| ENGINEERING_LAYOUT | 多 region 的工程布局；仍不跨 conflict | 拟议 Level 2；单独授权、用途声明和更强验证 |
| BENCHMARK_ALTERNATE | 明示脱离原连接假设的算法测试模型 | 类似 Level 3；独立数据集，不是南京 completion 默认交付 |

每个 profile 都须通过相同 identity、voltage、ownership、port 和 negative-evidence gate。
物理语义未确认的确定性算法依然是 UNRESOLVED；算法可重复不等于 RULE_INFERRED。

## 4. Allowed / forbidden operations

| 对象/操作 | 拟议允许条件 | 禁止/延后 |
|---|---|---|
| existing junction → existing T 的 synthetic connection | 双端 ownership 有批准证据或显式工程归属声明；MV 端口与电压 class 确认；无已有 attachment；正向准入与负向审查通过 | 未知 winding、电压未定、跨 case、重接已有引用、从 head 随意直挂 |
| inferred junction | 明确 source 证据唯一指向同一电气位置，且对应 interpreter 规则已审查 | 仅名称相似或 ID 相邻不能推导 |
| synthetic junction/Bus | 被批准的工程 region 需要独立节点，父 region/电压/归属明确，新增节点本身不声称 source 同位 | 为连通而合并两个 source components；未知端口短接 |
| synthetic Transformer | B 的配电角色、下游需求、MV/LV、容量来源、数量上限/数量依据、owner 明确，并单独修改 completion contract 获批 | 当前 0 个准入；A 禁止重复创建设备；不从 AP/Line 数猜数量 |
| synthetic backbone/bridge | 将来有端点、路径走廊、operating boundary 和工程设计依据的独立专项合同 | 当前 profiles 不允许；component A→B 仅为消除断开一律拒绝 |
| synthetic LV bus | existing T 已完成 MV 定位且 LV 端口/电压由后续批准 completion 规则确定；一设备一 LV bus，幂等 | 不能靠生成 LV bus 宣告 MV 已定位；不在本轮生成 |

Synthetic connection 在本合同中是拓扑关系，不隐含零阻抗导线或已有 Line。若未来需物理支线，应有独立 branch role 与参数 gate，不能让 exporter 默认把整个 feeder 配变短接成一个理想节点。

明确禁止表：

| Negative evidence | 自动动作 | 可接受后续处理 |
|---|---|---|
| identity ambiguity/duplicate/missing key | DO_NOT_SYNTHETIC_BRIDGE，不任选身份 | source 补充或人工身份裁决，版本化记录，不改 raw |
| 显式 voltage conflict/非法电压 | 禁止容差扩大、改标签、直连 | 校核 source 或另立有完整电压变换设备的设计；非本合同自动补 |
| known OPEN | 禁止闭合、并联旁路或附着到隔离侧规避 OPEN | 若业务要求更改运行方式，独立 scenario 明确授权；source OPEN 保留 |
| ownership 未决/跨 Feeder | 禁止凭目录、ID 或邻近强配 | 甲方 owner/region 声明，或明确批准的 case-scope 工程归属假设 |
| Transformer port/winding conflict | 禁止多侧并成一 MV junction | 完整端口/绕组证据及专项 rule review |
| cross-case ambiguity | 禁止跨 case 合并或复用源身份 | case 边界确认；alternate model 使用独立身份与映射 |
| 其它显式负证据、已有不兼容 attachment | fail closed，保留所有 conflict refs | 人工裁决或补证；不能以“缺失”覆盖已知值 |

“永远禁止”指自动忽略负证据；并非禁止未来获得新证据后进行显式、有版本的业务裁决。
BENCHMARK_ALTERNATE 可以重新定义实验模型，但不能借此给原 case 标 TOPOLOGY_COMPLETE，不能计入南京安全覆盖。

## 5. Attachment Point Selection Policy

### 5.1 Deterministic inferred 与 synthetic 的合同隔离

`INFERRED_ATTACHMENT_REVIEW_V1`：需要 source locator 支撑 owner、唯一节点、明确 MV port、电压兼容和已确认连接语义；输出仅在规则获批后为 RULE_INFERRED。
无引用 Transformer 缺连接声明，当前 A 无法通过该规则。新增 source evidence 会改变输入版本，必须重算。

`SYNTHETIC_SINGLE_REGION_ATTACHMENT_V1`：唯一候选由工程筛选产生，不声称实际位置唯一；即使恰好只有一个 junction，输出仍为 RULE_GENERATED。

### 5.2 Conservative selector（提案，当前未启用）

1. 只读取绑定的 accepted graph 和全量 source evidence；S2 必须是明确的 analysis input，不可潜入 accepted graph。
2. Transformer 必须唯一、无 incoming/outgoing connection declaration、无已投影 attachment；owner 与 MV side 语义必须明确。
3. region 候选限定 head-reachable、voltage-compatible `junction/bus`；head、Transformer port、source 110kV Bus、unsupported AP、unapproved switch port 排除。
4. 拒绝 D；最小 slice 还拒绝全 case 任一 source OPEN/UNKNOWN switching state。当前 Switch UNKNOWN 为 0；未来其它 switching devices 同样检查，不能只看 frontier。
5. 完整检查所有 source declarations 的潜在归属/隔离关系。任何未决证据可能与 proposed region 冲突时拒绝，不因设备目前 NO_REFERENCE 而断言 OPEN 无关。
6. 如果有已批准的强 location hint，取工程候选与 hint 的交集；零个拒绝；多个返回 SELECTION_UNDETERMINED。名称/Station/ID 不作隐式 tie-break。
7. 仅剩一个 region 才产生 proposal。按整个 batch 计算新增 degree、同 region 配变数量、已有配变密度；超过已批准 cap 全部拒绝或进入人工拆分，不能按 ID 取前 N 个。
8. 候选点同样必须通过局部 port、parallel edge、cycle、shortcut、归属和 negative-evidence validator。唯一选择不会豁免校验。

最小 slice 不用 seed。排序只用于序列化与稳定 ID，不能用于选物理节点。

### 5.3 多 region engineering distribution

将来的 `SYNTHETIC_TRANSFORMER_DISTRIBUTION_V1` 可使用 head 距离（graph hops，单位 hop，非 km）、节点 degree、支路分区、已有 Transformer 密度作为工程形态特征。
这些特征不能证明真实地理距离或负荷容量。先由业务冻结区域、密度/degree 上限和目标函数，再求整体分配；同 score 且无法通过工程依据区分时拒绝该批，不用 lowest ID、first sorted 或伪 nearest。
没有额定容量的设备不能按假容量做负荷平衡；不得为本阶段选择位置提前生成参数。

对称图上的自动分配若必须引入抽样，应作为另一个 ENGINEERING_LAYOUT 规则，声明非真实位置、实体隔离随机流和显式 seed；不能改写 frozen v1 中 topology 不随 seed 变化的规则。
当前建议不启用随机方案。graph-hop 分布可能造成集中负荷、失真电压降或虚假短路径，必须在后续参数和仿真 gate 再验证。

### 5.4 候选规则清单

各规则 provenance 都包含第 9 节完整字段，另记录 candidate set、排除理由、selection rationale 和 source/evidence locator。

| rule_id（proposal version 0.1.0） | cohort / positive evidence | exclusion evidence | generated objects / topology effect | 风险与覆盖 |
|---|---|---|---|---|
| INFERRED_ATTACHMENT_REVIEW_V1 | 任意；已确认 source 唯一连接语义 | owner/port/identity/voltage 不明 | 推导映射；非 synthetic | A 当前证据不支持；新增 FULL 未证明 |
| SYNTHETIC_SINGLE_REGION_ATTACHMENT_V1 | A；existing T、唯一合格 region、owner/MV side 已确认 | D、OPEN/UNKNOWN、未决冲突、已有连接、cap 未定/超限 | 每 T 一个 MV attachment node（如缺）和一条叶关系，0 新 T | 集中 degree 与支线物理含义待验证；S0 1 条结构候选/6 关系仍 0 新 FULL；S2 13/113 为条件上界 |
| SYNTHETIC_TRANSFORMER_DISTRIBUTION_V1 | A；多个已批准 engineering regions | 任意 hard gate、对称无唯一解、无 cap/目标函数 | 叶 attachment，可选工程 region node | 351/4,749 仅 junction 筛选包络；没有确定位置，不能报准确 completed 数 |
| SYNTHETIC_TRANSFORMER_ROLE_CONFIRMED_V1 | B；角色、需求、MV/LV、数量与容量来源确认 | ROLE_UNDETERMINED、任何 hard conflict | 新 T、MV attachment、以后 LV bus | 当前 eligible=0；数量未知，不能估 synthetic T 总数 |
| LOCATED_TRANSFORMER_LV_BUS_V1 | 已定位 T、LV 语义批准 | 未定位/未知 LV side/已有 LV bus | 一对一 LV bus，不改善 MV reachability | 沿用 completion 边界，后续 E3 实现 |
| ENGINEERED_BACKBONE_REVIEW_V1 | 当前无准入；未来专项工程设计 | 为图连通补桥、绕 OPEN、跨未知 owner | 本轮及推荐 profile 均无对象 | 不计 coverage 收益，不能承诺 100% |

## 6. Counterfactual feasibility：真实计数与条件上界

分析程序只重建已有 S0/S2 conducting adjacency 做 BFS，**不创建 synthetic edge、不写 completed topology**。
对 A 的假设为“每个无引用 Transformer 新增一个叶 attachment”。若原有所有有引用 target 已经可达，则这类叶 attachment 在纯目标可达性意义上可以使该 feeder FULL；否则仍非 FULL。
计算式：`new_target_full_upper_bound = count(screened A where remaining_referenced[policy] == 0)`；连接需求为这些 screened case 中全部 NO_REFERENCE target 数。
这不是运行电气仿真，也未证明 ownership、MV port、degree cap 或 source 隔离区域。

表中 Eligible 一栏是**结构筛选数**，不是所有合同 gate 已通过数；严格全 gate eligible 当前为 0。
Still unresolved = 5,134 − 表中 target FULL（包含 B，也不扣掉已经 FULL 但含 conflict 的 case）。Blocked 列是 A 筛选的 D 排除总数，非行间可加的独立损失；全数据 D 为 1,884。

| Proposed policy / basis | Eligible feeders（结构筛选） | Synthetic connections（假想需求） | Synthetic transformers | Expected FULL / upper bound | Still unresolved | Blocked by conflict |
|---|---:|---:|---:|---:|---:|---:|
| 当前 approved S0 / evidence only | 0 | 0 | 0 | **0 actual target FULL** | 5,134 | 全体 D 1,884 |
| S2 only（未接受） | 0 | 0 | 0 | **80 counterfactual target FULL** | 5,054 | 全体 D 1,884，其中 FULL 50 |
| S0：A、usable、非 D、至少一个 junction | 7 | 121 | 0 | **≤1** | ≥5,133 | A∩D 1,065 |
| S0：上项唯一 junction、全 case 无 OPEN | 1 | 6 | 0 | **0** | 5,134 | A∩D 1,065；另 6 被 OPEN 排除 |
| S2：A、usable、非 D（location 未定） | 650 | 11,835 | 0 | **≤697 = 80+617** | ≥4,437 | A∩D 1,065 |
| S2：上项至少一个 junction（location 未定） | 351 | 4,749 | 0 | **≤417 = 80+337** | ≥4,717 | A∩D 1,065 |
| S2：上项恰好一个 junction | 115 | 1,671 | 0 | **≤192 = 80+112** | ≥4,942 | A∩D 1,065 |
| S2：唯一 junction、全 case 无 OPEN | 13 | 113 | 0 | **≤93 = 80+13** | ≥5,041 | A∩D 1,065；另 102 被 OPEN 排除 |
| CONSERVATIVE 全 gate、仅当前已确认语义 | **0** | **0** | **0** | **新增 0；S0 总计 0** | 5,134 | D 及未确认 owner/MV/port/cap |
| B 新 T / ENGINEERING_LAYOUT 完整合同 | 0 已认证 | 未定，不记作 0 需求 | 未定；实际生成 0 | 无依据准确预测 | B 1,713 角色待定 | B∩D 546 |

前述 93 中仍有 50 个原 S2 FULL 属于 D；若同时排除所有 D，最多只剩 `30+13=43` 个 target FULL 候选，并非 93 个通过安全验收的 case。
S0 1 个候选与 S2 13 个候选不代表可累加批次。

13 个最窄 S2 候选中，只有松溪变松南线111的 E2.3-A observed_blockers 为空，其余仍存在 unsupported/unresolved/switch-degree 边界；因此 13 只是进入进一步审查的结构筛选。松南线也有 35 个待挂接 target，缺 ownership/MV port 证据。13 个候选 conducting cycle rank 均为 0，但未证明物理可用；其新增后 junction degree（existing degree + NO_REFERENCE 数）对 cap 很敏感：

| 仅作敏感性试算的 degree cap | 保留 Feeder | 假想连接 |
|---|---:|---:|
| 4 | 1 | 1 |
| 8 | 7 | 18 |
| 16 | 11 | 53 |
| 32 | 12 | 78 |
| 64 | 13 | 113 |

这些 cap **不是已批准工程参数**；不能为覆盖率选择 64。未冻结 cap 时 conservative generator 应返回 CONFIG_NOT_APPROVED。
例如沙洲变金都线125有 25 个无引用 Transformer，唯一 junction 原 degree=4，挂接后 degree=29；松溪变松南线111需挂 35 个，原 degree=2，成为 37。这说明“唯一节点”也可能是差的工程布局。

## 7. 结构约束与完成语义

候选 validator 和 apply 后 verifier 必须分别执行：

- connectivity：按已批准 scenario 的 conducting graph 重新 BFS；检查 scope 内全部必需目标；零目标不能 vacuous FULL。
- voltage：按批准 voltage class/port 校验，未知为未决；10/10.5 兼容规则仅按既有合同使用，20kV 与 10.5 不因 tolerance 连通。
- OPEN：保留 source normal state 与实际 operating scenario 分离；比较加入前后隔离区域，不能创造跨 known OPEN 的绕行；最小 profile 拒绝全 case 任一 OPEN/UNKNOWN。
- identity/ownership：跨 case 与 ambiguous identity fail closed；source key 相等不能自动跨 case 合并；每一对象唯一 owning case/Feeder。
- transformer semantics：一个叶 MV attachment 只接明确 MV port；不能连接未知 winding，也不能把配变当穿越 junction。
- topology risk：使用 multigraph 分别计算 structural/conducting cycle rank `m-n+c`（isolates 和平行边按一致口径计入）、parallel branches、self-loop、components、degree、duplicate attachment。叶节点加一条边应 Δcycle=0；新增并联/短路/捷径即拒绝或专项 review。
- shortcut：新叶关系不得改变任意两个既有节点的可达性或最短 hop 距离；不得连接两个既有 components。源图已有异常完整保留并报告，不能静默删除。
- radiality：不要求源图强制 radial、不为达标删边。若未来需要 radial operating state，另立 scenario 记录开关操作及 gate。

定义独立状态轴，不能只有 FULL：

| 轴 | 字段 / 值 | 判定 |
|---|---|---|
| Evidence | per-object evidence_class；case evidence_composition | SOURCE_CONFIRMED / RULE_INFERRED / RULE_GENERATED / UNRESOLVED；不压缩成最高等级 |
| Target coverage | source_target_coverage | 保留 FULL/PARTIAL/FAILED/NO_SOURCE_TARGET，分母固定 source identity groups |
| Completion | completion_status | TOPOLOGY_COMPLETE / TOPOLOGY_COMPLETE_WITH_SYNTHETIC / PARTIAL / ROLE_UNDETERMINED / BLOCKED |
| Simulation readiness | adapter_version、scenario_id、ready、reasons | 本轮全 false；参数、LV、Load/DER/profile、validation 各自 gate |

TOPOLOGY_COMPLETE 必须绑定 `completion_scope`：哪些 feeder、设备、端口、线路/边界属于模型、哪些按批准的工程边界 excluded；所有必需项已解决且无违反约束。不能因 target FULL 把未解释 Line/AccessPoint 自动算完整。
ROLE_UNDETERMINED 和 BLOCKED 可同时出现在 reasons 中；展示主状态优先 BLOCKED→ROLE_UNDETERMINED→PARTIAL→complete，原 evidence/readiness 字段不重写。
TOPOLOGY_COMPLETE_WITH_SYNTHETIC 统计新增 synthetic objects，并单列继承自 v1 的 synthetic MV head。若整个模型证据含 head 假设，即使新增 connections=0 也不能声称纯 source topology；新增 synthetic completion 与 inherited assumptions 分列。
确认无需 Transformer 的 case 可以按独立角色 scope 完成拓扑，但原 NO_SOURCE_TARGET 不改成 source-target FULL。

## 8. 配置边界

Frozen rule：case 隔离、source 不变、evidence 不提升、deterministic-first、negative-evidence veto、OPEN 不旁路、未知 winding 不短接、ID namespace/canonicalization、零 target 不自动 FULL、propose/validate/apply 分离。

Configurable engineering parameters（仅经批准的 profile 有效）：policy profile、approved region inventory、最大新增 degree、每 region 最大 Transformer 数、允许的 engineering density/目标函数版本。
单位分别为无量纲 enum、node refs、整数 incident branches、整数 devices/region；缺失 cap 不应用隐式默认。数量 cap 不代表容量安全。
voltage compatibility 不开放任意 tolerance：沿用冻结 class 映射；将来测量容差必须单位 kV、有限非负且有批准上界，不能跨标称等级。
seed 仅存在于明确随机的将来规则，否则必须 null/拒绝配置；不能在 frozen topology v1 增加 seed。
拒绝未知配置键，尤其 `force_complete`、`ignore_conflicts`、`auto_accept_s2`。config snapshot/hash 与批准声明绑定，修改配置后旧 validation token 失效。

## 9. Model / provenance / artifact design

以下是未来 schema 提案，不是对现有 models 的修改。

| Record / field | 类型、单位、可空性和约束 |
|---|---|
| CompletionProposal | proposal_id、case_id、feeder_id、input_manifest_hashes、base_graph_hash、rule/profile/config refs 必填字符串；candidate/rejection collections 必填，可为空 |
| SyntheticObject | synthetic_object_id 必填独立 ID；kind 为 CONNECTION/MV_ATTACHMENT/JUNCTION/TRANSFORMER/LV_BUS；不伪造 source_id |
| ownership | owning_case、owning_feeder 必填 EntityRef；ownership_basis enum 与 supporting refs/批准记录必填；未决不生成 |
| endpoints / role | connection 两端 derived node ID 和 port role 必填；其他 kind 不适用时 null；无隐式 winding/side |
| nominal_voltage_kv | 适用 node/port 时 Decimal 正有限值，单位 kV；candidate 可 null 并拒绝，accepted 必填；Transformer MV/LV 分字段 |
| source_entity_refs | existing T/Bus 等相关源引用数组；新 T 可空，但必须有 demand/role decision evidence；source ID/record locator 不伪造 |
| supporting_evidence_refs / conflict_refs | 必填数组，引用不可变 artifacts 中 evidence ID/row locator；conflict 为空须附完整检查结果，不表示未检查 |
| rule_id / rule_version / config_ref | 非空字符串；config_ref 含内容 hash；proposal 规则不等于 approved rule |
| decision_reason / policy_profile | 稳定 reason code + 可读说明、profile enum 必填 |
| deterministic_inputs | 必填 canonical inputs：候选集、工程特征、owner/voltage/port、选点/拒绝理由、input hashes、批次分配依据 |
| seed | int 或 null；仅随机 rule 可非空，记录随机流隔离版本 |
| software / artifact version | 软件 fingerprint、schema/rule/ID factory version、input manifests 必填 |
| validation | status、validator_version、proposal_hash、config_hash、risk metrics、rejection codes、approval refs 必填 |
| mapping | source refs ↔ derived IDs 为多对多显式记录；generated object 不反写 source |

Stable derived ID 提案：新 namespace `nanjing-synthetic-completion-id-v1`，SHA256 的 canonical ordered UTF-8 JSON 包含 namespace、kind、case、feeder、rule/version、source target key、semantic port role、attachment region key、config 内容 hash。
不含时间、绝对路径、随机执行顺序；同输入重跑幂等，不覆盖上一版本。生成新 T 的 key 来自批准的 device plan slot，不从 source factory 冒充 ID；device plan 未获批不得生成。

每条 connection 必须回答“为什么存在”：source target 缺什么、允许在哪个 region、为什么唯一/如何工程分配、采用何种假设、检查哪些负证据、是谁批准了 profile/业务语义。
人工 confirmation 也要作为有版本的外部 evidence，不能只留聊天文字然后当成 source fact。

未来完成 artifact（独立 `outputs/.../completion-<version>/`，只写新目录）：

| 文件 | 内容与验证 |
|---|---|
| manifest.json | schema/software/rule/config/input hashes、文件 hash/count、policy approval、base topology checksum |
| config_snapshot.json | 内容寻址配置与批准 profile，不含秘密 |
| completion_proposals.jsonl | 所有候选的固定输入和 selection decision |
| completed_topology.jsonl 或 cases/* | 不可变 base 引用 + 独立 overlay/物化 completed view；typed reload 验证两者一致 |
| synthetic_objects.jsonl | 全部新对象与 provenance，source/derived namespace 检查 |
| feeder_completion_details.jsonl | scope、target coverage、completion、readiness、source/inferred/synthetic/unresolved counts |
| rejected_candidates.jsonl | rejected/deferred reason、完整 evidence，不删不利候选 |
| risk_report.jsonl | before/after graph metrics、OPEN/voltage/port/shortcut/degree checks |
| evidence_composition.json | 从明细重汇总，包括继承 head 假设、S2 未批准数量 |
| source_derived_mapping.jsonl | 双向可追溯，source refs 保持只读 |
| report.md | 汇总、边界、未决问题、生成物非真实南京声明 |

每种 schema 都要冻结 required/nullable/enum/units/order 后再写实现。Verifier 校验 inventory/hash/count、引用完整性、ID 重算、source 不变、所有风险与 completion status 从明细独立重算；不能仅信任 manifest 中的 `validated=true`。

## 10. Future implementation architecture

流程：`analyze → propose → validate → apply → verify`。

- `models/`：最小 CompletionProposal、SyntheticObject、CompletionDecision、CompletionStatus/Provenance；无文件 I/O，无隐式全局配置。
- `analysis/`：case evidence/cohort refinement；保留 current E2.3-A adapter，不把 source dictionaries 泄漏到生成器。
- `generation/`：candidate generator 与 attachment selector 是纯函数，接收领域输入、显式 config、approved rule registry，返回 proposal/rejection；不写 graph。
- `validation/`：candidate validator/risk checker；返回绑定 proposal/base/config hashes 的结果。没有 VALIDATED 决策不得 apply。
- `generation/` completion engine：只消费 validated proposal；原 graph 不可变，创建独立 overlay。再检测重复/冲突与批次交互，禁止逐个通过却整体超限。
- `io/`：provenance writer、completion artifact writer、typed loader、verifier；序列化不决定拓扑。
- 独立 CLI：`analyze/propose/validate/apply/verify`；apply 必须明确 artifact、profile approval 和输出新目录，不提供自动 force。CLI 只编排。

保持 source interpreter / frozen v1 原封不动；不先搭插件框架、抽象工厂层或全局 engine。复用已有 EntityRef、canonical JSON 与校验模式，新增对象不塞入 source 字段。
候选结果与 accepted completion 分库存放，apply 不修改 accepted topology；accepted completion 是新的、经 review 的交付视图。

## 11. Slice implementation plan 与 Acceptance Gate

按最小范围推进；每个 slice 先规范和测试，再实现，交付后停等对应 review。

- [ ] **D1：冻结合同与 cohort refinement**。只增加 typed decisions、owner/MV/port/role evidence contract 与分析 artifact；确认 S0/S2 分母、OPEN 全 source inventory、unknown negative evidence；不生成 topology。
- [ ] **D2：conservative proposal-only**。首先验证 S0 的 1 条结构候选与其它拒绝样本；未获业务确认返回 rejected/deferred。输出独立 proposals；S2 13 条只保留 counterfactual inventory。
- [ ] **D3：validator/risk checker**。测试 OPEN 旁路、未知 voltage、跨 owner/identity、winding 冲突、平行边/自环/shortcut、batch degree、对称选点拒绝、hash/config tamper；独立复算与 source immutability。
- [ ] **D4：review 后 apply overlay**。只有获批 profile/业务 semantics 和 VALIDATED proposals 可进入；测试幂等、稳定 ID、字节复现、typed reload、原图及 source hash 不变；不随之进入 E3。
- [ ] **D5：全量 coverage acceptance**。5,159 case 完整 accounted、5,134 feeder 分层计数，所有 rejected/role-undetermined 保留；验收是覆盖审计完整，不是要求 100% completed。
- [ ] **后续独立 review**：ENGINEERING_LAYOUT、B 新设备、backbone 与 B/C deterministic rules 分开；E3、OpenDSS 另行明确授权。

实施前 gate 必须逐项回答：

| 问题 | Gate |
|---|---|
| 1. 何时可生成 connection？ | existing T 无声明，owner/MV/voltage/region/cap 明确，所有 hard checks 通过，独立 rule/profile 批准 |
| 2. 何时可新增 Transformer？ | 仅经确认的 B role+demand+count+MV/LV+capacity-source plan；当前无准入 |
| 3. 哪些 conflict 不可自动绕过？ | 第 4 节禁止表全部；profile level 不解除 |
| 4. zero-row 如何判角色？ | 甲方业务 evidence；名字/AP/SimConfig 不足，当前 1,713 ROLE_UNDETERMINED |
| 5. 选点如何 deterministic？ | 明确 region 筛选后唯一才取；tie 拒绝，禁止 ID/排序/随机 nearest |
| 6. 怎样检测错误拓扑？ | 第 7 节 checks，candidate 与批量 apply 后独立复验；未来电气仿真仍须另过 gate |
| 7. 如何区分 source？ | 新 namespace/overlay、per-object provenance、source hashes 与 mapping；不回写 source/accepted/frozen |
| 8. 谁可进入 E3？ | completion scope 通过、canonical blockers 已处理或有批准 adapter contract、无未决必需语义、E2/完成结果经 review 且用户明确授权 E3；当前 0 |
| 9. 谁仍 unresolved？ | B、D、无 accepted backbone、无唯一 region、owner/voltage/port/cap 未定、有引用但仍不达、未接受 S2 等按 reasons 保留 |
| 10. 哪些须业务确认？ | 设备工程归属与 MV 角色、B 角色/需求/数量、region/cap/支线物理语义；不是让用户批准任意连线 |

## 12. Open decisions 与 Q1/Q2/Q3

只有数据和现有合同不能决定的问题提交 review：

1. **A 的工程归属和设备语义**：是否可在指定白名单 case 内，把唯一 feeder 的无引用 Transformer 作为本 feeder 的 MV/LV 配变来建工程模型？需要明确 MV/LV/port 依据；不能笼统授权所有 case，尤其 44,596-device case。
2. **保守 attachment 的工程边界**：同意仅 accepted junction、全 case 无 OPEN/UNKNOWN、唯一 region、拒绝未决冲突的最小 profile 吗？region 最大 degree/设备数、支线物理含义需要业务设计依据，当前不替用户定数。
3. **B 角色与补充数据**：需甲方提供角色、需求、owner、设备数量/容量来源；无法提供时保留 ROLE_UNDETERMINED。无需 Transformer 的网络应走单独 role scope，而非伪造配变使 FULL。

S2、B/C 语义 review 是已知独立 gate，不是本文件默认批准项。

**Q1 — 仅 source-confirmed + deterministic inferred 能到哪里？**
现已批准 S0 为 0 target FULL。已计算 S2 和窄候选仍是 80 FULL（未批准），没有证明安全新增 FULL；307 个“所有目标有引用”仅是现有 connection evidence 必要条件 cohort，不是 achievable maximum。
不能给未来所有 deterministic 规则捏造一个精确最大值；在现有证据下 3,114 个 A 的完全无引用 target 与 1,713 个 B 的业务角色都不能由确定性推导凭空消失。

**Q2 — conservative synthetic 能到哪里？**
当前批准语义下新增 FULL=0。即使补足 A 的 owner/MV 语义，最窄 S0 筛选也仅 1 feeder/6 叶 attachment、0 新 FULL。
如果未来 S2 另获批准，唯一 junction、非 D、全 case 无 OPEN 的结构候选是 13 feeder/113 关系，目标 FULL 条件上界 93；扣除原 FULL 的 D 后为 43，且仍需度数上限、负证据和 completion scope 校验。
因此目前不能承诺 93 个完整安全拓扑，更不能把 697 的宽松包络写成 conservative coverage。

**Q3 — 接近/达到 5,134 需要什么？**
至少需要：批准更多 switch/port deterministic 语义；明确 A 的 owner/MV/LV 及人工工程布局；为无 usable backbone 的 case 提供主干工程设计；为 B 确认角色与需求，在应有配变时批准数量计划；为 referenced-but-incomplete 提供端口/连接补证；对 D 获得合法身份、电压、归属裁决并保留 OPEN operating constraints；最后独立完成参数、LV、Load/DER/profile 和仿真验收。
这些条件不保证数量接近 100%。如果要求每个 source case 原样覆盖且全部 source Transformer 带电，某些 OPEN/voltage/ownership 边界可能与目标直接冲突。不能通过 synthetic bridge 消除这一矛盾。
更强的完全人工 benchmark 需要另建 alternate dataset，并明确不计作南京 evidence-preserving completion。

推荐先做 **D1（合同与 cohort refinement，仍无 topology apply）**；它解决 owner/MV/region gate，而不是再次追求一个简单恢复规则。
本次提交 review 后停止，待合同明确批准再进入相应 slice；不进入 synthetic implementation 或 E3。

## 13. 分析材料与复现

- 只读分析程序：[e23d_feasibility.py](../analysis/e23d_feasibility.py)。仅分析，不属于 `src/` 产品实现。
- 全量逐 Feeder 筛选：`outputs/nanjing-e2-3-d/design-screening-v2/feeder_screening.jsonl`，5,134 行，保留 case/Feeder ID、原 case key、A/B/C/D、source 行数、S0/S2 junction 数/degree、剩余 referenced target、OPEN 数、witness/frontier 计数。
- 汇总：同目录 `summary.json`，保留所有筛选 case IDs、源字段非空统计、11 项 SimConfig 分布、degree sensitivity 和输入 checksum。它是 design counterfactual report，不是正式 completion artifact。
- 验证记录：同目录 `verification.json`；分析输出校验和：`analysis_checksums.json`。初次计算与最终版的全部准入/覆盖汇总一致；最终版两个分析文件与 `design-screening-v2-reproduction` 独立重算逐字节一致。degree 使用 multigraph incident branch 数，平行边分别计数。

```bash
.venv/bin/python docs/analysis/e23d_feasibility.py \
  --output outputs/nanjing-e2-3-d/design-screening-reproduction
```

输出目录必须不存在；不允许输出到 source/E2/E2.3-A。程序没有 connection apply、设备生成或 accepted graph 写入。
复现前须运行现有五组 verifier 并核对输入 manifest；本轮已执行。S0 BFS 与持久化 reachable_node_ids 逐 case 一致；summary 的 A/B/C/D、无引用 target 数、S0/S2 FULL 均有断言。
全部 5,159 case 的 Transformer evidence 中原始 ID 跨 case 重复数为 0；仍不证明归属。跨 case Transformer 原始 ID 重复审计属于风险检查，不构成可跨 case 合并许可；本分析的 feeder-scope 结果不替代 25 个无 Feeder case 的 ownership gate。
