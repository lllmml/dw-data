# Q-CONN-001

## 问题

`FromBus` / `ToBus` 的真实电气连接语义是什么？

## 当前证据

南京源数据中的端点引用可在同一 case 内精确命中 Bus、Switch、Station、Transformer、AccessPoint 等不同 source entity type，呈现为 mixed source graph。字面精确命中只能证明源引用关系。

## 当前安全行为

保留原始引用及记录定位；只按版本化候选矩阵解析 source reference，不将解析结果自动提升为已确认电气连接，不执行拓扑修复或母线—支路投影。

## 影响阶段

CSV → Canonical mapper、topology projection、OpenDSS generation、QSTS、operator adapters。

## Owner

甲方 / 配电网领域专家。

## Status

OPEN

# Q-PHASE-001

## 问题

`Phase` 字段采用什么编码规则？

## 当前证据

当前南京数据各类相位字段均为空，现有资料没有提供编码表或缺相表达规则。

## 当前安全行为

相位保持 `null`；不默认 `ABC`，不自行定义枚举归一化或缺相规则。

## 影响阶段

CSV → Canonical mapper、topology projection、OpenDSS generation、QSTS、operator adapters。

## Owner

甲方 / 配电网领域专家。

## Status

OPEN

# Q-TRANSFORMER-001

## 问题

Transformer 高低压端与 winding、Terminal 顺序之间的稳定对应关系是什么？

## 当前证据

源 schema 提供 HighVoltage、LowVoltage、ConnHV、ConnLV 以及 FromBus、ToBus 字段，但当前端点、电压和接线字段均为空，缺少实例或权威说明验证其顺序关系。映射规范中的 1、2 号 winding 对应仍待领域确认。

## 当前安全行为

保留源字段及其 provenance；在确认前不根据高低压字段推导已确认的 Terminal 连接、额外绕组或拓扑方向。

## 影响阶段

CSV → Canonical mapper、topology projection、data completion、OpenDSS generation、QSTS。

## Owner

甲方 / 变压器建模领域专家。

## Status

OPEN

# Q-SIMCONFIG-001

## 问题

SimConfig 是否代表真实交付配置，而不是示例或模板配置？

## 当前证据

全部 source case directory 中的 11 个 SimConfig 键值完全相同，且 `SourceBus`、`OutputVoltageBus` 使用当前无法解析的 `SUB_10KV`。

## 当前安全行为

仅将其作为源配置声明保留并记录字段级 provenance；不标记为已验证仿真参数，不据此判定 OpenDSS Ready。

## 影响阶段

CSV → Canonical mapper、OpenDSS generation、QSTS。

## Owner

甲方 / 仿真配置负责人。

## Status

OPEN

# Q-CASE-001

## 问题

一个 source case directory 是否代表一个独立 `GridCase`？

## 当前证据

南京 ZIP 中每个目录均包含同一组 12 类 CSV；当前版本化映射规范以目录相对路径作为 `source_case_key`，并规定一个目录形成一个 `GridCase`。其中 25 个目录的 Feeder 文件只有表头。

## 当前安全行为

按当前映射合同将每个目录保留为独立 `GridCase`；即使 Feeder 缺失也不删除 case，而以 `GRID_CASE_FEEDER_MISSING` quality issue 表达。确认前不跨目录合并或补配 Feeder。

## 影响阶段

Nanjing raw intake、CSV → Canonical mapper、全部后续 case 级处理。

## Owner

甲方 / 数据治理负责人。

## Status

OPEN
