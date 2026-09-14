# 南京 source-only 导入（E1）

E0/E1 实现待 review；本入口没有 topology、completion 或 OpenDSS 功能。
依赖管理仍为 pyproject.toml + uv.lock，无新增运行时依赖。

```bash
uv sync --dev --frozen
uv run --frozen python -m grid_case_generator.io.nanjing_source inspect data/raw/南京数据.zip
uv run --frozen python -m grid_case_generator.io.nanjing_source import-source data/raw/南京数据.zip --output outputs/nanjing-e1/source-import --imported-at 2026-09-14T00:00:00+08:00
uv run --frozen python -m grid_case_generator.io.nanjing_source verify outputs/nanjing-e1/source-import
uv run --frozen python -m pytest
```

output 必须是新目录，不能位于 raw 或经符号链接写入；输入 ZIP 不解压、不改写。
imported-at 是显式导入审计时间，不是负荷、开关或气象的历史时间。固定该参数时重复运行
源数据与 manifest 等内容可逐字比较。导入命令处理所有 inventory cases，不按 Feeder 是否
存在过滤。inspect/verify 成功退出 0；import-source COMPLETE 退出 0，INCOMPLETE 退出 1。
无法建立 inventory 会抛错并在新输出目录保存 failure.json，不能当作有效导入产物。

manifest.json 保存文件 checksum/记录数；import_report.json 含全部 case 的状态与计数。
case_report.json 分开给出 import_status、canonical_valid、canonical_errors；ERROR issue
不直接导致导入不完整。INCOMPLETE 应检查 file_accounting、case error 和 failed_input。
row_accountability.jsonl 完整保存每条已读原行；unmapped_source_records.jsonl 另列 rejected。
resolutions.jsonl 是源引用结果，绝非电气拓扑。Load/DER 表为空时无 Load/DER 实体。

```python
from grid_case_generator.io.source_artifacts import verify_source_artifact, read_source_case

root = 'outputs/nanjing-e1/source-import'
verified = verify_source_artifact(root)
# case_id 从 import_report.json 取得；不使用 raw case path 拼接文件系统路径。
records = read_source_case(root, case_id, verified_artifact=verified)
```

批量读时先验证一次，再复用 verified_artifact；验证后必须保持 artifact 只读。
默认 read_source_case 会自行校验整个 artifact。返回 typed Canonical records，Decimal 和 enum
恢复原类型。manifest checksum 用于完整性检测，不是抵御恶意篡改 manifest 的签名。

后续 E2 以 source artifact 为输入做 topology-only audit；全部 5,159 cases coverage report
经用户 review 后才能进行 Load/PV completion 与 OpenDSS。最终 source-shaped derived CSV
交付将另有 schema/exporter，当前 JSON/JSONL 不是最终交付格式替代品。

若后续消费者需要来源/引用证据，使用同一模块的 `read_source_case_details`。返回
SourceCaseDetails，包含 records、issues、provenance、resolutions、accounting、unmapped_records；
accounting 内 RawCsvRecord 仍保留原始字符串、字段顺序和 SourceRecordRef。它与仅返回领域
记录的 read_source_case 使用同一 checksum 校验流程。

进程中断而尚未生成 manifest 的目录是未发布的部分输出。不要手工补 manifest 或混合
两次运行；重新选择新 output 目录执行导入。E1 未实现断点续跑。


VerifiedSourceArtifact 保存 canonical resolved root 和只读 manifest。两个 reader 的
verified_artifact 参数只接受这个 handle，且请求 root 必须 resolve 到同一目录；跨 root
复用或传裸 manifest 会被拒绝。相同目录的相对/绝对路径可用，symlink 路径仍拒绝。
API 已从 verified_manifest 改为 verified_artifact；通过 verified.manifest 查看校验清单。

信任模型：handle 只记录 verify 时的校验结论，不是文件系统快照。复用 handle 不会再次
计算 checksum；如果外部在 verify 后修改同一路径的普通文件，reader 可能读到修改后的
内容。调用方必须保证目录在使用期间不变；不能保证时，不传 handle，让 reader 重新
verify。即使重新 verify，也不宣称消除了校验与打开文件之间的 TOCTOU 竞争。
