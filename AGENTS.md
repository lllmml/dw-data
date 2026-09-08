# AGENTS.md

本文件适用于整个仓库。

## 项目边界

- 以 `docs/intent.md` 为需求依据。
- 忠实保留甲方 source facts，不在 `data/raw/` 中修改或覆盖源文件，不静默修复原始字段、ID 或引用。
- 允许按已确认规则生成版本化、可追溯的派生拓扑、参数和时序数据；派生结果不得覆盖或冒充 source data。
- 在规范获得确认前，不臆造线路、负荷、分布式能源或仿真参数。

## 目录职责

- `docs/spec/`：数据字典、接口契约、生成规则与验收标准。
- `configs/`：环境无关、可复现的运行配置；敏感信息不得提交。
- `src/grid_case_generator/io/`：文件读取、写出和外部格式适配。
- `src/grid_case_generator/models/`：与具体文件格式无关的领域模型。
- `src/grid_case_generator/generation/`：规则驱动的数据生成逻辑。
- `src/grid_case_generator/simulation/`：OpenDSS 导出与仿真编排。
- `src/grid_case_generator/validation/`：结构、取值和仿真质量检查。
- `src/grid_case_generator/operators/`：面向下游算子的稳定数据接口。
- `tests/`：测试代码，结构尽量与 `src/` 对应。

## 开发约束

- 先更新规范和测试，再添加相应实现；避免超出当前需求的抽象。
- 数据模型必须明确字段含义、单位、可空性和标识符规则。
- 随机生成必须支持显式种子，并记录所用配置与规则版本。
- 流水线各阶段写入独立目录，不覆盖输入；大体积生成物放入 `outputs/`。
- 模块之间通过领域模型或明确契约交换数据，不依赖隐式全局状态。
- 新依赖应说明用途，并选择单一、可复现的依赖管理方式。
- 提交前运行与改动范围相符的测试和静态检查，并在交付说明中报告结果。

## 当前状态

已完成：Canonical foundation、Source import foundation，以及南京 ZIP inventory、12 类 CSV schema registry、raw CSV 无损读取和 `source_record_ref` 追踪。

未完成：CSV → Canonical mapper、topology projection、data completion、OpenDSS generation、QSTS 和 operator adapters。除非任务明确要求且相应规范已确认，不实现这些能力。
