# E0 / E1 南京 Source Import 验收交接

日期：2026-09-14。状态：实现与验收完成，等待用户 review；未进入 E2。
E0 commit：`34993aa`。E1 实现、测试和本报告保存在同一个独立 commit。
README/AGENTS 的已完成状态没有提前更新。

## 边界

E0 冻结了 synthetic MV feeder head 与 BUS/STATION/SERIES_SWITCH_V1/
LEAF_TRANSFORMER_MV_V1 派生规则和 E2 coverage gate。Q-CONN-001、Q-TRANSFORMER-001
保持 OPEN；现有 source reference contract 与 SourceImportIdFactory 算法不变。

E1 只实现 source import：intake 只读批量会话；Equipment 与源子记录、source snapshot、
SimConfig mapper；设备 duplicate assembly；完整 accounting；源引用集成；source artifact
持久化、校验及 typed evidence 重载。source connectivity 仍为 NOT_ASSESSED/null。

source Feeder anchor 保持 110 kV 源值；没有 synthetic head、站内主变、Load/PV、拓扑代码
或 OpenDSS 实现。Load/DER 发布实体均为 0。

## 验证命令与结果

```bash
uv run --frozen python -m pytest
uv run --frozen python -m compileall -q src tests
git diff --cached --check
uv run --frozen python -m grid_case_generator.io.nanjing_source import-source data/raw/南京数据.zip --output outputs/nanjing-e1/source-import-v2 --imported-at 2026-09-14T00:00:00+08:00
```

- 测试：168 passed；含跨进程 PYTHONHASHSEED、duplicate/conflict、故障隔离、原值保留、
  110 kV anchor、持久化 roundtrip、provenance、路径防护和 checksum 篡改检测。
- Python 语法编译与 Git 空白检查通过；项目没有配置独立 lint/type-check 工具，未新增依赖。
- 全量 5,159 cases 均为 Import COMPLETE；case 程序错误 0。
- 已读并完整 account for 1,007,354 条 source rows，与既有审计逐表一致。
- Canonical Valid：5,121 cases；38 cases 存在保留的源数值质量问题；不混淆导入状态。
- 通过 verify_source_artifact 校验 96,290 个文件的 SHA256、记录数及完整文件清单。
- typed reader 抽查普通、duplicate conflict、非法源值、缺 Feeder 四类真实 case，
  重载全部 source evidence 并用当前 validator 核对，结论与持久化报告一致。
- 原 ZIP SHA256 保持 `7ae1e246e5ac8073053d280cd64e66cdc491d5303dc2c15aa74f823be202de25`。

## 原始行数

| 类型 | source rows |
|---|---:|
| STATION | 59,375 |
| BUS | 68,537 |
| SWITCH | 272,716 |
| DISCONNECTOR | 18,016 |
| FEEDER | 5,134 |
| EARTHING_SWITCH | 225,301 |
| ACCESS_POINT | 34,661 |
| LINE | 156,527 |
| TRANSFORMER | 110,338 |
| LOAD | 0 |
| DER | 0 |
| SIM_CONFIG | 56,749 |

这些是 source rows，不等于 published entities。Equipment 发布 815,815 条：identical
组只发布一个 bundle，conflicting 组不发布 bundle；所有原行仍完整保存在 accounting。
source 无时标量测字段 issues 为 23,314，发布 OperationalSeries/Value 各 22,174；差额
来自同一 duplicate publication policy，不能把未发布代表误解为删除 source measurement。

## 源引用结果

- EXACT：432,008
- MISSING：890,235
- AMBIGUOUS：2,826
- UNRESOLVED：130,588

这些是源引用解析计数，绝非 electrical topology coverage，也不表示可仿真。
25 个缺 Feeder case 保留；异常大 case 也完整导入，E1 不过滤 source rows。

## 产物与使用

有效完整产物：`outputs/nanjing-e1/source-import-v2/`。
验收汇总：`outputs/nanjing-e1/source-import-v2-verification.json`。
这些大体积运行结果被 .gitignore 排除；本报告和可重现命令进入 Git。

`outputs/nanjing-e1/source-import-v1/` 是此前会话中断留下的部分输出，没有 manifest，
不是有效完整 artifact。未覆盖或混入 v2。E1 不支持断点续跑，使用新输出目录重跑。

完整 API/CLI 和数据边界见 `../guides/nanjing_source_import.md` 与
`../spec/nanjing_import_pipeline.md`。内部 JSON/JSONL 不是最终 source-shaped CSV 交付替代。

## 下一步 gate

停止等待 E1 review。收到批准后才进入 E2，实现派生 topology 并执行全部 5,159-case
coverage audit；该报告再经 review 后才可开始 E3 Load/PV completion 和 OpenDSS exporter。
