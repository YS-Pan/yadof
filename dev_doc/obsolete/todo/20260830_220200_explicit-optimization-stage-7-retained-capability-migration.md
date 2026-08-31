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

- [Hierarchical CAE research TODO](../../toDo/20260830_120818_hierarchical-cae-evidence-led-research.md) 继续
  拥有 representation/mapping/coordinate/resource 研究；本阶段只保证其 current deterministic
  capability 在新 program 下可用。
- [EHVI/qNEHVI TODO](../../toDo/20260828_121904_surrogate-qnehvi-remaining-work.md) 继续拥有 posterior
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

## 2026-08-31 执行前精化：consumer graph、parity matrix 与串行切片

本次精化的输入 HEAD 为 `f336bc75d6cb4798ceee523de0e24e2f4137af4e`，本文精化前
SHA-256 为 `BC1A5325B2D19F60AFC6471479233E44B5118BF4B716532DFCC211876FC34D0F`。
上一阶段已提供静态 declaration、冻结 source、program/run/generation scope、明确
Dataset/CostTable 和 evaluation handle；本阶段不改变这些所有权。

冻结后的 consumer graph 如下：

| capability | pre-migration consumer/boundary | Stage 7 program boundary | identity/checkpoint/failure parity | proof |
| --- | --- | --- | --- | --- |
| real GA/NSGA-III | `RealSearchStrategy.run_generation()` | program 调用 `full_real_search()`，显式 start/wait/close/commit | pymoo settings、seed、duplicate/refill 语义不变 | single/multi program tests |
| GPSAF deterministic selection | `GPSAFStrategy` -> `gpsaf.assistance.run_generation()` | program 显式物化 training data 并调用一个 generation-local typed selection operation | `alpha/beta/gamma/exploration_fraction`、candidate identity 和 full-real fallback 不变；`gamma` 只保留现有 identity/diagnostics | warmup/trained/failure tests |
| PCA/SVD | component 已接受 `SurrogateTrainingData` | 保留 Dataset/CostTable -> fit/predict/recover/scheduler | component v2、namespace、atomic checkpoint 不变 | 现有 Stage 6 program test + recovery/viewer tests |
| conditional-INR | component/runtime 从 `context.session` 重建 training data | component 接受显式 `SurrogateTrainingData`，scheduler/predict 只消费该值 | component v2、conditional checkpoint namespace 和 cold-train 行为不变 | explicit-data scheduler/predict tests |
| Hierarchical CAE | component/data adapter 从 session 重建 named data | component 由显式 `SurrogateTrainingData` 转换成 retained named deterministic input | component v1/v2、CAE namespace、applicability/coordinate capability 不变 | explicit-data fit/recovery/viewer tests |
| joint rawData posterior/projector/qNEHVI | posterior-assisted strategy 拥有整个 generation，conditional adapter 隐式读 session 取 schema | program 先显式物化 evidence，generation-local selector 将该值传入 sampler，projector 仍是 current-task typed boundary | draw alignment、finite support、projector fingerprint、qNEHVI hard stop 不变 | blocked readiness、joint draw、lazy backend tests |
| posterior readiness/fallback | `PosteriorAssistedStrategy.run_generation()` 内部 evaluate | 公开 selection 结果明确表示 surrogate/fallback，program 始终执行 real evaluation | conditional-INR/CAE 仍 performance-not-accepted + uncalibrated，不制造 eligible path | blocked fallback + hard-stop tests |
| evaluation/training overlap | `after_jobs_submitted` 在 distributed 为 submit 后、local 为完成后、fast 不执行 | program 以固定顺序 `start evaluation -> start training(previous immutable evidence) -> wait -> close -> finish training` | handle cancel/cleanup 和 scheduler diagnostics 保留 | fake-order + fast/local handle tests |
| metadata/progress/namespace | strategy runner + component helpers | program scope 写 generation/completion，component 使用 active program signature | source fingerprint、strategy switch、recording counters 不变 | resume/switch/metadata tests |
| viewer/cost/time/history | 直接读 durable recorded/checkpoint APIs | 不获得 orchestration 权限；仅适配新 namespace/metadata 输出 | 历史查询/清理、checkpoint discovery 不退化 | 既有 tools/viewer tests + structural search |
| CLI check/run/init/resume | loader 允许 legacy `build_optimization()` | starter/examples/baselines 全部交付静态 declaration + explicit program/helper | check 不 import，frozen helpers，completion pointer 不变 | CLI/program/benchmark integration tests |

串行执行切片冻结为：

1. 建立 typed deterministic component protocol 与 generation-local GPSAF selection DTO；迁移
   conditional-INR/PCA-SVD/CAE 的 Dataset/CostTable -> training -> predict/scheduler，不改变
   checkpoint identity。
2. 将 posterior-assisted 拆为 typed selection 与 program-owned real evaluation；conditional posterior
   schema 从显式 training data 获得，保留 blocked readiness、qNEHVI configuration hard stop、
   exploration 和 projector 对齐。
3. 将 starter、HFSS source example 和三个 benchmark baseline 迁移为 program/helper；该
   helper 明文呈现 selection、evaluation handle、training 和 commit 顺序，不调用
   strategy-owned loop。
4. 核对 viewer/tools/history/CLI/benchmark planner/postprocessors；只修改真实依赖旧
   boundary 的 consumer，并用 structural tests 证明其余 consumer 已是 durable read-only。
5. 删除新 program path 上的 callback。Stage 7 结束时允许的封闭清单仅为
   Stage 8 将删除的 legacy `OptimizationStrategy.run_generation()` adapter、legacy
   `evaluate_population(..., after_jobs_submitted=...)` 和 backend callback field；不得有 starter、
   example、benchmark 或新 public program caller。
6. 每个切片运行 focused tests；最后运行 installed-wheel full suites、授权的
   20 x 2 smoke 和 PCA/SVD + GPSAF 100 x 20 measured benchmark，并完成 docs/
   change record/archive/commit/fetch-push。

不进入实施的边界同时冻结：不调整 CAE 科学架构或 threshold，不将
conditional-INR/CAE posterior 标为 eligible，不开启 noise/trust-region/protocol TODO，
不运行真实 simulator/HTCondor。`gamma` 保持 factory/settings/validation/identity/
diagnostics current semantics，且不进入选择数学。

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
[Stage 8 cutover/release](../../toDo/20260830_220201_explicit-optimization-stage-8-cutover-and-release.md)。

## 2026-08-31 完成证据

本阶段按精化后的六个串行切片完成。deterministic surrogate component 现在公开 typed
training-data、prediction、scheduler lifecycle、latest-generation 和纯 freshness 边界；
conditional-INR 与 CAE 的 program path 不再从 session 重建 training input。GPSAF 与
posterior-assisted 公开 generation-local typed selection，选择函数不执行 real evaluation、
training 或 generation commit；starter、HFSS example 和三个 benchmark baseline 均明文执行
`select -> start evaluation -> start training -> wait/close -> finish training -> commit`。

PCA/SVD 保留原有 exact checkpoint recovery，并增加只读的 lagged-compatible recovery：它从
当前显式 evidence 重建 checkpoint row-id 子集，重新核验旧 content digest、schema、strategy、
settings、parameter normalization 与 artifact。compatible lookup 不 fit、不写 checkpoint；
canonical JSON 比较同时消除了 tuple/list 序列化形态差异。conditional posterior schema 由
显式 training data 提供，closed legacy fallback 只留给 Stage 8 删除。

验证结果：

- slice 过程中 core focused `50 passed in 10.46s`，consumer suite `96 passed in 78.64s`；
  duplicate-training 修复后的最终 focused suite 为 `48 passed in 3.09s`；
- corrected installed wheel 的完整 yadof suite 为 `448 passed in 87.84s`，benchmark package
  suite 为 `21 passed in 0.99s`；import-origin 均指向本 workspace `.venv` 的
  `site-packages`，版本分别为 yadof `0.4.2`、yadof-benchmark `0.2.2`；
- authorized synthetic-antenna smoke 在 host foreground 恰好运行一次，完成
  `40/40/40/40` planned/attempted/completed/finite、zero issues/publication failures，result
  runtime `7.0127993 s`。该 run 的 metadata 暴露 selector freshness 会在 evaluation 前训练、
  随后 explicit helper 对同一 evidence 再训练的重复副作用；实现随后改为 pure read-only
  freshness 与 exact lagged recovery。exact-once 约束下未重跑 smoke，也不把该 pre-fix run
  作为修复后的训练生命周期证据；
- corrected installed wheel 的 authorized PCA/SVD + GPSAF measured run 在 host foreground
  恰好运行一次，完成 `2000/2000/2000/2000`、zero issues/anomalies/publication failures，
  result runtime `639.2837664 s`、benchmark elapsed `685.680791 s`。20 个 generation 中
  generation 0 无 data 并 full-real fallback，generation 1 训练 100 rows；generation 2--19
  使用 latest `n-1` checkpoint。共有且仅有 19 个 training events/checkpoints（generation
  1--19、100--1900 rows），无重复 fit，最大 lag 为 1；
- smoke/measured 使用相同 strategy source SHA-256
  `E88A03AD14454ABDB5316BB2D70C1AD2521D8DC264B528D39132BA4B24915BDE`；measured program
  source fingerprint 为 `09FFE9A77A735C13263520C0C8C3D962292D8191C454B604C09694E6728FA094`，
  semantic signature 为 `EDD3F5A08C7E6346D6C8A28901142030A782CBE16DA83E4286070BEE30B7FE7F`，
  strategy digest 为 `561353C40EF08A111293A4B2A0BE127A6BBDDD79917C36BD28442EBA257B63CF`；
  `gamma=0.5` 未改变且不进入 selection math，recording failure counters 全为零。

consumer/structural proof 表明新 public program caller 不再使用 strategy-owned loop、hidden
session training read 或 callback。Stage 8 的封闭删除清单仅剩 legacy
`OptimizationStrategy.run_generation()` adapter、legacy campaign/factory loader、legacy
GPSAF/posterior phase materializer、`evaluate_population(..., after_jobs_submitted=...)` 与 backend
callback field，以及 `build_optimization()` compatibility surface；没有 starter、example 或
benchmark baseline 依赖这些边界。

automatic TODO check 逐项核对 component-config migration、reliable recording、incidental release
markers 与 redundancy tracker：本阶段未发现与其 trigger 一致的新证据。settings 已显式传递；
benchmark recording counters 为零；0.4 compatibility/Stage 8 标记是本阶段冻结的 cutover policy；
exact 与 lagged recovery 是不同验证边界。四个 TODO 均保持原状态，未自动激活；CAE、qNEHVI、
noise、trust-region 与 acquisition-protocol 的科学工作也未越权进入本阶段。
