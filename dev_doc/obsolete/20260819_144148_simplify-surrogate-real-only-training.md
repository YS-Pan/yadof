# 简化 Surrogate：真实仿真与 Field-Balanced 训练

## Status

- 实现于 2026-08-21 完成，并于 2026-08-22 按用户决定归档。
- 完成提交为 `ec05058d2ea227847fc21052682d5b660e26c4e1`。
- 后续结构调整由 active 的
  `../toDo/20260818_173629_modular-surrogate-optimize-methods.md` 和
  `../toDo/20260820_125457_workspace-submit-optimization-composition.md` 共同负责。

## Completed Outcome

- Conditional INR 训练只使用 recorded real evaluation rows，ensemble bootstrap 仅对真实
  rows 做有放回重采样，不再构造 mixup 或其它 synthetic targets。
- 删除 relative-loss、task-owned rawData importance、floor/boost、weighted query
  sampling、rank-based forced queries 及其 config、API、state、checkpoint、example、test
  和有效文档 surfaces。
- Query minibatch 按 numeric rawData field 分层，以 seeded、without-replacement 方式在
  field 内采样；budget 小于 active field 数时使用 deterministic rotation。训练步不足时仅
  延长到完成一次 equal-appearance rotation。
- Pointwise Smooth L1 先在 field 内平均，再对 active fields 做等权 macro average；field
  内 slot/scalar 数量不会增加该 field 的总训练权重。
- 保留 conditional-INR deep ensemble、真实-row bootstrap、member mean 和 member min/max
  spread。删除 GPSAF 中未接入有效选择的 historical fit error、noise scale、probabilistic
  knockout 和 interval handoff；spread 只保留为未校准诊断。
- 非训练态不会成为 optimizer-ready state，也不会使 GPSAF 消费无效 surrogate rows。

## State And Retention Contract

- Checkpoint manifest 显式记录 format、method、training policy、参数 normalization 定义、
  rawData schema/query identity、训练配置、Torch version 和 deterministic semantic
  signature。
- 完整 artifact tree 先在同一文件系统原子发布，unique namespace manifest 最后写入作为
  commit record；root generation JSON 只是 convenience pointer。
- Recovery 只扫描当前 semantic namespace 的 committed manifests。Compatible state 可以
  在策略切换后恢复；incompatible artifacts 和真实 evidence 保留但不 cross-load、不自动
  prune，也不要求 `history clear`。
- Viewer 只读取当前格式的 committed checkpoints，使用 artifact 自身持久化的训练配置，
  并在 generation 选择前过滤参数 normalization 不兼容的 state。

## Verification

- 独立 `gpt-5.6-sol`、`max`、no-context 复核提出的参数定义签名、skipped readiness、有限
  训练步覆盖、retained recovery、viewer 自描述配置、原子测试和 GPSAF spread handoff 七项
  问题均已修正。
- Wheel build、force-reinstall 和 import-origin 验证通过；导入来自 sibling `.venv` 的
  `site-packages/yadof`。
- 69 项 focused tests 通过；完整安装态 pytest 为 258 passed、8 条预期的
  loss-tolerant-recording warnings。
- 有效 architecture、terminology、blueprints、user docs、example 和 nested viewer docs
  已同步；没有启动真实 simulator 或 HTCondor。

## Completion

- 本 handoff 范围内的训练语义、旧 surface 删除、state isolation、原子发布、viewer、文档
  与安装态测试均已完成，没有剩余 active 工作。
- 两份后续结构任务必须保留这里建立的 real-only、rawData-field-balanced、rawData-first、
  real-validation、state-retention 和 checkpoint-atomicity 契约。
