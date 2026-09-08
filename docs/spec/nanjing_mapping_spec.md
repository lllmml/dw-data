# 南京 CSV 到 Canonical Model 映射规范

## 1. 文档信息

| 项目 | 值 |
|---|---|
| 状态 | Draft，待字段语义确认 |
| 映射 ID | `nanjing_csv` |
| 映射版本 | `0.1.0` |
| Canonical 合同 | `docs/spec/canonical_data_spec.md` `0.2.0` |
| 数据审计 | `docs/spec/nanjing_source_audit.md` |

本文定义南京数据 12 类 CSV 到 Canonical Model 的 Source Adapter 映射。它不定义参数补全、连接修复、OpenDSS 导出或生成规则。

## 2. 通用导入合同

### 2.1 算例和记录定位

- 每个压缩包内馈线目录形成一个 `GridCase`；`source_case_key` 为目录相对路径的精确保留值。
- 不以 `Feeder_ID` 作为唯一建 case 的依据，因为存在只有表头的 `Feeder` 文件。
- 每条数据行必须建立稳定的 `source_record_ref = 压缩包内相对文件路径 + 1-based 数据行号`。行号不包含表头。
- 所有由该行直接建立的实体记录使用 `record_origin=SOURCE`、`source_mapping_id=nanjing_csv` 和 `source_mapping_version=0.1.0`。

### 2.2 通用字段转换

1. 所有 `*_ID` 和引用列按字符串读取，不得先转为整数或浮点数。
2. 源空字符串映射为 `null`，不生成默认值；字符串 `"0"` 保留原文并产生适用的质量事件。
3. 单位包含在列名中的数值直接解析为 Canonical 对应单位的 `Decimal`。
4. 每个设备源 ID 映射到 `Equipment.source_id`；子类型通过同一 `equipment_id` 关联。
5. `FromBus`、`ToBus` 和 `*_Bus` 等端点列先映射到 `Terminal.raw_connected_ref`。
6. 唯一精确命中候选实体时可填写 `resolved_source_ref` 并标记 `source_ref_status=EXACT`；这仍不是物理连接确认。
7. 本映射不直接填写 `Terminal.connectivity_node_ref`。在连接语义获得确认前，`connectivity_status=NOT_ASSESSED`。
8. 科学计数法展开、疑似精度修复、模糊或近似匹配不得作为直接映射；确认后必须以 `REPAIRED` 字段级 provenance 记录。
9. 直接复制或简单类型/枚举归一化的字段依靠 `source_record_ref + source_mapping_id + source_mapping_version` 反查，不要求逐字段物理生成 `FieldProvenance`。
10. 重复源 ID 不得覆盖。Canonical ID 必须纳入 `source_record_ref` 进行消歧，并设置相应 `identity_status`。

### 2.3 通用枚举和量测规则

- `Open` / `Closed` 映射为 `OPEN` / `CLOSED`；未知原文保留并映射为 `UNKNOWN`。
- `TRUE/FALSE`、`True/False` 不区分大小写映射为 Boolean；其他值形成质量事件。
- 相位文本若非空，按经确认的相位编码解析；当前相位编码未确认且字段全空，不得默认三相。
- 无时间戳的开关量测映射为 `OperationalSeries.series_kind=SNAPSHOT`，点级和序列级质量包含 `TIME_UNKNOWN`，`timestamp=null`。

## 3. 文件映射

### 3.1 `01_Station.csv`

每行建立一条 `Station`。

| 原始字段 | Canonical 字段 | 转换/约束 |
|---|---|---|
| `Station_ID` | `station.source_id`；派生 `station.station_id` | 原文字符串；逻辑键包含 case 和实体类型 |
| `Station_Type` | `station.station_type` | 保留原文；受控值确认后可归一化 |
| `Station_Name` | `station.name` | 原文字符串 |
| `Station_Voltage_Level` | `station.nominal_voltage_kv` | Decimal，kV |
| `Station_Lon` | `station.longitude` | Decimal；当前为空；CRS 未确认不得解释 |
| `Station_Lat` | `station.latitude` | Decimal；当前为空；CRS 未确认不得解释 |

### 3.2 `02_Bus.csv`

每行建立一条 `Bus`。

| 原始字段 | Canonical 字段 | 转换/约束 |
|---|---|---|
| `Bus_ID` | `bus.source_id`；派生 `bus.bus_id` | 字符串，允许 `_bs` 等后缀 |
| `Bus_Name` | `bus.name` | 原文字符串 |
| `Bus_BaseKV` | `bus.base_voltage_kv` | Decimal，kV |
| `Bus_Phase` | `bus.phases` | 解析为 PhaseSet；当前全空，保持 null |
| `Bus_Station_ID` | `bus.station_source_ref.raw_ref`、`resolved_source_ref` 和状态 | 精确匹配只确认 Station 源引用；科学计数法值仅作修复候选 |
| `Bus_IsSource` | `bus.is_source` | Boolean；仅保留源声明 |

### 3.3 `03_Switch.csv`

每行建立 `Equipment(equipment_type=SWITCH)`、`SwitchingDevice` 和两个 Terminal。源端点为空仍保留端点位置。

| 原始字段 | Canonical 字段 | 转换/约束 |
|---|---|---|
| `Switch_ID` | `equipment.source_id`；派生 `equipment.equipment_id` | 重复/冲突不得覆盖 |
| `Switch_FromBus` | `terminal[1].raw_connected_ref`、`resolved_source_ref` 和状态 | 候选类型可为 Bus、Switch、Station、Transformer、AccessPoint；不填连接节点 |
| `Switch_ToBus` | `terminal[2].raw_connected_ref`、`resolved_source_ref` 和状态 | 同上 |
| `Switch_Phase` | `equipment.phases` | 当前全空，保持 null |
| `Switch_NormalState` | `switching_device.normal_state` | `Open/Closed` 枚举映射 |
| `Switch_IsTie` | `switching_device.is_tie` | Boolean |
| `Switch_RatedCurrent_A` | `switching_device.rated_current_a` | Decimal，A；当前全空 |
| `Switch_HasMeasurement` | `switching_device.measurement_capable` | Boolean |
| `Switch_Meas_I_A` | `operational_series(metric=current, unit=A)` 快照值 | 时间为空时 `TIME_UNKNOWN` |
| `Switch_Meas_P_kW` | `operational_series(metric=active_power, unit=kW)` 快照值 | 保留负值；方向和离群另报质量问题 |
| `Switch_Meas_Q_kVAR` | `operational_series(metric=reactive_power, unit=kvar)` 快照值 | 保留负值；方向和离群另报质量问题 |
| `Switch_Meas_Timestamp` | 上述快照值的 `timestamp` | 当前全空；不得伪造时间 |

### 3.4 `04_Disconnector.csv`

每行建立 `Equipment(equipment_type=DISCONNECTOR)`、`SwitchingDevice` 和两个 Terminal。

| 原始字段 | Canonical 字段 | 转换/约束 |
|---|---|---|
| `Disconnector_ID` | `equipment.source_id`；派生 `equipment.equipment_id` | 原文字符串 |
| `Disconnector_FromBus` | `terminal[1].raw_connected_ref`、`resolved_source_ref` 和状态 | 当前全空，`source_ref_status=MISSING` |
| `Disconnector_ToBus` | `terminal[2].raw_connected_ref`、`resolved_source_ref` 和状态 | 当前全空，`source_ref_status=MISSING` |
| `Disconnector_NormalState` | `switching_device.normal_state` | `Open/Closed` 枚举映射 |

### 3.5 `05_Feeder.csv`

每行建立一条 `Feeder`。没有数据行的目录仍保留由目录建立的 `GridCase`，并形成数据质量事件。

| 原始字段 | Canonical 字段 | 转换/约束 |
|---|---|---|
| `Feeder_ID` | `feeder.source_id`；派生 `feeder.feeder_id` | 字符串 |
| `Feeder_Name` | `feeder.name` | 原文字符串，不作为主键 |
| `Feeder_SourceBus` | `feeder.source_bus_source_ref` | 解析源 Bus 引用；精确命中不等于完成消费者连接投影 |

### 3.6 `06_EarthingSwitch.csv`

每行建立 `Equipment(equipment_type=EARTHING_SWITCH)`、`SwitchingDevice` 和一个 Terminal。

| 原始字段 | Canonical 字段 | 转换/约束 |
|---|---|---|
| `EarthingSwitch_ID` | `equipment.source_id`；派生 `equipment.equipment_id` | 原文字符串 |
| `EarthingSwitch_Bus` | `terminal[1].raw_connected_ref`、`resolved_source_ref` 和状态 | 当前全空，`source_ref_status=MISSING` |
| `EarthingSwitch_State` | `switching_device.observed_state` | 字段未说明是否常态，不映射到 `normal_state` |

### 3.7 `07_AccessPoint.csv`

每行建立 `Equipment(equipment_type=ACCESS_POINT)`、`AccessPoint` 和一个 Terminal。AccessPoint 不自动转为 Load 或 DER。

| 原始字段 | Canonical 字段 | 转换/约束 |
|---|---|---|
| `AccessPoint_ID` | `equipment.source_id`；派生 `equipment.equipment_id` | 原文字符串 |
| `AccessPoint_Bus` | `terminal[1].raw_connected_ref`、`resolved_source_ref` 和状态 | 当前全空；不填连接节点 |
| `AccessPoint_Phase` | `equipment.phases` | 当前全空，保持 null |
| `AccessPoint_UserType` | `access_point.user_type` | 当前全空 |
| `AccessPoint_ContractCapacity_kVA` | `access_point.contract_capacity_kva` | Decimal，kVA；当前全空 |

### 3.8 `08_Line.csv`

每行建立 `Equipment(equipment_type=LINE)`、`Line` 和两个 Terminal。

| 原始字段 | Canonical 字段 | 转换/约束 |
|---|---|---|
| `Line_ID` | `equipment.source_id`；派生 `equipment.equipment_id` | 原文字符串 |
| `Line_FromBus` | `terminal[1].raw_connected_ref`、`resolved_source_ref` 和状态 | 候选可为多种实体类型；不填连接节点 |
| `Line_ToBus` | `terminal[2].raw_connected_ref`、`resolved_source_ref` 和状态 | 同上 |
| `Line_Phase` | `equipment.phases` | 当前全空，保持 null |
| `Line_Type` | `line.line_type` | 当前全空 |
| `Line_Model` | `line.model` | 当前全空 |
| `Line_Length_km` | `line.length_km` | Decimal，km；当前全空 |
| `Line_R1_ohm_per_km` | `line.r1_ohm_per_km` | Decimal，Ω/km；当前全空 |
| `Line_X1_ohm_per_km` | `line.x1_ohm_per_km` | Decimal，Ω/km；当前全空 |
| `Line_NumCircuits` | `line.number_of_circuits` | 正整数；当前全空 |

源文件未提供的 Canonical 零序、电容或额定电流字段保持 null；本映射不补全。

### 3.9 `09_Transformer.csv`

每行建立 `Equipment(equipment_type=TRANSFORMER)`、`Transformer`、两个 Terminal 和两个 `TransformerWinding`。两绕组只对应当前源列结构，不推断额外绕组。

| 原始字段 | Canonical 字段 | 转换/约束 |
|---|---|---|
| `Transformer_ID` | `equipment.source_id`；派生 `equipment.equipment_id` | 原文字符串 |
| `Transformer_FromBus` | `terminal[1].raw_connected_ref`、`resolved_source_ref` 和状态 | 当前全空；不填连接节点 |
| `Transformer_ToBus` | `terminal[2].raw_connected_ref`、`resolved_source_ref` 和状态 | 当前全空；不填连接节点 |
| `Transformer_Phase` | `equipment.phases` | 当前全空，保持 null |
| `Transformer_RatedCapacity_kVA` | `transformer.rated_capacity_kva` | Decimal，kVA；源值 0 保留并标记质量问题 |
| `Transformer_HighVoltage_kV` | `transformer_winding[1].rated_voltage_kv` | Decimal，kV；当前全空 |
| `Transformer_LowVoltage_kV` | `transformer_winding[2].rated_voltage_kv` | Decimal，kV；当前全空 |
| `Transformer_R_pct` | `transformer.r_pct` | Decimal，%；当前全空 |
| `Transformer_X_pct` | `transformer.x_pct` | Decimal，%；当前全空 |
| `Transformer_ConnHV` | `transformer_winding[1].connection` | 当前全空 |
| `Transformer_ConnLV` | `transformer_winding[2].connection` | 当前全空 |
| `Transformer_NumTaps` | `transformer.number_of_taps` | 整数；当前全空 |
| `Transformer_TapRange` | `transformer.tap_range_raw` | 当前全空；格式确认前不解析为 min/max |

### 3.10 `10_Load.csv`

每行建立 `Equipment(equipment_type=LOAD)`、`Load` 和一个 Terminal；当前文件均无数据行，本节只规定已存在的源 schema 映射，不授权生成 Load。

| 原始字段 | Canonical 字段 | 转换/约束 |
|---|---|---|
| `Load_ID` | `equipment.source_id`；派生 `equipment.equipment_id` | 原文字符串 |
| `Load_Bus` | `terminal[1].raw_connected_ref`、`resolved_source_ref` 和状态 | 不预设能解析或已连接 |
| `Load_Phase` | `equipment.phases` | PhaseSet；编码未确认时保留原文和质量状态 |
| `Load_P_kW` | `load.active_power_kw` | Decimal，kW |
| `Load_Q_kVAR` | `load.reactive_power_kvar` | Decimal，kvar |
| `Load_PF` | `load.power_factor` | Decimal；超前/滞后方向不能从该列单独推断 |

### 3.11 `11_DER.csv`

每行建立 `Equipment(equipment_type=DER)`、`DER` 和一个 Terminal；当前文件均无数据行，本节不授权生成 DER。

| 原始字段 | Canonical 字段 | 转换/约束 |
|---|---|---|
| `DER_ID` | `equipment.source_id`；派生 `equipment.equipment_id` | 原文字符串 |
| `DER_Bus` | `terminal[1].raw_connected_ref`、`resolved_source_ref` 和状态 | 不预设能解析或已连接 |
| `DER_Phase` | `equipment.phases` | PhaseSet；编码未确认时保留原文和质量状态 |
| `DER_Type` | `der.der_type` | 开放枚举，保留未知原文 |
| `DER_RatedCapacity_kVA` | `der.rated_capacity_kva` | Decimal，kVA |
| `DER_RatedPower_kW` | `der.rated_power_kw` | Decimal，kW |
| `DER_PF` | `der.power_factor` | Decimal，绝对值不大于 1 |
| `DER_ConnType` | `der.connection` | 中立枚举/字符串 |
| `DER_ControlMode` | `der.control_mode` | 中立枚举/字符串，不绑定 OpenDSS |

### 3.12 `12_SimConfig.csv`

同一 case 中的键值行聚合为一条 `SimulationProfile`。该记录只保留源配置声明，不表示 OpenDSS 或其他引擎就绪。每个聚合字段必须能够反查对应键值行的 `source_record_ref`；由于属于多行聚合，这是需要字段级 `SOURCE` provenance 的非平凡转换。

| `Config_Key` | Canonical 字段 | 转换/约束 |
|---|---|---|
| `SimulationMode` | `simulation_profile.mode` | 原文加受控映射 |
| `Algorithm` | `simulation_profile.solver` | 原文加受控映射 |
| `BaseFrequency` | `simulation_profile.frequency_hz` | Decimal，Hz |
| `BaseVoltage_kV` | `simulation_profile.source_voltage_kv` | Decimal，kV |
| `SourceBus` | `simulation_profile.source_bus_source_ref` | 保留 raw ref；`SUB_10KV` 当前未解析；不填连接节点 |
| `OutputVoltageBus` | `simulation_profile.output_voltage_bus_source_ref` | 保留 raw ref；`SUB_10KV` 当前未解析 |
| `MaxIterations` | `simulation_profile.max_iterations` | 正整数 |
| `Tolerance` | `simulation_profile.tolerance` | Decimal；精确收敛语义待消费者规范确认 |
| `MVAsc3` | `simulation_profile.mva_sc3` | Decimal，MVA |
| `MVAsc1` | `simulation_profile.mva_sc1` | Decimal，MVA |
| `UnitSystem` | `simulation_profile.unit_system` | 原文加受控映射 |
| 其他键 | `simulation_profile.extensions["nanjing.<key>"]` | 原值完整保留并记录字段级来源 |

## 4. 南京 Source Adapter 的 Import Complete

对本映射，Import Complete 至少要求：

- 12 类文件均被识别；缺文件、只有表头或表头偏差均形成明确质量事件；
- 每条源数据行都有 `source_record_ref`；
- 所有 ID、原始引用和非空字段已无损保留，转换失败保留原文；
- 重复或冲突 ID 未被覆盖或静默合并；
- 端点的源引用状态已记录，且未把精确匹配冒充为物理连接；
- 未知枚举和异常数值已形成质量事件。

Import Complete 不要求所有引用精确解析，不要求 `connectivity_node_ref` 非空，也不表示 Snapshot、QSTS、OpenDSS 或任何算子就绪。

## 5. 本映射不做的事情

- 不生成线路参数、相位、Load、DER 或时序数据；
- 不修复长 ID、重复冲突或空端点；
- 不根据 mixed source graph 构造母线—支路图；
- 不把统一 `SimConfig` 值标记为真实、独立或已验证参数；
- 不定义 OpenDSS readiness 或未来算子输入合同。

## 6. 映射待确认事项

1. 甲方是否确认所有 12 类表头及字段单位？
2. `FromBus` / `ToBus` 的允许目标类型和业务含义是什么？
3. 相位文本若后续出现，其编码表是什么？
4. `EarthingSwitch_State` 应继续映射为 `observed_state`，还是有资料证明其为 `normal_state`？
5. 变压器高低压列是否总能稳定对应 1、2 号绕组和端点顺序？
6. `SimConfig` 的 11 个键是否属于交付数据事实，还是示例/模板配置？
