# Station/Feeder/Bus Case Assembly Contract

## 1. 文档信息

| 项目 | 值 |
|---|---|
| 状态 | D-2-E 实现基线 |
| 规范版本 | `0.1.0` |
| Canonical 合同 | `docs/spec/canonical_data_spec.md` `0.4.0` |
| Source Import 基线 | `docs/spec/source_import_foundation.md` `0.2.0` |
| Identity 合同 | `docs/spec/identity_resolution_contract.md` `0.2.0` |
| Reference 合同 | `docs/spec/reference_resolution_contract.md` `0.2.0` |
| Source Mapping | `nanjing_csv` `0.3.0` |

本文冻结 D-2-E 的 Station、Feeder、Bus case assembly 和局部 accounting。该层只
装配调用方已经通过现有 mapper 得到的 `RecordMappingOutcome`，不是新的 Raw
CSV/ZIP 到 Canonical pipeline。

## 2. 边界

D-2-E 可以接收 `RawCsvRecord`，但只用于把既有 mapper outcome 关联回原始行、读取
已冻结的引用字段和保留 row accountability。它不得：

- 打开 ZIP、读取或解码 CSV；
- 调用 mapper 或 identity classifier；
- 生成 `source_record_ref`；
- 实现 Equipment/Terminal mapper 或 mixed endpoint resolution；
- 推断 topology/connectivity，或把 `EXACT` 提升为 `CONFIRMED`；
- 决定 `Dataset.import_status`；
- 声明南京 12 类文件的 Dataset Import Complete；
- 写出 manifest、JSONL 或完整 import report。

## 3. 输入关联模型

每个 scoped raw row 由一个不可变 `CaseRowMappingOutcome` 关联：

| 字段 | 类型 | 必需性 | 说明 |
|---|---|---:|---|
| `raw_record` | `RawCsvRecord` | R | Intake 已产生的 Station/Feeder/Bus 行 |
| `identity_status` | `IdentityStatus`/null | C | 成功 mapper output 必须与其顶层实体一致；record-fatal 行为 null |
| `mapping_outcome` | `RecordMappingOutcome[Station\|Feeder\|Bus]` | R | 已由现有 mapper 产生；assembly 不重新映射 |

该对象是 row 与 mapper outcome 的关联，不是第二套 identity record。实现不得新增与
`SourceIdentityRecord` 平行的 identity source of truth。

关联必须验证：

- raw row、mapped record/unmapped record 的 `source_record_ref`、case 和 source type
  一致；
- 成功记录的 `source_id`、`identity_status` 和 provenance 与 raw row 对应；
- record-fatal outcome 必须包含同一 raw row 的完整 `UnmappedSourceRecord`；
- 一个 assembly 调用中 `source_record_ref` 唯一，且全部属于同一个 case；
- 只接受 `STATION`、`FEEDER`、`BUS`。

## 4. Duplicate assembly semantics

Duplicate group key 和 identical/conflicting 判定仍由 Identity Contract 定义。D-2-E
不重新分类，只验证同组 status 一致并执行下列装配规则。

### 4.1 `DUPLICATE_IDENTICAL`

- group 中全部 raw rows 保留在 row accounting；
- 按 `source_record_ref` 逐字符升序选择最小者对应的 mapper output，作为唯一
  published Canonical entity；
- 其 Canonical ID、source provenance 和 `identity_status=DUPLICATE_IDENTICAL`
  保持 mapper output 原值；
- 其他 mapper outputs 不进入 `CaseAssemblyResult.records`；
- 每个 group row 各产生一个 `SOURCE_ID_DUPLICATE_IDENTICAL/WARNING` issue，均以
  published entity 为 `target_ref`；
- 每个 row accounting entry 均指向同一 published entity；
- 非 representative row 的 mapper field issue 必须以相同 code/path/value/severity 和
  该字段已冻结的 occurrence key 重新生成 ID，并改为指向 published entity；
- published entity 建立的 reference candidate 保留
  `DUPLICATE_IDENTICAL`，因此引用仍解析为 `AMBIGUOUS`，不得选中该 entity。

最小 locator 只用于选择 identical payload 的 published representation，不用于引用
候选选择、冲突修复或 connectivity。

### 4.2 `DUPLICATE_CONFLICT`

- group 中全部 raw rows 保留在 row accounting；
- group 内任何 mapper output 都不得进入 `CaseAssemblyResult.records`；
- 不选择 representative，不合并字段，也不建立 Canonical entity；
- 每个 group row 各产生一个 `SOURCE_ID_DUPLICATE_CONFLICT/ERROR` issue，
  `target_ref=null`；
- group row 的 mapper field issue 必须保留，但重新生成 ID 并令
  `target_ref=null`，不得指向未发布的 mapper output；
- assembly 必须向 candidate index 提供一个 deterministic identity-conflict marker；
- 对该 `(case_id, source_entity_type, source_id)` 的精确引用必须解析为
  `AMBIGUOUS`，即使 Canonical candidate 为零；不得变为普通 `UNRESOLVED`。

## 5. Reference assembly

只对 published Station/Feeder/Bus records 建立 Canonical candidates。Conflict marker
不是 Canonical candidate，不包含 `EntityRef`。

D-2-E 只装配：

- `Bus_Station_ID -> STATION`；
- `Feeder_SourceBus -> BUS`。

Resolver result 的 `identity_conflicts` 按 Reference Contract 表达没有 Canonical
candidate 的 conflicting identity。`AMBIGUOUS`/`UNRESOLVED` 仍由南京 reference
issue policy 产生对应 issue。`MISSING`/`EXACT` 不产生 reference issue。

## 6. `GridCase.feeder_ref`

此规则只设置既有 `GridCase.feeder_ref`，不抽象为通用 case-level resolver：

- published Feeder 恰好一条且其 identity 为 `UNIQUE` 时设置引用；
- 没有 Feeder source identity 或所有 Feeder rows 均为 record-fatal 时，保持 null 并
  产生一个 `GRID_CASE_FEEDER_MISSING/WARNING`；
- 存在多个 unique Feeder identity、任一 identical duplicate Feeder group 或任一
  conflicting duplicate Feeder group 时，保持 null 并产生一个
  `GRID_CASE_FEEDER_AMBIGUOUS/ERROR`；
- 不按名称、行号、目录或 locator 选择 Feeder。

## 7. Row accountability

`RowAccountability` 必须完整保留 `raw_record`，并包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| `raw_record` | `RawCsvRecord` | 被 account for 的完整 Intake row |
| `terminal_category` | enum | `MAPPED`、`DUPLICATE`、`UNRESOLVED`、`REJECTED` |
| `identity_status` | `IdentityStatus`/null | record-fatal 行为 null |
| `canonical_ref` | `EntityRef`/null | identical rows 共同指向 published representative；conflict/rejected 为 null |
| `issue_ids` | tuple[`CanonicalId`, ...] | 与该 row 关联的全部 issue，按 issue order 排序 |
| `resolution_indexes` | tuple[int, ...] | 指向 result `resolutions` 的位置，升序且无重复 |

Identical duplicate rows 共享 published entity，因此也共享该 entity 作为 owner 时的
resolution index；conflicting/rejected rows 没有 resolution index。

terminal category 按以下优先级唯一确定：

1. mapper outcome 为 record-fatal：`REJECTED`；
2. identity status 非 `UNIQUE`：`DUPLICATE`；
3. unique Bus/Feeder 的引用结果为 `AMBIGUOUS` 或 `UNRESOLVED`：`UNRESOLVED`；
4. 其余成功记录，包括 reference `MISSING` 或 `EXACT`：`MAPPED`。

Field-level recoverable issue 不改变成功 row 的 terminal category。Accounting 只声明
本次传入的 Station/Feeder/Bus rows 均有终态；它不评价文件缺失、header/读取
diagnostics、其他九类文件或 Dataset ImportStatus。

## 8. `CaseAssemblyResult`

不可变 result 明确为 `CaseAssemblyResult`，字段为：

| 字段 | 类型 | 说明 |
|---|---|---|
| `grid_case` | `GridCase` | 已应用本合同 feeder rule 的新 immutable record |
| `records` | tuple[`Station\|Feeder\|Bus`, ...] | published source entities |
| `issues` | tuple[`DataQualityIssue`, ...] | mapper、duplicate、reference、feeder issues |
| `unmapped_records` | tuple[`UnmappedSourceRecord`, ...] | record-fatal rows |
| `resolutions` | tuple[`ReferenceResolutionResult`, ...] | published Bus/Feeder 的两类引用结果 |
| `accounting` | tuple[`RowAccountability`, ...] | 每个 scoped input row 恰好一项 |

该类型不是 `Dataset ImportResult`，不包含或计算 `ImportStatus`。

## 9. Issue identity and deterministic ordering

### 9.1 Duplicate issues

每个 duplicate row 一项 issue：

- `issue_id` key 严格为 foundation 规定的
  `(dataset_id, case_id, target type/null, target id/null, field_path, code,
  source_record_ref, occurrence_key)`；message、输入顺序和导入时间不参与；

- `field_path`：`station.source_id`、`feeder.source_id` 或 `bus.source_id`；
- `code`：由 identity status 唯一决定；
- `source_record_ref`：该 row locator；
- `occurrence_key=""`；
- `observed_value`：未经改写的 source ID；
- identical 的 `target_ref` 为 published entity；conflict 为 null。

### 9.2 Feeder issues

每 case 至多一个 feeder-selection issue：

- `issue_id` 使用同一 foundation key，且使用本节冻结的 target/path/null locator/
  occurrence values；

- `target_ref={entity_type: GRID_CASE, entity_id: case_id}`；
- `field_path="grid_case.feeder_ref"`；
- `source_record_ref=null`；
- `occurrence_key=""`；
- `observed_value=null`。

### 9.3 Ordering

- records：`(entity_type, source_record_ref, canonical_id)`；entity type 顺序固定为
  `STATION`, `FEEDER`, `BUS`；
- issues：`(case_id-or-empty, source_record_ref-or-empty, field_path-or-empty,
  code.value, target-type-or-empty, target-id-or-empty, issue_id)`；
- unmapped records：`(source_file_type.value, source_record_ref)`；
- resolutions：`(owner_source_entity_type, owner_source_record_ref,
  reference_field_path)`；
- accounting：`(source_file_type.value, source_record_ref)`。

所有排序只用于稳定输出，不用于选择引用或冲突实体。
