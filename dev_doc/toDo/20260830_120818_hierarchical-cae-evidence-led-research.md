# Hierarchical CAE 证据驱动研究与改进（无性能 gate）

## 本文角色与用户决定

- 本文是手动 TODO，独立拥有基础 `HierarchicalCAEComponent` 的 architecture、训练、
  full-grid rawData prediction、coordinate readout、表示诊断、资源权衡和后续改进。
- 2026-08-30 用户明确决定：CAE 性能不使用“全部指标/全部 cell 通过才成功”的黑白 gate。
  benchmark 应形成连续、多维、可按用途解释的 evidence；一个 case 或字段失败不能自动否决
  其他 domain 的收益，一个平均指标也不能隐藏弱字段。
- 本决定不改写旧 sealed plans/results。历史 `performance_accepted=false`、Gate 0 v5/v8
  失败和 2026-08-30 all-cell gate false 继续作为对应实验的事实；它们不再充当未来 CAE
  研究、模块存在性或所有用途的全局开关。
- posterior calibration、EHVI/qNEHVI、同预算 optimization 与发布由
  [EHVI/qNEHVI TODO](20260828_121904_surrogate-qnehvi-remaining-work.md) 独立拥有。CAE 可以在
  没有 posterior readiness 的情况下继续作为确定性 experimental/GPSAF component 研究；
  EHVI 也不能用一个全局 CAE 分数替代自己的 posterior capability 证据。
- [抗噪声扩展](20260828_082308_noise-robust-regime-specialized-surrogate.md) 继续 `PARKED`，
  不是基础 CAE 的验收指标或 blocker。本文默认 `data_filter_mode=none`，不使用 clean
  leakage、roughness、regime classification、class balance 或 MoE/router 指标。

## 当前组件与不变边界

- 当前 opt-in component 使用 selector-specific scalar/Conv1d/Conv2d codecs、global/group/
  field-private teacher latents、shared-codec parameter predictor members、完整 rawData/current
  cost inference、atomic checkpoint/recovery、finite member draws、all-axis coordinate readout
  和 viewer adapter。
- rawData-first 边界不变：预测必须重建完整 named rawData，再由当前 `calc_cost.py` 解释；不
  建立 authoritative `parameters -> cost` 路径，不把 prediction 写入真实 history。
- 默认 filtering 为 `none`；`frequency` 是显式 opt-in extension。任何 architecture、filter、
  latent/rank 或 loss 的实质变化进入新的 semantic namespace，并保留旧 checkpoint/evidence。
- schema completeness、finite output、state identity、checkpoint atomicity、recorder non-entry、
  资源安全上限和 common real-evaluation boundary 是工程/安全约束，不是性能优劣 gate。

## 已有实验上下文与本文采用的结论

基础 Hierarchical CAE benchmark、PCA/SVD measured study、详细数值表、artifact/receipt
位置、数值限制和联合解释已迁移到
[CAE/PCA-SVD measured evidence context](../context/20260830_143110_hierarchical-cae-pca-svd-measured-evidence.md)。
该 context 是实验事实与解释的跨 session 保存位置；本文只保留会改变未来执行决策的摘要。

### 已验证事实

- 基础 CAE benchmark 完成 6/6 simulation cells、24/24 logical cells；没有 execution、data
  或 checkpoint failure。旧 sealed all-cell rule 得到 `gate_passed=false`、
  `performance_accepted=false`，但这是 exact historical rule 的输出，不是当前全局 CAE
  性能判决。
- 结果按 domain 分化：synthetic antenna 有明显 end-to-end cost/ranking 收益但 worst-field
  较弱；SAW 的 rawData、cost、ranking 与训练成本呈混合收益；Chrono 的 rawData、
  worst-field 和大训练规模 ranking 明显落后 conditional-INR。
- PCA/SVD study 完成三个 cases、24 个 logical cells，并严格区分 truth-encoding 的 rank-32
  oracle reconstruction 与 deployable ridge predictor。所有 cases 都有明显
  `parameters -> latent` gap；oracle 不能进入 candidate selection、ranking 或 HV。
- CAE 与 PCA/SVD 两个 benchmark 不是相同 exact design seeds/test rows，只能作
  domain-level triangulation，不能当作 paired treatment effect estimate。

### 本文采用的研究判断

- **不存在普遍的非线性表示收益。** Synthetic antenna 的 linear oracle 几乎无损，CAE
  的强 end-to-end 收益更可能来自 nonlinear parameter mapping、field-structured inductive
  bias 或 training objective。
- **SAW 有非线性端到端建模价值，但纯 representation 收益大概率有限。** Linear oracle
  已解释约 98.9% energy，而 CAE 与 ridge deployable 的差异仍同时包含 representation 和
  mapping。
- **Chrono 有 linear-representation headroom，但当前 CAE 未利用它。** 后续应先定位
  representation、mapping、scaling 与 worst-field error concentration，而不是用接近的
  cost MAE 掩盖 rawData/ranking 退化。
- 当前证据支持按 domain、metric、capability 和 resource tradeoff 继续研究；既不支持
  “CAE 已全面成功”，也不支持“24/24 old gate fail 所以 CAE 没有价值”。

### 仍未识别的因果边界

现有 CAE arm 把 nonlinear parameter predictor 与 nonlinear representation 绑定；PCA/SVD
deployable 把 linear representation 与 ridge 绑定。因此还没有量化纯 nonlinear
representation treatment effect。至少缺少 CAE oracle reconstruction、同一 PCA/SVD latent
上的 nonlinear coefficient predictor、matched split/seed/rank/budget，以及 decoder-only、
mapping-only 和 coordinate-head ablation。在这些对照完成前，只能声称 domain-specific
end-to-end nonlinear-path 收益。

## 后续工作

### 1. 用可辨识对照拆开表示与映射

在不读取新 blind outcome 前冻结一个新的 paired diagnostic study：

- 复用同一 design-level train/validation/test split、相同 preprocessing、cost interpreter、
  seeds 和 metric implementation；
- 增加 CAE oracle reconstruction，报告 field-macro/worst-field、relative/physical error 和
  rank/latent capacity curve；
- 增加 nonlinear MLP-to-PCA/SVD-coefficients arm，必要时再增加 CAE latent 的简单线性/非线性
  predictor ablation；
- 对 PCA/SVD 与 CAE 使用可解释的 matched representation budget；若不能严格匹配，报告
  parameter count、latent dimensions、fit/inference cost，而不是宣称公平等容量；
- 用 paired effect sizes、seed spread/intervals 和 per-field breakdown 判断收益来源，不产生
  单个 aggregate pass/fail。

优先使用已合法访问的数据完成分析；若需要新 simulator designs 或长训练，先报告精确命令、
case/cell/design 数、预计时间/资源并取得用户授权。

### 2. 按 case 处理已暴露的弱点

- **Chrono：** 先检查 near-zero scale、field-private codec、latent allocation、predictor loss 与
  worst fields 的 error concentration；比较 CAE oracle 后再决定问题位于 representation 还是
  mapping。不得用 cost MAE 接近掩盖 rawData/ranking 退化。
- **SAW：** 解释 MAE 变差而 RMSE/排名改善的误差分布，区分 outlier reduction 与整体 bias；
  调查 1000/2000 cost reversal 是否稳定。
- **Synthetic antenna：** 重点查明 nonlinear mapping 收益和 worst-field/coordinate regression；
  线性 oracle 近乎无损时，不为追求“非线性表示”而增加 decoder 复杂度。
- coordinate readout 单独报告。full-grid CAE 可用不等于 arbitrary-coordinate quality 足够，
  coordinate weakness 也不应否决只消费 full-grid prediction 的用途。

### 3. 维护 evidence ledger，不维护性能 gate

每次新 architecture/state 的记录至少包含：

- exact semantic/checkpoint identity、data roles、seeds、完成/失败 rows；
- field-macro、worst-field、physical/relative、current-cost、ranking/Pareto；
- full-grid 与 coordinate capability 的分离结果；
- training/inference wall、RSS/CUDA、parameters/checkpoint size；
- 相对 conditional-INR、PCA/SVD oracle/deployable 和必要 ablations 的 effect sizes；
- 结论适用的 cases/use cases、限制和下一个最有信息量的实验。

不得写一个通用 `performance_accepted=true/false` 作为所有消费者的真值。具体消费者可以有
自己的最低能力或安全要求，但必须注明用途，并允许其他用途基于同一 evidence 作不同决定。

## 非目标

- 不重新激活抗噪声/MoE 路线，不修改其 v5/v8 失败。
- 不把 PCA/SVD oracle 当 candidate prediction，不把预测写入 recorder。
- 不因本文创建而授权新 simulator campaign、长训练、posterior calibration、formal EHVI
  benchmark、默认迁移或发布推荐。
- 不为了通过旧阈值而删字段、改 cost、泄漏 test、隐藏 seeds 或事后改变 metric。
- 不要求 CAE 必须优于所有简单基线；如果线性 representation 加 nonlinear mapping 更简单且
  更强，允许选择它并减少 CAE 复杂度。

## 完成规则

本文不以 gate 通过为完成条件。满足以下条件即可归档或拆成更窄的后继任务：

- paired diagnostics 已把 CAE representation 与 parameter-to-latent mapping 的主要贡献拆开，
  或留下足够证据说明在当前数据/预算下仍不可辨识；
- Chrono、SAW、synthetic antenna 的结论均按 case/metric/use case 报告，weak fields、coordinate
  和资源 tradeoff 未被平均值隐藏；
- 已作出 evidence-backed 的下一步决定：保留并改进、只用于特定 domains、采用更简单基线，
  或停止该 architecture；不需要制造全局 passed/failed 标签；
- 适用的 source/tests、architecture、blueprints、terminology、user docs、benchmark studies
  和 change records 与最终决定同步，并按届时开发指南完成相称验证；
- 任何 posterior/EHVI handoff 只陈述 exact component capability，不把本文重新变成 EHVI
  readiness 的隐藏性能 gate。
