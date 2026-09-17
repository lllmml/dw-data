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

已完成：Canonical foundation、Source import foundation、南京 raw intake、E1 Source Import MVP（含 mapper 与可校验 typed reload），以及 E2 derived topology interpreter、reachability 和持久化 coverage artifact。E2.3-A evidence foundation completed：全量 failure evidence、readiness 和候选 counterfactual artifact；不改变 accepted topology。

E2.3-D Design Review 已通过；E2.3-D1 contract/cohort refinement 已完成：正式合同、只读 eligibility/prohibition/readiness、全量 action cohorts 与可验证 artifact。D2 已实现 proposal-only engine、版本化业务确认输入、独立 validation 和 counterfactual artifact；不等于 accepted topology completion。

D3 按用户单独授权实现 deterministic recovery：EXACT DIRECT 普通 series Switch、
唯一入 Line 且远端 UNBOUND 的 leaf Switch 表示；发布独立 accepted topology v2，
重算 physical/conducting coverage 与 D2 eligibility。v1/source/D2 保持不变，不整体接受 S2。
规范见 `docs/spec/nanjing_deterministic_topology_recovery.md`，交付见 D3 handoff。

下一 Gate：D3 交付 review。D2 synthetic 提案仍最多 PROPOSED/VALIDATED，未 apply。
不自动进入 synthetic backbone、synthetic junction、zero-Transformer device generation、
E3、OpenDSS 或 QSTS；这些能力仍须单独明确授权。

未完成：E3 data completion、OpenDSS generation、QSTS 和 operator adapters。E2 review 通过且用户明确授权前，不进入 E3；后续能力仍须相应规范已确认。
