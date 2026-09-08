# Source Identity Classification Contract 规范

## 1. 文档信息

| 项目 | 值 |
|---|---|
| 状态 | Source Import MVP 实现基线 |
| 规范版本 | `0.1.0` |
| Canonical 合同 | `docs/spec/canonical_data_spec.md` `0.3.0` |
| Source Import 基线 | `docs/spec/source_import_foundation.md` `0.1.0` |
| 首个 Source Mapping | `nanjing_csv` `0.2.0` |

本文只定义源实体身份分组、重复分类和结果表达。它不定义 Canonical 字段映射、
源引用解析、connectivity、拓扑、合并或数据治理规则。

## 2. 适用记录

MVP 对具有 source ID 的顶层源实体执行身份分类：

- `STATION` -> Canonical `Station`；
- `FEEDER` -> Canonical `Feeder`；
- `BUS` -> Canonical `Bus`；
- `LINE`、`SWITCH`、`DISCONNECTOR`、`EARTHING_SWITCH`、`TRANSFORMER`、
  `ACCESS_POINT`、`LOAD`、`DER` -> Canonical `Equipment`。

Equipment 必须使用具体 source entity type 分组，不得先折叠为通用
`EQUIPMENT`。例如相同 source ID 的 `LINE` 与 `SWITCH` 属于不同组。

缺少必需 source ID 的 raw record 不进入身份分类；它按 Source Import foundation
作为 record-level fatal mapping error 进入 unmapped source record accounting。

## 3. 分类输入

每个 `SourceIdentityRecord` 必须包含：

| 字段 | 类型 | 必需性 | 说明 |
|---|---|---:|---|
| `case_id` | `CanonicalId` | R | 已由现有 ID factory 建立的所属 case ID |
| `source_entity_type` | `SourceEntityType` | R | 第 2 节定义的具体源实体类型 |
| `source_id` | `SourceId` | R | intake 解码后的非空原始字符串 |
| `source_record_ref` | string | R | Intake 提供的稳定记录 locator |
| `decoded_fields` | tuple[(string, string), ...] | R | 按版本化 source header 顺序保存的完整字段名和值 |

`decoded_fields` 的每个字段名和值都必须是字符串；空字段保持 `""`。分类器不得
trim、转换大小写、执行 dtype inference、Unicode normalization、科学计数法展开
或任何其他文本归一化。

## 4. Duplicate grouping key

分组键固定为以下三元组：

```text
(case_id, source_entity_type, source_id)
```

三个分量均按其精确值比较。source ID 的前导零、大小写、Unicode code points、
后缀和科学计数法字符串形式均有意义。不同 case 或不同具体 source entity type
不得互相分组。

## 5. Duplicate comparison

同一 group key 只有一条记录时，结果为 `UNIQUE`。

同一 group key 有多条记录时，只比较每条记录的 `decoded_fields` 完整有序向量。
比较包括字段名、字段顺序、空字符串和每个 decoded raw string 的逐字符值。

比较输入明确不包含：

- `source_record_ref`；
- ZIP member/file path；
- CSV logical row number 或物理文本行号；
- Canonical ID、导入时间、issue message 或运行顺序。

因此，相同 decoded fields 位于不同文件或不同行时仍为 identical duplicate；
locator 差异只保留各源记录身份，不把相同内容变为 conflict。

## 6. Duplicate outcome

| 条件 | 每条组内记录的 `identity_status` | DataQualityIssue code | 默认 severity |
|---|---|---|---|
| group 仅一条记录 | `UNIQUE` | 无 | 无 |
| group 多条且所有 `decoded_fields` 完全一致 | `DUPLICATE_IDENTICAL` | `SOURCE_ID_DUPLICATE_IDENTICAL` | `WARNING` |
| group 多条且任意 `decoded_fields` 不同 | `DUPLICATE_CONFLICT` | `SOURCE_ID_DUPLICATE_CONFLICT` | `ERROR` |

分类状态按整个 group 判定：一旦任意记录不同，同组所有记录均为
`DUPLICATE_CONFLICT`，不得只标记差异行。

每条 duplicate source record 各产生一条 `DataQualityIssue`，并携带该记录自己的
`source_record_ref`。issue target 使用现有 `SourceImportIdFactory` 按该源记录建立的
Canonical entity ID；issue ID 也必须通过该 factory 生成。南京 mapping 0.2.0
使用 Source Import foundation 默认 severity，不定义 override。

## 7. 分类输出与确定性

每个输入记录产生且只产生一个 `SourceIdentityClassification`：

| 字段 | 类型 | 必需性 | 说明 |
|---|---|---:|---|
| `record` | `SourceIdentityRecord` | R | 原始分类输入，不得替换或合并 |
| `identity_status` | `IdentityStatus` | R | 第 6 节结果 |
| `issue` | `DataQualityIssue`/null | N | duplicate 时必需；`UNIQUE` 时为 null |

输出按 `(case_id, source_entity_type, source_id, source_record_ref)` 的精确字符串值
稳定排序。输入迭代顺序变化不得改变各 locator 对应的 status、issue ID、code 或
severity。

## 8. MVP 行为与边界

- 禁止 merge、deduplicate、覆盖或删除 source records。
- identical duplicate 也必须保留所有 source records 和各自确定性 Canonical ID。
- duplicate 只通过顶层实体 `identity_status` 和 `DataQualityIssue` 表达。
- 分类器不修改 raw fields、source ID 或 locator。
- 分类器不打开 ZIP、不读取 CSV，也不生成 `source_record_ref`。
- 分类器不实现 Bus/Equipment mapper、reference resolver、connectivity 或 topology。
- `DUPLICATE_IDENTICAL` 不授权后续层任选一条记录；引用命中 duplicate identity 时
  仍按 mapping contract 处理为 ambiguous。
