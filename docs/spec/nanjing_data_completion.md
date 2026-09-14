# 南京补全边界

版本 0.1.0；E0 边界已冻结，E3 实现及具体参数配置尚未批准。

SOURCE 是原始值；DERIVED 是明确规则推导；RULE_GENERATED 是 synthetic 工程生成。
复用 FieldProvenance，记录 rule_id/version、config_ref、seed、source refs。生成实体无
虚假 source_id/source_record_ref；使用独立版本化派生 ID factory。raw ZIP 永远只读。

先通过 E2 全量 topology coverage review，才开始补全：有效原值优先，仅真正缺失才生成；
非法原值保留并报告，不冒充缺失修复。线路参数库按电压和可解释 role 区分，长度稳定
SHA256 seeded sampling，有界且非真实 GIS 长度。Transformer 容量优先使用合法源值，
缺失从 dataset-level 经验分布采样。异常样本排除统计但不删除 source rows。

每个明确定位配变的 synthetic LV bus 上建立聚合 Load，峰值由容量、利用率、PF 决定。
8760 hourly load multiplier 包括日内、工作日/周末、季节和有界噪声，非负且峰值归一化。
PV 仅在有效 Load LV bus 布点；penetration = Σ PV rated kW / max_t Σ load kW(t)。
PV multiplier 属于 [0,1]、夜间为 0，包含季节日照和有界天气扰动；不是历史气象重建。
同输入、配置、seed、软件版本生成确定性字节产物；随机流按实体和规则隔离，不用 hash()。

当前仿真只采用 balanced three-phase equivalent，不用于真实三相不平衡研究。
OpenDSS 只消费 validated CompletedGridCase；Snapshot 通过才执行可配置时间窗口的 QSTS。
以上均为后续 Slice，E0/E1 不新增 generation/simulation 实现或 synthetic source records。

## 交付边界

内部 JSON/JSONL 不代替最终交付。后续 Slice 先冻结独立 derived delivery schema，再实现
source-shaped `01_Station.csv` 至 `12_SimConfig.csv` 的派生副本。仅派生副本写入允许
生成的 Line/Transformer/Load/DER/simulation configuration。8760 profiles 独立存储于
profiles/load_profiles.*、profiles/pv_profiles.*，并附 manifest、configuration version、
provenance 和源/派生 ID 对照。合成数据不声称还原南京真实运行状态。
