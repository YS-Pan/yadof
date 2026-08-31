# 显式 optimization 重构阶段 5：拆分 search、prediction 与 selection 原语

## 本次精化输入（2026-08-31）

- 输入 HEAD/Stage 4 accepted commit 为
  `7249298bfdb04201bbba773f305548eadb651a9b`，分支 `main`，worktree/staged diff 均为空；
  Stage 4 commit 后 fresh fetch 为 behind 0 / ahead 1，未达到 push gate。
- 本文 pre-refinement SHA-256 为
  `943CE72A8AA77D2776800CF6325EA8A3B91722D3995DEF32303968FAB38AC34B`；overall plan
  SHA-256 为 `9F5328880D7BCF70AD18A1B3F64C5E250C848C4E215A0F782C695D9D6F3D4753`。
- 接受基线是 installed yadof `0.4.2`、外层 `.venv/Lib/site-packages/yadof/__init__.py`；Stage 4
  full suite 为 `419 passed in 86.88s`，final direct explicit-surrogate 为 `20 passed in 2.76s`。
  本阶段 pre-change optimize/GPSAF/posterior/PCA focused baseline 为 `45 passed in 6.62s`。
- Stage 4 smoke `40/40/40/40` 与 measured `2000/2000/2000/2000` 均 collected/valid、zero
  issues；继续使用 strategy SHA-256
  `08E4BE42C4E4A8D377866BF8BC21765A0B776A27C32823290F97210FE086CBA7`，GPSAF
  `gamma=0.5` 不变。

## 精化时确认的当前实现事实

- `RealSearchStrategy`、GPSAF assistance 与 posterior full-real fallback 各自建立 `PymooContext`、
  history survivor state、duplicate archive 与 RNG，再各自把 population 交给 common real evaluator；
  三处共享 mechanics，但 generation orchestration 仍隐藏在 strategy method。
- `gpsaf.records.CandidateRecord` 同时携带 normalized design、predicted cost 与 concrete pymoo
  `Individual`。它适合 private adapter，不适合 workspace program；candidate identity、rounded duplicate
  key 与 durable evidence identity 尚未成为三个独立 value。
- pymoo backend 已正确拥有 GA/NSGA-III object、operator、ask/tell、survival、reference directions 与
  numeric fitness adapter。当前 duplicate policy 在 configured ask attempts 后进入无界 random refill；
  正常空间可完成，但 exhausted/quantized space 没有 explicit terminal failure。
- Stage 4 PCA/SVD 已返回 typed `SurrogatePrediction`；GPSAF 仍把它和 retained component 的 legacy
  tuple 在 `predict_records()` 内直接转成 private record。posterior path 的 `JointObjectiveSamples` 与
  Stage 2 `CostTable` 已有独立类型，不能进入 deterministic survival。
- campaign durable resume 本来就是 generation-boundary history reconstruction；overall invariant 明确
  不恢复 arbitrary mid-generation Python locals。因此本阶段的 opaque state continuation 必须支持同一
  generation 的显式 next-state/fork，而不能用 pickle 承诺跨进程 pymoo continuation。

## 冻结 public candidate、prediction 与 state contract

从 lightweight `yadof.optimize` 导出 backend-neutral frozen values：

- `SearchCandidate`：`candidate_id`、ordered normalized variables、rounded `duplicate_key`、origin 与可选
  source evidence ID；不暴露 pymoo Individual，不把 candidate ID 当 evidence ID/design key。
- `CandidatePool`：ordered unique candidates、产生它的 exact state ID/revision 与 bounded JSON-safe
  diagnostics；private backend records 只供 package adapter 使用。
- `PredictedCostRows`：与 pool candidate IDs/rows exact 对齐的 finite current-cost mean rows、objective
  width、interpretation/state identity 与 source；它不是 `CostTable`、`SurrogatePrediction` rawData owner
  或 `JointObjectiveSamples`。显式 binder 从 Stage 4 `SurrogatePrediction` 构造，retained component 只在
  narrow legacy adapter 构造同一 typed value。
- `CandidateSelection`：ordered real-evaluation candidates、next opaque state、selection/fallback diagnostics
  与 `population` projection；不携带 predicted rawData/member/posterior data。
- `SearchState`：generation-local opaque value，只公开 deterministic state ID、revision、algorithm/problem/
  seed/duplicate policy 与 counters；private payload 持有 cloned pymoo algorithm/context/RNG/records。
  每个 primitive 不修改输入 state，而返回 next state；同一输入可 deterministic fork。它不 pickle、
  不跨 workspace/strategy/generation/snapshot；complete-generation resume 由 durable CostTable/history 与
  seed 重建，这是唯一 durable resume contract。

## 冻结 search/select primitives 与 commit point

在一个 dependency-neutral public module 提供以下职责（名称可按实现微调，但不合并职责）：

1. `prepare_search(context, search, ...)` 验证 exact strategy/generation/problem/settings，建立 opaque
   history-informed state、history duplicate archive、seed domain 与 pymoo-owned survivor state；
2. `search_candidates(state, count, origin=...)` 在 clone 上 ask configured batches、按 duplicate key 去重，
   再做 bounded random refill，返回 exact ordered pool + next state；无法填满时抛 typed
   `InsufficientCandidatePoolError`，绝不无界循环或返回 partial success；
3. `bind_surrogate_prediction(pool, prediction)` 与 private legacy binder 只做 typed identity/width/finiteness
   validation；predicted rawData/member spread 被丢弃前仍由原 owner 持有；
4. `select_candidates(state, pool, predicted, count)` 把 typed current-cost rows 交给 pymoo survival，返回
   ordered selection + next state；GA single-objective total-cost ordering和 NSGA-III survival 保持现状；
5. `advance_search(state, pool, predicted)` 只通过 pymoo tell 推进 beta simulation；
6. `compose_real_population(state, primary, exploration, size, ...)` 按 current exploration/order/archive/
   refill policy 组合唯一 population；
7. `full_real_search(context, search, ...)` 是共享的完整 real fallback/real-only composition，只调用上述
   primitive 并保留 generation-zero warm start、later offspring 与 source naming。

selection 成功并返回 `CandidateSelection` 是 search-state commit point；真实 evidence commit 仍只发生在
Stage 3 evaluator/recorder。program 可显式保留 previous state、使用 next state 或 fork，但不能从
candidate/prediction 伪造 backend payload。

## 冻结 adapters、fallback 与保留能力

- `RealSearchStrategy.run_generation()` 只调用 shared full-real primitive、common evaluator 与 result
  adapter；不再私有建立 pymoo loop。
- GPSAF alpha/beta/exploration 改为 search/pool -> typed prediction -> selection/advance/compose；PCA/SVD
  binder 必须消费 Stage 4 DTO。conditional-INR/hierarchical-CAE 在 Stage 7 前保留 narrow legacy
  prediction binder，但旧 loop 不保留第二套 ask/survival/refill。
- posterior-assisted candidate pool 与 full-real fallback 复用 prepare/search/full-real primitives；其
  posterior readiness、joint samples、qNEHVI numeric path、support hard stop 与 applicability gate不迁入
  deterministic predicted-cost type。
- soft selection/materialization/prediction failure 必须丢弃全部 derived selection 后从 fresh seed-domain
  state 执行 complete full-real search。`QNEHVISupportRejected`/configuration hard stop、evaluation/
  recording failure、`KeyboardInterrupt`/`SystemExit` 不在 soft catch 内。
- candidate pool exhaustion对 real-only 是 explicit error；GPSAF/posterior derived path 可把它作为 soft
  fallback 原因，但 fallback 若也 exhaust 则向上抛出。predicted values 永不进入 state checkpoint、
  recorder、Dataset/CostTable 或 history。
- GPSAF `alpha`/`beta`/`gamma` factory/default/validation/error/semantic identity/diagnostics 原样保留；
  `gamma` 继续不新增选择数学。不同 gamma 的 fixed-seed selection parity 与 identity/diagnostic delta
  必须同时有 direct evidence。

## 精确测试、文档与 benchmark delta

- 在修改 source 前从 accepted Stage 4 wheel 冻结 GA/NSGA-III、real-only 与 PCA/SVD+GPSAF fixed-seed
  candidate/population golden evidence；改后 old strategy adapter 与逐 primitive composition必须 exact
  ordering parity。
- direct tests 覆盖 candidate/pool/state immutability、candidate/design/evidence identity分离、state
  next/fork determinism、wrong state/generation/strategy rejection、bounded duplicate/refill/exhaustion、
  single/multi survival、ask/tell/survival owner spy、warm-start/later offspring。
- prediction tests 覆盖 exact candidate ID/order/row/objective binding、nonfinite/partial rejection，以及
  `CostTable`/`JointObjectiveSamples`/unbound `SurrogatePrediction` 不能直接传入 selection。
- adapter tests 覆盖 real/GPSAF/posterior full-real parity、complete soft fallback、hard-stop 与 recorder
  propagation、all-infinite result、lazy parent imports、strategy switch 和 no predicted persistence。
- 同步 architecture、optimize/recorded-data/tests blueprints、search/primitives/pymoo/GPSAF/posterior file
  blueprints、terminology、optimization/package user docs 与 change record。

最终按 installed-package workflow build/reinstall/import-origin，运行 focused 与完整 pytest。fast
benchmark 使用 fresh Stage 5 smoke `20 x 2` 与唯一 measured `100 x 20` workspace；两个 expanded
plans 除 budget 外同源，strategy digest 保持 `08E4BE42…6CBA7`、GPSAF `gamma=0.5`；measured 必须
collected/valid、`2000/2000/2000/2000`、zero anomalies，并记录 search state/revision、pool、duplicate/
refill/selection diagnostics。单 seed HV 仍不是算法优劣 gate。

## 状态、授权与依赖

本文是已获单一 Goal 后续精化/执行授权的预测性 TODO。它依赖 Stage 2 的 CostTable、Stage 3
的 EvaluationHandle 与 Stage 4 的 explicit PCA/SVD prediction。Stage 4 完成后，执行者重新
核对 current RealSearch/GPSAF/pymoo state、identity、duplicate/refill、fallback 和 benchmark，
在本文内冻结精确 public/internal primitives，无需等待用户。

## 已知 pre-change 边界

- current `RealSearchStrategy.run_generation()` 与 GPSAF `run_generation()` 隐藏 history ->
  pymoo state -> pool -> prediction -> survival -> exploration -> real evaluation 的完整编排。
- pymoo 应继续拥有 GA/NSGA-III algorithm objects、operators、ask/tell、reference directions 和
  survival 数值；它们不需要成为 yadof 的 broad public object graph。
- GPSAF predicted mean current costs、posterior joint objective samples 和 real CostTable 语义
  不同，不能为了“统一 prediction”混成一个 array type。
- qNEHVI/posterior-assisted 的 readiness/fallback 是独立路径，不因本阶段自动 eligible/default。

## GPSAF gamma 的已定边界

2026-08-30 用户明确决定本重构不修改 GPSAF `gamma`。即使 current evidence 表明它不参与
候选选择数学，本阶段也必须：

- 保留 factory keyword、immutable settings、default、validation 和 error behavior；
- 保留 strategy/component semantic identity 中的 `gamma`；
- 保留 diagnostics/reporting 中现有 `gamma` 语义；
- 不写 removal migration、不把它替换成 ignored compatibility alias、不调整 `alpha`/`beta`；
- 用 old/new parity 证明重构没有让 `gamma` 新增或失去当前行为。

未来删除需要独立用户授权、TODO 和 evidence，不属于本 Goal。

## 预期精确结果

把隐藏 generation orchestration 拆成可组合但窄的 primitives，职责大致为：

1. 从 real CostTable 与 opaque optimizer state 准备/search 一个 unique candidate pool；
2. 调用 Stage 4 typed surrogate prediction；
3. 将 GPSAF predicted current cost 交给 pymoo survival/selection；
4. 按 current exploration/duplicate/archive/refill policy 组合真实评估 population；
5. 返回 selected candidates、next opaque search state 与 bounded diagnostics；
6. 由 caller 通过 Stage 3 common real evaluator 获取新的 evidence。

public program 不直接操作 pymoo Algorithm internals。可序列化/恢复的 search state 由 yadof
拥有，workspace 只传递 opaque value/handle。candidate identity、design duplicate key 与 evidence
identity 分离。

real-only、GPSAF deterministic 和 posterior-assisted paths 可以共享真实 history/pool/evaluator
primitives，但 prediction/acquisition-specific 类型与失败语义保持独立。soft fallback 必须丢弃
不完整 derived choices 后走完整 real search；recorder/hard-stop failure 不得被 catch。

## 预计范围与非目标

预计修改 optimize strategy/pymoo/gpsaf 的窄 boundaries、state/metadata、tests 和直接合同。
旧 strategy-owned loop 可以在 Stage 6 pilot 前保留为 adapter，但只能调用新 primitives，并有
Stage 8 删除条件。

不重写 pymoo/BoTorch 数值，不激活 qNEHVI，不修改 surrogate 数学/checkpoint，不删除现有
algorithms/tools/backend，不让 selected prediction 绕过 real evaluation，不修改 `gamma`。

## 精化时必须决定

- pool/search/select public 粒度与 opaque state commit point；
- candidate/result DTO、duplicate key、seed 与 deterministic ordering；
- search state 与 generation metadata/checkpoint identity；
- old loop adapter 的最短迁移边界；
- prediction type dispatch 如何在不建立 registry/`hasattr` 探测的情况下保持 lightweight；
- full-real fallback 的共享层级。

这些是已授权内部选择。若需要改变 GPSAF 数学、默认 strategy 或移除能力，必须暂停。

## 验证

至少覆盖：

- old/new real search 与 GPSAF deterministic parity，固定 seeds 与 candidate ordering；
- GA/NSGA-III、single/multi-objective、reference directions、ask/tell/survival owner spy；
- duplicate/archive/refill/exploration 与 insufficient-pool failure；
- GPSAF `alpha`/`beta`/`gamma` settings、validation、identity、diagnostics 全部 unchanged；
- predicted current cost、posterior joint samples、real CostTable 类型拒绝互换；
- fallback/hard-stop、all-infinite、recorder propagation 和 common real-evaluator handoff；
- opaque search-state resume、strategy switch、lazy optional imports；
- no predicted data in recorder/history/checkpoint。

按 installed-wheel workflow 完成 focused/full tests。fast smoke 与唯一 100 x 20 measured
benchmark 使用 Stage 4 PCA/SVD + GPSAF；要求 collected/valid/attempted 2000，并分析 selection
parity、duplicate/refill 和 wall time，不要求 HV improvement。posterior/full-real fallback 另用
targeted structural tests，不能由代表性 benchmark 代替。

## 本次执行结果（2026-08-31）

- 新增 backend-neutral frozen `SearchCandidate`、opaque/non-pickle
  `SearchState`、`CandidatePool`、`PredictedCostRows` 和 `CandidateSelection`；
  candidate ID、rounded duplicate key 与 optional source evidence ID 已分离。每个 primitive
  clone private pymoo/RNG payload 并返回 next revision，可从同一输入 deterministic fork，且绑定
  exact strategy/problem/generation/snapshot identity。
- 新增 explicit prepare/continue/fork/search/warm-start/bind/select/advance/combine/compose/full-real
  primitives。pymoo 继续独占 algorithm、ask/tell/operator/reference-direction/survival 数值；ask 与
  random refill 有界，无法满足 exact pool 时抛 `InsufficientCandidatePoolError`，不返回 partial
  success。
- `RealSearchStrategy`、GPSAF 和 posterior full-real fallback 已共用同一 complete real-search
  composition。GPSAF alpha/beta/exploration 改为 typed pool -> prediction -> selection/advance ->
  composition；retained surrogate 仅在一个 legacy binding edge 转换为同一 `PredictedCostRows`。
  posterior readiness、joint samples、qNEHVI hard stop/applicability 与 soft fallback 仍是独立能力。
- Stage 4 `SurrogatePrediction` binder 验证 exact state/pool/candidate order/objective width/finiteness；
  `CostTable`、`JointObjectiveSamples` 和 unbound `SurrogatePrediction` 均不能直接 selection。
  prediction 不进入 recorder、dataset/checkpoint/history；所有 selected candidates 仍经 Stage 3
  common real evaluator。
- accepted Stage 4 wheel pre-change focused baseline 为 `45 passed in 6.62s`；SHA-256
  `2BD48AF6084045D5FE43B82B962C098B61991C9C41FDB0E9BE12EA4D250E17CE` 的 golden harness
  冻结 GA/NSGA-III、real-only 与 GPSAF seeded population/ordering/diagnostics，改后 installed wheel
  exact parity。final focused 为 `55 passed in 6.75s`，broader optimize/surrogate 为
  `116 passed in 19.19s`，installed-wheel full pytest 为 `429 passed in 94.96s`。
- fresh smoke `temp/20260831_110042-stage5-benchmark-smoke` collected/valid
  `40/40/40/40`、zero issues/anomalies/publication failures；唯一 measured
  `temp/20260831_110042-stage5-benchmark-measured` collected/valid
  `2000/2000/2000/2000`、zero issues/anomalies/publication failures。measured optimization command
  `649.1225638 s`、result runtime `649.4805222 s`、benchmark elapsed `697.618195 s`；final HV
  `0.17932445257445517` 仅为 descriptive evidence。
- measured generation 0 是 warmup，generation 1--19 均使用 surrogate；每个 surrogate generation
  exact selection 90 + exploration 10，20 个 state ID distinct，revision 为 warmup `2` / surrogate
  `16`，duplicate/refill totals 均为 0。20/20 training/checkpoint alias/namespace manifest/artifact
  完整，artifact hash 与 training state/data digest sets 全部一致。
- smoke/measured strategy bytes 与 SHA-256 均为
  `08E4BE42C4E4A8D377866BF8BC21765A0B776A27C32823290F97210FE086CBA7`；GPSAF
  `gamma=0.5` 在 20 个 generation identity/diagnostics 中保持不变，fixed-seed direct tests 证明
  不同 gamma 只改变 identity/diagnostics、不改变当前 selection ordering。
- reliable-recording check 证明 primitive/prediction 不持久化、soft fallback 不吞 recorder failure、
  measured 2,000 rows 全部发布；bounded redundancy check 删除 real-only 与 assistance 的第二套
  real-search loop，只保留语义不同的 prediction/acquisition adapter。release-marker check 只命中明确的
  Stage 7 retained-capability wording；component-configuration check 只见 factory-owned settings 与
  core population/seed/archive/training-lag policy，无第二入口。四份 recurring auto TODO 保持 active。
- architecture、optimize/recorded-data/tests 与全部相关 file blueprints、terminology、optimization/
  package user docs 已同步；change record 为
  `dev_doc/change_records/20260831_112512_add-explicit-search-selection-primitives.md`。本文
  post-refinement/pre-implementation SHA-256 为
  `0630D23EBFCC7D3C1733D73E2402D3D9375D531D5613F9774675BE738628402A`；进入阶段时
  worktree clean，无 pre-existing user changes。

## 完成、归档与自动续跑

search/predict/select 已成为可由 program 组合的唯一内部算法 primitives，旧 adapter 只转发，
pymoo ownership、GPSAF 全部当前语义（含 `gamma`）、fallback 与 real-evaluation boundary 有
直接 evidence；文档/automatic TODO check/change record/commit/fetch-push 完成后，归档本文、
更新 ledger，并自动进入
[Stage 6 workspace program pilot](../../toDo/20260830_174612_explicit-optimization-stage-6-workspace-program-pilot.md)。
