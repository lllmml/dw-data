# 2026-09-09 Source Reference Integration Handoff

## 1. Handoff metadata

- 日期：2026-09-09（Asia/Shanghai）
- 当前分支：`main`
- 当前 HEAD：`acf12155f62dd1a2079fbf5dca8cbc009cf2649f`
- 最近完整测试：`uv run --frozen python -m pytest`，`146 passed`
- Python 基线：CPython `>=3.11,<3.14`
- 依赖：运行时无第三方依赖；pytest 仅为 dev dependency；使用已提交的
  `uv.lock`
- `MEMORY.md`：仓库当前不存在该文件
- 本 handoff 创建前工作区为 clean

本文是下一次 coding agent session 的事实摘要。发生冲突时，以 `AGENTS.md`、
`docs/intent.md` 和版本化 `docs/spec/` 为准，不以本文替代规范。

## 2. Project current state

### 2.1 已完成的 slices

| Slice | 状态 | 已完成内容 |
|---|---|---|
| Slice A | 完成 | Source Import foundation spec；确定性 ID、质量代码、错误边界、Import Status、Python 基线 |
| Slice B | 完成 | Canonical value objects/enums/dataclasses、ID factory、quality foundation、稳定 JSON serialization、Python/uv 工程 |
| Slice C | 完成 | 南京 ZIP 只读 inventory、安全路径检查、12 类 schema registry、BOM-safe raw CSV reader、稳定 locator、真实 ZIP smoke |
| Slice D-1 | 完成 | Source Intake Contract；Dataset、GridCase、Station、Feeder 最小 mapper 和 unmapped accounting 基础 |
| Slice D-2-A | 完成并修复 | Source Identity Classification Contract；Station/Feeder/Bus/Equipment source identity grouping 与 duplicate classification primitives |
| Slice D-2-B | 完成 | 最小 Bus mapper；只传播 identity status，不解析引用或建立 connectivity |
| Slice D-2-C | 完成 | Source Reference Resolution Contract `0.1.0` |
| Slice D-2-D | 完成并修复 | Generic exact-match resolver、candidate index、确定性显式排序、空 candidate source ID 约束 |
| Resolver integration | 完成 | 南京 Adapter 层的 Station/Bus/Feeder candidate 构建、Bus→Station 和 Feeder→Bus 引用装配、独立 issue policy |

“CSV → Canonical mapper 已完成”仍不成立。当前只实现 Dataset、GridCase、Station、
Feeder、Bus 的基础映射；8 类 Equipment 及其子记录尚未实现。README 和
`AGENTS.md` 的“mapper 未完成”描述虽然不反映当前的部分进展，但对完整 Source
Import MVP 仍然成立。

### 2.2 重要 commits

| Commit | 内容 |
|---|---|
| `71b78149f9c4e0ee7ead6fde2fb89ee3da70206f` | 定义 Source Import foundation spec |
| `d26884a0ab8932c602793f1cabacc5a194733b42` | Canonical Source Import foundation 实现 |
| `1bd4df3d635a8110f0b96e08eb9af4bc62abd410` | 南京只读 Source Intake |
| `db590dec46bb68c2a8bba968569996d5cede507b` | Source Intake Contract 与初始 mapper |
| `af450b5b72cb6209f57da10f460ffc5fb9215208` | Identity classification foundation |
| `05fbeb6c160b8accf2eefb01878df05489cb7d6d` | 收口 identity classifier 与 mapper 边界 |
| `ece2e90d0d21433241da0b71aa3275b4e57260ad` | 最小 Bus mapper |
| `495415033ed22f21086dade63aba1d84ec64b52b` | Reference Resolution Contract |
| `7476c8d9e9e92cd191a8ac84bb4a2e0a65b5b227` | Generic reference resolver foundation |
| `5d2cff734420d2abe08cfbc14749420d24b0704f` | 修复 candidate index 的显式 Enum 排序 |
| `acf12155f62dd1a2079fbf5dca8cbc009cf2649f` | 南京 exact reference resolver integration |

### 2.3 当前架构

```text
南京 ZIP（只读）
  -> Source Intake
       SourceDatasetInventory / SourceCaseInventory
       RawSourceFile / RawCsvRecord / IntakeDiagnostic
  -> SourceIdentityRecord
  -> classify_source_identities
       SourceIdentityClassification
  -> 南京 Canonical mapper
       Dataset / GridCase / Station / Feeder / Bus
       RecordMappingOutcome / UnmappedSourceRecord
  -> ReferenceCandidate builder
  -> build_reference_candidate_index
  -> resolve_source_reference
       ReferenceResolutionResult
  -> 南京 immutable reference integration
       新 Bus / Feeder + Canonical SourceReference
  -> 南京 reference issue policy
       DataQualityIssue（仅 AMBIGUOUS / UNRESOLVED）
```

依赖方向保持为：`io/nanjing_source` Adapter 可依赖 `models` 和通用
`validation` primitives；通用 `models`/`validation` 不依赖南京 CSV、ZIP 或字段名。
Mapper、identity classifier 和 resolver 均不直接打开 ZIP。

## 3. Frozen contracts

### 3.1 当前版本

| Contract | 版本/身份 |
|---|---|
| Canonical Data Spec | `0.3.0` |
| Source Import Foundation | `0.1.0` |
| Source Intake Contract | `0.1.0` |
| Identity Resolution Contract | `0.1.1` |
| Reference Resolution Contract | `0.1.0` |
| Nanjing Mapping | `nanjing_csv` `0.2.0` |
| Nanjing Source Audit | `0.1.0`，ZIP SHA-256 `7ae1e246e5ac8073053d280cd64e66cdc491d5303dc2c15aa74f823be202de25` |

这些合同已经过逐 Slice review。不要在业务实现 Slice 中顺手改变字段语义、ID
输入、candidate scope、status 条件或 severity policy；需要改变时先建立独立规范
Slice 并升级相应版本。

### 3.2 不得改变的边界

- `data/raw/` 和南京 ZIP 永远只读；不得解压或写回源目录、覆盖文件或修改 ZIP。
- Intake 是唯一读取 ZIP/CSV 的层。Mapper 只消费 intake objects，不自行打开文件、
  解码 CSV 或生成 `source_record_ref`。
- 缺失字段保持 `null`；不得为 schema 完整性虚构值、相位、时间、参数或连接。
- 未确认的 `FromBus`/`ToBus` 语义不得用于 connectivity、topology repair 或
  bus-branch projection。
- 不实现 fuzzy matching、ID repair、最近 ID、科学计数法展开、trim、大小写转换或
  Unicode normalization。
- `EXACT` 只表示 source reference 唯一精确命中；绝不自动转换为
  `connectivity_status=CONFIRMED`。
- Resolver 不创建 Canonical ID、Canonical entity、`EntityRef`、
  `DataQualityIssue`、connectivity 或 topology，也不修改任何输入对象。
- Severity 决策不进入 resolver 或 generic `DataQualityIssue` dataclass；由版本化
  Adapter/issue policy 决定。南京 mapping `0.2.0` 没有 override，使用 foundation
  defaults。
- Identity classifier 只分组和分类，不创建 Canonical entity/ID/ref/issue。
- Duplicate records 不得 merge、deduplicate、覆盖、删除或选择第一条；identical
  duplicates 同样全部保留。
- Import Complete、Canonical Valid、OpenDSS Ready、Operator Ready 是四个独立
  结论。Issue（包括 ERROR）的存在本身不使已完整 account for 的导入变为
  `INCOMPLETE`。

### 3.3 关键 invariants

#### Raw strings 与 locator

- 所有 `*_ID`、引用和 text 在 intake 层都是未经推断的 `str`；空 CSV 字段保持
  `""`。
- `"001"`、`"1"`、`"1e0"`、19 位 ID、Unicode 和 `_bs` 后缀必须保持不同。
- Locator 固定为
  `zip-member:<RFC3986-percent-encoded-member>#data-row=<1-based-logical-row>`；
  embedded newline 不增加 logical row。
- Mapper 复制 Intake 生成的 locator，不重新编码路径或计算 row number。

#### Deterministic IDs

- 统一通过 `SourceImportIdFactory` 实现 `source-import-id-v1`；业务代码不得自行拼
  hash 输入。
- Dataset ID 只依赖 source artifact checksum；mapping version 更新不得改变
  Dataset/GridCase/source entity ID。
- 每个 source entity ID 包含 `source_record_ref`，所以 duplicate rows 具有不同
  Canonical IDs。
- FieldProvenance ID 包含 mapping ID/version；quality issue ID 不包含可读 message、
  imported time 或绝对文件路径。

#### Source provenance

- `record_origin=SOURCE` 时 `source_mapping_id` 与 `source_mapping_version` 必须均
  非空。
- 单行直接映射实体必须携带 Intake locator。多行聚合记录（例如未来的
  SimulationProfile）可令 record-level locator 为 null，但必须用 FieldProvenance
  定位各行。
- Reference candidate 必须复用 mapper-produced `source_id`、`source_record_ref`、
  `identity_status` 和既有 Canonical entity ID，不从 raw CSV 重建 source identity。

#### Identity classification

- Group key 固定为 `(case_id, source_entity_type, source_id)`。
- Duplicate comparison 只比较完整、有序、decoded raw `fields`，包含空字符串；不含
  locator、路径和 row number。
- 单条为 `UNIQUE`；多条全字段相同为 `DUPLICATE_IDENTICAL`；任意不同则组内全部为
  `DUPLICATE_CONFLICT`。
- Equipment identity 必须保留具体 source type，不能预先折叠成通用
  `EQUIPMENT`。

#### Reference resolution

- Candidate index key 固定为 `(case_id, concrete source_entity_type, source_id)`；
  不跨 case、source type 或 Candidate Matrix 查询。
- Index key 显式按 `(case_id, source_entity_type.value, source_id)` 排序；不得依赖
  Python Enum tuple ordering。
- String match 逐字符、区分大小写，不执行任何 normalization。
- Resolver request 对空源字段保留 `raw_reference_value=""`，得到 `MISSING`、空
  candidates 和 null resolved ref。
- 转换为 Canonical `SourceReference` 时，Canonical 合同明确要求 MISSING 的
  `raw_ref=null`；非 MISSING 才构造 `SourceId(raw_reference_value)`。
- `EXACT` 仅当候选数恰好为 1 且 candidate `identity_status=UNIQUE`。
- 多候选或唯一 candidate status 非 UNIQUE 均为 `AMBIGUOUS`；
  `DUPLICATE_IDENTICAL` 也不能安全选择。
- 非空引用且无候选为 `UNRESOLVED`。
- Resolver 只返回 request、status、完整确定性 candidate set 和已有 resolved ref。
- Adapter policy 对 `AMBIGUOUS` 创建
  `SOURCE_REFERENCE_AMBIGUOUS`，对 `UNRESOLVED` 创建
  `SOURCE_REFERENCE_UNRESOLVED`；MISSING/EXACT 不创建 reference-resolution
  issue。

#### Mapping errors

- Optional field parse failure 是 field-level recoverable：保留实体、Canonical 字段
  null、issue 保存原文。
- 必需 source ID 缺失或 raw row malformed 是 record-level fatal：不得伪造实体
  ID；完整保存 `UnmappedSourceRecord` 和关联 issue。
- 已完整 account for 的 field/record error 不阻止 Import Complete；未 account for
  的部分处理才是 INCOMPLETE。

## 4. Current implementation details

### 4.1 Canonical foundation

- `src/grid_case_generator/models/types.py`
  - string-safe `Identifier`/`CanonicalId`/`SourceId`
  - enums、`EntityRef`、`SourceReference`
- `src/grid_case_generator/models/records.py`
  - Source Import MVP 的 frozen/slotted Canonical dataclasses
  - `TraceableRecord` SOURCE provenance invariant
- `src/grid_case_generator/models/identifiers.py`
  - 所有 Source Import deterministic ID factory APIs
- `src/grid_case_generator/models/quality.py`
  - stable issue code registry 和 default severity map
- `src/grid_case_generator/validation/quality.py`
  - default severity helper、error category、import status helper
- `src/grid_case_generator/io/canonical_json.py`
  - dataclass/enum/Decimal/Identifier/null 的 byte-stable JSON serialization

### 4.2 Source Intake

- `archive.py`：`inventory_archive(path) -> SourceDatasetInventory`
- `csv_reader.py`：`read_raw_csv_member(...) -> RawSourceFile`
- `locator.py`：`SourceRecordRef`、safe path validation、locator construction
- `models.py`：inventory/raw record/diagnostic immutable objects
- `schema.py`：南京 12 类 exact filename/header registry

真实南京 ZIP smoke test 已验证：checksum 匹配、5,159 cases、61,908 CSV、每 case
12 类文件可 inventory，且源文件 stat/checksum 不变。完整逐表 mapper/audit golden
regression 尚未实现。

### 4.3 Mapper foundation

文件：`src/grid_case_generator/io/nanjing_source/mapping.py`

当前 APIs：

```text
map_dataset(inventory, *, name, imported_at, import_status) -> Dataset
map_grid_case(inventory, *, dataset_id) -> GridCase
map_station(record, *, dataset_id, case_id, identity_status)
    -> RecordMappingOutcome[Station]
map_feeder(record, *, dataset_id, case_id, identity_status)
    -> RecordMappingOutcome[Feeder]
map_bus(record, classification)
    -> RecordMappingOutcome[Bus]
```

`RecordMappingOutcome` 在成功时携带 record，在 record-fatal 时携带
`UnmappedSourceRecord`；同时可携带 issues 和 `ImportErrorCategory`。Station 已处理
optional Decimal parse failure、missing ID 和 malformed row。Feeder 保留 raw source
bus ref；Bus 保留 raw station ref，二者基础 mapper 先表达 MISSING/UNRESOLVED，后续
integration 再装配最终 resolution status。

### 4.4 Identity foundation

文件：`src/grid_case_generator/validation/identity.py`

```text
classify_source_identities(
    records: Iterable[SourceIdentityRecord]
) -> tuple[SourceIdentityClassification, ...]
```

输出稳定排序，保留每条输入，不产生 Canonical entity、ID 或 issue。

### 4.5 Generic resolver foundation

文件：`src/grid_case_generator/validation/reference_resolution.py`

```text
build_reference_candidate_index(
    candidates: Iterable[ReferenceCandidate]
) -> ReferenceCandidateIndex

resolve_source_reference(
    index: ReferenceCandidateIndex,
    request: ReferenceResolutionRequest
) -> ReferenceResolutionResult
```

实现为纯 exact-match lookup；candidate bucket 和结果均确定性排序；二分查找、index
build 和 index invariant 都使用显式 key sort function。

### 4.6 南京 resolver integration

新增文件：

- `src/grid_case_generator/io/nanjing_source/reference_integration.py`
- `src/grid_case_generator/io/nanjing_source/reference_issue_policy.py`
- `tests/io/nanjing_source/test_reference_integration.py`

公开 APIs：

```text
reference_candidate_from_mapped_record(record) -> ReferenceCandidate
build_nanjing_reference_candidate_index(records) -> ReferenceCandidateIndex
integrate_bus_station_reference(raw_record, bus, index)
    -> ReferenceIntegrationOutcome[Bus]
integrate_feeder_source_bus_reference(raw_record, feeder, index)
    -> ReferenceIntegrationOutcome[Feeder]
reference_issues_for_result(
    result, *, dataset_id, target_ref, severity_for=default_policy
) -> tuple[DataQualityIssue, ...]
```

设计决策：

- `reference_integration.py` 位于南京 Adapter 层，而不是 generic validation 层。
- Candidate builder 只接收 mapper-produced Station/Feeder/Bus，校验 SOURCE origin、
  `nanjing_csv` `0.2.0` provenance、非空 locator/source ID，并直接复用 source ID 与
  entity ID。
- Integration request 的 raw reference 从匹配的 `RawCsvRecord.fields` 逐字读取；
  owner identity/provenance 必须与 raw record 一致。
- Bus 的 allowed candidate types 固定为 `STATION`；Feeder 固定为 `BUS`，与 Candidate
  Matrix 一致。
- 使用 `dataclasses.replace` 返回新的 frozen Bus/Feeder；原 mapper output 不变。
- `ReferenceIntegrationOutcome` 同时保留新 record 和 resolver result。
- `reference_integration.py` 不导入 issue registry 或 severity policy。
- 独立 Adapter issue policy 负责 status→issue code，并调用可注入的
  `severity_for`。默认使用 foundation severity，未来版本化 mapping 可显式 override。
- Tests 覆盖 source ID 原样复用、provenance mismatch、identical/conflicting
  duplicate preservation、immutable assembly、MISSING 双层表示、EXACT、AMBIGUOUS、
  UNRESOLVED、default severity 和 explicit override。

## 5. Pending issues and limitations

### 5.1 Source Import implementation gaps

- 没有完整 case/dataset Source Import orchestrator。当前需要调用方手工连接 intake、
  classification、mapper、candidate index、integration 和 issue policy。
- Station/Feeder mapper 接收裸 `identity_status`，Bus mapper 接收完整
  `SourceIdentityClassification`；调用接口尚未统一，但不得把 identity logic 搬回
  mapper。
- `map_bus` 尚未从 `grid_case_generator.io.nanjing_source.__init__` 导出；目前需要从
  `.mapping` 直接导入。
- Bus 的 invalid optional Decimal/Boolean 仍抛出 Slice-boundary `ValueError`，尚未按
  foundation 转为 field-level recoverable issue。
- Identity classification 尚未由 Adapter orchestration 自动从 RawCsvRecord 构造输入；
  duplicate identity issues 尚未统一创建。
- `GridCase.feeder_ref` selection policy 尚未实现；当前 mapper 始终为 null。规范要求：
  唯一 UNIQUE Feeder 才设置；0 个为 missing issue；多条或 duplicate identity 为
  ambiguous issue。
- IntakeDiagnostic→DataQualityIssue 转换尚未实现。
- Unmapped source records 只有内存对象，没有 JSONL writer 或全量 accounting report。
- 没有 manifest、records JSONL、quality issues JSONL、field provenance JSONL 或完整
  import report writer。
- Dataset `import_status` 由调用方传入，尚未由完整 accounting 结果计算。

### 5.2 Mapper coverage gaps

- 尚未实现 SWITCH、DISCONNECTOR、EARTHING_SWITCH、LINE、TRANSFORMER、
  ACCESS_POINT、LOAD、DER 的 Equipment mapper。
- 尚未建立对应的 Terminal、Line、SwitchingDevice、Transformer、
  TransformerWinding、AccessPoint、Load、DER records。
- Reference candidate builder 当前只支持 Station/Feeder/Bus；具体 Equipment source
  types 尚未进入 candidate index。
- Resolver integration 当前只覆盖：
  - `Bus_Station_ID -> STATION`
  - `Feeder_SourceBus -> BUS`
- Switch/Line mixed-type endpoint references、空候选类型字段、Transformer/AccessPoint/
  Load/DER terminals、SimConfig references 尚未集成。
- SimConfig→SimulationProfile、FieldProvenance 和 snapshot OperationalSeries 尚未实现。

### 5.3 Full-data regression gaps

- 已有真实 ZIP inventory smoke，但尚未执行完整 mapper/importer。
- `nanjing_source_audit.md` 中逐表 row counts、25 个空 Feeder files、Bus station ref
  MISSING/UNRESOLVED、Switch duplicate groups、measurement counts 等尚未成为 full
  import golden regression。
- Load/DER 全部 only-header，必须保持“无源实体”；不得为通过 regression 生成记录。

### 5.4 仍待业务确认，不得在代码中解决

- `FromBus`/`ToBus` 的真实电气语义与 topology projection。
- 相位编码；当前保持 null，不默认 ABC。
- Transformer winding/Terminal 顺序和实际连接语义。
- 长 ID/科学计数法/疑似精度损失的权威修复规则。
- 开关量测时间、功率方向与离群值治理。
- `EarthingSwitch_State`、Station CRS、SimConfig 真实性、`SUB_10KV` 对应关系。
- 线路/Transformer 参数补全、Load/DER 生成、时序生成。
- OpenDSS、QSTS 和 Operator Adapter readiness。

## 6. Suggested next slice

建议下一 Slice 为 **D-2-E：Station/Feeder/Bus case assembly and import policy**，先完成
已有 mapper 的小型端到端闭环，不直接进入 Equipment 或 topology。

建议范围：

1. 定义一个 immutable case mapping result，汇总 GridCase、Station、Feeder、Bus、
   issues、unmapped records、resolution results 和明确 accounting 状态。
2. 只消费 `SourceCaseInventory`/`RawSourceFile`/`RawCsvRecord`，不打开 ZIP 或读取
   CSV。
3. 为 Station/Feeder/Bus 构造 identity inputs，统一关联 classification 与 raw row；
   required ID 缺失直接进入现有 unmapped accounting。
4. 保留所有 duplicates，并按 foundation policy 创建 duplicate issues。
5. 映射所有成功记录后建立 case candidate index，再集成 Bus→Station 和
   Feeder→Bus references；由独立 policy 创建 reference issues。
6. 实现已经冻结的 `GridCase.feeder_ref` 规则，不调用 generic source-reference
   resolver 选择 Feeder。
7. 将 Bus optional Decimal/Boolean failures 收口为 field-level recoverable issues，
   不让完整 case orchestration 因单字段异常中断。
8. 明确该 slice 只 account for 三类 entity files，不得将结果声明为完整南京
   12-table Dataset import，也不写 full manifest/report。

完成该闭环后，再单独规划 Equipment mapper slices。多类型 endpoint resolver 应在所需
Equipment candidates 全部成功映射后运行，不能因候选不完整而提前把引用永久标为
UNRESOLVED。

## 7. Recommended next prompt

```text
阅读：

- AGENTS.md
- docs/handoff/2026-09-09-reference-integration.md
- docs/spec/canonical_data_spec.md
- docs/spec/source_import_foundation.md
- docs/spec/source_intake_contract.md
- docs/spec/identity_resolution_contract.md
- docs/spec/reference_resolution_contract.md
- docs/spec/nanjing_mapping_spec.md

确认当前 HEAD 以 acf12155f62dd1a2079fbf5dca8cbc009cf2649f 为基线，先检查
worktree，不覆盖用户改动。

进入 D-2-E：Station/Feeder/Bus case assembly and import policy。

开始编码前先提出 foundation plan。若现有 specs 无法唯一确定 orchestration result
或 accounting 边界，先列出最小规范问题，不要猜测。

本 Slice 只消费 Source Intake 输出，不打开 ZIP、不读取 CSV。测试先行，实现：

1. Station/Feeder/Bus raw rows 到 SourceIdentityRecord 的 adapter glue；
2. identity classification 与现有 mapper 的稳定关联；
3. duplicate records 全保留及 duplicate DataQualityIssue policy；
4. 成功映射实体构建 case candidate index；
5. Bus→Station、Feeder→Bus exact reference integration 与 reference issues；
6. GridCase.feeder_ref 的冻结规则；
7. Bus optional Decimal/Boolean 错误转为 field-level recoverable issue；
8. immutable case mapping result，包含 records/issues/unmapped/resolutions/accounting。

不要实现 Equipment/Terminal mapper、mixed endpoint resolution、topology、connectivity、
ID repair、fuzzy matching、generation、OpenDSS、QSTS、Operator Adapter 或 full output
writer。EXACT source reference 不得提升为 CONFIRMED connectivity。不要把三类文件的
局部闭环声明为完整 Dataset Import Complete。

运行：

uv run --frozen python -m pytest

完成后停止，报告修改文件、测试结果、spec 偏离和下一 Slice 建议；不要自动进入
Equipment mapper。
```
