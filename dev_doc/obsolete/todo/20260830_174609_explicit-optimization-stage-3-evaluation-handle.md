# 显式 optimization 重构阶段 3：统一 EvaluationBatch 与 EvaluationHandle 生命周期

## 本次精化输入（2026-08-31）

- 输入 HEAD/Stage 2 accepted commit：
  `39da8b3a9ea2262b73a6411c40035ec21c558a5f`，分支 `main`，worktree/staged diff 均为空；
  post-commit `fetch origin main` 后 behind 0 / ahead 4，因未达到 ahead >= 5 未 push。
- 本文 pre-refinement SHA-256：
  `A8A9219D6FEEEE03D6A598C3AC7C22AC0B24C36838A78EE7336500699C723E08`；overall plan
  SHA-256：`2AD03C3944AFFFCC9D17942DBA5AA7159AA383243819B24333A7D9AD13E7F053`。
- 接受基线是 installed yadof `0.4.2`，import origin 为外层
  `.venv/Lib/site-packages/yadof/__init__.py`；Stage 2 full suite 为
  `400 passed in 81.00s`。Stage 2 已证明 successful committed original evidence 才进入 optimizer
  history，pending row 无 readable handle，CostTable 只在 optimizer adapter 产生正确宽度 `inf`。
- Stage 2 fast smoke `40/40/40` 和 measured `2000/2000/2000` 均 collected/valid；本阶段继续
  使用 strategy source SHA-256
  `08E4BE42C4E4A8D377866BF8BC21765A0B776A27C32823290F97210FE086CBA7` 的同一完整显式
  NSGA-III + GPSAF + PCA/SVD settings，GPSAF `gamma=0.5` 不变。

## 精化时确认的当前实现事实

- public `evaluate_population()` 同时拥有 candidate materialization、session/snapshot 创建、backend
  dispatch、publication/interpretation 和 cleanup；三个 `_dispatch_*` 最后都经过
  `ResultFinalizationCoordinator`，但随后只保留 cost tuple。
- coordinator 已在 `PublicationReceipt.wait_committed()` 后按 population index 解释并 expose
  `JobResult`；因此 handle 不需要第二套 recorder/result queue，只需把 finalized rows 保留为唯一
  terminal result。
- fast worker poll loop、local `Popen.communicate()` 与 Condor submit/poll loop 都有明确 cleanup，
  但没有 common cancellation signal。窄 adapter 可以在各自等待边界检查同一个 thread-safe event，
  无需把 worker/process/cluster concrete type 暴露给 caller。
- `CampaignSession.begin_generation()` 当前不检查 generation-scoped asynchronous work，`close()`
  直接 shutdown writer 和 snapshots。新增 handle registry 必须在 writer shutdown 前 cancel/wait/close，
  并在下一 snapshot 创建前拒绝仍 open 的上一 generation handle。
- standalone evaluation 的 session/snapshot 可以推迟到 start；这样 prepared-but-never-started batch
  没有 workspace lock、snapshot directory、writer thread 或伪造 evidence。已有 campaign path 则复用
  caller 的 exact current snapshot，不能另建 snapshot。

## 冻结 public lifecycle 与 result contract

从 `yadof.evaluate_manager` 导出：

- frozen `EvaluationBatch`：由 `prepare_evaluation(workspace, population, ...)` 创建，冻结 input order、
  effective mode/timeout/workers/environment、run/generation provenance、objective width 以及可选现有
  session/snapshot lease；prepare 只 materialize iterable 并验证 batch-level configuration，parameter
  assignment/prepare failure 仍是 start 后的 per-candidate result。
- `EvaluationHandleState`：`created`、`running`、`cancelling`、`completed`、`failed`、`closed`；
  `EvaluationHandle(batch)` 保持 created，`start()` 和 convenience `start_evaluation(batch)` 启动唯一
  non-daemon owner thread。
- frozen `EvaluationResult`：包含 batch ID、mode、input-order finalized `JobResult` rows、objective width、
  `cancel_requested` 与 bounded JSON-safe batch diagnostics；其 `costs` property 是同步 optimizer facade
  唯一的 fixed-shape adapter，只有 row cost 缺失时生成正确宽度 `inf`。

`wait(timeout=None)` 对 terminal success 返回同一个 `EvaluationResult` object；timeout 只中止本次
wait，不改变 handle。framework failure（尤其 recorder/publication failure）由所有 waiter 重复抛出，
不会变成 individual `inf`。`start()` 重复调用在已启动状态返回同一 handle；closed 或 start 前已
cancelled 的 handle 不再启动。

`cancel()` 精确采用以下 policy：

- created handle 直接形成 ordered `cancelled` terminal rows，evidence state 标为 `not_started`，
  不创建 session/snapshot/job/segment；重复 cancel 返回 false；
- running handle 原子转为 cancelling 并设置 common event。fast 停止分配、hard-stop active worker
  tree；local 停止 queued work并 terminate active workflow tree；Condor 停止 submit、保留已可收集
  completion并对其余 cluster 调用现有 remove。每个未完成 candidate 形成 durable status
  `cancelled`，进入同一 coordinator，因此 candidate/evidence identity、ordered exposure 和
  not-applicable interpretation 与其他 execution failure 一致；
- completion 与 cancel 竞态以 backend 已观测的完整 result 为准；已 finalized evidence 永不回滚。
  timeout 保持 `timeout`，backend crash 保持 `error`，cleanup/remove failure 写入 bounded row metadata；
- completed/failed/closed handle 的 cancel 是 no-op。`close()` 对 active handle先 cancel 再 wait，释放
  registry/snapshot lease；重复 close 保持同一 cached result/failure semantics。context manager 在
  caller exception 下执行相同 cancel/wait cleanup，原 caller exception 不被普通 cancellation 覆盖。

public result 的 `JobResult.raw_data_*` 在 finalization 后为空，只含 recorder-owned/committed evidence
identity 与 bounded runtime metadata；program 需要 rawData 时通过 Stage 2 Dataset handle 读取，不能
从 backend scratch path 取得未 owned payload。coordinator 在 finalized row metadata 中加入 durable
`candidate_id/evidence_id` 和 receipt/group state，结果可见点仍严格晚于 rawData validation、ownership、
segment commit 和 interpretation classification。

## 冻结 generation scope 与 backend delta

- `CampaignSession` 仅登记复用该 session/current snapshot 的 open handles。登记后切换 generation
  fail-fast；`session.close()` 复制 registry 后逐个 cancel/close，再 shutdown writer、释放 lock、删除
  snapshots。它不持锁等待 handle，避免 recorder callback/close deadlock。
- completed-but-not-closed handle 仍算 open lease；同步 facade 和 future scope 都必须在 generation
  boundary close。standalone handle 自己创建并在 terminal publication 后关闭 owned session，不登记
  到自身 session 造成递归 close。
- fast/local/distributed 的 dispatch return type 统一为 finalized `JobResult` rows；existing
  `evaluate_population()` 和 `run_smoke_test()` 均以 prepare/start/wait/close 组合，不保留第二条同步
  orchestration。hidden `after_jobs_submitted` 只作 Stage 7 前 compatibility hook，不成为 handle state，
  不给 fast/local 伪造 scheduler submission event。
- common cancellation event 是最小 capability；backend-specific worker/resource/cluster/cleanup fields
  只留在 bounded per-row metadata。handle diagnostics 只保留 batch ID、mode、candidate/status counts、
  cancel phase 和 terminal timing，不嵌入 stdout、rawData、exception traceback 或 scheduler ads。
- 新 durable `cancelled` execution status 加入现有 status schema；Stage 2 Dataset 原样呈现它，
  CostTable 分类为 `not_applicable`，history/recorder/query 不把它误作 completed evidence。

## 精确测试、文档与 benchmark delta

- 新增 direct lifecycle tests，覆盖 created/start/wait/double wait/double close、cancel before start/during/
  after completion、wait timeout、多 waiter、caller exception、framework failure wakeup 和 sync parity；
- 用 small local process、fast worker 以及 fake Condor submission/removal 直接证明 active/queued cleanup、
  ordered mixed completion/cancel、callback compatibility 和 backend diagnostics；不运行真实 HTCondor
  full budget；
- publication gate test 在 cost callback 中检查 receipt committed，并证明 handle 尚未 terminal；new
  session 重开后 candidate IDs/status 与 handle rows一致；recorder failure 必须唤醒 waiter并保持 fatal；
- generation tests 证明 open handle 阻止 next snapshot，normal/exception `session.close()` 无 handle、
  pending receipt、writer、snapshot 或 child ownership；Stage 2 dataset/cost identity join 与 cancelled
  recorder non-entry 规则保持一致；
- 同步 architecture、evaluate-manager/recorded-data/optimize/tests blueprints、相关 file blueprints、
  terminology、optimization/package/evaluation user docs 和 change record。

最终按 installed-package workflow build/reinstall/import-origin，运行 focused 与完整 pytest。fast
benchmark 使用 fresh Stage 3 smoke `20 x 2` 与唯一 measured `100 x 20` workspace；两者 strategy
source digest 必须继续为 `08E4BE42…6CBA7`，除 budget 外 policy 相同，measured 必须
collected/valid、attempted/completed/finite `2000/2000/2000`。该 benchmark 只证明统一 handle path
的结构/回归，不以单 seed HV 作算法优劣结论。

## 状态、授权与依赖

本文是已获单一 Goal 后续精化/执行授权的预测性 TODO。它依赖 Stage 1 的 publication receipt
和 Stage 2 的 stable Dataset/CostTable identity。Stage 2 完成后，执行者在本文内重新核对
fast/local/distributed 实现、snapshot/session ownership、timeouts/cancel/cleanup 和 accepted
evidence，再冻结精确 API；不等待新的用户指示。

把 handle 放在 surrogate/program 之前，是为了先建立任何显式异步顺序都不能绕过的 framework
生命周期。尚未精化时，`EvaluationBatch`、`EvaluationHandle`、`start/wait` 只是职责名称，
不是兼容承诺。

## 已知 pre-change 边界

- 现有 `evaluate_population()` 同步返回完整 population；三 backend 有成熟但不同的 worker、
  process、HTCondor transport 与 cleanup。
- distributed 有 scheduler-specific `after_jobs_submitted`，fast 不伪造 submit event；这个 hook
  不能成为未来 program overlap 的公共抽象。
- CampaignSession、generation task snapshot、recorder flush 与 result ordering 已有强合同。
  异步 handle 必须受这些 scope 管理，不能让用户代码取得未 commit evidence 或跨 generation
  泄漏工作。
- candidate failure 仍是 ordered row；recorder failure 仍是 campaign-fatal。

## 预期精确结果

提供 backend-neutral 的 bounded evaluation lifecycle：

```python
batch = prepare_evaluation(candidates, snapshot=...)
handle = start_evaluation(batch)
# program may do independent bounded work here
results = handle.wait()
```

精化后的 contract 必须覆盖：

- `prepare/start/wait/cancel/close` 或等价窄动作，状态至少能区分 created/running/cancelling/
  completed/failed/closed；
- start 后由 framework scope 持有 snapshot lease、candidate identity/order、backend resources、
  recorder ownership 与 cleanup obligations；
- result 只有在 rawData validated、owned、committed 且 current interpretation 完成/失败分类后
  对 program 可见；
- `wait`/`cancel`/`close` 的重复调用与异常传播具有明确幂等性；
- cancel 尽力停止未开始/正在运行工作，仍正确收集已完成 evidence；无法撤销的 scheduler
  work、cleanup failure 与 timeout 有可诊断终态；
- generation scope 退出时自动 wait/cancel/close 或按精确 policy 收口，下一 generation 不能在
  open handle、pending receipt 或未关闭 backend resource 上开始；
- population order、objective width、individual failure 和 recorder-fatal 语义与同步路径等价；
- fast/local/distributed 共享 public state/result contract，但保留各自实现，不用最低公分母
  重写 transport。

默认同步 helper 可以由 handle 组合实现。显式 overlap 由以后 `optimization.py` 在同一
generation scope 内决定；本阶段不把 training/search 迁入 program。

## 预计范围与非目标

预计修改 public evaluation API、common coordinator、三个 backend 的窄 adapter、generation/
campaign scope tracking、tests 和直接文档。旧同步调用方可以在本阶段内部迁到统一 handle；
若需要短暂兼容 facade，必须有 Stage 8 删除条件，不能成为永久第二实现。

不在本阶段：

- 改写 pymoo/GPSAF/surrogate 算法；
- 让 handle 跨 generation、跨 workspace 或脱离 CampaignSession 持续；
- 暴露 Condor job/fast worker 等 backend concrete type 给 workspace program；
- 允许返回未 committed rawData、predicted result 或第二套 history；
- 实现任意 Python continuation/resume；
- 修改 GPSAF `gamma`。

## 精化时必须解决的选择

- prepared batch 与 start 是否合并，候选 validation 发生在哪个边界；
- cancel 的 cooperative/forced 分层和 terminal result shape；
- handle diagnostics/metadata 的 JSON-safe 上限；
- program 异常时 scope 的默认 cancel/wait 顺序；
- fast/local/distributed 的最小共同 capability 与 backend-specific optional diagnostics；
- 同步 API 的迁移周期及 Stage 8 no-consumer proof。

这些属于已授权内部设计。只有需要新增跨 generation work、真实 scheduler destructive action 或
改变现有 failure semantics 时才暂停。

## 验证

至少覆盖：

- 三 backend 的 prepare/start/wait、ordered success/failure、double wait/close；
- cancel before start、during work、after completion，以及 process tree/worker/Condor cleanup；
- user code exception、timeout、backend crash、recording failure 与 waiter wakeup；
- result publication-before-visibility，new-session durable recovery；
- generation scope 正常/异常退出没有 open handle、pending receipt、child process 或 scheduler
  ownership；
- 禁止下一 generation/open second campaign 的非法状态；
- 同步 facade 与 handle path parity；
- fast/local/distributed resource diagnostics 与 current timeout/retry semantics；
- Stage 2 Dataset/CostTable identity 对齐和 recorder non-entry。

按 development guide 完成 installed-wheel focused/full tests。full-budget 只用 fast synthetic；
local/distributed 用 fake/contract/small smoke。然后运行 overall policy 的同源 smoke 与唯一
100 x 20 measured benchmark。该代表性 benchmark 不能替代三 backend cancel/cleanup tests。

## 本次执行结果（2026-08-31）

- 新增 frozen `EvaluationBatch`、`EvaluationHandleState`、`EvaluationHandle` 与 deeply immutable
  `EvaluationResult`；`prepare_evaluation()`/`start_evaluation()` 公开导出，同步 evaluator 与 smoke
  facade 均组合 prepare/start/wait/close，不保留第二条 orchestration。
- fast/local/distributed 统一返回 input-order finalized `JobResult` rows 并观察同一个 cancel event；
  fast/local 的 active process tree、queued work 以及 fake Condor outstanding clusters 均有直接
  cleanup 证据，已完成且 committed 的 row 不回滚。新增 durable `cancelled` status，但 cancel-before-start
  不创建 session、snapshot、job、segment 或 evidence。
- campaign handle 复用 exact current snapshot，open lease 阻止下一 generation；session close 在 writer/
  snapshot cleanup 前 cancel/close handles。publication gate、new-session candidate/evidence identity、
  multi-waiter、timeout/context exception、recorder-fatal wakeup 与 synchronous parity 均有 direct tests。
- direct lifecycle `10/10`，focused evaluation/recording/dataset/optimization `109/109`；最终 installed-wheel
  full suite 为 `410 passed in 86.27s`，import origin 为外层
  `.venv/Lib/site-packages/yadof/__init__.py`。
- fresh smoke `temp/20260831_082851-stage3-benchmark-smoke` 为 collected/valid
  `40/40/40/40` planned/attempted/completed/finite、zero anomalies，elapsed `11.545118 s`；唯一 fresh
  measured `temp/20260831_083033-stage3-benchmark-measured` 为 collected/valid
  `2000/2000/2000/2000`、contracts match、zero anomalies/simulation errors，elapsed `568.137814 s`
  （evaluation command `520.077 s`）。descriptive final HV `0.16326709272848938` 不是 gate。
- 两个 expanded plans 除 `20 x 2` / `100 x 20` budget 外 baseline digest、seed、execution policy、
  workflow、strategy 均相同，strategy source SHA-256 均为
  `08E4BE42C4E4A8D377866BF8BC21765A0B776A27C32823290F97210FE086CBA7`；GPSAF `gamma=0.5`
  的 factory/identity/validation/diagnostics 未改变。
- reliable-recording check 直接证明 commit-before-visibility、fatal writer failure、cancel non-entry 与
  shutdown ordering 一致；bounded redundancy check 用 handle composition 删除原同步 orchestration
  duplication。release-marker/component-configuration checks 未命中，四份 recurring auto TODO 保持
  active。进入阶段时 worktree clean，没有 pre-existing user changes。
- architecture、evaluate-manager/recorded-data/tests blueprints、相关 file blueprints、terminology 与
  optimization/config/package user docs 已同步；change record 为
  `dev_doc/change_records/20260831_084158_add-unified-evaluation-handle-lifecycle.md`。

## 完成、归档与自动续跑

统一 handle 已成为同步和未来 program 的唯一 evaluation lifecycle，三 backend 语义、scope、
cleanup 和 durable-result gate 有直接证据，docs/change record/automatic TODO check/commit/
fetch-push 完成后，将本文归档到 `obsolete/todo/`，更新 ledger，自动进入
[Stage 4 surrogate fit/predict](../../toDo/20260830_174610_explicit-optimization-stage-4-surrogate-fit-predict.md)。
