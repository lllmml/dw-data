# 配电网算例生成框架

本项目面向智能电网算子的测试与验证：在保持南京配电网原始拓扑不变的前提下，逐步形成统一数据模型、完整算例、OpenDSS 模型和数据质量报告。

当前已实现 Source Import 的 Canonical foundation：领域记录、确定性 ID、质量代码和内存 JSON 序列化。尚未实现南京 ZIP/CSV 读取、字段映射、引用解析、参数生成或仿真。

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
- 规范先行：字段、单位、约束和生成规则先写入 `docs/spec/`，再实现代码。
- 分层解耦：输入格式、领域模型、数据生成、仿真和质量验证彼此独立。
- 结果可追溯：后续生成结果应能关联输入版本、配置和生成规则。
- 最小实现：只实现已由规范冻结的当前 Slice，不提前实现生成、仿真或算子适配。

## 开发环境

项目支持 CPython 3.11~3.13，使用 `uv` 和已提交的 lock 管理开发环境：

```bash
uv sync --dev --frozen
uv run --frozen python -m pytest
```

运行时不使用第三方依赖；`pytest` 仅属于开发依赖。
