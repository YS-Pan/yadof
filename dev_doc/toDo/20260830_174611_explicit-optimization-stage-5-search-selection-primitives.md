# 显式 optimization 重构阶段 5：拆分 search、prediction 与 selection 原语

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

## 完成、归档与自动续跑

search/predict/select 已成为可由 program 组合的唯一内部算法 primitives，旧 adapter 只转发，
pymoo ownership、GPSAF 全部当前语义（含 `gamma`）、fallback 与 real-evaluation boundary 有
直接 evidence；文档/automatic TODO check/change record/commit/fetch-push 完成后，归档本文、
更新 ledger，并自动进入
[Stage 6 workspace program pilot](20260830_174612_explicit-optimization-stage-6-workspace-program-pilot.md)。
