# 南京阶段实施与 review gates

- E0：completion/topology contracts 与派生决策；只有规范，无拓扑实现。
- E1：Source Import MVP；Equipment/operational mapper、assembly、全量 accounting、
  intake 编排、必要索引修复、持久化 source artifact。frozen tests、独立 commit、结果报告，
  停止等待 review。
- E2：实现 topology interpreter；5,159-case topology-only coverage audit、报告、独立
  commit，停止等待 review。E2 review 通过前禁止 E3、OpenDSS exporter。
- E3：Line/Transformer/Load/PV completion、配置、8760 profiles 和对应文档测试。
- E4：OpenDSS Snapshot/QSTS 和对应文档测试。
- E5：batch acceptance、先冻结 delivery schema 再实现 completed delivery、最终文档。

E0 DoD：规则和证据、排除策略、覆盖指标齐全，Q-CONN/Q-TRANSFORMER 保持 OPEN。
E1 DoD：12 类文件、每条已读行和非空值有归宿；源 identity/reference/Decimal 不变；
source connectivity 不提升；ImportStatus 独立于 quality；产物可恢复且 checksum 可验证；
测试通过、提交后停止。README/AGENTS 不把待 review Slice 标成已完成。

## E2.3-A 后续 review 顺序

E2.3-A 仅完成 topology recovery evidence/readiness foundation，不改变 frozen v1 或接受 S2。
下一重大 review 为 E2.3-D Synthetic Topology Completion Contract；不自动进入 B/C 实现。
候选反事实不是已批准规则；synthetic topology、E3、OpenDSS 仍需相应合同与明确授权。

## E2.3-D1 完成后的边界

E2.3-D Design Review 已通过。D1 完成正式 synthetic completion contract、typed
eligibility/prohibition/readiness、全量 mutually-exclusive action cohorts、只读 artifacts
与 verifier；依据 [D1 合同](nanjing_synthetic_topology_completion.md)。

D1 不生成或 apply synthetic node/connection/device，不接受 S2，不修改 accepted topology
或 frozen v1。Synthetic topology implementation 仍未开始；B/C、D2、E3、OpenDSS 均须
对应 review 和明确授权。完成 D1 全量验收和独立提交后 STOP，不自动进入 D2。
