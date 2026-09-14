# 南京 Source Import MVP pipeline

版本 0.1.0（E1）。继承 canonical 0.4.0、nanjing_csv 0.3.0、intake、identity、reference
及 Station/Feeder/Bus assembly 合同。只新增完整导入编排，不改变冻结匹配或源 ID 算法。

## 输入、输出与处理顺序

Source Intake 单独持有只读 ZIP 会话，inventory 后每个 member 至多读取一次；按 case
产生 RawSourceFile。case mapper 只消费 intake objects。先分类所有有合法身份的行，复用
Station/Feeder/Bus assembly；再映射/发布八类 Equipment，建立完整 typed candidates 与
conflict markers 后解析 Terminal。源 Terminal 永远 connectivity NOT_ASSESSED/null。

Equipment outcome 包含 Equipment 与其 source 子记录 bundle；使用现有 Equipment、
Terminal、Line、SwitchingDevice、Transformer/Winding、AccessPoint、Load、DER。
identical duplicate 只发布最小 locator 的完整 bundle，所有行仍保留 accounting；引用仍
AMBIGUOUS。conflicting duplicate 不发布任何 bundle，保存 conflict marker 与逐行 issue。
不重新实现 identity classifier 或 generic resolver。source winding 1/2 仅对应 HV/LV 列
和端点位置，不断言实际电气方向，不继承未提供的 winding 容量。

所有原行完整写入 row_accountability.jsonl（含 header、values、fields、locator、终态、
canonical refs、issue IDs）；rejected 行另写 unmapped_source_records.jsonl。identical
非代表行 field issue 重新指向已发布实体；conflict field issue target=null。
非空未知 phase 保留原文、phases=null、SOURCE_ENUM_UNKNOWN，不默认 ABC。
Decimal 解析失败 null+原文 issue；可解析非法值保留+SOURCE_VALUE_OUT_OF_RANGE。
ID/引用科学计数法或可疑格式只报告；引用 "0" 仍参与严格解析且单独报告 invalid literal。

开关 I/P/Q 各非空字段建立至多一个 SNAPSHOT series/value；无时间戳为 TIME_UNKNOWN，
保留有符号 P/Q，不能拼成时序。无法确认的非空时间文本保留在 accounting，报 TIME_UNKNOWN，
不猜时区。非空但无法解析数值只报告，不创建伪值。

SimConfig 聚合为 source SimulationProfile。每个已发布字段都有 SOURCE FieldProvenance
定位键值行；重复相同键值使用最小 locator 代表、所有行可追踪；冲突键不选择值，目标
字段 null，使用 SOURCE_VALUE_PARSE_FAILED/WARNING（occurrence=Config_Key）记录冲突。
未知键保存在 namespaced extensions，同时保留 raw rows；无 Config_Key 的行 record-fatal。
SourceBus/OutputVoltageBus 只匹配 BUS。仿真 mode/solver 原文保存，不转换成引擎行为。

## Accounting / status

每个预期文件位置、diagnostic、已读行、非空字段必须有归宿。MAPPED/DUPLICATE/
UNRESOLVED/REJECTED 行终态延续现有优先级。完整原行是未知/未解释字段的保真归宿，
并不声称其已得到业务解释。issues 不直接决定 ImportStatus。
缺文件、空文件、header mismatch 有明确 inventory/file accounting 可为 COMPLETE。
读取/解码中断、CSV parser 无法继续、非预期 case error 为 INCOMPLETE（已建 inventory）。
可完整保留的列数不符行是 record-fatal，仍可 COMPLETE。无可信 inventory 时 FAILED，
仅发布失败诊断。每个 case 异常单独报告，继续后续 case；不创建虚假成功记录。
Canonical Valid 检查类型/必填身份、ID 唯一、引用完整性、源数值范围及 provenance，
与 ImportStatus 分开。不输出 OpenDSS Ready 或仿真四状态。

## Artifact 0.1.0

新目录中存 manifest.json、inventory.json、dataset.json、import_report.json、cases/<case-id>/：
records/<type>.jsonl、field_provenance.jsonl、quality_issues.jsonl、resolutions.jsonl、
row_accountability.jsonl、unmapped_source_records.jsonl、file_accounting.json、case_report.json。
case_id 作为路径片段必须来自源 ID factory，不把 raw case path 直接拼接到输出。
manifest 记录 source checksum、schema/mapping/software version 和各文件 SHA256/记录数。
序列化复用 canonical_json：Decimal 为十进制字符串，无 float/NaN/Infinity。
读取器检查版本、相对安全路径、symlink、文件完整清单与 checksum，再恢复 typed records。
输出拒绝 raw、任何输入目录/源文件、已有目录；中断产物 manifest 不声明成功。
运行 imported_at 为显式参数；相同输入与显式元数据产生相同字节，不把时钟隐藏在纯函数中。
无新依赖；uv.lock/frozen 环境保持现有方式。

## 验收

设备类型/端点位置与 null；mixed typed references；duplicate/conflict accounting；
SimConfig 字段 provenance；无时标量测；非法字段；畸形 CSV/缺表/空表/读取中断；
输入顺序确定性；artifact roundtrip/checksum/path guards；全部 case 均有结果。
E1 不包含 topology、synthetic head、completion、delivery 或 OpenDSS 实现。

API：map_source_case(SourceCaseInventory, tuple[RawSourceFile], dataset_id, diagnostics)
返回 immutable SourceCaseResult；import_archive(path, new_output, imported_at) 按 case 写出。
imported_at 必须为带 offset 的 ISO 8601 时间；作为显式 audit metadata，不是业务量测时间。
命令入口 `python -m grid_case_generator.io.nanjing_source` 只提供 inspect/import-source/verify。

`read_source_case_details` 还恢复 typed quality issues、FieldProvenance、ReferenceResolutionResult、
RowAccountability 和 UnmappedSourceRecord；这些 sidecars 是 E2 的 source evidence 输入，
无需重新打开 CSV。只读 case details 不建立或推断任何 electrical connectivity。

E1 review-fix：unknown Config_Key 的 extension key 严格采用 mapping 0.3.0 的
`nanjing.<key>`；相应 provenance field_path 为 `simulation_profile.extensions.nanjing.<key>`。
verify_source_artifact 返回绑定 resolved root 的 VerifiedSourceArtifact；两个 reader 的
verified_artifact 参数只接受该 handle，拒绝其它 root 或裸 manifest。复用 handle 不重算
checksum，调用方必须保证验证后目录不变；它不是文件系统快照或 TOCTOU 防护。
