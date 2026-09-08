# Source Intake Contract 规范

## 1. 文档信息

| 项目 | 值 |
|---|---|
| 状态 | Source Intake / Canonical Mapper 稳定接口 |
| 规范版本 | `0.1.0` |
| Canonical 合同 | `docs/spec/canonical_data_spec.md` `0.3.0` |
| Source Import 基线 | `docs/spec/source_import_foundation.md` `0.1.0` |
| 首个实现 | 南京 ZIP / CSV intake，mapping `nanjing_csv` `0.2.0` |

本文只定义 Source Intake 的输入、输出和不变量。它不定义 CSV 到
Canonical 字段的映射、重复身份判定、引用解析、连接推断或任何消费者逻辑。
本文中的“必须”“不得”为实现强约束。

## 2. 分层边界

数据流固定为：

```text
source artifact -> Source Intake -> intake output -> Canonical Mapper
```

- Source Intake 是唯一允许打开源 ZIP 和读取源 CSV 的层。
- Canonical Mapper 不得打开 ZIP、读取 CSV、解码文件、发现 case 或生成
  `source_record_ref`。
- Canonical Mapper 的 source-side 输入只能来自本规范的 intake 输出对象。
  Mapper 可接收已建立的父级 Canonical ID、显式身份状态和导入运行元数据；
  这些值不得冒充或改写源字段。
- Intake 不执行 Canonical 字段转换，不把空字符串转换为 `null`，不解析实体引用，
  不计算重复身份状态，也不创建 Canonical record。
- Mapper 前的任何阶段不得 trim、大小写转换、数值转换、Unicode normalization、
  科学计数法展开或以其他方式改写 raw string。

## 3. Intake 输入

### 3.1 Source artifact

当前南京实现接收一个指向 ZIP 文件的本地 `PathLike`。Source Intake 必须以只读
方式访问该文件，计算完整文件 SHA-256，并将调用方提供的路径表示记录为
`source_uri`。不得解压到 `data/raw/`，不得修改、替换或向 ZIP 新增 member。

无法打开源制品、无法计算 checksum 或无法建立可信 inventory 是 run-level fatal，
不得发布伪造或部分可信的 `SourceDatasetInventory`。

### 3.2 ZIP inventory

Inventory 必须枚举每个 ZIP member，并在 case discovery 前验证 member path：

- member path 必须是相对路径；
- `/`、`\` 或 Windows drive 开头的 absolute path 必须拒绝；
- 以 `/` 或 `\` 分段后的任何字面 `..` parent traversal segment 必须拒绝；
- inventory 不解压 member。

南京 `csv_member_count` 统计所有名称以精确小写 `.csv` 结尾的非目录 member；
`member_count` 统计 ZIP 中全部 member，包括显式目录 member。

### 3.3 Case discovery

南京 case discovery 使用版本化 filename/header registry。任一非目录 member 的
basename 与 registry 中某个 filename 字面精确相等时，其未经 trim、解码改写或
路径归一化的 parent path 是一个 `source_case_key`。同一 parent 只形成一个 case。

对每个已发现 case，inventory 必须逐一检查 registry 声明的 12 个精确 member
位置。缺失或重复位置不得用相似文件名代替，必须以 diagnostic account for。
只有 header 或没有 Feeder 数据行不影响 case discovery。

## 4. Intake 输出对象

下表中 `R` 表示必需，`N` 表示允许为空。所有集合均使用不可变 tuple；对象使用
不可变 value object / dataclass 表示。

### 4.1 `SourceDatasetInventory`

| 字段 | 类型 | 必需性 | 说明 |
|---|---|---:|---|
| `source_uri` | string | R | 调用方提供的 source artifact 路径表示；不得进入确定性 ID 输入 |
| `source_checksum` | string | R | `sha256:<64 位小写十六进制>` |
| `member_count` | integer | R | ZIP 全部 member 数，非负 |
| `csv_member_count` | integer | R | `.csv` 非目录 member 数，非负且不大于 `member_count` |
| `cases` | tuple[`SourceCaseInventory`, ...] | R | 按 `source_case_key` 字面排序，key 唯一 |
| `diagnostics` | tuple[`IntakeDiagnostic`, ...] | R | inventory/file-position 诊断；允许为空 tuple |

不变量：checksum 必须由 Source Intake 对完整 artifact 字节计算；Mapper 不得为获得
checksum 重新打开 artifact。Inventory 的存在只证明输入已被枚举，不等于 Import
Complete、Canonical Valid 或消费者 readiness。

### 4.2 `SourceCaseInventory`

| 字段 | 类型 | 必需性 | 说明 |
|---|---|---:|---|
| `source_case_key` | string | R | ZIP 内 case parent path 的精确保留值，非空 |
| `members` | tuple[(`SourceFileType`, string/null), ...] | R | registry 顺序下每类文件的精确 member path；缺失/重复时为 null |

不变量：每个 registry `SourceFileType` 恰好出现一次；非空 member path 必须通过
安全路径检查，且 parent path 精确等于 `source_case_key`。`is_complete` 只表示预期
文件位置各有一个 member，不表示表头正确、有数据行或 Canonical 可用。

### 4.3 `RawSourceFile`

| 字段 | 类型 | 必需性 | 说明 |
|---|---|---:|---|
| `source_case_key` | string | R | 所属 case 的精确 key |
| `source_file_type` | `SourceFileType` | R | 版本化 registry 中的文件类型 |
| `member_path` | string | R | 已验证安全的完整 ZIP member path |
| `header` | tuple[string, ...]/null | N | CSV parser 解码后的逻辑表头；读取前失败时为 null |
| `records` | tuple[`RawCsvRecord`, ...] | R | 按 `data_row` 顺序；允许为空 tuple |
| `diagnostics` | tuple[`IntakeDiagnostic`, ...] | R | 文件或记录级 intake 诊断 |

不变量：只有 header 与该 registry 版本字面精确相等时才产生 records。只有表头的
文件产生空 records 和 `SOURCE_FILE_NO_DATA_ROWS`；空文件或表头偏差产生
`SOURCE_HEADER_MISMATCH`。Intake 不把上述状态转换为 Canonical record。

### 4.4 `RawCsvRecord`

| 字段 | 类型 | 必需性 | 说明 |
|---|---|---:|---|
| `source_case_key` | string | R | 所属 case key |
| `source_file_type` | `SourceFileType` | R | 所属 source 文件类型 |
| `header` | tuple[string, ...] | R | 已识别版本化表头 |
| `data_row` | integer | R | 不含 header 的 1-based CSV 逻辑记录号 |
| `source_record_ref` | `SourceRecordRef` | R | 由 Intake 创建的稳定记录 locator |
| `values` | tuple[string, ...] | R | `csv` 完成结构性引号处理后的原始字段值 |
| `fields` | tuple[(string, string), ...]/null | N | 字段数匹配时按 header 顺序配对；畸形记录为 null |

不变量：`values` 的每一项必须是 `str`；空 CSV 字段保持 `""`。Intake 不执行
dtype inference。引号内 embedded newline 属于同一逻辑记录。`fields` 非空时，其
字段名序列必须等于 `header`，其值序列必须等于 `values`；`fields=null` 时仍必须
保留 `header` 和全部 `values`，以供 unmapped source record accounting。

### 4.5 `SourceRecordRef`

`SourceRecordRef` 是不可变、string-compatible value object，其标量值固定为：

```text
zip-member:<encoded-member-path>#data-row=<N>
```

- percent encoding、保留字符和大写 `%HH` 规则严格使用
  `source_import_foundation.md` 4.1 节；
- `N` 是不含 header 的 1-based CSV 逻辑记录号；
- 同一 artifact 中每个可定位 CSV 逻辑记录必须具有唯一且可重复生成的值；
- Mapper 只能复制该值到 Canonical `source_record_ref` 或 issue/unmapped accounting，
  不得重新编码路径、重新计算行号或创建替代 locator。

### 4.6 `IntakeDiagnostic`

| 字段 | 类型 | 必需性 | 说明 |
|---|---|---:|---|
| `code` | `IntakeDiagnosticCode` | R | Intake 稳定诊断代码 |
| `message` | string | R | 可读说明，不参与任何确定性 ID |
| `source_case_key` | string/null | N | 能定位到 case 时填写 |
| `member_path` | string/null | N | 能定位到 member 时填写 |
| `source_record_ref` | `SourceRecordRef`/null | N | 能定位到逻辑记录时填写 |
| `expected_header` | tuple[string, ...]/null | N | header 诊断适用时填写 |
| `observed_header` | tuple[string, ...]/null | N | header 已可读取时填写 |

当前稳定 intake codes 为：`SOURCE_FILE_MISSING`、`SOURCE_FILE_READ_FAILED`、
`SOURCE_HEADER_MISMATCH`、`SOURCE_FILE_NO_DATA_ROWS`、`SOURCE_ROW_MALFORMED`。

## 5. Intake diagnostic 与 Canonical issue 边界

`IntakeDiagnostic` 不是 `DataQualityIssue`，不具有 Canonical `issue_id`、severity、
target ref 或 field path。它陈述 Intake 观察到的文件/原始记录状态，不得被当作
Canonical record 序列化。

后续 mapping/import policy 层负责：

1. 按版本化 mapping 将适用 diagnostic 转换为 `DataQualityIssue`；
2. 使用 Source Import 默认 severity 或该 mapping 明文定义的 override；
3. 通过已有 ID factory 生成 issue ID；
4. 判断输入是否已 account for，并独立计算 `Dataset.import_status`。

Diagnostic 的存在、数量或 code 本身不直接决定 `import_status`。转换不得丢失已有
case/member/record locator，且可读 `message` 不得进入确定性 ID。

## 6. Mapper 输入约束

- Mapper 可接收 `SourceDatasetInventory`、`SourceCaseInventory`、`RawSourceFile`、
  `RawCsvRecord` 和显式 mapping/import metadata。
- Mapper 不接收 `ZipFile`、文件 handle、CSV text stream 或未经过 Intake 的 row dict。
- Mapper 对 raw source value 的访问必须来自 `RawCsvRecord.values/fields`；record-level
  fatal 时必须使用同一对象保留 header、values 和 `source_record_ref`。
- Mapper 在 Canonical 边界才可按版本化规则执行 `"" -> null`、Decimal/Boolean/enum
  转换；转换失败必须保留原文并按 Source Import error contract account for。
