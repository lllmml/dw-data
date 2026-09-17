# 配电网算例生成框架

本项目面向智能电网算子的测试与验证：忠实保留南京配电网 source facts，并通过版本化、可追溯且不覆盖源数据的派生过程，逐步形成统一数据模型、完整算例、OpenDSS 模型和数据质量报告。

当前已完成：

- Canonical foundation：领域记录、确定性 ID、质量代码和内存 JSON 序列化；
- Source import foundation：导入边界、错误分类、质量与 provenance 合同；
- Nanjing raw intake：南京 ZIP inventory、12 类 CSV schema registry、raw CSV 无损读取和 `source_record_ref` 追踪；
- E1 Source Import MVP：CSV → Canonical mapping、source artifact 校验与 typed reload；
- E2 Derived Topology：独立规则投影、source-side reachability、版本化 artifact 与 coverage report；
- E2.3-A evidence foundation completed：可复现的拓扑恢复证据、readiness 与候选反事实分析；accepted topology 保持不变。

E2.3-A 运行方法见 [recovery evidence guide](docs/guides/nanjing_topology_recovery.md)。E2.3-D Design Review 已通过；D1 synthetic completion contract/cohort refinement 已完成，运行与校验见 [D1 guide](docs/guides/nanjing_synthetic_completion_contract.md)。当前 synthetic eligible=0；synthetic topology implementation 仍未开始。停止等待 D1 review，不自动进入 D2、B/C、E3 或 OpenDSS。

运行方法见 [E2 guide](docs/guides/nanjing_topology_interpretation.md)，验收见 [E2 handoff](docs/handoff/2026-09-15-e2-topology.md)。

当前未完成：

- data completion；
- OpenDSS generation；
- QSTS；
- operator adapters。

## 目录结构

```text
.
├── AGENTS.md                    # 开发约束与协作说明
├── configs/                     # 可版本管理的运行配置
├── data/
│   ├── raw/                     # 甲方原始数据，只读保留
│   ├── interim/                 # 解析、清洗后的中间数据
│   └── processed/               # 完整且标准化的算例数据
├── docs/
│   ├── decisions/               # 待甲方或领域专家确认的决策问题
│   ├── intent.md                # 项目目标与范围
│   └── spec/                    # 数据字典、接口和规则规范
├── outputs/                     # OpenDSS 模型、报告等生成物
├── src/
│   └── grid_case_generator/
│       ├── io/                  # 外部数据读写与格式适配
│       ├── models/              # 统一内部数据模型
│       ├── generation/          # 设备参数与运行数据生成
│       ├── simulation/          # OpenDSS 模型及仿真衔接
│       ├── validation/          # 数据与仿真结果质量检查
│       └── operators/           # 下游智能电网算子数据接口
└── tests/                       # 与 src 分层对应的测试
```

目录中的 `.gitkeep` 仅用于保留尚无内容的目录。

## 设计原则

- 原始数据不可变：`data/raw/` 中的输入不在流水线内原地修改。
- 源事实与派生结果分离：允许按已确认规则生成拓扑、参数和时序派生物，但不得覆盖源数据，且必须记录 provenance。
- 规范先行：字段、单位、约束和生成规则先写入 `docs/spec/`，再实现代码。
- 分层解耦：输入格式、领域模型、数据生成、仿真和质量验证彼此独立。
- 结果可追溯：后续生成结果应能关联输入版本、配置和生成规则。
- 状态独立：Import Complete、Canonical Valid、OpenDSS Ready 和 Operator Ready 分别判定。
- 最小实现：只实现已由规范冻结的当前 Slice，不提前实现生成、仿真或算子适配。

## 开发环境

项目支持 CPython 3.11~3.13，使用 `uv` 和已提交的 lock 管理开发环境：

```bash
uv sync --dev --frozen
uv run --frozen python -m pytest
```

运行时不使用第三方依赖；`pytest` 仅属于开发依赖。
