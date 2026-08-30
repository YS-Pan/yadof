# Hierarchical CAE 与 PCA/SVD measured evidence

## 角色与证据边界

本文保存 2026-08-30 已完成的基础 Hierarchical CAE benchmark、PCA/SVD measured study，
以及两组结果对“非线性表示收益”的联合解释。它是跨 session 的实验上下文，不是未来工作
指令、当前 architecture contract、性能 gate 或新 simulator/训练授权。当前代码、architecture、
blueprints、用户指令和活动 TODO 优先于本文。

本文从以下活动 TODO 迁出详细实验结果：

- [Hierarchical CAE 证据驱动研究](../toDo/20260830_120818_hierarchical-cae-evidence-led-research.md)
- [Posterior-assisted EHVI/qNEHVI](../toDo/20260828_121904_surrogate-qnehvi-remaining-work.md)

拆分和首次联合解释的 tracked provenance 见
[2026-08-30 12:18 change record](../change_records/20260830_121831_split-cae-ehvi-todo-and-reassess-benchmark.md)。

## Artifact 身份与位置

### 基础 Hierarchical CAE benchmark

权威 workspace（相对外层 modular workspace）：

`temp/20260830_094718-hierarchical-cae-base-performance-measured-visible-20260830`

迁移时已核对的主要文件：

- [spec.json](../../../temp/20260830_094718-hierarchical-cae-base-performance-measured-visible-20260830/spec.json)
- [state.json](../../../temp/20260830_094718-hierarchical-cae-base-performance-measured-visible-20260830/state.json)
- [gate plan](../../../temp/20260830_094718-hierarchical-cae-base-performance-measured-visible-20260830/resources/gate_plan.json)
- [gate result](../../../temp/20260830_094718-hierarchical-cae-base-performance-measured-visible-20260830/postprocessing/base-hierarchical-cae-performance-gate/gate-result.json)
- [postprocessor summary](../../../temp/20260830_094718-hierarchical-cae-base-performance-measured-visible-20260830/postprocessing/base-hierarchical-cae-performance-gate/summary.md)

### PCA/SVD measured study

原 benchmark workspace：
`temp/20260829_220837-pca-svd-measured-20260829`。三个 simulation cells 已完成，但 frozen
postprocessor 因把 JSON token `false` 写入 Python source 而在首次 test access 前失败；原 run
正确保持 terminal `failed`。

独立 recovery workspace：
`temp/20260830_073509-pca-svd-analysis-recovery`。它只给 frozen postprocessor 注入
`false = False`，没有改变 source、spec、plan、partition、hyperparameter、metric、stopping
rule 或 simulation result，也没有重跑 simulator。

迁移时已核对的主要文件：

- [recovery receipt](../../../temp/20260830_073509-pca-svd-analysis-recovery/recovery-receipt.json)
- [measured summary](../../../temp/20260830_073509-pca-svd-analysis-recovery/reports/pca-svd-measured-summary.md)
- [analysis JSON](../../../temp/20260830_073509-pca-svd-analysis-recovery/postprocessing/pca-svd-analysis/analysis.json)
- [metrics CSV](../../../temp/20260830_073509-pca-svd-analysis-recovery/postprocessing/pca-svd-analysis/metrics.csv)
- [pre-test gate](../../../temp/20260830_073509-pca-svd-analysis-recovery/postprocessing/pca-svd-analysis/pretest-gate.json)

Tracked completion provenance 见
[PCA/SVD completion record](../change_records/20260830_074344_complete-pca-svd-measured-evidence.md)。
外层 `temp/` artifact 是 ignored workspace evidence；若以后移动或清理，应以 tracked record、
本文件所列 hashes 和仍可访问的 receipt 共同核对，不把单一路径存在性当作科学有效性。

## 基础 Hierarchical CAE benchmark

### 条件与完成状态（已验证事实）

- benchmark 和 postprocessor 均完成；6/6 simulation cells、24/24 logical analysis cells。
- cases 为 ngspice SAW ladder、Project Chrono trebuchet、synthetic antenna。
- 每 case 使用两个 design seeds、train=1000/2000、两个 model seeds；每个 logical cell 有
  400 个 test designs。
- 候选为 architecture v2、`data_filter_mode=none` 的基础 Hierarchical CAE；对照为当时的
  conditional-INR。
- 没有 execution、data 或 checkpoint failure。24/24 均通过 partition completion、finite
  current-cost projection、checkpoint reload、training wall、RSS、CUDA memory、parameter
  count、all-axis finite coordinate query、query-state immutability 和 sealed
  `coordinate_vs_grid <= 0.75` check。
- 旧 preregistration 要求每个 cell 的所有性能阈值同时通过。24 个 cell 均至少失败一项，
  所以 sealed 输出为 `gate_passed=false`、`performance_accepted=false`。这是旧规则对 exact
  matrix 的历史运算结果，不是当前通用 CAE 性能判决。
- 性能 check 的失败频数为：field-macro standardized MAE 17/24、RMSE 8/24、current-cost
  macro MAE 4/24、worst-field RMSE 16/24、Spearman 8/24、pairwise Pareto dominance 9/24、
  coordinate-to-real relative guard 16/24。

### 相对 conditional-INR 的端到端结果（已验证事实）

每项为同一 case/train 下四个 `(design seed, model seed)` replicate 的均值。ratio 小于 `1`
表示 CAE 误差更低；delta 大于 `0` 表示 CAE 排名更好。wall ratio 只比较本次训练墙钟。

| case | train | raw MAE ratio | raw RMSE ratio | cost MAE ratio | Spearman Δ | Pareto agreement Δ | worst-field RMSE ratio | wall ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Chrono | 1000 | 3.433 | 3.326 | 0.919 | -0.122 | -0.0003 | 10.664 | 0.749 |
| Chrono | 2000 | 4.178 | 4.364 | 0.984 | -0.242 | -0.0874 | 8.578 | 0.745 |
| SAW | 1000 | 1.140 | 0.985 | 0.848 | +0.0237 | -0.0381 | 1.021 | 0.415 |
| SAW | 2000 | 1.135 | 0.949 | 1.167 | +0.0017 | +0.0037 | 0.966 | 0.403 |
| synthetic antenna | 1000 | 1.016 | 0.952 | 0.788 | +0.392 | +0.075 | 2.203 | 0.517 |
| synthetic antenna | 2000 | 0.826 | 0.767 | 0.683 | +0.396 | +0.079 | 2.219 | 0.477 |

### 对结果的解释（有证据支持的判断）

- **Synthetic antenna：** train=2000 的 field-macro、cost 和 ranking 有稳定明显优势；
  train=1000 也改善 cost/ranking。worst-field 约为 INR 的 2.2 倍，coordinate-to-real
  relative error 也偏高，因此平均收益不能外推为所有字段或 coordinate capability 改善。
- **SAW：** 结果混合。CAE raw RMSE 与 ranking 略优、训练墙钟约为 INR 的 40%，raw MAE
  约差 14%；cost 在 1000 rows 较好、2000 rows 较差。它支持用途限定的价值，不支持全局
  优于或全局失败。
- **Chrono：** 当前 CAE 没有兑现 rawData 表示/预测收益。field-macro standardized error
  约为 INR 的 3.3--4.4 倍，worst-field 约为 8.6--10.7 倍，train=2000 ranking 明显更差。
  cost MAE 接近或略优说明 task cost 对部分 rawData 误差不敏感，不能用 cost 平均掩盖表示
  问题。
- **资源：** 24 个资源边界全部满足。三个 case 的 CAE/INR 平均 wall ratio 约为 antenna
  0.50、SAW 0.41、Chrono 0.75；复杂度价值仍需按 case 和用途判断。

## PCA/SVD measured study

### 诊断角色（已确认设计意图）

PCA/SVD 同时具有两个严格分离的角色：

1. **oracle reconstruction：** 对已知 validation/test rawData 作 rank-32 线性投影与重建。
   它编码 truth，只测 representation ceiling，不能进入 candidate prediction、selection、
   optimization ranking 或 hypervolume。
2. **deployable predictor：**
   `normalized parameters -> ridge -> PCA/SVD coefficients -> complete rawData -> current cost`。
   oracle 与 deployable 的差距用于判断主要困难来自低秩表示，还是
   `parameters -> latent` 映射。

正式 `pca_svd()` component 还提供 deterministic、可恢复的 GPSAF baseline，但没有 posterior
或 readiness capability。

### 条件、完整性与数值限制（已验证事实）

- 三个 case 各有 2,800 个 result-independent designs。SAW 和 antenna 完成 2,800/2,800；
  Chrono 保留 729 个失败 simulation，不重采样，得到 2,071 completed rows，其中 test rows
  为 296/400。
- recovery 完成 24 个 logical cells：三个 cases、两个 training sizes、centered PCA/
  uncentered SVD、oracle/deployable arms；12 个 oracle、12 个 deployable，无缺失关键 metric、
  ranking metric、非正 cost gap 或 oracle 进入 selection/HV 的违规。
- 两个 benchmark 属于相同 task family 和 training scale，但不是相同 exact design seeds/test
  rows。因此与 CAE benchmark 只能作 domain-level triangulation，不能当作 paired treatment
  effect estimate。
- Chrono 的 per-coordinate training scales 接近零，standardized RMSE 数值病态；该 case 应
  结合 physical/relative、current-cost、ranking 和 Pareto 指标解释。
- synthetic-antenna SVD explained-energy macro 的 `1.000000127` 是约 `1.3e-7` 的 randomized
  float32 数值 overshoot，按原值保留，没有截断或据此选择模型。

### 线性对照结果（已验证事实）

下表对 PCA/SVD 两种 decomposition 取均值。

| case | train | oracle explained energy | oracle relative Frobenius | deployable cost RMSE | deployable Spearman | deployable-oracle cost RMSE gap |
|---|---:|---:|---:|---:|---:|---:|
| Chrono | 1000 | 0.9786 | 0.2399 | 0.3027 | 0.3579 | 0.1678 |
| Chrono | 2000 | 0.9631 | 0.2393 | 0.2968 | 0.3702 | 0.1644 |
| SAW | 1000 | 0.9893 | 0.0698 | 0.2695 | 0.6017 | 0.2062 |
| SAW | 2000 | 0.9894 | 0.0685 | 0.2673 | 0.6040 | 0.2088 |
| synthetic antenna | 1000 | ~1.0000 | 0.000057 | 0.1637 | 0.7747 | 0.1630 |
| synthetic antenna | 2000 | ~1.0000 | 0.000056 | 0.1656 | 0.7731 | 0.1651 |

Deployable Spearman 约为 SAW 0.60、Chrono 0.36--0.37、antenna 0.77；pairwise dominance
agreement 约为 0.88、0.52--0.53、0.947，但 Pareto-set F1 仅约 0.28--0.38，不能把 pairwise
agreement 解读成强 Pareto-front recovery。PCA 与 SVD deployable 近似相同，training prefix
从 1,000 增至 2,000 没有跨 case 一致改善。

资源记录：单 arm fit 为 0.208--6.209 s，test prediction 为 0.049--1.546 s；最大 process RSS
6.77 GiB、最大 CUDA allocation 223.2 MiB、单 checkpoint 约 0.313--12.73 MiB。RSS 是串行
analysis process peak，不是模型的增量分配。

Frozen analysis plan SHA-256：
`26bb9407d3096b264fed529c08a89d5ee5b102fd33ac72aef07b70dc31d97a76`；frozen
postprocessor SHA-256：
`205c295656b2ac447bb5b4faaa477a5231c50e739c236e875dd2396401b30ae3`。

## 联合解释：Hierarchical CAE 的非线性表示收益

### 当前可以支持的结论

- **不存在普遍的非线性表示收益。** Antenna 的 rank-32 linear oracle 几乎无损，CAE 的强
  end-to-end ranking/cost 收益更可能来自非线性 parameter mapping、field-structured
  inductive bias 或 training objective，而不是线性 subspace 无法表示 rawData。
- **SAW 有明确的非线性端到端建模收益，但纯表示收益大概率有限。** Linear oracle 已解释
  约 98.9% energy、relative Frobenius 约 0.069；CAE 相对 ridge deployable 的 cost/ranking
  较好，但该差异同时包含 representation 和 mapping。
- **Chrono 有 nonlinear representation headroom，但当前 CAE 未利用它。** Linear oracle
  relative Frobenius 约 0.239，然而当前 CAE rawData/worst-field/ranking 明显落后 INR，cost
  也未优于 PCA/SVD deployable。合理判断是 architecture/training/mapping 尚未兑现潜力，而
  不是线性基线已解决该问题。
- 收益是 domain-、metric- 和 use-case-specific。证据既不支持“CAE 已全面成功”，也不支持
  “24/24 gate fail 所以 CAE 没有价值”。

### 当前不能支持的结论与缺口

现有 CAE arm 将 nonlinear parameter predictor 与 nonlinear representation 绑定，PCA/SVD
deployable 将 linear representation 与 ridge 绑定，因此没有识别纯 nonlinear representation
treatment effect。至少缺少：

- frozen CAE encoder/decoder 对 held-out truth 的 CAE oracle reconstruction；
- 同一 PCA/SVD latent 上容量匹配的 nonlinear `parameters -> coefficients` predictor；
- 相同 split/seed/test rows 下的 matched latent/rank/parameter budget 与 paired uncertainty；
- decoder-only、mapping-only 和 coordinate-head ablation。

这些缺口属于活动 CAE TODO 的未来工作。完成前只能声称“CAE end-to-end 非线性路径的
domain-specific 收益”，不能声称已量化“CAE 非线性表示本身”的收益。
