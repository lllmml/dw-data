# 南京 v1 派生电气模型决策

状态：用户已接受的仿真派生假设（E0）；不代表真实源字段业务语义确认。
依据：用户重新检查完整南京 ZIP 后冻结的 feeder-head、series switch 和 leaf transformer
模式。实现规则见 `../spec/nanjing_topology_interpretation.md`。

Feeder_SourceBus 指向 110 kV Bus，实际 feeder 为 10/20 kV，因此 v1 在 synthetic MV
feeder head 截断上游网络，不臆造站内主变。Station pattern 仅在源引用证据链闭合时投影。
Switch 只接受一入一出两 Line 模式，Transformer 只接受唯一入 Line 的 leaf 模式。
采用这些有限规则是为了产生可追踪仿真模型，不是修复或重新解释 Source Facts。

Q-CONN-001 和 Q-TRANSFORMER-001 继续 OPEN。source reference 合同不变，raw ZIP 不变。
规则未覆盖实体保留并记录原因；实际覆盖率必须经 E2 全量报告 review，不能预先宣称可仿真。
