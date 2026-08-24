# 持续检查 reliable recording 一致性

## 背景

- 2026-08-15 的
  [loss-tolerant evaluation recording 变更记录](../../change_records/20260815_165136_unify-loss-tolerant-evaluation-recording.md)
  完成了 common `JobResult` finalizer、owned envelope、campaign session、OS lock、
  immutable ZIP segments、generation task snapshot、hot history 和容错查询等跨模块重构。
- 2026-08-24 的用户需求根据完整 benchmark 证据有意反转了其中的丢失策略：仿真速度
  不再优先于结果完整性。未发布预算满时必须等待 writer；一次 population/evaluation
  返回前必须完成其中全部 segment 的原子发布；writer 无法发布时必须中止 campaign，
  不得继续后续仿真。旧变更记录是历史，不再是当前可靠性契约。
- 当前架构仍跨越 evaluation backend、optimizer、resource calibration、surrogate、
  viewer、history clear 和任务热重载，后续修改可能暴露绕过 backpressure、边界等待或
  失败传播的路径。

## 目标

- 在日常任务自然接触该链路的代码、测试、文档或运行故障时，对已进入范围的证据做一次
  有界一致性检查。
- 保持 fast/local/distributed 共用 finalizer 和 campaign writer；保持 immutable segment、
  tolerant reader、generation snapshot 与 campaign lock 的既有正确性。
- 保证每个 finalized row 在后续 evaluation/generation 开始前已经持久化；无法满足时以
  明确 `RecordingError` 停止 campaign，绝不静默丢弃或把它伪装成个体 `inf`。

## 指导

### 触发与范围

- 仅当正常任务已经读取、修改或诊断上述重构直接相关的实现、测试或文档时，检查当前
  diff、直接调用方/消费者和相邻测试。不要为本 toDo 单独扫描整个仓库、重放真实
  simulator 或启动无关大型重构。
- 客观匹配包括：backend 绕过 common finalizer；full queue 拒绝或丢弃 envelope；
  population/evaluation 在 pending 或 in-flight evidence 存在时返回；write failure、writer
  death 或 oversized envelope 被吞掉后继续仿真；shutdown 放弃尾部结果；campaign
  lock/writer 生命周期泄漏；旧 JSONL/global-ZIP 路径重新成为生产入口；segment 被覆盖；
  以及当前文档、blueprint、公开 API、wheel 内容和实现互相矛盾。
- 普通性能设想或仅凭代码外观产生的怀疑不构成触发。无法证明具体不一致时，不要扩大
  当前任务。

### 报告与修复

- 发现匹配时，先说明问题、影响、复现证据和违反的可靠记录契约，再实施最小完整修复。
- 保留有界内存：count/byte budget 应通过 backpressure 限制 pending ownership；不要用
  无界队列换取不丢失。micro-batch 与后台单 writer 可以保留，但 generation/evaluation
  boundary 必须等待全部发布。
- 同一个 retained batch 的临时写失败可按配置次数重试。尝试耗尽、oversized envelope
  或 unexpected writer death 必须唤醒所有等待者并中止 campaign；不得 drop-and-continue。
- simulator、task rawData、current cost 等个体失败仍按原契约形成正确宽度的 `inf` 和
  durable diagnostic row。腐坏的历史 segment 仍由 tolerant reader 隔离，不能把只读
  查询故障反向变成运行中 writer 的数据丢弃策略。
- 行为或契约变化时同步修改直接测试、architecture、blueprint、terminology、user
  documentation 和 change record，并执行 installed-wheel 验收。

## Completion Rule（完成规则）

- 对一次自然触发而言：已报告有证据的一致性问题，完成当前权限与范围内的最小完整
  修复，并通过与风险相称的测试；若受外部授权阻塞，则明确报告阻塞与后续决定。
- 本 toDo 是持续性的；一次问题修复后仍保留在 `toDo/auto/`。

## Obsolete Rule（过期规则）

persistent
