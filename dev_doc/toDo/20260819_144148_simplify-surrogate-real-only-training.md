# 简化 Surrogate：只用真实仿真结果进行均匀训练

## Execution Dependency

- 这是手工触发、一次性的后续任务。
- 必须先完整执行
  `dev_doc/toDo/20260818_173629_modular-surrogate-optimize-methods.md`，确认其中的代码、
  测试、文档、安装态验收和归档条件全部满足，并把该文件移入 `dev_doc/obsolete/`，
  才能执行本 toDo。
- 现在提前记录本任务，是为了让前置目录重构不要把 mixup、task-owned query weights、
  相对损失或曲线形状启发式提升为所有 surrogate 方法必须实现的公共 contract。
  前置重构可以为保持当时行为而把它们暂时放进 `conditional_inr/`，但不能把它们写进
  父包 `contracts.py`、`training_data.py`、registry 或 method capability 的稳定接口。
- 前置重构中的 characterization tests 可以临时冻结这些行为以保证搬迁安全，但这些
  tests 不是永久兼容承诺。本任务负责在结构稳定后有意识地删除对应行为和断言。

## Context

- 当前 conditional INR 不只拟合真实仿真 rawData，还叠加了多层人为训练策略：
  mixup 合成变量/target、task-owned rawData importance masks、`floor/boost`、加权
  full-query loss、按权重进行的 query sampling、低维 rawData slot 强制入样，以及额外
  relative-loss 分支。
- 这些机制最初用于移动共振、目标窗口、不同 rawData shape 和大矩阵训练，但也让算法
  依赖具体曲线/窗口语义，增加 workspace 配置、task hook、checkpoint 字段、测试和文档，
  并使预测问题难以归因。
- 用户希望 surrogate 更简洁、优雅：训练 evidence 只来自已经完成的真实仿真结果，
  不再用人为线性插值样本，也不根据某条曲线或 objective window 定制训练注意力。
- yadof 的 rawData-first 契约不变。surrogate 仍预测完整兼容 rawData，再通过当前
  `calc_cost.py` 计算 objective；cost window 只决定 cost，不再反向改变模型训练分布。

## Goal

- conditional INR 的每个训练 `(X, Y)` 都来自 recorded/campaign-hot 的真实 evaluation
  row 及其真实 rawData，不构造 synthetic parameter/target pairs。
- 所有进入模型的 rawData numeric query 采用同一训练语义；大 rawData 可做 uniform
  stochastic query minibatching，但不能按 task、curve shape、objective window、rawData
  rank 或 importance mask 偏置抽样或 loss。
- 训练 objective 收敛为一个直接、清楚的 pointwise loss。删除额外 relative-loss 与
  mixup-loss 分支，避免多个带权 loss 项和对应调参。
- 删除不再需要的配置、task hook、job-template API、checkpoint/state 字段、示例、测试
  和有效文档，不保留静默忽略的 compatibility wrapper。
- 用固定真实 train/holdout 数据记录简化前后的 rawData error、current-cost error 和
  candidate ranking 结果。比较用于说明取舍，而不是在结果变差时自动把旧启发式加回去。

## Required Removals

### 1. Remove mixup completely

- 删除 `SURROGATE_INR_MIXUP_WEIGHT` 默认值、验证和用户配置入口。
- 删除 `INRTrainConfig.mixup_weight`、mixup pair/`lambda` 生成、synthetic `x_mix`/
  `y_mix`、mixup loss、coefficient normalization 和 mixup training-history 字段。
- 新训练和恢复路径都不能调用或重建 mixup。不要把默认值改成零后保留死分支。

### 2. Remove curve/window-specific importance training

- 删除 workspace `calc_cost.py:rawdata_importance_weights()` surrogate hook。
- 删除 `SURROGATE_RAWDATA_IMPORTANCE_FLOOR`、
  `SURROGATE_RAWDATA_IMPORTANCE_BOOST`。
- 删除 `job_template.api.get_rawdata_importance_weights()`、
  `calculate_rawdata_importance_weights()` 及 package exports。
- 删除 `build_rawdata_importance_weights()`；对 `mark_axis_range()`、
  `mark_axis_points()` 做直接调用检查，如果 importance 机制移除后没有独立 cost/rawData
  contract 调用方，也一起删除，不能仅为旧示例保留。
- 删除 conditional-INR state/checkpoint 中的 `query_weights`，删除 weighted loss 和
  importance-weighted query-sampling 代码。query minibatch 改为 uniform sampling。
- 删除基于 rawData rank 的 `_always_include_query_indices()` 或重构后的同类逻辑；scalar、
  curve、surface 不再因为 shape 获得不同的强制采样待遇。

### 3. Use one direct real-data loss

- 删除 `SURROGATE_INR_RELATIVE_LOSS_WEIGHT` 与
  `SURROGATE_INR_RELATIVE_LOSS_EPS`，以及 normalized-target relative-loss 分支和相应
  history 字段。
- 保留一个标准 pointwise loss，并在 method 内清楚命名。Smooth L1 及其通用数值参数
  可以保留；不要再组合 value/relative/mixup 三种目标或暴露 task-specific loss knobs。
- loss 在 uniform full-query 或 uniform query minibatch 上计算。不得从 current cost、
  objective threshold 或 curve metadata 生成训练权重。

## Explicitly Preserved Mechanisms

以下机制本身不生成 task/curve-specific training evidence，不应仅因为“简化”而删除：

- rawData-first prediction、current-cost re-evaluation 和 real-evaluation validation；
- schema validation、non-finite sample isolation、constant-slot preservation、target scaling
  floor、finite filling和 checkpoint atomic publication；
- uniform query minibatching、sample batching、query chunking、device selection、optimizer、
  gradient clipping和 resource controls；
- conditional INR 的 coordinate representation、Fourier features、network capacity 参数；
- deep ensemble 与 bootstrap。bootstrap 只从真实 evaluation rows 有放回抽样，不构造
  synthetic coordinate/target，因此仍满足 real-only training；
- inference-time continuous-variable prediction和 viewer off-grid query。它们是推理，不是
  training evidence。

如果实现时发现上述保留项中也存在 task/curve-specific 特例，应先提供具体数据流证据，
再决定是否纳入本任务；不要凭名称进行大范围删除。

## Target Training Contract

```text
completed real evaluations
  -> normalized variables + schema-valid real rawData
  -> generic filtering / constant handling / target scaling
  -> real rows + uniformly selected rawData queries
  -> one pointwise training loss
  -> conditional-INR ensemble
  -> predicted full rawData
  -> current workspace cost
  -> real evaluation validation by optimizer
```

必须可从代码和测试证明：

- model training 没有接收两个真实 rows 的 convex combination 或任何 fabricated target；
- 每个被训练的 target 都能追溯到一个真实 rawData scalar；
- query subsampling 在全部 modeled scalar positions 上均匀进行；
- training code 不导入或调用 task cost-window/importance API；
- objective semantics 只在 predicted rawData 转 current cost 时出现。

## Checkpoint And Existing Workspace Policy

- 新 checkpoint manifest 明确记录一个职责型 training policy 名称，例如
  `real_uniform`，不要使用 `v2`、`new` 等版本过渡标签。
- 新 artifacts 不再写 `query_weights`、mixup/relative-loss config 或对应 history。
- 旧 checkpoint 是 derived state，真实 recorded rawData 才是 source truth。active
  optimizer/runtime 不得把旧 mixup/weighted-policy checkpoint 当成符合新 policy 的当前
  model；应把它诊断为 training-policy incompatible，并从真实 history 重新训练。
- 不自动删除、改写或伪装升级旧 checkpoint。`history clear` 的现有显式删除语义不变。
- surrogate viewer 至少应能在 summary 中说明旧 checkpoint 的 policy/incompatibility。
  是否继续提供旧 checkpoint inference 只取决于能否在不保留旧训练分支的情况下复用
  相同网络结构；不能为了 viewer 恢复 mixup/importance training code。
- workspace 中已删除的 config names 应按未知配置明确失败，促使用户清理；不要接受后
  静默忽略。task 中遗留的 `rawdata_importance_weights()` 不再参与 surrogate，且
  `yadof check` 应给出可操作诊断，避免用户误以为它仍有效。

## Expected Post-Refactor Files

本任务在前置模块化 toDo 完成后，优先检查其最终文件而不是机械套用当前路径。预计影响：

- `src/yadof/surrogate/conditional_inr/modeling.py`：删除 mixup、relative loss、weighted
  loss/sampling；
- `src/yadof/surrogate/conditional_inr/backend.py` 与 `data.py`：删除 task importance
  获取、rank-based forced queries 和 query-weight state；
- `src/yadof/surrogate/conditional_inr/types.py`、`checkpoints.py`：精简 train config、
  state、artifact 和 recovery policy；
- `src/yadof/surrogate/contracts.py`、`training_data.py`：确认没有把 augmentation、
  task weights 或 curve importance 变成公共 method contract；
- `src/yadof/config.py`、`src/yadof/job_template/api.py`、
  `job_template/__init__.py`、`job_template/rawdata_contract.py`；
- `examples/hfss-newchoke/job_template/calc_cost.py` 及任何后续新增的 reference workspace；
- optimizer-facing surrogate tests、rawData contract tests、config tests、checkpoint/viewer
  tests和 artifact tests；
- root architecture、terminology、surrogate module/file blueprints、user workflow/cost/config
  docs，以及 surrogate-viewer nested documentation 中受 checkpoint policy 影响的部分。

先使用前置重构后的 method registry/blueprint 确认真实路径和调用方。不要重新创建旧顶层
`surrogate/runtime.py` 或 `modeling.py` 兼容层来完成本任务。

## Implementation Plan

### Phase 0 - Establish A Real-Only Baseline

- [ ] 准备固定、可重复的真实 evaluation train/holdout fixture；不得通过 mixup 或其他
  插值扩充它。
- [ ] 记录现有实现的 rawData error、current-cost error、ranking 和训练时间，保存为本次
  变更的比较证据，不把旧 prediction bitwise equality 设为验收条件。
- [ ] 增加 structural tests，捕获所有 synthetic target、importance weighting、
  rank-based query inclusion 和多 loss 分支，确保后续删除是可证明的。

### Phase 1 - Simplify Conditional-INR Training

- [ ] 先删除 mixup 和 relative-loss 分支，使训练只剩真实 target 的一个 loss。
- [ ] 再删除 query weights、importance sampling 和 forced query indices，将大字段采样
  改为 seeded uniform sampling。
- [ ] 精简 method config/state/train history；删除不再使用的函数、参数、imports 和
  defensive fallback，不增加新的调权抽象。
- [ ] 验证 deep-ensemble 每个 member 只看到真实 rows 或其 bootstrap resample。

### Phase 2 - Remove Framework And Task Surfaces

- [ ] 删除五个不再支持的 workspace config names 和相应验证/tests/docs：一个 mixup、
  两个 importance、两个 relative-loss 参数；以 source 列表逐一核对，避免漏删。
- [ ] 删除 job-template importance API、helper、exports 和 calc-cost hook；检查 axis-mark
  helpers 是否还有独立职责后决定一并删除。
- [ ] 更新 reference workspaces，使 cost extraction 继续只表达 objective semantics，
  不再定义 surrogate attention callback。
- [ ] 对遗留 config/hook 提供清楚的 check/validation 诊断，不保留 silent no-op。

### Phase 3 - Checkpoint, Viewer, And Recovery

- [ ] 写入新的 `real_uniform` training policy 和精简 artifact。
- [ ] active recovery 拒绝旧 synthetic/weighted training policy，并从真实 recorded data
  重新训练；验证 rawData/history 没有被改写。
- [ ] 更新 viewer discovery/summary/audit capability，使 incompatibility 可见且不会错误
  地把旧 checkpoint 标记成新 policy。
- [ ] 证明新 checkpoint recovery、workspace/method isolation 和 current-cost
  reinterpretation 仍然成立。

### Phase 4 - Documentation And Verification

- [ ] 从有效 architecture、terminology、blueprints 和 user docs 删除 mixup/importance/
  relative-loss 作为当前能力的说明；历史 change records 保持不改。
- [ ] 更新 tests，删除只验证旧旋钮存在的断言，新增 real-only/uniform-training 断言。
- [ ] 运行 fixed holdout 比较并记录结果；即使简化后的某项 metric 下降，也先报告真实
  tradeoff，不通过恢复 task-specific heuristic 来掩盖。
- [ ] 按开发文档完成 wheel build、force-reinstall、import-origin check、focused tests 和
  完整 pytest，随后更新 change record 并归档本 toDo。

## Verification Plan

- Static/source checks:
  - active `src/`、tests、user docs、architecture、blueprints 和 examples 中不再存在
    `mixup`、rawData importance API/config、`query_weights` 或 relative-loss active path；
  - 历史 `change_records/` 和 `obsolete/` 允许保留事实记录；
  - surrogate parent common contracts 不含任何 task/curve training-adjustment field。
- Focused behavior tests:
  - trainer inputs 只由真实 rows 或 bootstrap indices 构成；
  - uniform query minibatch 可复现、无 rank/window bias，并最终覆盖不同 rawData shapes；
  - full rawData reconstruction、member intervals、current-cost conversion、scheduler、
    workspace/method isolation 和 failure handling 保持；
  - removed config/hook 给出明确诊断；
  - old-policy checkpoint active recovery 被拒绝并触发 real-history retraining；新 policy
    checkpoint 可恢复；viewer 不误报 policy。
- Acceptance:
  - 对同一真实 holdout 报告简化前后 rawData/cost/ranking metrics 与训练时间；
  - 构建并 force-reinstall wheel，确认 import 来自 `.venv/Lib/site-packages/yadof`；
  - 运行相关 surrogate/job-template/config/viewer tests 和完整 pytest；
  - 不启动真实 simulator 或 HTCondor，除非用户另行明确授权。

## Completion Rule

- 前置 modular-surrogate/optimize toDo 已完整完成并归档。
- conditional INR 的生产训练只使用真实 evaluation rows/targets（bootstrap 仅重采样真实
  rows），只使用一个 pointwise loss，并对 modeled rawData queries 进行 uniform 训练。
- mixup、relative-loss、task-owned importance、floor/boost、weighted query sampling、
  rank-based forced queries 及其 config/API/state/checkpoint/test/doc surfaces 已从当前实现
  删除，没有 zero-default 死分支、silent compatibility alias 或重复实现。
- 新/旧 checkpoint policy 行为明确：新 checkpoint 可恢复，旧 synthetic/weighted model
  不会被 active optimizer 当作新 policy 使用，真实 recorded rawData 保持不变并可重训。
- fixed real holdout 比较已经记录，所有文档和 blueprints 反映新 contract，安装态完整
  pytest 通过；本 toDo 随完成变更记录一起移入 `dev_doc/obsolete/`。
