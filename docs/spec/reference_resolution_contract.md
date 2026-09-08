# Source Reference Resolution Contract 规范

## 1. 文档信息

| 项目 | 值 |
|---|---|
| 状态 | Source Import MVP 实现基线 |
| 规范版本 | `0.1.0` |
| Canonical 合同 | `docs/spec/canonical_data_spec.md` `0.3.0` |
| Source Import 基线 | `docs/spec/source_import_foundation.md` `0.1.0` |
| Identity 合同 | `docs/spec/identity_resolution_contract.md` `0.1.1` |
| 首个 Source Mapping | `nanjing_csv` `0.2.0` |

本文冻结 Source Reference Resolution 的输入、候选索引、精确匹配、结果状态和
质量事件边界。它不确认任何引用的电气连接语义，也不授权数据修复或拓扑推断。

## 2. 职责与边界

Reference Resolution 只负责：

1. 使用 request 中未经改写的 source reference value 查询明确允许的候选实体；
2. 按本合同判断 reference resolution status；
3. 返回不可变的 resolution result。

Reference Resolution 不得：

- 修改或替换 Canonical entity；
- 创建 Canonical entity、Canonical ID 或 `EntityRef`；
- merge、删除、覆盖或选择性保留 source entity；
- 修复 source ID 或 source reference；
- trim、大小写转换、Unicode normalization 或科学计数法展开；
- 使用模糊匹配、名称相似匹配、最近数值 ID、目录名或 locator 排序匹配；
- 推断 topology 或创建 connectivity；
- 创建 `DataQualityIssue`。

固定处理顺序为：

```text
Intake output
-> Identity Classification
-> Mapper-created Canonical source entities
-> ReferenceCandidate index
-> ReferenceResolutionRequest + candidate index
-> ReferenceResolutionResult
```

Resolver 不打开 ZIP、不读取 CSV，也不调用 Canonical ID factory。如何将 result
装配到最终不可变 Canonical record，由 Source Adapter orchestration 负责，不属于
Resolver；该装配不得被描述为原地修改 Canonical entity。

## 3. 核心数据结构

所有集合使用不可变 tuple；后续 Python 实现使用
`dataclass(frozen=True, slots=True)`。`R` 表示必需，`N` 表示允许为空。

### 3.1 `ReferenceResolutionRequest`

| 字段 | 类型 | 必需性 | 说明 |
|---|---|---:|---|
| `case_id` | `CanonicalId` | R | owner 所属 case，也是唯一允许查询的 case |
| `owner_source_entity_type` | `Identifier` | R | 版本化 mapping 声明的 owner source record/entity type token |
| `owner_source_id` | `SourceId`/null | N | owner 具有 source identity 时保留其原始 ID；聚合或无 ID owner 可为 null |
| `owner_source_record_ref` | string | R | Intake 提供的 owner source record locator |
| `reference_field_path` | string | R | 版本化 mapping 声明的稳定引用字段路径 |
| `raw_reference_value` | string | R | Intake 解码后的逐字符原值；允许为 `""` |
| `allowed_candidate_source_entity_types` | tuple[`SourceEntityType`, ...] | R | mapping Candidate Matrix 明文给出的 source identity types；允许为空 tuple |

不变量：

- `owner_source_record_ref` 和 `reference_field_path` 必须非空；
- owner 属于 Identity Contract 顶层实体时 `owner_source_id` 必须非空；没有独立
  source identity 的 mapping owner 不得为满足字段而伪造 ID；
- `raw_reference_value` 必须是字符串；空 source value 只表示为 `""`；
- allowed types 必须无重复，且不得包含通用 `EQUIPMENT`；
- allowed types 由调用方从版本化 Candidate Matrix 提供，Resolver 不推断；
- owner type 是 mapping 侧记录类型，不等同于 candidate identity type。例如南京
  `SIM_CONFIG` 可作为引用 owner，但它没有 source ID，不进入 Identity
  Classification，也不得作为候选 source identity type。

`reference_field_path` 必须能在同一 mapping version 内唯一识别 owner 的引用字段。
南京 mapping 可使用如 `bus.station_source_ref`、`feeder.source_bus_source_ref`、
`terminal[1].raw_connected_ref` 等稳定路径；两端设备的不同端点不得共用无法区分的
field path。

### 3.2 `ReferenceCandidate`

| 字段 | 类型 | 必需性 | 说明 |
|---|---|---:|---|
| `case_id` | `CanonicalId` | R | candidate 所属 case |
| `candidate_source_entity_type` | `SourceEntityType` | R | Identity Contract 中的具体 source identity type |
| `source_id` | `SourceId` | R | 未经 normalization 的非空 source ID |
| `source_record_ref` | string | R | candidate 源记录 locator |
| `identity_status` | `IdentityStatus` | R | Identity Classification 已给出的状态 |
| `entity_ref` | `EntityRef` | R | Mapper 已创建的 Canonical entity 引用 |

Candidate 只能由已完成 mapper 的 Canonical 顶层源实体及其 source provenance
建立。`source_id`、`source_record_ref` 和 `identity_status` 必须与该 Canonical
record 一致；`entity_ref` 只能引用该现有记录。Resolver 不创建或改写上述值，也不
重新执行 identity classification。

设备 candidate 必须保留其具体 source identity type，例如 `SWITCH` 或
`TRANSFORMER`；其已有 `entity_ref.entity_type` 按 mapping 规则可以是
`EQUIPMENT`。这两个 type 表达不同层次，不得互相替代。

当前南京 mapping 中，`STATION`、`FEEDER`、`BUS` 分别对应已有 Canonical
`EntityRef` type `STATION`、`FEEDER`、`BUS`；所有具体设备 source identity type
对应 `EQUIPMENT`。Index builder 必须验证该映射一致性，但不得创建新的 ref。

### 3.3 `ReferenceResolutionResult`

| 字段 | 类型 | 必需性 | 说明 |
|---|---|---:|---|
| `resolution_status` | `SourceReferenceStatus` | R | 本 MVP 只允许 `MISSING`、`EXACT`、`AMBIGUOUS`、`UNRESOLVED` |
| `request` | `ReferenceResolutionRequest` | R | 原 request，逐字段保留 |
| `candidates` | tuple[`ReferenceCandidate`, ...] | R | 本次查询得到的全部精确候选，确定性排序 |
| `resolved_ref` | `EntityRef`/null | N | 仅 `EXACT` 时允许，且必须等于唯一 candidate 的 `entity_ref` |

`candidates` 是在 request 的 case、allowed types 和 raw value 下命中的完整候选集，
不是 Resolver 挑选后的子集。MVP 不产生 `NORMALIZED_CANDIDATE` 或
`CONFIRMED_REPAIR`。

Result 是解析事实的独立输出。若 Adapter 将其转换为 Canonical
`SourceReference`，必须逐字使用 request 的 raw value：`MISSING` 时
`raw_ref=null`，其余状态时 `raw_ref=SourceId(raw_reference_value)`；status 和
resolved ref 必须与 result 一致。

## 4. Candidate index

Candidate index 的键固定为：

```text
(case_id, source_entity_type, source_id)
```

其中 `source_entity_type` 是 Identity Contract 定义的具体 source identity type，
不是 Canonical `EntityRef.entity_type`。索引值是该 key 下全部
`ReferenceCandidate` 的不可变 tuple。

索引建立必须满足：

- 只接收已由 Mapper 创建的 Station、Feeder、Bus 和 Equipment 顶层记录；
- 每个 candidate 必须保留 `identity_status` 和 source provenance；
- candidate 必须放入与自身 `case_id`、具体 source type、`source_id` 完全一致的 key；
- 同一 source record 不得因索引建立而 merge、覆盖或丢弃；
- 同 key 的所有 duplicate records 都必须保留为独立 candidate；
- 不得把各具体 Equipment source types 预先折叠到 `EQUIPMENT` key；
- 不得建立跨 case 或不含 source type 的辅助 fallback index。

处理 request 时，Resolver 只对每个 allowed type 查询：

```text
(request.case_id, allowed_type, SourceId(request.raw_reference_value))
```

然后取这些精确 key 对应 candidate tuple 的并集。Resolver 不得查询其他 type 或
case，也不得因查询结果为空而扩大 scope。allowed types 为空且 raw value 非空时，
候选集为空，结果为 `UNRESOLVED`。

## 5. 匹配规则

Source reference 与 candidate `source_id` 必须逐字符精确相等。比较：

- 区分大小写；
- 保留前导零、后缀和空白；
- 不 trim；
- 不进行 Unicode normalization；
- 不展开或解析科学计数法；
- 不执行数字、浮点、大小写或任何其他 normalization。

因此以下三个值是不同引用：

```text
"001"
"1"
"1e0"
```

文件路径、名称、row number、`source_record_ref` 和 Canonical ID 不参与字符串
匹配。`source_record_ref` 只区分同一逻辑 source identity 下的多条 candidate。

Mapping 特定的 invalid-literal 检查不属于 Resolver。即使 import policy 另行对
某个原值产生 `SOURCE_REFERENCE_INVALID_LITERAL`，也不得由 Resolver 改写该值或
启用替代匹配。

## 6. Resolution status

### 6.1 `MISSING`

条件：`raw_reference_value == ""`。

输出不变量：

- `candidates=()`；Resolver 不查询 candidate index；
- `resolved_ref=null`；
- 转换为 Canonical `SourceReference` 时 `raw_ref=null`。

### 6.2 `EXACT`

条件必须同时满足：

- `raw_reference_value != ""`；
- 精确 candidate 集合恰好一条；
- 唯一 candidate 的 `identity_status=UNIQUE`。

输出不变量：

- `candidates` 包含该唯一 candidate；
- `resolved_ref` 必须等于该 candidate 已有的 `entity_ref`。

`EXACT` 只声明 source reference 唯一命中，不声明或暗示 connectivity 已确认。

### 6.3 `AMBIGUOUS`

满足以下任一条件：

- 精确 candidate 集合包含多条记录；
- 精确 candidate 集合恰好一条，但该 candidate 的 `identity_status` 不是 `UNIQUE`。

输出不变量：

- `candidates` 保留全部精确命中；
- `resolved_ref=null`；
- 不得选取任一 candidate。

### 6.4 `UNRESOLVED`

条件必须同时满足：

- `raw_reference_value != ""`；
- 精确 candidate 集合为空。

输出不变量：

- `candidates=()`；
- `resolved_ref=null`。

## 7. Duplicate reference policy

`DUPLICATE_IDENTICAL` 不代表任一 candidate 可以安全替代整个 source identity。
Canonical ID 包含各记录自己的 `source_record_ref`，因此 duplicate records 是不同的
Canonical entities。

无论 duplicate identity 的 decoded fields 是否相同：

- `DUPLICATE_IDENTICAL` 必须导致引用 `AMBIGUOUS`；
- `DUPLICATE_CONFLICT` 必须导致引用 `AMBIGUOUS`；
- 不得自动 merge；
- 不得选择第一条、最后一条或最小 locator；
- 不得按 `source_record_ref`、Canonical ID、名称或输入顺序选择。

即使因上游不完整而只有一个 duplicate-status candidate 进入 index，仍必须为
`AMBIGUOUS`，不得降级为 `EXACT`。

## 8. DataQualityIssue 边界

Resolver 不创建 `DataQualityIssue`，result 也不包含 issue ID、severity 或可读
message。Import policy / Source Adapter 根据 result status 创建质量事件：

| resolution status | 是否产生 issue | code | 默认 severity |
|---|---:|---|---|
| `MISSING` | 否 | 无 | 无 |
| `EXACT` | 否 | 无 | 无 |
| `AMBIGUOUS` | 是 | `SOURCE_REFERENCE_AMBIGUOUS` | `ERROR` |
| `UNRESOLVED` | 是 | `SOURCE_REFERENCE_UNRESOLVED` | `WARNING` |

南京 mapping `0.2.0` 没有 severity override，因此必须使用上表默认值。实际 issue
必须携带 request 的 `case_id`、`owner_source_record_ref`、
`reference_field_path` 和原始 reference value，并通过现有 ID factory 生成；这些
职责不进入 Resolver。

Issue 的存在不改变 `Dataset.import_status` 判定。只要引用原值、result 和适用 issue
已被完整 account for，`AMBIGUOUS` 或 `UNRESOLVED` 不阻止 Import Complete。

## 9. 确定性与纯度

相同 candidate index 和 request 必须得到值相等的
`ReferenceResolutionResult`，不受以下顺序影响：

- candidate 输入顺序；
- candidate index 建立顺序；
- 同 key duplicate records 的输入顺序；
- `allowed_candidate_source_entity_types` 的遍历顺序。

Result 中 `candidates` 固定按以下 tuple 的逐项字符串值排序：

```text
(
  case_id,
  candidate_source_entity_type,
  source_id,
  source_record_ref,
  entity_ref.entity_type,
  entity_ref.entity_id
)
```

排序只用于稳定输出，不用于挑选 candidate。Resolver 不读取时钟、随机数、文件系统
或进程全局状态，不修改 request、candidate、index 或任何 Canonical entity。

## 10. Contract test plan

后续 implementation Slice 必须先将以下合同场景写为单元测试：

| 场景 | 预期结果/断言 |
|---|---|
| empty reference | `MISSING`；不查询候选；空 candidates；resolved null |
| unique exact match | 唯一 `UNIQUE` candidate；`EXACT`；resolved 等于已有 `EntityRef` |
| zero candidate | 非空原值；`UNRESOLVED`；resolved null |
| multiple candidates | `AMBIGUOUS`；保留全部候选；不得任选 |
| duplicate identical candidate | `DUPLICATE_IDENTICAL` 导致 `AMBIGUOUS` |
| duplicate conflict candidate | `DUPLICATE_CONFLICT` 导致 `AMBIGUOUS` |
| cross-case isolation | 其他 case 的相同 source ID 不得命中 |
| cross-source-type isolation | allowed types 外相同 source ID 不得命中；Equipment types 不混合 |
| scientific notation preservation | `"001"`、`"1"`、`"1e0"` 分别查询，不 normalization |
| input-order determinism | 候选与 allowed type 顺序变化不改变状态、候选排序或 resolved ref |
| resolver purity | request、index、candidate 和 Canonical entity 在调用前后值相等 |

测试还必须断言 Resolver 不调用 ID factory、不创建 issue，并且 `EXACT` result 不包含
connectivity 或 topology 状态。

## 11. 后续实现接口

后续 Resolver implementation Slice 的最小公开接口为：

```text
build_reference_candidate_index(
    candidates: Iterable[ReferenceCandidate]
) -> ReferenceCandidateIndex

resolve_source_reference(
    index: ReferenceCandidateIndex,
    request: ReferenceResolutionRequest
) -> ReferenceResolutionResult
```

`ReferenceCandidateIndex` 是本规范第 4 节 key 到确定性 candidate tuple 的只读表示。
这两个接口均为纯函数边界；不接收 ZIP、CSV handle、Canonical ID factory、issue
factory、topology graph 或 connectivity model。
