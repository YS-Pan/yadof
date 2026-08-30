# 显式 optimization 重构阶段 4：surrogate 显式 fit/predict 与 state 生命周期

## 状态、授权与依赖

本文是已获单一 Goal 后续精化/执行授权的预测性 TODO。Stage 2 提供 stable training rows，
Stage 3 提供 framework-owned lifecycle；两者完成后，执行者根据当前 PCA/SVD implementation、
checkpoint repository、scheduler、viewer 和 benchmark evidence 在本文内冻结精确 API，无需
新的用户指示。

`fit`、`predict`、`SurrogateState`、`TrainingHandle` 是职责名称，不预先冻结公共拼写。

## 已知 pre-change 问题

当前 surrogate component 通常从 `CampaignSession` 内部调用 training-data query，并由
strategy/scheduler 隐式决定何时训练。workspace 普通 Python 无法显式构造、变换并传入
training dataset。PCA/SVD 是最窄的首个迁移对象：它是 deterministic rawData-first baseline，
不携带 posterior readiness，deployable path 只从 normalized parameters 预测 coefficients，
truth-encoding oracle 不能进入 selection。

checkpoint correctness 不能只绑定路径或 source fingerprint。用户可以用 NumPy/SciPy 过滤、
重排或变换训练数据，framework 也不能推断任意 Python 代码的科学语义。

## 预期精确结果

先让 `pca_svd()` 使用显式输入和输出证明完整路径：

- fit 接受 Stage 2 的 real EvidenceDataset/CostTable 或它们的 owned、traceable transform；
- training input 明确列出 row identity、field schema、parameters、rawData targets、mask/status
  与 materialized-data digest；
- 任意 materialized NumPy/SciPy arrays 若失去 lineage，仍必须计算 exact content digest；
  可选 user `transform_id` 只补充 provenance/intent，不替代内容 hash，framework 不猜代码语义；
- 无法 materialize/hash 的 lazy/custom input 只能被明确拒绝，或产生 non-recoverable ephemeral
  state；不能悄悄复用 checkpoint；
- checkpoint semantic identity 绑定 actual training-data digest、component settings、parameter/
  rawData schema 和 strategy/component namespace；path/log/source provenance 与数学 identity
  分离；
- fit 返回 immutable state 或受 generation scope 管理的 TrainingHandle；同步/异步、cancel、
  failure、memory release 和 checkpoint commit 都有明确终态；
- predict 只消费 state + candidate rows，返回 typed transient rawData/current-cost prediction 与
  bounded diagnostics；prediction 永不进入 recorder；
- PCA/SVD oracle API 继续明确 diagnostic-only，不能成为 deployable candidate predictor；
- current `calc_cost.py` 在完整 predicted rawData 上解释 cost，checkpoint 不冻结 cost policy。

## 预计范围

- PCA/SVD public component/runtime/scheduler/checkpoint 与 lightweight parent API；
- 显式 training dataset adapter、content digest/provenance 和 state lifecycle；
- current GPSAF consumer 的窄适配，为 Stage 5 search/select 输入 typed prediction；
- viewer/checkpoint discovery 的兼容读取；
- tests、architecture、surrogate/optimize blueprints、terminology、user docs 和 change record。

本阶段不迁移 conditional-INR、Hierarchical CAE 或 posterior sampler 的全部实现；它们保持
当前工作路径，Stage 7 再迁移。不得改变其 checkpoint namespace/readiness/default，也不修改
GPSAF `gamma`。

## 精化时必须决定

- materialized digest 的 canonical dtype/shape/order/NaN policy；
- fit 同步返回还是统一 TrainingHandle，以及与 EvaluationHandle overlap 的资源/cleanup 规则；
- ephemeral state 是否公开、何时允许、如何禁止误恢复；
- training-data lineage 的最小 public surface；
- checkpoint publication 与 existing atomic state repository 的复用边界；
- prediction DTO 如何区分 full rawData、GPSAF predicted current cost 和 posterior joint samples。

这些是已授权设计选择。若需要把 prediction 持久化为 truth、绕过 current cost projector 或改变
PCA/SVD 数学，必须暂停。

## 验证

至少覆盖：

- raw/filtered/reordered/duplicated training dataset 和 stable lineage；
- identical content/different path、different content/same transform label 的 identity；
- C/F order、dtype、shape、schema、non-finite/mask canonicalization；
- ephemeral/recoverable decision、atomic checkpoint commit、interrupted fit/recovery；
- sync/async fit、cancel/failure、generation scope cleanup、strategy switch；
- deployable ridge prediction、zero-width interval、oracle diagnostic-only；
- prediction through current cost projector、recorder/history non-entry；
- parent import lazy Torch behavior、viewer discovery 与 current PCA/SVD regression；
- Stage 3 handle overlap 只由 caller 显式表达且资源 ownership 清楚。

完成 wheel/force reinstall/import-origin/focused/full tests，并运行 overall policy 的 fast smoke 与
唯一 100 x 20 measured benchmark。比较 current vs explicit PCA/SVD selection/dataflow parity，
不把单 seed HV 作为 surrogate 优劣结论。

## 完成、归档与自动续跑

PCA/SVD 不再从 session 隐式读取 training data，explicit fit/state/predict、digest/checkpoint、
lifecycle 和 recorder boundary 均有直接 evidence；文档、automatic TODO check、change record、
commit/fetch-push 完成后，归档本文、更新 ledger，并自动进入
[Stage 5 search/select](20260830_174611_explicit-optimization-stage-5-search-selection-primitives.md)。
