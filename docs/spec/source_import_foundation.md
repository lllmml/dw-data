# Source Import Foundation 规范

## 1. 文档信息

| 项目 | 值 |
|---|---|
| 状态 | Source Import MVP 实现基线 |
| 规范版本 | `0.1.0` |
| Canonical 合同 | `docs/spec/canonical_data_spec.md` `0.3.0` |
| 首个 Source Adapter | `docs/spec/nanjing_mapping_spec.md` `0.2.0` |

本文定义 Source Import MVP 的工程表示、确定性 ID、记录定位、导入错误分类、质量代码、最小序列化和 Python 工程基线。它不改变 Canonical 领域语义，不定义南京字段映射，也不授权任何数据修复或生成。

本文中的“必须”“不得”为实现强约束。

## 2. 边界

### 2.1 本基线覆盖

- Source Adapter 对源制品的只读访问和记录级 account for；
- Canonical 记录的 Python 表示和最小物理序列化；
- 可重复生成的 Canonical ID 和质量事件 ID；
- record-level fatal mapping error 与 field-level recoverable error 的处理；
- Source Import 通用质量代码及默认严重度；
- Import Complete、Canonical Valid 和消费者 readiness 之间的边界。

### 2.2 本基线不覆盖

- 源引用的真实电气连接语义；
- mixed source graph 到 bus-branch graph 的投影；
- 相位编码、Transformer 真实连接语义或拓扑修复；
- 线路、Transformer、Load、DER 或时序参数的生成；
- OpenDSS、QSTS 或 Operator Adapter readiness。

## 3. Canonical Model 的 Python 表示

1. Canonical 记录必须使用显式 `dataclass(frozen=True, slots=True)` 表示；不使用字典作为领域模型的唯一内部表示。
2. `Identifier`、`CanonicalId` 和 `SourceId` 的 Python 值均为 `str`；必须在模型边界验证非空和相应作用域。
3. 精确十进制数值使用 `decimal.Decimal`；不得使用二进制 `float` 作为中间表示。
4. Canonical 枚举使用字符串枚举；可空字段使用 `T | None`，且只有确认缺失时才为 `None`。
5. `EntityRef` 和 `SourceReference` 是独立、不可变值对象；实现不得将 `EXACT` 编码成 connectivity 布尔值或合并字段。
6. 每个按源行建立的记录都必须携带 Canonical 通用可追踪字段。由多行聚合的记录不伪造单一 `source_record_ref`，并按字段建立 `FieldProvenance`。
7. Source Adapter 按 case 分区处理；在同一 case 中先建立源实体和身份索引，再解析引用。禁止跨 case 自动匹配。

## 4. 源记录定位

### 4.1 `source_record_ref` 格式

对 ZIP 内 CSV 数据行，格式固定为：

```text
zip-member:<encoded-member-path>#data-row=<N>
```

- `<encoded-member-path>` 是 ZIP member 的完整相对路径，使用 UTF-8 字节按 RFC 3986 percent-encoding 编码；路径分隔符 `/` 保留，非保留字符 `A-Z a-z 0-9 - . _ ~` 保留，其他字节使用大写十六进制 `%HH`。
- `#`、`?` 和路径文本中的字面 `%` 必须编码，避免与 locator 结构混淆。
- `N` 是不包含表头的 1-based CSV 逻辑记录序号；如字段内含换行，仍只计一条 CSV 逻辑记录，不使用物理文本行号。
- member 路径必须在读取前验证为相对路径，不得包含逃逸到输入根之外的父目录段。
- `source_record_ref` 在所属 Dataset 内唯一。Dataset 由 `source_checksum` 定位源制品，因此 locator 不重复写入 ZIP 文件名或外部路径。

## 5. Deterministic Canonical ID 合同

### 5.1 通用算法

ID 算法版本为 `source-import-id-v1`。每个 ID 的哈希输入是本节定义的有序 JSON 数组：

1. JSON 使用 UTF-8，不转义 Unicode，不含 BOM 或多余空白，分隔符固定为 `,` 和 `:`，空值编码为 JSON `null`。
2. 数组第一项固定为 `source-import-id-v1`，第二项是下表的 kind，后续项按表中顺序编码。
3. 对该 UTF-8 字节串计算 SHA-256，以 64 位小写十六进制输出。最终 ID 格式为 `<kind>:<sha256-hex>`。
4. 输入字符串按已解码的源文本或 Canonical ID 原值使用；不得 trim、改变大小写、展开科学计数法或执行 Unicode 归一化。
5. 可读 `message`、导入时间、文件系统绝对路径和输出目录不得进入任何 ID 输入。

### 5.2 MVP 会创建的 ID

| Canonical ID | kind | 有序输入（不含通用的版本和 kind） |
|---|---|---|
| `Dataset.dataset_id` | `dataset` | 小写的 `sha256:<source artifact SHA-256>` |
| `GridCase.case_id` | `case` | `dataset_id`, `source_case_key` |
| `Station.station_id` | `station` | `case_id`, `STATION`, `source_id`, `source_record_ref` |
| `Feeder.feeder_id` | `feeder` | `case_id`, `FEEDER`, `source_id`, `source_record_ref` |
| `Bus.bus_id` | `bus` | `case_id`, `BUS`, `source_id`, `source_record_ref` |
| `Equipment.equipment_id` | `equipment` | `case_id`, `equipment_type`, `source_id`, `source_record_ref` |
| `Terminal.terminal_id` | `terminal` | `equipment_id`, `terminal_no` |
| `TransformerWinding.winding_id` | `winding` | `equipment_id`, `winding_no` |
| `SimulationProfile.simulation_profile_id` | `simulation-profile` | `case_id`, `source_sim_config` |
| `OperationalSeries.series_id` | `operational-series` | `case_id`, `target_ref.entity_type`, `target_ref.entity_id`, `source_record_ref`, `source_field` |
| `FieldProvenance.provenance_id` | `field-provenance` | `target_ref.entity_type`, `target_ref.entity_id`, `field_path`, `origin`, `source_record_ref`, `source_field`, `source_mapping_id`, `source_mapping_version` |
| `DataQualityIssue.issue_id` | `quality-issue` | `dataset_id`, `case_id` 或 null, `target_ref.entity_type` 或 null, `target_ref.entity_id` 或 null, `field_path` 或 null, `code`, `source_record_ref` 或 null, `occurrence_key` |

补充规则：

- Source Import 对文件型源制品必须计算 SHA-256，即使 Canonical 通用合同允许其他产生方的 `source_checksum` 为空。
- `dataset_id` 只表示源制品身份；不包含 `source_uri`、Dataset 可读名称、`source_mapping_id`、`source_mapping_version` 或 Canonical spec version。同一字节级源制品在 mapping version 升级后的 dataset/case/source entity ID 必须保持不变。
- 源实体 ID 总是包含 `source_record_ref`。因此同一逻辑键的重复行仍保持独立身份，无需在重复发生后切换 ID 算法。
- `source_field` 使用源 schema 中的精确字段名。南京开关量测中，I/P/Q 三个字段分别形成至多一条 OperationalSeries。
- `occurrence_key` 是 validator/mapper 对同一 scope、field 和 code 的稳定机器区分符；只有一个事件时固定为空字符串。它可使用候选 source entity type 或稳定检查项名，不得使用列表遍历顺序、随机数或可读 message。
- `FieldProvenance` 表示 mapping 事实，因此它的 ID 包含 mapping ID/version；这不影响 Dataset、GridCase 和源实体的稳定身份。
- 本 MVP 不从南京源数据创建 `OperatingScenario`，因此不生成 `scenario_id`。`OperationalValue` 不含独立 CanonicalId；Line、SwitchingDevice、Transformer、AccessPoint、Load 和 DER 子记录复用 `equipment_id`，不另生成 ID。
- 新增由 Source Import 创建的 CanonicalId 字段时，必须先升级本规范并增加有序输入，不得在代码中自行拼接。

## 6. Import status 与错误恢复边界

### 6.1 三个独立结论

- `Dataset.import_status` 只按 `canonical_data_spec.md` 7.1 节判定 Source Adapter 是否完整处理并 account for 输入。
- `Canonical Valid` 只检查 Canonical 内部合同。一次 `COMPLETE` 导入可以产生部分 Canonical-invalid 记录或质量事件。
- 消费者 readiness 不属于 Source Import，不得从 `import_status`、issue severity 或引用解析率推导。

### 6.2 错误分类

| 分类 | 典型条件 | 必须处理 | 对 `import_status` 的影响 |
|---|---|---|---|
| Field-level recoverable | 可选 Decimal/Boolean/enum 无法解析；非空值超出 Canonical 取值约束；未知枚举 | 保留源记录。无法解析的 Canonical 字段为 `null`，原文写入 issue；能解析但超范围的源数值按 Canonical 规范保留并报 issue，不自动截断或替换 | 只要该值已 account for，不阻止 `COMPLETE` |
| Record-level fatal mapping | 创建顶层源实体所必需的 source ID 缺失；CSV 行结构无法与已识别表头对齐；关键字段缺失导致无法确定聚合目标 | 不得伪造 ID 或创建半身份实体，也不创建其 Terminal、子类或量测记录。必须以 `source_record_ref` 将原始字段完整写入 unmapped source record，并产生 `ERROR` issue | 若原行已完整保留且报告，可仍为 `COMPLETE`；否则为 `INCOMPLETE` |
| Run-level fatal | 无法读取源制品、无法计算 checksum、无法建立输入清单或导入过程在无可信产物前终止 | 停止发布导入产物；仅保留明确标记为失败的运行诊断 | 为 `FAILED` |
| Partial processing | 已建立 Dataset 身份，但存在已知文件或记录因 I/O、解码、取消或内部错误未被处理或保留 | 保留已完成部分的清单与诊断，不得声明 Import Complete | 为 `INCOMPLETE` |

直接源实体的 ID 列对该行是 record-level required。对南京 SimConfig，`Config_Key` 缺失也是 record-level fatal mapping error；空的可选 `Config_Value` 只表示目标字段为 `null`，不得伪造值。

## 7. DataQualityIssue 稳定代码与默认严重度

下表是 Source Import MVP 允许的最小稳定 code 集。南京 mapping `0.2.0` 没有 severity override，因此表中严重度对其是强制值。未来 Adapter 只能通过版本化 mapping 规范明文 override，实现不得按运行分支自行选择 severity。

| code | 默认 severity | 使用条件 |
|---|---|---|
| `SOURCE_FILE_MISSING` | `ERROR` | Adapter 合同声明的文件位置不存在 |
| `SOURCE_FILE_READ_FAILED` | `ERROR` | 已发现的文件因 I/O、损坏或解码错误无法完整读取 |
| `SOURCE_HEADER_MISMATCH` | `ERROR` | 表头与版本化 source schema 不一致 |
| `SOURCE_FILE_NO_DATA_ROWS` | `INFO` | 文件可读且表头正确，但没有数据记录 |
| `SOURCE_ROW_MALFORMED` | `ERROR` | CSV 逻辑记录无法与已识别表头对齐 |
| `SOURCE_REQUIRED_VALUE_MISSING` | `ERROR` | source entity ID、Config_Key 等 record-level required 值缺失 |
| `SOURCE_VALUE_PARSE_FAILED` | `WARNING` | 可恢复字段无法转换为声明类型 |
| `SOURCE_VALUE_OUT_OF_RANGE` | `ERROR` | 非空值可解析，但违反 Canonical 取值约束 |
| `SOURCE_ENUM_UNKNOWN` | `WARNING` | 封闭枚举出现未知源文本 |
| `SOURCE_IDENTIFIER_SUSPICIOUS_FORMAT` | `WARNING` | ID/引用出现科学计数法或已知精度损失外观；只报告，不修复 |
| `SOURCE_ID_DUPLICATE_IDENTICAL` | `WARNING` | 同一逻辑源 ID 组的原始字段逐值相同 |
| `SOURCE_ID_DUPLICATE_CONFLICT` | `ERROR` | 同一逻辑源 ID 组存在任一原始字段差异 |
| `SOURCE_REFERENCE_INVALID_LITERAL` | `WARNING` | 引用原文为映射规范明确声明的无效字面值，南京 MVP 当前为字符串 `"0"` |
| `SOURCE_REFERENCE_AMBIGUOUS` | `ERROR` | 在允许候选类型并集内命中多条，或唯一目标的身份已冲突 |
| `SOURCE_REFERENCE_UNRESOLVED` | `WARNING` | 非空引用在允许候选类型中无字面精确命中 |
| `SOURCE_MEASUREMENT_TIME_UNKNOWN` | `WARNING` | 源量测非空但时间戳未知，只能形成 `TIME_UNKNOWN` Snapshot |
| `GRID_CASE_FEEDER_MISSING` | `WARNING` | case 中没有可建立的 Feeder，`feeder_ref=null` |
| `GRID_CASE_FEEDER_AMBIGUOUS` | `ERROR` | case 中存在多个 Feeder 或 Feeder 身份重复/冲突，不得任选 |
| `CANONICAL_REQUIRED_FIELD_MISSING` | `ERROR` | 已建立 Canonical 记录缺少必需字段 |
| `CANONICAL_UNIQUE_CONSTRAINT_VIOLATION` | `ERROR` | Canonical ID 或其他 Canonical 唯一作用域被破坏 |
| `CANONICAL_REFERENCE_INTEGRITY_ERROR` | `ERROR` | 非空 Canonical `EntityRef` 指向不存在或类型不兼容的实体 |

`MISSING` 源引用主要由 `SourceReference`/Terminal 状态表达，不为每个空引用强制生成 issue。上表中特定的 feeder 级结果例外。issue 的存在不改变 6.1 节的边界。

与单条源记录相关的 issue 必须通过 Canonical 通用可追踪字段携带该行 `source_record_ref`；定位信息不得只出现在可读 `message` 中。`FieldProvenance` 的 `source_mapping_id/source_mapping_version` 同样使用 3 节所述通用可追踪字段。

## 8. 最小序列化与 unmapped source record

### 8.1 Canonical 输出

Source Import MVP 使用目录化 JSON/JSONL：

- `manifest.json`：格式版本、Canonical/mapping 版本、源 URI/checksum、导入时间、`import_status`、记录数和输出文件 checksum；
- `records/<record-type>.jsonl`：按 Canonical 记录类型分文件，每行一条记录；
- `field_provenance.jsonl` 和 `quality_issues.jsonl`：分别保存来源与质量事件；
- `import_report.json`：Import Complete 检查、Canonical Valid 检查和汇总统计。三类结论必须分开字段表达。

Identifier 和 enum 序列化为 JSON string，`Decimal` 序列化为不丢失精度的十进制 JSON string，缺失值为 JSON `null`。不得输出 NaN、Infinity 或二进制浮点近似值。

输出必须写入新的、与输入分离的目录。实现必须拒绝将输出目录设为 `data/raw/` 及其任何子目录，不得改写、替换或在原 ZIP 中新增 member。

### 8.2 Unmapped source records

`unmapped_source_records.jsonl` 是导入报告产物，不是 Canonical 实体。每条至少包含：

- `source_record_ref`；
- `source_case_key`；
- `source_file_type`；
- 按表头顺序保留的原始字段名与字符串值；
- 导致无法建立记录的 issue ID/code。

空源字段在该原始报告中保留为空字符串，不提前转换为 `null`。只有在 Canonical 映射边界才执行空字符串到 `null` 的转换。

## 9. Python 工程基线

1. Source Import MVP 支持 CPython `3.11`~`3.13`；`pyproject.toml` 必须声明 `requires-python = ">=3.11,<3.14"`。
2. `pyproject.toml` 是项目元数据、构建配置和直接依赖的唯一人工维护入口。项目使用现有 `src/` layout 和 `setuptools.build_meta` 构建后端。MVP 不增加任何第三方运行时依赖；ZIP、CSV、hash、JSON、Decimal 和 dataclass 均使用 Python 标准库。
3. `pyproject.toml` 使用 `[dependency-groups]` 声明 `dev = ["pytest>=8,<9"]`。依赖管理基线为 `uv`：由 `pyproject.toml` 声明依赖，提交 `uv.lock`，并使用 frozen lock 创建可重现环境。`uv` 是开发/构建工具，不是应用运行时依赖。
4. 标准环境同步命令为 `uv sync --dev --frozen`；标准测试命令为 `uv run --frozen python -m pytest`。在已根据同一 lock 激活的虚拟环境中，可使用 `python -m pytest`。
5. Slice A 只固定上述合同，不创建 `pyproject.toml`、lock 或代码。这些文件由后续实现 Slice 按本节创建。

## 10. 实现前检查

Source Import implementation 必须在开始前确认：

- 所用 source mapping 已列出每个引用字段的候选 source entity type 和 Canonical EntityRef type；
- 顶层源实体的 `identity_status` 已按 Canonical 合同计算；
- 每个 Source Import 可创建的 CanonicalId 字段都在 5.2 节有唯一算法；
- 质量 code 和 severity 来自本规范或明确的版本化 override；
- 任何未确认的业务语义都不会作为 resolver 默认规则。
