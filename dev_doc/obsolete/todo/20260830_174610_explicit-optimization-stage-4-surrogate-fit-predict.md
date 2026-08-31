# 显式 optimization 重构阶段 4：surrogate 显式 fit/predict 与 state 生命周期

## 本次精化输入（2026-08-31）

- 输入 HEAD/Stage 3 accepted commit 为
  `38c091d264cc47d9457878d76d8a784b97e7e45b`，分支 `main`，worktree/staged diff 均为空；
  Stage 3 commit 后 fresh fetch 为 behind 0 / ahead 5，已 normal push 到 `origin/main`。
- 本文 pre-refinement SHA-256 为
  `33E66D8E101CF3ACDF26A7EB0AE67304C8DF4181A48BBA2A876DF79741D27B00`；overall plan
  SHA-256 为 `DD4F8FF70433F94E0E2A27C0C1B700B89C1F245257946C6BA4DE179EDF27FE40`。
- 接受基线是 installed yadof `0.4.2`、外层 `.venv/Lib/site-packages/yadof/__init__.py`；Stage 3
  full suite 为 `410 passed in 86.27s`，final closure package/lifecycle 为 `16 passed in 44.72s`。
  本阶段 pre-change PCA/SVD + viewer focused baseline 为 `25 passed in 8.26s`。
- Stage 3 fast smoke `40/40/40/40` 与 measured `2000/2000/2000/2000` 均 collected/valid、zero
  anomalies；本阶段仍使用 SHA-256
  `08E4BE42C4E4A8D377866BF8BC21765A0B776A27C32823290F97210FE086CBA7` 的完整显式
  NSGA-III + GPSAF + PCA/SVD strategy，GPSAF `gamma=0.5` 不变。

## 精化时确认的当前实现事实

- PCA/SVD 数学已分离为 exact named-field template、centered PCA/uncentered SVD、canonical basis
  sign、multi-output ridge 与 diagnostic-only oracle；deployable prediction 只从 normalized parameters
  重建完整 rawData。无需改变这些数值算法。
- `NamedTrainingData` 已对齐 parameters/rawData/row IDs，但不是 parent public contract；
  `training_design_signature()` 同时 hash row ID、float64 parameters 和 main-array dtype/shape/C-order
  bytes，未区分 materialized content identity 与 lineage/provenance，也没有 typed mask/status。
- `PCASVDComponent.ensure_fresh_enough()`/`start_training()` 仍在 component 内调用
  `training_data_from_session()`；该 helper 先按 job name 组装 parallel tuples，而 Stage 2 已提供可按
  row identity join 的 `EvidenceDataset`/`CostTable`。
- PCA/SVD scheduler 用 process-global `ThreadPoolExecutor`/`Future` 和独立 snapshot，只有 status
  facade；caller 不能持有、cancel、wait 或 scope-close training work。Stage 3 session registry 目前只
  命名 evaluation handle，normal generation loop 也没有显式 finish-generation work boundary。
- checkpoint publication 已是 no-pickle NPZ artifact tree rename + atomic JSON commit，current cost
  不进入 checkpoint；recovery 的不足是它重新隐式扫描当前 recorded data，而不是接收 caller 冻结的
  exact training input。
- generic viewer 当前只发现 conditional-INR/hierarchical-CAE；PCA/SVD checkpoint 虽已可恢复，尚无
  read-only discovery/prediction adapter。

## 冻结 materialized training-data contract

从 `yadof.surrogate` 导出 frozen `SurrogateTrainingData` 及
`materialize_training_data(dataset, cost_table, *, row_ids=None, transform_id=None)`：

- adapter 只以 Stage 2 row identity join；默认稳定选择 committed original 或 explicit derived、具有
  readable rawData、finite normalized parameters 且 interpretation `succeeded` 的 rows。显式 `row_ids`
  是严格选择，任何 missing/non-trainable row 都报错，不静默替换或产生 optimizer `inf`。
- public value 明确携带 parameter names、aligned normalized rows、owned frozen structured rawData、
  source/evidence row IDs、interpretation/evidence status、lineage、row-valid mask、bounded JSON-safe
  provenance、可选 `transform_id`、rawData schema signature、content digest 与 provenance digest。
  直接 materialized NumPy/structured samples 可构造同一 value；lazy iterator/custom loader、object/
  structured/complex/masked 或 non-finite main target 被拒绝，不提供 non-recoverable ephemeral state。
- content digest 的 domain/version 固定；parameter matrix canonicalize 为 finite little-endian float64
  C-order 并包含 shape，rawData 按 canonical selector order hash complete schema signature、logical
  dtype/shape 与 little-endian C-order main bytes。C/F memory layout 与 source path/row ID/transform label
  不改变 content digest；dtype、shape、row order、duplicate count、mask/status inclusion或任何数值改变
  digest。当前 strict adapter 的 valid mask 全 true，masked arrays fail closed。
- provenance digest 独立绑定 ordered row/evidence identity、status、lineage 与 optional transform ID。
  `transform_id` 只表达 user intent；相同 label 不能覆盖 content hash，不同 path/identity 的 identical
  materialized content 可以复用数学 state，但 manifest 仍保存各自 provenance。

## 冻结 fit/state/handle 与 checkpoint contract

`PCASVDComponent` 新增显式 `training_data()`、`fit()`、`start_fit()`、`recover()` 与 `predict()`：

- sync `fit()` 组合同一个 public `TrainingHandle` path；`start_fit()` 返回唯一 non-daemon owner-thread
  handle。`TrainingHandleState` 区分 created/running/cancelling/completed/cancelled/failed/closed；wait
  timeout 不 cancel，repeated wait/cancel/close 和 framework failure 有 cached semantics，context manager
  在 caller exception 时 cancel/wait cleanup。
- PCA/SVD cancellation 是诚实 cooperative policy：可在 fit 前、model fit 后与 checkpoint publication
  前停止；不能中断正在执行的单个 Torch decomposition kernel。cancel 发生在 commit 前不得 publish
  manifest/state；atomic manifest 已 commit 的 race 保留 completed state。normal generation boundary
  wait 后 close，exception/campaign close cancel 后 wait。
- CampaignSession registry 泛化为 exact-current-snapshot generation handles，并记录 boundary policy；
  evaluation 保持 cancel-on-abnormal-close，training 在 normal `finish_generation()` wait/close。下一
  generation 仍拒绝 open handle，session shutdown 在 writer/snapshot cleanup 前收口所有 handle，且
  不持 state lock 等待。
- recover/has-state/freshness 必须收到 exact `SurrogateTrainingData`；PCA/SVD runtime 删除 durable/
  session implicit training scan。in-memory/cache recovery 同时验证 content digest、component settings、
  strategy namespace、parameter-definition signature、rawData schema 与 NumPy/Torch versions。
- checkpoint manifest/state 把旧的混合 `training_design_signature` 拆为 semantic
  `training_data_digest` 与 non-semantic `training_provenance_digest`/row lineage/transform ID；publication
  继续复用现有 artifact rename + atomic manifest commit。旧 PCA/SVD state 可留存/被 viewer 描述，
  但缺少新 exact-content contract 时 runtime cold-fit，不猜兼容。
- terminal handle 释放 training input/callable/thread/snapshot lease；state 只持 deployable model 与
  bounded provenance。strategy switch/deactivation wait/cancel current handle、释放 memory，不删除历史
  namespace artifacts。

## 冻结 typed prediction 与当前 consumer delta

- frozen `SurrogatePrediction` 明确标记 deterministic rawData/current-cost prediction，携带 state/data
  signature、ordered normalized candidates、complete transient structured rawData、current-cost rows、
  zero-width intervals、snapshot interpretation fingerprint 与 bounded diagnostics。它不是 posterior
  joint samples，也不是 real `CostTable`。
- `predict(state, candidates, snapshot=...)` 只用 caller state 与 exact generation snapshot；完整 predicted
  rawData 继续经过 current `calc_cost.py`，任何 prediction 都不调用 finalizer/recorder/history。oracle
  DTO 继续 `diagnostic_only=True`/`validation_rawdata_encoded=True`，不能传给 typed deployable consumer。
- current GPSAF compatibility adapter 在 selection 前用 Stage 2 dataset/cost materialize 一份 explicit
  data 传给 freshness/state/prediction；after-submission callback 在其实际 backend timing 点重新冻结
  explicit data 并 start handle。PCA/SVD component 不再读取 session。conditional-INR/hierarchical
  methods 与 posterior readiness 本阶段不变；legacy prediction tuple 只由 narrow adapter 从 typed DTO
  产生，并在 Stage 8 no-consumer cutover 删除。
- generic read-only surrogate viewer 增加 PCA/SVD discovery、deterministic one-member prediction/plot/
  audit adapter，验证 manifest/artifact/data schema/parameter normalization；不修改 checkpoint、history
  或 current task。

## 精确测试、文档与 benchmark delta

- direct materialization tests 覆盖 raw/filtered/reordered/duplicated/derived rows、strict selection、stable
  lineage、identical content/different path/identity、different content/same transform ID、C/F order、dtype、
  shape、non-finite/masked rejection和 row/schema/status digest boundaries；
- direct lifecycle tests 覆盖 sync/async/double wait/timeout/cancel before/during/after commit、fit failure、
  interrupted atomic publication/recovery、normal/exception generation cleanup、strategy deactivation 与
  training-input memory release；
- prediction tests 覆盖 explicit state-only deployable rawData/current cost/zero-width interval、cost hot
  snapshot、oracle rejection boundary、typed DTO immutability，以及 recorder/dataset/history non-entry；
- viewer tests 覆盖 PCA/SVD discovery, deterministic prediction/plot/audit 与 old/incompatible manifest
  isolation；parent import 继续证明 lazy Torch。
- 同步 architecture、surrogate/recorded-data/optimize/tests blueprints、training/lifecycle/linear-subspace/
  viewer file blueprints、terminology、optimization/config/package user docs 和 change record。

最终按 installed-package workflow build/reinstall/import-origin，运行 focused 与完整 pytest。fast
benchmark 使用 fresh Stage 4 smoke `20 x 2` 与唯一 measured `100 x 20` workspace；两个 expanded
plans 除 budget 外必须同源，strategy digest 保持 `08E4BE42…6CBA7`、GPSAF `gamma=0.5`；measured
必须 collected/valid、`2000/2000/2000/2000`、zero anomalies。单 seed HV 仍不是算法优劣 gate。

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

## 本次执行结果（2026-08-31）

- 新增 frozen `SurrogateTrainingData` 与 strict materializer；semantic content digest 只绑定
  canonical materialized parameters/complete rawData，provenance digest 独立绑定 row/status/lineage/
  optional transform。lazy、masked、object/complex/structured-main 与 non-finite target 均 fail closed。
- PCA/SVD 已提供 explicit `training_data/start_fit/fit/recover/predict`，删除其 session implicit scan、
  process-global executor/Future facade 和 mixed `training_design_signature`。统一 `TrainingHandle`
  覆盖 sync/async/wait/cancel/failure/close，generic generation registry 按 normal wait / abnormal cancel
  policy 在 writer/snapshot cleanup 前收口。
- checkpoint 保留原 atomic artifact/manifest publication，新增分离的
  `training_data_digest`/`training_provenance_digest`；exact data/settings/namespace/parameter/rawData
  schema/NumPy/Torch 不匹配时 cold-fit，不猜兼容。
- frozen `SurrogatePrediction` 携带 state/data signature、ordered candidates、完整 transient rawData、
  current-snapshot cost、zero-width intervals 与 bounded diagnostics；direct tests 证明 prediction/oracle
  不能进入 recorder/dataset/history。current GPSAF 只在真实 selection/after-submit timing 冻结 explicit
  data，`gamma=0.5` 不变。
- generic viewer 已能 read-only discover/audit PCA/SVD checkpoint，并对单成员做 deterministic
  prediction/plot；旧/不兼容 manifest 与 deployable recovery 隔离。conditional-INR、hierarchical CAE
  与 posterior path 保持原能力，留待 Stage 7。
- direct explicit-surrogate `20/20`、GPSAF/posterior compatibility `25/25`、installed-wheel full pytest
  `419 passed in 86.88s`；import origin 为外层 `.venv/Lib/site-packages/yadof/__init__.py`。
- fresh smoke `temp/20260831_094259-stage4-benchmark-smoke` 为 collected/valid
  `40/40/40/40`、zero issues、2/2 training completed、elapsed `11.635633 s`；唯一 fresh measured
  `temp/20260831_094502-stage4-benchmark-measured` 为 collected/valid
  `2000/2000/2000/2000`、zero issues/recording failures、20/20 training completed，evaluation command
  `623.791692 s`、result runtime `624.151074 s`。generation 0 warmup，generation 1--19 均使用 surrogate；
  final HV `0.21129372436533064` 不是 gate。
- measured 的 20 份 manifest/artifact 均存在，content/provenance digest 分离、非空且各 20 个 unique；
  manifest content set 与 training-event content set 完全相同。smoke/measured 除 `20 x 2` / `100 x 20`
  budget 与 workspace-local path 外同源，strategy bytes/SHA-256 均为
  `08E4BE42C4E4A8D377866BF8BC21765A0B776A27C32823290F97210FE086CBA7`。
- reliable-recording check 证明只读 committed training、prediction non-entry 与 generation/session
  cleanup 顺序一致；bounded redundancy check 删除 PCA/SVD implicit scan/mixed digest/global future
  dual path。release-marker/component-configuration checks 未命中；四份 recurring auto TODO 保持 active。
  进入阶段时 worktree clean，没有 pre-existing user changes。
- architecture、surrogate/recorded-data/optimize/tests 与 viewer blueprints、terminology、optimization/
  config/package user docs 已同步；change record 为
  `dev_doc/change_records/20260831_100109_add-explicit-surrogate-fit-state-prediction.md`。本文
  post-refinement/pre-implementation SHA-256 为
  `B7E1CC3C73CDDC81CC4E5D063ABBD5377D3E1B501459B5A2FA777763C85DFC13`。

## 完成、归档与自动续跑

PCA/SVD 不再从 session 隐式读取 training data，explicit fit/state/predict、digest/checkpoint、
lifecycle 和 recorder boundary 均有直接 evidence；文档、automatic TODO check、change record、
commit/fetch-push 完成后，归档本文、更新 ledger，并自动进入
[Stage 5 search/select](20260830_174611_explicit-optimization-stage-5-search-selection-primitives.md)。
