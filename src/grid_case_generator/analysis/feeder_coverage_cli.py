"""Read-only feeder coverage and switch semantic sensitivity over E2.2 artifacts."""
import argparse
from grid_case_generator.analysis.feeder_coverage import POLICIES, REASONS
from grid_case_generator.io.feeder_coverage_artifacts import run_feeder_analysis


def render_report(reports):
    report = reports['feeder_coverage']; population = report['population']; policies = report['policies']
    rows = []
    for policy in POLICIES:
        v = policies[policy]; main = v['transformer_goal_status']; strict = v['strict_topology_status']
        rows.append(f"| {policy} | {main['FULL']} | {main['PARTIAL']} | {main['FAILED']} | {strict['FULL']} | {strict['PARTIAL']} | {strict['FAILED']} | {v['target_full_but_strict_incomplete']} |")
    s2 = policies['S2']; failures = reports['failure_analysis']['policies']['S2']['failed']
    semantic = reports['policy_recovery']['semantic_relaxation']
    state = reports['policy_recovery']['from_S2']
    failure_rows = []
    for reason in REASONS:
        a = state['S2_UNKNOWN_NONCONDUCTING']['by_primary_failure_reason'][reason]
        b = state['S2_UNKNOWN_CONDUCTING']['by_primary_failure_reason'][reason]
        c = semantic['by_primary_failure_reason'][reason]
        failure_rows.append(f"| {reason} | {failures['primary'][reason]} | {failures['overlapping_tags'][reason]} | {a['failed_to_full']} / {a['failed_to_partial']} | {b['failed_to_full']} / {b['failed_to_partial']} | {c['baseline_failed']} | {c['failed_to_full']} / {c['failed_to_partial']} |")
    return f'''# Nanjing feeder-level coverage analysis

**COUNTERFACTUAL ANALYSIS ONLY — completion logic unchanged**

## 原始分母与逐 feeder Switch 数量

- 原始 Feeder 行：{population['raw_feeder_rows']}；case-local identity groups：{population['feeder_identity_groups']}；
  published Feeder：{population['published_feeders']}；不同 raw Feeder_ID：{population['distinct_raw_feeder_ids']}。
- source case directories：{population['source_case_count']}；无 Feeder 的 case：{population['cases_without_feeder']}。
  无 Feeder case 单列在 case_details.jsonl 与 case_cohort，不冒充 feeder。
- 每 Feeder 的 ID、case、Switch identity groups/raw rows/published/candidates/state/type 分布
  见 feeder_details.jsonl；可直接查看 feeder_switch_counts.csv，一条 Feeder identity group 一行。
- 设备分析范围为原始 case directory；多 Feeder case 不声称唯一设备归属，switch_count 为 null。

## 不同 switch policy 下能达到多少完整 feeder

主指标：全部源 Transformer identity groups 从 head 可达；部分可达为 PARTIAL，
零个可达为 FAILED。没有 Transformer 目标也计 FAILED，并单列 no_transformer_targets，
不以空集合宣称成功。S2 中无 Transformer 目标的 feeder 数为 {s2['no_transformer_targets']}。
辅助严格口径：所有源 Line、Switch、Transformer 均唯一且可达，并有可用源侧 Line。
两者都不是已经完成 E3 参数/负荷/时序补全或 OpenDSS readiness 的证明。

| Policy | 主 FULL | 主 PARTIAL | 主 FAILED | 严格 FULL | 严格 PARTIAL | 严格 FAILED | 主 FULL 但严格不完整 |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

SEMANTIC_CONSERVATIVE 保留 S2 的投影结构，但阻断新增 semantic UNKNOWN Switch。
SEMANTIC_OPTIMISTIC 允许这些 Switch 按已知 NormalState 导通（仅 CLOSED），与当前 S2
相同。全部政策保留已知 OPEN；NormalState UNKNOWN 的额外两项敏感性实验单列。
不能为不满足结构、EXACT inner references 或 endpoint safety 的未知 Switch 臆造边。
S2_NORMAL_ONLY 是普通 Switch proposal 的范围，Tie 不自动纳入该普通规则。

## 失败分类与每类 UNKNOWN 放宽恢复量

以下前五列以当前 S2 的失败 feeder 为 cohort；后两列以 semantic conservative 的
失败 feeder 为 cohort。恢复数字为“FAILED→FULL / FAILED→PARTIAL”，来自实际图实验。
primary 按 missing_source、switch_unknown、tie_unresolved、topology_disconnected、
transformer_unreachable 的顺序分类，只用于互斥统计，不宣称已证明根因。
同一 feeder 可同时有多个 observed tags，overlap 列不能相加；所有 PARTIAL 的阻塞
证据另有 not_full 汇总与逐 feeder 明细。无目标的失败保留 NO_SOURCE_TRANSFORMER_TARGETS。

| 失败类别 | S2 primary | S2 overlap | 状态未知非导通恢复 F/P | 状态未知假设导通恢复 F/P | semantic conservative 失败 | semantic optimistic 恢复 F/P |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(failure_rows)}

拓扑语义放宽 conservative→optimistic：失败变完整 {semantic['failed_to_full']}，
失败变部分 {semantic['failed_to_partial']}；包括原 PARTIAL 在内，新达到主 FULL 共
{semantic['newly_full']} 个。严格 FULL 新增 {semantic['strict_newly_full']}，严格 FAILED→PARTIAL
{semantic['strict_failed_to_partial']}。policy_recovery.json 同时给出 overlapping-tag 恢复及状态转移。

相对当前 S2，仅放宽 NormalState UNKNOWN：非导通投影新增主 FULL
{state['S2_UNKNOWN_NONCONDUCTING']['newly_full']}，假设导通新增主 FULL
{state['S2_UNKNOWN_CONDUCTING']['newly_full']}。显式 semantic UNKNOWN 已在 S2 中允许，
不能把 conservative→optimistic 的收益再叠加到 S2 上。

## 如何理解“最终能补全多少”

当前 S2 的拓扑目标完整 feeder 为 {s2['transformer_goal_status']['FULL']} /
{population['feeder_identity_groups']}；这是本规则下全部源 Transformer 可达的确定性计数。
仍有 {s2['transformer_goal_status']['PARTIAL']} 个部分可达、{s2['transformer_goal_status']['FAILED']} 个失败。
完整 feeder 中 {s2['target_full_but_strict_incomplete']} 个未通过严格资产范围完整性。
在当前冻结的非 Switch 规则下，表中给出不同 policy 的实测候选范围；不代表最终
参数补全、仿真成功率，也不把“有一个可达 Transformer”的 case 当完整 feeder。

## 追溯与边界

所有输入 manifest checksum 及输出文件 checksum 在 manifest.json 中。S0/S2 的逐 case
counterfactual graph SHA256 和 coverage 与原 E2.2 核对一致。CSV 与 JSON 都保留原始
Feeder ID、source case 和 locators；无 source repair、无全局 feeder 合并。
本分析未修改 raw/E1/E2/E2.2 产物、accepted contract、Switch proposal 或补全逻辑。
没有生成 Load/PV/OpenDSS，不进入 E3。
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'baseline', 'projection', 'output'): parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    def progress(index, total, result):
        if index % 100 == 0 or index == total: print(f'Feeder coverage {index}/{total}: {result["case_id"]}', flush=True)
    reports = run_feeder_analysis(args.source, args.baseline, args.projection, args.output, render_report, progress=progress)
    print(reports['feeder_coverage']['population'], flush=True)
    print({p: v['transformer_goal_status'] for p, v in reports['feeder_coverage']['policies'].items()}, flush=True)


if __name__ == '__main__': main()
