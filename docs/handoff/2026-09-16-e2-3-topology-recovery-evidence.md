# E2.3-A — Topology Recovery Evidence & Readiness Foundation

Scope: evidence foundation only. Accepted topology, source facts and frozen v1 semantics
unchanged. Candidate rules only run in isolated counterfactual graphs. No synthetic
connections, B/C/D implementation, E3, OpenDSS, Load/PV or 8760 generation.

## Baseline and implementation

Input commit: `eabda1e217afd969539bbf9b64e636f12d06eba0`; initial worktree clean.
Delivery commit: this handoff's independent commit, obtainable with
`git log -1 --format=%H -- docs/handoff/2026-09-16-e2-3-topology-recovery-evidence.md`.

Implemented a pure typed-source case analyzer, independent evidence/readiness enums,
streaming artifact writer, detail-reaggregating verifier and CLI. No /tmp prototype JSON
is copied into formal output. Four existing input verifiers run before and after each
full analysis. The S0/S2 graph hashes and coverage are checked against existing artifacts.

- Spec: [topology recovery](../spec/nanjing_topology_recovery.md).
- Reproduction: [guide](../guides/nanjing_topology_recovery.md).
- Runtime dependencies: unchanged; existing stdlib-only runtime and uv.lock.
- Output directory: `outputs/nanjing-e2-3/topology-recovery-evidence-v1/`.
- Independent repeated run: `outputs/nanjing-e2-3/topology-recovery-evidence-v1-reproduction/`.
- Comparison evidence: `outputs/nanjing-e2-3/topology-recovery-evidence-v1-verification.json`.

Incomplete directories from interrupted runs have no accepted manifest and are not
formal results. Only the verified output directory above is the delivery artifact.

## Validation

Full pytest: 348 passed, including 22 new E2.3-A tests; existing tests unchanged.
Compileall and git diff --check pass. Regression tests include already accepted Switch
ports in candidate graphs and unrecognized/missing Transformer headers, alongside
zero targets, reference compositions, identity ambiguity, known OPEN, voltage,
AccessPoint, multiple blockers, multigraph experiments, no evidence promotion,
source immutability, repeat/hash-seed/order determinism, checksum and binding tamper.

两次全量重算均覆盖 5,159 cases；完整验证结果与统计见下文。

## 全量 evidence 与覆盖结果

全部 5,159 source cases 保留；分母为 5,134 条真实 source Feeder identity groups。
无 Feeder 的 25 cases 仍写入 case_details 和设备证据，不伪造 Feeder。

| 互斥 source-evidence cohort | Feeder | legacy FAILED | PARTIAL | FULL |
|---|---:|---:|---:|---:|
| Transformer CSV 有已识别表头、零数据行 | 1,713 | 1,713 | 0 | 0 |
| 至少一个 Transformer 无任何连接引用 | 3,114 | 2,290 | 824 | 0 |
| 全部 Transformer 至少存在某种引用 | 307 | 89 | 138 | 80 |
| 合计 | 5,134 | 4,092 | 962 | 80 |

307 正式命名为 **necessary evidence upper-bound cohort**，不是 recoverable、
achievable 或 expected FULL。存在 raw reference 不证明端口、电压或 ownership 语义。
当前主 FULL 仍为 80 / 5,134，未证明安全的新 FULL；S2 仍是 counterfactual policy。

独立 target coverage 为 FULL 80 / PARTIAL 962 / FAILED 2,379 /
NO_SOURCE_TARGET 1,713；legacy FAILED 4,092 保留用于历史比较，不允许空目标成为 FULL。

| Transformer reference composition（有 Feeder 的 source cases） | Identity groups |
|---|---:|
| NO_REFERENCE | 96,038 |
| SWITCH_ONLY | 26 |
| LINE_ONLY | 14,240 |
| LINE_AND_SWITCH | 31 |

总计 110,335 groups；全部 source cases 另有 3 个无 Feeder case 内的 Transformer。
S0/S2 projected attachments 均为 14,245；可达数分别为 5 / 7,024。
本批 Transformer identity ambiguous 为 0，reference ambiguous 为 0，
unresolved reference flag 为 4；这些维度独立于引用 composition，保留逐声明证据。
`113997367245538568_lzwtest22278` 的 44,596 个 Transformer 全部保留，
列在 largest_transformer_cases 首位，没有 outlier 删除或身份重分配。

## Frontier 与未来 completion cohort

S2 observed feeder counts 可重叠：Switch degree 1,881、AccessPoint unsupported 1,700、
endpoint unresolved 1,118、endpoint ambiguous 578、known OPEN 1,074、voltage conflict 205、
Transformer multi-incidence 16。另有 no Line 1,880、no head-reachable Line 758、
reachable Line but no reachable Transformer 1,454。S0/S2 的 primary classification
和 overlapping observations 分别输出；primary 只是固定优先级统计，不冒充根因。

未来 completion flags（非互斥）：

- A：3,114 Feeder。已有 Transformer 缺连接/attachment/ownership；不能生成重复 Transformer。
  获得新的源连接证据是 synthetic 之外的替代路径；仅凭现有证据不能接线。
- B：1,713 Feeder。ROLE_UNDETERMINED；不能默认应该新增 Transformer。
- C：227 Feeder。全部目标有引用但路径未完整，值得继续 deterministic rule review；
  其中 89 FAILED、138 PARTIAL，不等于 227 条可恢复。
- D：1,884 Feeder。存在 identity、voltage、known OPEN frontier 或 ownership 约束；
  不允许通过 synthetic bridge 绕过这些约束。D 可与 A/B/C 重叠。

Primary recovery readiness：ROLE_UNDETERMINED 1,713、BLOCKED_BY_CONFLICT 1,338、
NEEDS_SYNTHETIC_COMPLETION 2,049、NEEDS_RULE_REVIEW 34。主分类优先级不抹去其它 reasons；
例如受冲突约束的 A case 仍保留 A flag。SOURCE_EVIDENCE_SUFFICIENT 在本批为 0。
所有 E3 readiness 都为 false；所有新增 synthetic connection count 都为 0。
已有 synthetic MV head *nodes* 单列，不能冒充 source-confirmed connection。

## Candidate witnesses 与实际 counterfactual

| Candidate | Eligible devices | Feeders | Reachable Transformer delta | FAILED→PARTIAL | 新 FULL |
|---|---:|---:|---:|---:|---:|
| LEAF_SWITCH_TERMINAL_REPRESENTATION_V1 | 20,708 | 1,189 | 0 | 0 | 0 |
| UNIQUE_SWITCH_DECLARED_T_ATTACHMENT_V1 | 12 | 12 | +10 | 0 | 0 |
| MULTI_INCOMING_T_ATTACHMENT_V1 | 9 | 3 | +9 | 3 | 0 |
| MULTI_LINE_T_AS_MV_JUNCTION（风险实验） | 26 | 17 | +66 | 15 | 1 |

前三条均未加入 accepted topology。S2-only connections 与 candidate witnesses 均为
UNRESOLVED，不因 counterfactual reachability 升级 RULE_INFERRED。

窄规则累计：FULL 80 / PARTIAL 965 / FAILED 2,376 / NO_SOURCE_TARGET 1,713；
reachable Transformer +19。Leaf 与 unique 的 eligible feeder overlap 为 0；
Leaf 与 multi-incoming overlap 为 1；unique 与 multi-incoming overlap 为 0。
完整 overlaps 与累计实验见 summary.json，不简单相加重复恢复。

宽松 multi-Line 风险实验达到 81 FULL，但新增 13 个 structural cycle rank 和
13 个 conducting cycle rank，且 Transformer 高低压侧没有证明。
它明确为 RISK_EXPERIMENT_ONLY / NOT_RECOMMENDED，不是安全收益，未进入 accepted topology。
Cycle rank 仅是风险诊断，不代表完成全部电压/设备/跨 feeder ownership 安全验证。

## 复现与输入不变性

两次全量 analyze 使用 PYTHONHASHSEED=1 / 999，从四组 verified 输入独立重算。
每次均执行输入 verifier 前后检查、逐 case 图哈希/覆盖核对、输出 verifier 和
summary/report 明细重汇总。全部输出文件（包括 manifest 与 report）逐字节比较；
比较摘要见 outputs/nanjing-e2-3/topology-recovery-evidence-v1-verification.json。

正式 manifest SHA256：`b088c5567362b6ae39caf2ed3bf56069e63ff3ac6cbe138d9ee347a7f432fe52`。

Python source-tree fingerprint：`6a3fc9bb88b15993012f9b61cab7448ed5b0e8c6708c3df5908baf331232a833`。

- baseline input manifest SHA256：`40f4bb350e33415306d80e6c7436cddff8d72a2294e0261d0beac3063477bd55`。
- feeder input manifest SHA256：`fd3c1f0bff34afa203f202148060941822198548669aa3f3594b16fbdca72a48`。
- projection input manifest SHA256：`581ab83e6d610191b47ae30b2d48b4b6ab186a4c1cec980a3ee5fa79324ab8e2`。
- source input manifest SHA256：`9d244c812bae8f5f9b1f5e6e1aca8d7bda13fde4b31da9f2ec6ad044f6e135a3`。


与输入 commit 相比，未修改 generation/topology.py、models/topology.py、frozen
nanjing_topology_interpretation.md 或四组输入 artifacts。版本化新输出只包含分析证据，
未写 accepted ElectricalTopology，没有 synthetic topology implementation。

## 下一 review / 停止边界

**下一重大 Gate：E2.3-D — Synthetic Topology Completion Contract（设计 review）。**

B representation 不增加主 coverage；C1 不改变主状态；C2 仅 3 条 FAILED→PARTIAL。
大部分限制来自源证据缺失，不是一个遗漏的简单 interpreter rule。因此不自动实现 B/C。
本 Slice 完成后 STOP；不进入 B/C/D implementation、E3、OpenDSS 或 Load/PV/8760。
