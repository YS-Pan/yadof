# 显式 optimization 重构阶段 7：迁移全部保留能力与外围消费者

## 状态、授权与依赖

本文是已获单一 Goal 后续精化/执行授权的预测性 TODO。Stage 6 pilot 成功后，执行者必须用
consumer inventory、imports/callers、tests、checkpoint/viewer/benchmark evidence 在本文内冻结
迁移批次和 parity matrix；不等待新的用户指示。

本阶段迁移“已有能力的 orchestration/data boundary”，不自动执行其他 active/parked TODO 所
拥有的科学研究、真实 simulator campaign 或默认策略决定。

## 必须保留并迁移的能力

至少 inventory 并处理：

- real search、GA/NSGA-III、GPSAF；
- conditional-INR、PCA/SVD、Hierarchical CAE 的 training/prediction/checkpoint/scheduler；
- joint rawData posterior、cost projector、typed readiness、posterior-assisted 与 qNEHVI；
- blocked-readiness/full-real fallback、hard stop、real exploration；
- strategy/component namespace、semantic identity、generation metadata、progress；
- `after_jobs_submitted` 的所有真实消费者；
- surrogate viewer、cost/time tools、history query/clear、CLI run/check/init；
- yadof-benchmark strategy modules、fixtures、postprocessors 和 source examples；
- starter/examples/user docs 最终交付所需的 capability surface。

迁移后这些消费者必须使用 Stage 2--6 的 Dataset/CostTable、handle、fit/predict、search/select
和 program scope。不得用 hidden session reads、backend hook 或 strategy-owned loop 继续保留
第二种事实上的 orchestration。

## 科学 handoff 边界

- [Hierarchical CAE research TODO](20260830_120818_hierarchical-cae-evidence-led-research.md) 继续
  拥有 representation/mapping/coordinate/resource 研究；本阶段只保证其 current deterministic
  capability 在新 program 下可用。
- [EHVI/qNEHVI TODO](20260828_121904_surrogate-qnehvi-remaining-work.md) 继续拥有 posterior
  suitability、eligible-path canary、真实同预算研究和发布决定；本阶段保持 exact-state
  readiness/fallback，不虚构 eligible evidence。
- noise-robust、trust-region 与 acquisition-protocol TODO 保持其 active/PARKED/trigger 状态。
  迁移 current boundary 不构成执行授权。
- 需要真实 simulator、长 training 或新 scientific threshold 时按 overall plan 暂停。

active handoff 中若仍把 current `build_optimization()`/hidden loop 描述成未来唯一边界，本阶段
应更新为“当前 pre-cutover contract + 新 program handoff”，但不得重写 sealed evidence 或
obsolete history。

## after_jobs_submitted 与 overlap

`after_jobs_submitted` 不能成为新 program 的通用 lifecycle。迁移时：

- distributed submission 返回/更新 Stage 3 handle，program 可在 start 后显式安排 independent
  training，再 wait；
- fast/local 通过同一 handle 能力表达真实可用 overlap，不伪造 scheduler event；
- scheduler-specific diagnostics 可保留在 backend handle metadata；
- 最后一个 consumer 迁移并有 tests 后删除 hidden callback；若 Stage 8 才能安全删除，记录
  exact consumer/deletion proof，禁止新增调用方。

## GPSAF gamma 与 prediction 类型

GPSAF `gamma` 的 factory/settings/validation/identity/diagnostics 保持 current semantics，不删除、
不弃用、不加入选择数学。GPSAF predicted current costs、posterior joint samples、deterministic
rawData predictions 和 real CostTable 分别走 typed boundaries。迁移不得用 broad `Any`、
`hasattr` 或字符串 registry 混淆 capability。

Acquisition Capability Protocol 只有其独立 TODO 的第二真实实现/blocked-caller trigger 命中时
才实施；本阶段不能为了“统一接口”虚构第二 acquisition。

## 迁移方式

精化时按 consumer graph 划分串行 slices，但保持一个 Stage 7 TODO：

1. 冻结 capability/consumer matrix、current signatures/checkpoint identities 和 parity fixtures；
2. 先迁移 deterministic components 与 common schedulers；
3. 再迁移 posterior/readiness/fallback；
4. 迁移 viewer/tools/CLI/benchmark/starter-input consumers；
5. 搜索并证明 hidden session read、callback、old loop consumer 的剩余清单；
6. 每个 slice 运行 focused tests，全部完成后运行 full acceptance 与 benchmark。

允许内部 module move，但 public capability 不因结构简化消失。checkpoint/state 若需要 migration，
必须保留 exact identity、atomic commit 和明确 cold-train/recovery 行为，不解释 incompatible
artifact。

## 验证

除 full suite 外，至少建立 capability matrix，逐项记录 pre/post API、identity、checkpoint、
failure/fallback 与测试：

- conditional-INR/PCA-SVD/CAE fit/predict/recovery/viewer；
- real-only/GPSAF/posterior-assisted blocked fallback；
- qNEHVI lazy optional backend、joint draw alignment、real evaluator handoff；
- single/multi objective、duplicate/refill、all-real fallback；
- async training/evaluation order、cancel/cleanup、strategy switch；
- fast/local/distributed transport/resources/timeouts；
- CLI check/run/resume、tools/history 与 benchmark integration；
- no hidden session training read、no predicted recorder entry；
- GPSAF `gamma` unchanged。

representative fast 100 x 20 benchmark 仍使用 PCA/SVD + GPSAF，并不足以证明全部矩阵；advanced
paths 用 targeted synthetic/fake/structural tests 和既有合法 artifacts。不得把 blocked posterior
改成 eligible 只为覆盖代码。local/distributed full-budget 与真实 simulator 不在授权内。

按开发指南完成 wheel/force reinstall/import-origin/focused/full tests、overall smoke/measured、
docs/change record/automatic TODO check 和 commit/fetch-push。

## 完成、归档与自动续跑

全部 retained consumers 已在新 program/primitives 上有直接 parity evidence；旧 callback/loop/
session-read 只剩 Stage 8 明确可删除的零或封闭清单；没有能力/default/checkpoint/readiness
退化，GPSAF `gamma` 不变。随后归档本文、更新 ledger，不等待用户，自动进入
[Stage 8 cutover/release](20260830_220201_explicit-optimization-stage-8-cutover-and-release.md)。
