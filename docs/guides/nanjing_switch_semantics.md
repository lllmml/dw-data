# E2.1 Switch connectivity semantics investigation

E2.1 是独立、只读的源数据诊断。E1 SourceReference、Terminal connectivity、
E2-v1 interpreter 和 `outputs/nanjing-e2/topology-v2/` 都保持不变。
所有 counterfactual 明确标记 `COUNTERFACTUAL ONLY / NOT ACCEPTED TOPOLOGY`，
不输出替代 topology，也不实现 SERIES_SWITCH_V2。

## 运行

在仓库根目录，使用既有 uv lock 环境：

```bash
uv run --frozen python -m grid_case_generator.analysis \
  --source outputs/nanjing-e1/source-import-v2 \
  --baseline outputs/nanjing-e2/topology-v2 \
  --output outputs/nanjing-e2-1/switch-semantics-v1
```

程序先完整校验两个输入及它们的 checksum 关联、case inventory；然后从 E1 typed
records/accountability 重建局部 motif。不会重新打开 raw ZIP，也不筛掉异常 case。
输出目录必须尚不存在，且与两个输入相互独立。每 100 cases 显示进度。

只分析一个 case 时加 `--case-id 'case:<64位hash>'` 并使用新输出目录。
单 case 模式仍校验完整输入。没有 random seed 或 random sampling。

## 文件与口径

| 文件 | 内容 |
|---|---|
| manifest.json | 分析版本、输入 E1/E2 manifest checksum、各输出 checksum/count |
| dataset_summary.json | 完整 population、候选数量、语义分类、case purity 摘要 |
| switch_candidates.jsonl | 每个候选的 A/B/X/Y、两条 Line、六个端点的原始状态/目标、诊断结果、证据 refs |
| motif_distribution.json | 互斥 motif、可重叠 equality flags、状态/IsTie/HasMeasurement/外侧实体类型分组 |
| endpoint_type_distribution.json | 原 SourceReference 与额外精确查询并列统计、实体类型对、图距离、ID 差异特征 |
| case_pattern_summary.jsonl | 每 case 候选数、主导 motif/purity、minority 数、counterfactual 指标 |
| explicit_endpoint_breakdown.json | 当前 E2 显式端点排除设备的细分与全部候选的细分 |
| degree_distribution.json | 全部源身份组、UNIQUE Switch、baseline SWITCH_DEGREE 的独立 degree/direction 分布 |
| counterfactual_reachability.json | 原基线及 A/B/C 的独立分析指标；没有明确 layer 子集时 C 不评估 |
| representative_examples.json | 每类按 case_id + source_record_ref 排序取前三个真实 motif |

`source_switch_rows`、`published_switch_entities`、`source_switch_identity_groups`
与候选数是不同口径。Baseline 原因只取设备映射，不重复统计 Line terminal 映射。
同一个设备出现在不同统计维度中不表示多台 Switch。百分比以对应候选 population
为分母，保留六位小数；case_count 以独立 case ID 去重。

## 如何理解结果

- `source_reference_status/source_target_ref/source_entity_type` 是 E1 事实。
- `diagnostic_status/diagnostic_target_ref/diagnostic_entity_type` 是独立的、全类型
  case-local 精确文本查询；它不回写 SourceReference，也不改变 Candidate Matrix。
- 已有 EXACT 引用的目标在源图诊断中优先；额外类型中的同文本 ID 不覆盖原引用。
- `COMPATIBLE_SOURCE_EVIDENCE` 只表示源端点声明与 Line 外侧端点相符，不表示真实
  电气连接已确认。`UNRESOLVED_SEMANTICS` 不等于 confirmed conflict。
- 图距离按 SourceReference 的 owner→target 边计数，Line 自身也是顶点；
  经一条 Line 从一个 endpoint 到另一个 endpoint 通常是两跳。
- Bus→Station membership 是可验证的不同 source entity layer 证据。
  距离近、同 Station 或数字接近本身不构成兼容性规则。
- ID 特征只比较给定的 A/X 或 B/Y，不做搜索、repair、科学计数法展开或拓扑接受。
- `minority_motif_count` 仅表示不是该 case 主导 motif 的记录数，不表示数据错误。

Scenario A 忽略 Switch 显式端点字段，保留 UNIQUE、一入一出、exact inner references
以及 NormalState；B 仅选明确 direct/reverse compatible source evidence；C 仅在有
明确 Bus/Station 层级关系子集时加入该子集。全部非 Switch E2 决策原样复用，
包括 Transformer attachment、Bus 电压排除和 feeder head。OPEN/UNKNOWN 不导通。

## 校验

```python
from grid_case_generator.io.switch_semantics_artifacts import verify_investigation_artifact
manifest = verify_investigation_artifact('outputs/nanjing-e2-1/switch-semantics-v1')
```

验证后的输入在运行期间须保持不变。任何 V2 建议仅在单独 proposal 中，状态为
PROPOSED / NOT ACCEPTED / NOT IMPLEMENTED，等待用户 review。
