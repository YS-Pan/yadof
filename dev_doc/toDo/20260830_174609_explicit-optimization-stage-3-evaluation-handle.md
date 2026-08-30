# 显式 optimization 重构阶段 3：统一 EvaluationBatch 与 EvaluationHandle 生命周期

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

## 完成、归档与自动续跑

统一 handle 已成为同步和未来 program 的唯一 evaluation lifecycle，三 backend 语义、scope、
cleanup 和 durable-result gate 有直接证据，docs/change record/automatic TODO check/commit/
fetch-push 完成后，将本文归档到 `obsolete/todo/`，更新 ledger，自动进入
[Stage 4 surrogate fit/predict](20260830_174610_explicit-optimization-stage-4-surrogate-fit-predict.md)。
