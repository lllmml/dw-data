# 南京 E2 派生拓扑

E2 只消费已持久化的 E1 Canonical records、row accountability 和 source evidence。
运行入口先执行 `verify_source_artifact`，再经 `read_source_case_details` typed reload。
不重新打开 ZIP，不修改 E1、Terminal connectivity 或 SourceReference status。
无需新增依赖，使用项目既有 uv lock / Python 3.11–3.13 环境。

## 全量运行

在仓库根目录执行：

```bash
uv run --frozen python -m grid_case_generator.generation \
  --source outputs/nanjing-e1/source-import-v2 \
  --output outputs/nanjing-e2/topology-v2 \
  --config configs/nanjing_topology.toml
```

输出目录必须尚不存在，且与 E1 目录相互独立。重复实验使用新的版本目录。
全量输入 inventory 与 E1 import report 的 case 集合必须一致；不按 canonical_valid、
Feeder 是否存在、Line 是否存在或规模筛选。南京正式输入应覆盖全部 5,159 cases。
每 100 个 case 打印进度。输入 manifest 的 SHA256 写入 E2 manifest；不记录运行时间、
绝对路径或随机种子，以保持输出确定性。

## 单 case

从 E1 `import_report.json` 找到 `case_id`，例如：

```bash
uv run --frozen python -m grid_case_generator.generation \
  --source outputs/nanjing-e1/source-import-v2 \
  --output outputs/nanjing-e2/single-case-v1 \
  --case-id 'case:5c4d95b9c5ed2a743eca2d54297c9cb66757b44b90c8e3db8ce214ff5a5f4399'
```

单 case 仍先校验完整 E1 artifact；只输出选择的 case。

## 查看结果与排除原因

- `dataset_coverage_report.json`：全部数量、feeder anchor 状态、按规则/状态计数、排除原因分布。
- `cases/<case-id>/case_report.json`：源 case key、电压、source/published/projection/reachable 数量和 usable 判定。
- `cases/<case-id>/topology.json`：节点、支路、MV head、可达节点和可达 Transformer IDs。
- `cases/<case-id>/projections.jsonl`：全部解释记录及完整有序去重证据。
- `cases/<case-id>/exclusions.jsonl`：非 PROJECTED 记录子集，`exclusion_reason` 为稳定枚举代码。
- `manifest.json`：文件 checksum/count、输入 checksum、case inventory、规则与 ID 版本。
- `config.json`：本次有效配置快照（Decimal 用字符串无损保存）。

`source_line_rows` 是全部 E1 Line 行；`published_lines` 是发布的 Equipment/Line 实体；
`projected_lines` / `excluded_lines` 划分已发布 Line；`unpublished_line_rows` 单列未发布源行，
`unpublished_line_groups` 统计没有发布实体的身份组/不可识别行。不同口径不能相加当作实体数。
Switch/Transformer/AccessPoint 同样单列 source rows、published entities 和 candidate groups。
`*_candidates` 包括未发布冲突身份组；未发布记录引用既有 GridCase 加原始 locators，
不生成假的 source entity ID。

BUS 和 STATION rule counts 按 Line endpoint 计数；Switch/Transformer/AccessPoint rule counts
按设备/未发布身份组计数，排除其重复的 Line endpoint 映射。全局 projection status 和
exclusion reason distribution 则统计所有 projection records，包括设备、端点和 Line，
因此一个根因可能出现在多条可追溯映射中，不等于独立设备故障数。
`switch_closed/open/unknown` 仅统计成功 structural projection 的 Switch 状态。

## 配置与规则

配置位置：`configs/nanjing_topology.toml`。修改唯一键即可改变 fallback：

```toml
fallback_nominal_voltage_kv = 10.5
```

必须为有限正数；未知键（包括 seed）、布尔值和字符串一律拒绝。
明确 20kV 名称用 20.0 kV，明确 10kV 名称用 10.5 kV；两者使用 NAME_INFERENCE。
无明确命名才使用 fallback / DEFAULT。名称冲突排除；source Bus 与 SimConfig 不回写。
Feeder 上游 110 kV Bus 仅保留为证据，不投影成 MV junction，也不生成站内主变。

规则及限制见 [冻结合同](../spec/nanjing_topology_interpretation.md)。只有完整闭合的
Station → Feeder source Bus 证据链可连接 MV head。Switch 只允许完整源图的一入一出两条
不同 Line；Transformer 只允许唯一入 Line 的 MV attachment。显式设备端点语义未确认时
保守排除；AccessPoint 不转成 Load。完整源行图计数不因 Line 被排除而减少。

usable electrical subgraph 定义为：有有效 synthetic MV head，且存在从它出发的
accepted conducting Line path。`has_reachable_transformer` 独立计算。图遍历只经过已接受
Line 和 CLOSED Switch；OPEN/UNKNOWN 阻断；环保留。结构投影的 Transformer 不一定可达。
这些指标不声明 OpenDSS Ready。Q-CONN-001、Q-TRANSFORMER-001 仍为 OPEN。

## 校验与 typed reload

```python
from grid_case_generator.io.topology_artifacts import (
    verify_topology_artifact, read_topology_case,
)
root = 'outputs/nanjing-e2/topology-v2'
verified = verify_topology_artifact(root)
case_id = verified.manifest['case_ids'][0]
result = read_topology_case(root, case_id, verified_artifact=verified)
print(result.coverage)
```

验证后的输入必须保持不变（与 E1 verified-reader 合同一致）。E3 可读取本 artifact；
E2 review 通过且 E3 另获授权之前，不实现参数补全、LV bus、Load/PV、时序、OpenDSS 或 QSTS。
