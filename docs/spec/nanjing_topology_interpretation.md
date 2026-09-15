# 南京派生拓扑合同

版本：`nanjing-derived-topology-v1 / 1.0.0`。状态：用户冻结的 E0 规则；E2 已实现，等待全量覆盖报告 review。

## 边界

EXACT source reference ≠ confirmed real-world connectivity ≠ accepted v1 derived electrical projection。
Source Terminal 的 raw/resolved reference 和 NOT_ASSESSED connectivity 不回写。
Q-CONN-001、Q-TRANSFORMER-001 保持 OPEN。本合同不修改 source candidate matrix。

## 电源与电压

有效 feeder anchor 必须有唯一 UNIQUE Feeder、精确唯一 source Bus 引用。
用户全量审计指出该 Bus 为 110 kV，不能直接充当 distribution source。
每个有效 feeder 在 E2 建立 deterministic synthetic MV feeder-head bus；保留 Feeder、
source Bus 和 supporting source refs 的映射。明确 20kV 名称取 20.0 kV，明确 10kV
取 10.5 kV；其余读取显式 voltage fallback，不散落默认数值。名称冲突报告，不改源值。
Vsource 从该 MV head 开始；不生成 110/MV 站内主变，上游站内网络不在 v1 范围。

## 规则（版本均为 1.0.0）

- `BUS_JUNCTION_V1`：Line endpoint 精确唯一命中 Bus，可作为 electrical junction；
  必须由 interpreter 输出映射，不允许 exporter 直接读 raw endpoint。电压冲突需报告，
  不得将 source 110 kV Bus 静默降压或代替 MV head。
- `STATION_FEEDER_HEAD_V1`：仅 Line_FromBus 精确唯一命中 Station、case 唯一 feeder、
  feeder source Bus EXACT 且该 Bus.station_source_ref EXACT 指向同一 Station，才将
  Line source side 投影到 synthetic MV head。Line_ToBus→Station 不适用。
- `SERIES_SWITCH_V1`：Switch identity/reference 唯一；source Line graph 恰好两条不同
  incident Line，一条 Line_ToBus 指向它，另一条 Line_FromBus 指向它；无其它显式
  source evidence 冲突。映射为 two-terminal switch。normal CLOSED 导通、OPEN 断开，
  UNKNOWN 不按 CLOSED。degree=1、degree>2、同方向、duplicate/conflict 均不适用。
- `LEAF_TRANSFORMER_MV_V1`：Transformer identity/reference 唯一；仅有一条 incident
  source Line 且为 Line_ToBus→Transformer；无显式 endpoint evidence 冲突。该端解释
  为配变 MV/HV attachment；后续 completed 层可建立一对一 synthetic LV bus。
  Line_FromBus→Transformer、多 incident Line、身份冲突均不适用。
- AccessPoint 保留并报告 unsupported/excluded，不用于负荷布点。

所有未命中规则的 mixed connection 均 unresolved/excluded。incident count 基于完整
source Line evidence，不能先删除不利证据再满足 degree 条件。ambiguous identity 不任选。
显式但语义不明的 endpoint evidence 不算自动兼容；E2 应保守报告不能证实无冲突。
不 fuzzy match、不随机接线、不为辐射性删边、不依赖 ID 大小或排序选择物理连接。

每条 mapping 必须保存 source case/entity/terminal refs、完整 supporting source refs、
rule_id、rule_version、派生目标 ID、结果和 exclusion reason。派生 ID 使用独立版本化
factory，不调用 SourceImportIdFactory 伪造源身份。E2 实现前冻结有序 hash 输入和字段表。

## E2 强制 coverage gate

全部 5,159 cases 的 topology-only audit 必须报告：total cases、valid feeder anchors、
synthetic MV heads、source/included/excluded lines、BUS mappings、STATION projections、
SERIES_SWITCH projected/OPEN/excluded、LEAF_TRANSFORMER projected、excluded transformers、
source-reachable modeled transformers、至少一个 reachable transformer 的 cases、usable
subgraph cases、unresolved/ambiguous/unsupported counts、exclusion reasons distribution。
计数口径同时区分 source rows、published entities、projection 和 source-reachable subset。
报告须带输入 checksum、规则版本、配置和逐 case 明细，并由用户 review。
报告通过前禁止 Load/PV completion、OpenDSS exporter；tiny fixture 不替代真实覆盖审计。

## E2 派生映射记录字段（E0 冻结边界）

| 字段 | 类型/可空性 | 含义 |
|---|---|---|
| source_case_ref | EntityRef，必需 | 既有 GridCase |
| source_entity_ref | EntityRef，必需 | 被投影的既有源实体 |
| source_terminal_ref | EntityRef，可空 | 来源为明确源 Terminal 时填写，不伪造端口 |
| supporting_source_refs | 有序且去重的 source_record_ref tuple，必需 | 规则判定全部源证据；多记录不压成一个 locator |
| rule_id / rule_version | 非空 string，必需 | 上述版本化规则 |
| projection_status | PROJECTED / UNRESOLVED / AMBIGUOUS / UNSUPPORTED / EXCLUDED | 独立于 source resolver status |
| derived_target_ids | 派生 ID tuple，必需，可为空 | 未投影时为空；不伪造 source EntityRef |
| exclusion_reason | 非空稳定 string code，可空 | 非 PROJECTED 时必需 |
| nominal_voltage_kv | Decimal，可空，kV | 仅适用电气节点；非空必须为正，MV head 必需 |
| voltage_source | NAME_INFERENCE / SOURCE / DEFAULT，可空 | 与电压规则/配置一起追溯，不修改源电压 |

派生 ID namespace 固定 `nanjing-derived-topology-id-v1`。采用 UTF-8 紧凑有序 JSON 数组
[namespace, kind, case_id, owning_source_entity_id, role] 的 SHA256，格式 `<kind>:<hex>`。
kind/role 仅允许 E2 明文列举的 feeder-head、junction、switch-port 等，无时间/绝对路径/
seed 输入；拓扑不得随采样 seed 改变。具体目标集合和端口 role 在 E2 实现测试中落实。

## E2 最小 topology configuration

配置文件：`configs/nanjing_topology.toml`。E2 已实现配置加载与 fail-fast 校验。

| 字段 | 类型 | 默认值 | 约束与含义 |
|---|---|---|---|
| fallback_nominal_voltage_kv | 有限数值，kV | 10.5 | 必须 > 0；synthetic modeling default，不是 source fact |

E2 读取配置后必须验证有限且 > 0，否则 fail fast。算法从此字段读取 fallback，不另设
散落的默认数值。明确 20 kV 名称 → 20.0 kV，明确 10 kV 名称 → 10.5 kV，二者标记
voltage_source=NAME_INFERENCE；其它名称使用配置值并标记 DEFAULT。不修改 Bus_BaseKV
或 source SimConfig；名称/电压冲突保留明确的 conflict/unresolved 原因，不静默覆盖。
E2 coverage report 额外报告 MV heads by NAME_INFERENCE、MV heads by DEFAULT、
voltage-conflict / unresolved counts。当前不引入 E3 line/load/DER configuration system。

## E2 implementation contract

Derived ID kind/role pairs are closed: `feeder-head/mv`, `junction/bus`,
`switch-port/in`, `switch-port/out`, `switch/series`, `transformer-mv/mv`,
`line/connection`. Ownership is the existing Feeder, Bus or Equipment ID.
All derived nodes have a positive finite Decimal voltage in kV; branches contain
existing derived endpoint IDs and a conducting boolean. Transformer attachments
are MV nodes only. Source references retain their original EntityRef types.
Configuration rejects unknown keys (including seed), booleans and nonpositive or
nonfinite numbers. Explicit naming uses case directory basename and Feeder.name,
case insensitive standalone numeric `10/20` followed by optional whitespace and
`kV`; simultaneous 10 and 20 evidence excludes the head with NAME_VOLTAGE_CONFLICT.
10 and 10.5 source voltages are compatible with derived 10.5; other explicit
positive Bus voltages must match. Invalid explicit voltage evidence is excluded.
Upstream source Bus voltage is provenance only and exempt from MV comparison.
SimConfig voltage disagreements are reported separately and never rewritten.

Supporting locators are lexicographically ordered and deduplicated, including all
accountability rows for every participating entity and all incident source rows.
Explicit Switch/Transformer endpoint values are conservatively excluded because
compatibility semantics are unconfirmed. Malformed Line evidence prevents device
degree certification. Distinct incident lines are counted by raw Line_ID, with
repeated/missing identities excluded rather than selecting a representative.

Usable means a valid synthetic head and at least one accepted conducting Line
reachable from it. A reachable transformer is an independent measure; neither
measure declares OpenDSS Ready. Rings are retained. Missing anchors do not prevent
local structural projections, but no node is source-reachable without a head.

### Persisted derived records

| Record | Required fields | Nullable fields / semantics |
|---|---|---|
| ElectricalNode | node_id, closed DerivedRole, source_entity_ref, nominal_voltage_kv, voltage_source | none; voltage in kV |
| ElectricalBranch | branch_id, closed DerivedRole, source_entity_ref, from_node_id, to_node_id, conducting | none; both endpoints refer to derived nodes |
| ElectricalTopology | case_id, nodes, branches, reachable_node_ids, reachable_transformer_ids | feeder_head_id may be null; all collections ordered tuples |
| TopologyCaseResult | topology, projections, coverage | none |
| TopologyCoverage | case_id, feeder_anchor_status, usable_subgraph, has_reachable_transformer, counts, projection_status_counts, exclusion_reasons, rule_counts | source_case_key preserves source null; nominal_voltage_kv and voltage_source null on conflicting names |

Projection fields remain as frozen above. IDs are strings from the independent factory,
not Canonical source identities. Persisted enums use their exact values; Decimal uses
canonical JSON strings. Collections have deterministic order; derived-target tuples use
semantic port order. Supporting locators use lexical ordering only for serialization,
never to choose connectivity.

Unpublished conflicting/rejected source identity groups use the existing GridCase as
source_entity_ref and retain every raw locator; no fake source EntityRef is created.
Line source-row, published-entity, unpublished-row/group and accepted/excluded-published
counts remain separate. Switch/Transformer/AccessPoint candidates include unpublished
identity groups; source-row and published counts are reported independently. Device
rule counts exclude repeated Line endpoint mappings; global projection/reason counts
include every mapping. BUS/STATION counts are per endpoint. Closed/open/unknown counts
refer only to projected switches. E1 canonical-invalid cases remain in the audit.

Voltage-bearing projections and voltage audits also retain the feeder-anchor evidence
that determined derived voltage; node-local evidence alone is insufficient when the
voltage came from Feeder.name. The input artifact, config snapshot and rule versions
are bound together by the E2 manifest. Reload validates graph endpoints, target IDs,
reachable Transformer subset and the usable/reachable report flags.
