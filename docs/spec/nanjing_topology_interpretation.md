# 南京派生拓扑合同

版本：`nanjing-derived-topology-v1 / 1.0.0`。状态：用户冻结的 E0 规则；E2 尚未实现。

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
