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

## 已完成 benchmark 的证据边界

### 运行事实

权威 workspace：
`temp/20260830_094718-hierarchical-cae-base-performance-measured-visible-20260830`。

- benchmark 状态为 `completed`，postprocessor 为 `succeeded`；6/6 simulation cells 和 24/24
  logical analysis cells 完成。
- 三个 cases：ngspice SAW ladder、Project Chrono trebuchet、synthetic antenna。
- 每 case 两个 design seeds、train=1000/2000、两个 model seeds；每个 logical cell 使用 400
  个 test designs。候选是 architecture v2、`data_filter_mode=none` 的基础 Hierarchical CAE；
  对照是当前 conditional-INR。
- 旧 preregistration 要求每个 cell 的所有阈值都通过。最终 24 个 cell 都至少失败一个性能
  check，因此 sealed 输出是 `gate_passed=false`、`performance_accepted=false`。这只是旧规则
  对该 exact matrix 的运算结果，不是本 TODO 的当前决策规则。
- 没有 execution/data/checkpoint failure。24/24 均通过：partition completion、finite cost
  projection、checkpoint reload、training wall、RSS、CUDA memory、parameter count、all-axis
  finite coordinate query、query state unchanged，以及旧 `coordinate_vs_grid <= 0.75` check。
- 失败频数为：field-macro standardized MAE 17/24、RMSE 8/24、current-cost macro MAE 4/24、
  worst-field RMSE 16/24、Spearman 8/24、pairwise Pareto dominance 9/24、coordinate-to-real
  relative guard 16/24。它们描述薄弱面，不再相加成模型生死判据。

### CAE 相对 conditional-INR 的端到端结果

下表每项是同一 case/train 下 4 个 `(design seed, model seed)` replicate 的均值。ratio 小于
`1` 表示 CAE 误差更低；delta 大于 `0` 表示 CAE 排名更好。wall ratio 只比较本次训练墙钟。

| case | train | raw MAE ratio | raw RMSE ratio | cost MAE ratio | Spearman Δ | Pareto agreement Δ | worst-field RMSE ratio | wall ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Chrono | 1000 | 3.433 | 3.326 | 0.919 | -0.122 | -0.0003 | 10.664 | 0.749 |
| Chrono | 2000 | 4.178 | 4.364 | 0.984 | -0.242 | -0.0874 | 8.578 | 0.745 |
| SAW | 1000 | 1.140 | 0.985 | 0.848 | +0.0237 | -0.0381 | 1.021 | 0.415 |
| SAW | 2000 | 1.135 | 0.949 | 1.167 | +0.0017 | +0.0037 | 0.966 | 0.403 |
| synthetic antenna | 1000 | 1.016 | 0.952 | 0.788 | +0.392 | +0.075 | 2.203 | 0.517 |
| synthetic antenna | 2000 | 0.826 | 0.767 | 0.683 | +0.396 | +0.079 | 2.219 | 0.477 |

解释：

- **Synthetic antenna：** CAE 在 train=2000 的 field-macro、cost 和 ranking 上均有稳定、
  大幅优势，train=1000 也明显改善 cost/ranking；但 worst-field 约为 INR 的 2.2 倍，
  coordinate-to-real relative error 也偏高。平均收益真实存在，但不能据此声称所有字段或
  coordinate capability 同样改善。
- **SAW：** 结论混合。CAE raw RMSE 与排名略优，训练时间约为 INR 的 40%；raw MAE 约差
  14%。cost 在 1000 rows 更好、2000 rows 更差。它支持“某些用途有收益”，不支持全局优于
  或全局失败。
- **Chrono：** 当前 CAE 没有兑现 rawData 表示/预测收益：field-macro standardized error 是
  INR 的约 3.3--4.4 倍，worst-field 是 8.6--10.7 倍，ranking 在 train=2000 明显更差。
  cost MAE 接近或略优说明 task cost 对部分 rawData 误差不敏感，不能用 cost 平均掩盖表示
  问题。Chrono 是当前最优先的失败诊断 case。
- **资源：** 所有 24 个资源边界均满足，三个 case 的平均 wall ratio 约为 0.41、0.75、0.50。
  CAE 在 SAW 参数更少、Chrono 与 antenna 参数更多；复杂度价值应按 case 和用途衡量。

## PCA/SVD 的目的与已完成 evidence

### 为什么把 PCA/SVD 加入 surrogate

PCA/SVD 最初用于检验 Hierarchical CAE 的非线性表示是否有必要，后来扩展为两个严格分离的
诊断：

1. **oracle reconstruction：** 读取已知 validation/test rawData，投影到 rank-32 线性
   subspace 再重建。它只测 representation ceiling，编码了 truth，不能预测未知 candidate，
   不能进入 selection、optimization ranking 或 HV。
2. **deployable predictor：** `normalized parameters -> ridge -> PCA/SVD coefficients -> complete
   rawData -> current cost`。oracle 与 deployable 的差距用于判断困难主要来自低秩表示，还是
   `parameters -> latent` 映射。

将它实现为正式 `pca_svd()` component 还提供了可恢复、可复用的 deterministic GPSAF baseline，
但没有 posterior/readiness capability。实现与三 case measured evidence 见
[完成记录](../change_records/20260830_074344_complete-pca-svd-measured-evidence.md)。

### 线性对照结果

下表对 PCA/SVD 两种 decomposition 取均值。两个 benchmark 使用相同任务家族和训练规模，但
不是相同 exact design seeds/test rows，因此只能作 domain-level triangulation，不能当作配对
effect estimate。

| case | train | oracle explained energy | oracle relative Frobenius | deployable cost RMSE | deployable Spearman | deployable-oracle cost RMSE gap |
|---|---:|---:|---:|---:|---:|---:|
| Chrono | 1000 | 0.9786 | 0.2399 | 0.3027 | 0.3579 | 0.1678 |
| Chrono | 2000 | 0.9631 | 0.2393 | 0.2968 | 0.3702 | 0.1644 |
| SAW | 1000 | 0.9893 | 0.0698 | 0.2695 | 0.6017 | 0.2062 |
| SAW | 2000 | 0.9894 | 0.0685 | 0.2673 | 0.6040 | 0.2088 |
| synthetic antenna | 1000 | ~1.0000 | 0.000057 | 0.1637 | 0.7747 | 0.1630 |
| synthetic antenna | 2000 | ~1.0000 | 0.000056 | 0.1656 | 0.7731 | 0.1651 |

Chrono 的 per-coordinate training scales 接近零，standardized RMSE 数值病态；对该 case 应以
physical/relative、current-cost、ranking 和 Pareto 共同解释。PCA/SVD 与 1000/2000 training
size 没有跨 case 一致胜者；所有 case 都有明显 parameter-to-latent gap。

## 对 Hierarchical CAE 非线性表示收益的评估

### 可以得出的结论

- **不存在普遍的非线性表示收益。** Synthetic antenna 的 rank-32 linear oracle 已几乎无损，
  所以该 case 几乎没有可供 nonlinear decoder 赢得的 representation headroom。CAE 的强
  end-to-end ranking/cost 收益更可能来自非线性 parameter mapping、field-structured inductive
  bias 或训练目标，而不是“线性 subspace 表示不了 rawData”。
- **SAW 存在明确的非线性端到端建模收益，但纯表示收益看起来有限。** linear oracle 已解释
  约 98.9% energy、relative Frobenius 约 0.069；然而 ridge deployable 的 cost RMSE 约 0.267--
  0.269、Spearman 约 0.60，而 CAE 达到 cost RMSE 约 0.202/0.165、Spearman 约 0.772/0.860。
  这证明 nonlinear end-to-end path 有价值，但不能把收益唯一归因于 CAE representation。
- **Chrono 有 nonlinear representation headroom，但当前 CAE 没有实现它。** linear oracle 的
  relative Frobenius 约 0.239，明显弱于另外两个 case；当前 CAE 的 rawData/worst-field 与
  ranking 又明显落后 conditional-INR，cost RMSE 也没有优于 PCA/SVD deployable。合理结论是
  architecture/training/mapping 尚未利用这个 headroom，而不是线性基线已解决该问题。
- **收益是 domain- 和 metric-dependent。** 当前证据支持继续做有针对性的 CAE 研究，也支持
  在 synthetic antenna/部分 SAW 用途保留 opt-in 价值；它既不支持“CAE 已全面成功”，也不
  支持“24/24 gate fail 所以 CAE 没有价值”。

### 当前证据不能回答的问题

本次 CAE benchmark 测的是完整 `parameters -> nonlinear predictor -> CAE latent -> decoder ->
rawData`，PCA deployable 同时把 representation 和 linear ridge mapping 绑在一起。因此它没有
识别纯 nonlinear representation treatment effect。至少缺少：

- frozen CAE encoder/decoder 对 held-out truth 的 **CAE oracle reconstruction**；
- 在同一 PCA/SVD latent 上使用容量匹配的 nonlinear `parameters -> coefficients` predictor；
- 同 split/seed/test rows 下的 matched latent/rank/parameter budget 和 paired uncertainty；
- decoder-only、mapping-only 与 coordinate-head ablation。

在这些对照完成前，文档只能说“CAE end-to-end 非线性路径的收益”，不能声称已量化“CAE
非线性表示本身”的收益。

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
