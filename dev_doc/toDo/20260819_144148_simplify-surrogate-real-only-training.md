# 简化 Surrogate：真实仿真与 Field-Balanced 训练

## Execution Order

- 这是手工触发、一次性的第一阶段任务。
- 必须先完整执行本 toDo，完成代码、测试、文档、安装态验收和归档，再执行
  `dev_doc/toDo/20260818_173629_modular-surrogate-optimize-methods.md`。
- 本任务直接在当前 `surrogate/`、`optimize/` 文件布局中建立最终训练语义。后续目录重构
  只能移动和解耦已经简化的实现，不得先迁移再删除 mixup、task-owned query weights、
  相对损失、rank-based forced queries 或旧 checkpoint compatibility。
- 本任务允许有意识地改变现有 surrogate/GPSAF 数值行为。当前 surrogate 在真实问题上的
  效果本身尚不理想；本次优先获得可解释、可调试的干净基线，而不是保持旧启发式的行为
  等价性。

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
- 当前代码仍保留用 deep-ensemble current-cost min/max spread 与训练行回算
  `historical error` 构造 GPSAF noise scale 的 helper、optimizer-facing error 读取和
  interval handoff，但 live alpha/beta survival 只使用 mean predicted costs，并没有调用
  probabilistic knockout/noisy comparison；`historical_error` 只被读取后传入一个未使用的
  参数。因此两者当前已经不改变候选选择，但死路径、额外计算、API 和 diagnostics 仍会
  误导维护者。训练集内误差不是 out-of-sample trust evidence，ensemble spread 也尚未经过
  真实 benchmark 校准；本阶段应删除这些无效 decision surfaces 并用测试固定现有的
  selection invariance，同时保留 ensemble、bootstrap 和 spread 输出本身。
- 本任务只面向新的优化。旧仿真 history、旧 checkpoint 和旧 workspace 配置不属于迁移
  输入；开始新优化时使用空 workspace，或由用户显式执行 `history clear`。

## Goal

- conditional INR 的每个训练 `(X, Y)` 都来自 recorded/campaign-hot 的真实 evaluation
  row 及其真实 rawData，不构造 synthetic parameter/target pairs。
- rawData query 按 field/slot 分层均衡；在每个 field/slot 内对 coordinate 使用 seeded
  cyclic sampling。不得按 task、curve shape、objective window、rawData rank 或 importance
  mask 偏置抽样或 loss。
- 训练 objective 收敛为一个直接、清楚的 pointwise loss。删除额外 relative-loss 与
  mixup-loss 分支；每个 field/slot 先计算 pointwise loss 平均值，再做等权 macro average，
  避免大 field 仅凭 scalar 数量淹没小 field。
- 保留 conditional-INR deep ensemble、真实 row bootstrap、member mean 和 member min/max
  spread 输出；保持并明确 ensemble spread 与训练集内 fit error 不影响 GPSAF candidate
  decision，删除暗示或试图实现这种影响的死路径，等真实 benchmark 后再单独设计 trust
  policy。
- 删除不再需要的配置、task hook、job-template API、checkpoint/state 字段、示例、测试
  和有效文档，不保留静默忽略的 compatibility wrapper。
- 建立职责清楚的 checkpoint schema 和真正的原子发布；不实现旧 checkpoint/history
  reader、转换器或 viewer compatibility。
- 本次验收以数据流、可复现性和结构正确性为门槛，不以旧 surrogate 指标不退化为门槛。
  `20260807 saw` 等快速真实仿真问题留作后续 benchmark 和 surrogate 调试，不阻塞本任务。

## Non-Goals

- 不在本任务中校准或重新启用 ensemble trust decision。
- 不为追平旧结果重新引入 curve/window/rank-specific heuristic。
- 不实现新的 surrogate 模型，不调整 GPSAF/GA/NSGA-III 的其他数值策略。
- 不读取、迁移、显示或恢复旧仿真 history 和旧 checkpoint。

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
  importance-weighted query-sampling 代码。query minibatch 改为 field/slot-balanced
  seeded cyclic sampling。
- 删除基于 rawData rank 的 `_always_include_query_indices()` 或重构后的同类逻辑；scalar、
  curve、surface 不再因为 shape 获得不同的强制采样待遇，而是按所属 field/slot 参与同一
  分层采样 contract。

### 3. Use one direct real-data loss

- 删除 `SURROGATE_INR_RELATIVE_LOSS_WEIGHT` 与
  `SURROGATE_INR_RELATIVE_LOSS_EPS`，以及 normalized-target relative-loss 分支和相应
  history 字段。
- 保留一个标准 pointwise loss，并在 method 内清楚命名。Smooth L1 及其通用数值参数
  可以保留；不要再组合 value/relative/mixup 三种目标或暴露 task-specific loss knobs。
- 每个被采样 field/slot 内先求 pointwise Smooth L1 平均值，再对 field/slot loss 做等权
  macro average。full-query 与 minibatch 路径必须使用相同的 field-balanced 聚合语义。
- 不得从 current cost、objective threshold、field size、rawData rank 或 curve metadata
  生成额外训练权重。

### 4. Replace global query sampling with field-balanced cyclic sampling

- 每个 modeled rawData field/slot 是一个独立 sampling stratum；schema 中没有 numeric
  query 的 slot 不参与。
- 每个 training step 尽可能均匀分配 query budget。若 budget 小于 active slot 数，使用
  seeded round-robin 跨 step 轮换 slot，保证没有 slot 永久缺席。
- 每个 slot 内维护由 seed 决定的 coordinate permutation；按顺序取样，耗尽后使用确定性
  派生 seed 重新洗牌并继续循环。不得每步独立有放回随机抽样后仅依赖概率意义上的覆盖。
- sampler 的 seed 必须由现有优化 seed、generation、ensemble member 和明确的训练阶段
  索引稳定派生；相同输入/config/seed 产生相同 query sequence。
- 测试必须证明每个 slot 在有限、可计算的 step 数内得到覆盖，并覆盖 query budget 小于、
  等于和大于 slot 数，以及 slot size 小于和大于分配 quota 的情况。

### 5. Remove dead uncalibrated GPSAF trust surfaces

- 保留 ensemble member prediction、mean prediction 和 per-objective member min/max spread
  的 API、checkpoint 和 viewer 输出。
- 保留 `SURROGATE_INR_BOOTSTRAP_MEMBERS`、`SURROGATE_INR_BOOTSTRAP_FRACTION` 及真实 row
  bootstrap。bootstrap 不构造 synthetic target，仍符合 real-only contract。
- 删除未接入 live selection 的 probabilistic knockout/noisy comparison/noise-scale helper
  及 ensemble interval half-width handoff；仅改变 spread 数值不得改变本阶段 GPSAF 选择出的
  candidates。
- 删除 optimizer-facing `evaluate_historical_errors()` trust surface 及 GPSAF 对训练行回算
  error 的无效读取、传递和 diagnostics。若训练集 fit error 对 viewer/debug 仍有价值，
  必须改名为明确的
  `training_fit_*` audit，只允许按需诊断，不得作为 uncertainty 或 candidate noise。
- 暂不以其他 heuristic 替代上述 noise scale。未来只有在快速真实 benchmark 上用
  evaluation 前 prediction 与 evaluation 后真值组成 out-of-sample residual，并验证 spread
  与错误/排序关系后，才能另行接回 trust decision。

## Explicitly Preserved Mechanisms

以下机制本身不生成 task/curve-specific training evidence，不应仅因为“简化”而删除：

- rawData-first prediction、current-cost re-evaluation 和 real-evaluation validation；
- schema validation、non-finite sample isolation、constant-slot preservation、target scaling
  floor、finite filling；
- field-balanced seeded cyclic query minibatching、sample batching、query chunking、device
  selection、optimizer、gradient clipping 和 resource controls；
- conditional INR 的 coordinate representation、Fourier features、network capacity 参数；
- deep ensemble 与 bootstrap。bootstrap 只从真实 evaluation rows 有放回抽样，不构造
  synthetic coordinate/target，因此仍满足 real-only training；
- ensemble mean 与 member min/max spread 的 inference、checkpoint 和 viewer 输出；
- inference-time continuous-variable prediction和 viewer off-grid query。它们是推理，不是
  training evidence。

checkpoint 发布不是现有可直接“保留”的行为：当前 JSON/NPZ 直接写入并不原子。本任务
必须实现临时 artifact/manifest 写入、完整验证和 manifest 最后原子 replace 的真实发布点。

如果实现时发现上述保留项中也存在 task/curve-specific 特例，应先提供具体数据流证据，
再决定是否纳入本任务；不要凭名称进行大范围删除。

## Target Training Contract

```text
completed real evaluations
  -> normalized variables + schema-valid real rawData
  -> generic filtering / constant handling / target scaling
  -> real rows or bootstrap resamples of real rows
  -> field/slot-balanced seeded cyclic rawData queries
  -> one pointwise loss, macro-averaged across fields/slots
  -> conditional-INR ensemble + diagnostic member spread
  -> predicted full rawData
  -> current workspace cost
  -> real evaluation validation by optimizer
```

必须可从代码和测试证明：

- model training 没有接收两个真实 rows 的 convex combination 或任何 fabricated target；
- 每个被训练的 target 都能追溯到一个真实 rawData scalar；
- query subsampling 对 field/slot 均衡，并在每个 slot 内以 seeded cyclic 顺序有限覆盖；
- field/slot 的训练贡献不随其 scalar 数量线性放大；
- training code 不导入或调用 task cost-window/importance API；
- objective semantics 只在 predicted rawData 转 current cost 时出现；
- ensemble spread 与训练集内 fit error 不参与 GPSAF candidate comparison、noise 或排序。

## Checkpoint And Fresh-Workspace Policy

- 新 manifest 分开记录：
  - `format_version`：manifest/artifact schema 的显式格式号；
  - `surrogate_method = "conditional_inr"`；
  - `training_policy = "real_field_balanced"`。
- 新 checkpoint 直接写入最终 method namespace，例如
  `SURROGATE_CHECKPOINT_DIR/conditional_inr/generation_*.json`；后续目录重构不得再次改变
  该持久化布局或重新做格式迁移。
- artifacts 不再写 `query_weights`、mixup/relative-loss config、旧 historical trust fields
  或对应 training-history 字段；继续写 bootstrap config 和 ensemble member artifacts。
- writer 先在同一文件系统内写临时 artifact/auxiliary/manifest，验证所有引用、shape 和
  checksum/size 后，以 manifest 最后 `os.replace()` 作为发布点。异常和进程中断不得留下
  可被 discovery 当作完整 checkpoint 的半成品。
- 不实现旧 flat checkpoint、旧 synthetic/weighted checkpoint 或旧 history 的读取、转换、
  自动重训和 viewer compatibility。测试不得保存 legacy fixture。
- 新运行必须使用空 workspace，或由用户显式执行 `yadof history clear --yes` 后开始。
  framework 不得为了迁移而自动删除用户文件。
- workspace 中已删除的 config names 应按未知配置明确失败。task 中遗留的
  `rawdata_importance_weights()` 不再参与 surrogate，且 `yadof check` 应给出可操作诊断。

## Expected Current Files

本任务先在当前布局中实现最终训练语义，预计影响：

- `src/yadof/surrogate/modeling.py`：删除 mixup、relative loss、weighted loss/sampling，
  实现 field-balanced cyclic sampler 与 field macro loss；
- `src/yadof/surrogate/runtime.py`：删除 task importance 获取、rank-based forced queries、
  query-weight state 和 optimizer-facing in-sample historical error；
- `src/yadof/surrogate/types.py`、`checkpoints.py`：精简 train config/state/artifact，保留
  ensemble/bootstrap/spread，并实现最终 schema、method namespace 和 atomic publication；
- `src/yadof/optimize/gpsaf_phases.py`：删除使用 ensemble spread 与训练集 error 的死
  noise/noisy-comparison 路径；
- `src/yadof/config.py`、`src/yadof/job_template/api.py`、
  `job_template/__init__.py`、`job_template/rawdata_contract.py`；
- `examples/hfss-newchoke/job_template/calc_cost.py` 及任何后续新增的 reference workspace；
- optimizer-facing surrogate tests、rawData contract tests、config tests、checkpoint/viewer
  tests和 artifact tests；
- root architecture、terminology、surrogate module/file blueprints、user workflow/cost/config
  docs，以及 surrogate-viewer nested documentation 中受 checkpoint policy 影响的部分。

完成后由后续 modular toDo 移动这些文件；本任务不提前创建完整 method registry 或重构
目录，也不为将来的路径保留双实现/转发层。

## Implementation Plan

### Phase 0 - Characterize The Data Flow

- [ ] 准备固定、可重复的 real-row fixture；不得通过 mixup 或其他插值扩充它。
- [ ] 记录当前 synthetic target、importance weighting、rank-based query inclusion、
  ensemble/historical-error GPSAF noise path 和非原子 checkpoint 写入的准确调用面。
- [ ] 可记录 rawData error、current-cost error、ranking 和训练时间作为调试证据，但不把
  bitwise equality 或指标不退化设为完成门槛。
- [ ] 用失败注入确认当前 checkpoint 哪些写入顺序会暴露半成品，为 atomic publication
  regression test 建立基线。

### Phase 1 - Simplify Conditional-INR Training

- [ ] 先删除 mixup 和 relative-loss 分支，使训练只剩真实 target 的一个 loss。
- [ ] 再删除 query weights、importance sampling 和 forced query indices，实现按 slot
  均衡、slot 内 seeded cyclic 的 query sampler。
- [ ] full-query 和 minibatch 都改为 per-slot pointwise mean + equal macro average；验证结果
  不依赖 slot 展平后的 scalar 数量比例。
- [ ] 精简 method config/state/train history；删除不再使用的函数、参数、imports 和
  defensive fallback，不增加新的调权抽象。
- [ ] 验证 deep-ensemble 每个 member 只看到真实 rows 或其 bootstrap resample。

### Phase 2 - Remove Dead Uncalibrated GPSAF Trust Inputs

- [ ] 保留 ensemble/bootstrap 训练、member prediction、mean 和 min/max spread 输出。
- [ ] 删除没有 live caller 的 noise scale、probabilistic knockout 和 noisy-cost helper，以及
  interval half-width 与训练集内 historical error 的无效读取、传递和 diagnostics。
- [ ] 对相同 predicted costs/seed，在人为改变 spread 和 training-fit audit 后断言 candidate
  selection 不变。
- [ ] 删除 optimizer-facing historical-error API；如 viewer 保留 training-fit audit，重命名
  并明确标注 in-sample、diagnostic-only。

### Phase 3 - Remove Framework And Task Surfaces

- [ ] 删除五个不再支持的 workspace config names 和相应验证/tests/docs：一个 mixup、
  两个 importance、两个 relative-loss 参数；以 source 列表逐一核对，避免漏删。
- [ ] 删除 job-template importance API、helper、exports 和 calc-cost hook；检查 axis-mark
  helpers 是否还有独立职责后决定一并删除。
- [ ] 更新 reference workspaces，使 cost extraction 继续只表达 objective semantics，
  不再定义 surrogate attention callback。
- [ ] 对遗留 config/hook 提供清楚的 check/validation 诊断，不保留 silent no-op。

### Phase 4 - Publish The Final Fresh-Only Checkpoint

- [ ] 写入独立的 `format_version`、`conditional_inr` method ID 与
  `real_field_balanced` training policy，并使用最终 method-namespaced path。
- [ ] 实现临时文件/目录、完整验证和 manifest-last atomic replace；用失败注入证明半成品
  不可发现，重试不会把两个 generation artifact 混合。
- [ ] recovery 只接受当前 schema/method/policy；删除所有 legacy reader/fixture/compatibility
  分支，不访问或改写旧 rawData/history。
- [ ] 更新 viewer discovery/summary/audit 只读取新 checkpoint，继续显示 ensemble member
  与 spread，但不把 spread 命名为 calibrated confidence interval。
- [ ] 证明新 checkpoint recovery、workspace isolation 和 current-cost reinterpretation
  仍然成立。

### Phase 5 - Documentation And Verification

- [ ] 从有效 architecture、terminology、blueprints 和 user docs 删除 mixup/importance/
  relative-loss 作为当前能力的说明；历史 change records 保持不改。
- [ ] 更新 tests，删除只验证旧旋钮存在的断言，新增 real-only/field-balanced-training
  断言。
- [ ] 把测试/文档中的 `uniform` 准确改为 field/slot-balanced seeded cyclic；记录 synthetic
  fixture 指标仅供调试，不因下降而恢复 task-specific heuristic。
- [ ] 文档明确 `20260807 saw` 等真实快速仿真 benchmark 属于后续调试阶段；本任务不启动
  真实 simulator，也不声称完成 ensemble trust calibration。
- [ ] 按开发文档完成 wheel build、force-reinstall、import-origin check、focused tests 和
  完整 pytest，随后更新 change record 并归档本 toDo。

## Verification Plan

- Static/source checks:
  - active `src/`、tests、user docs、architecture、blueprints 和 examples 中不再存在
    `mixup`、rawData importance API/config、`query_weights` 或 relative-loss active path；
  - 历史 `change_records/` 和 `obsolete/` 允许保留事实记录；
  - GPSAF active candidate-decision path 不读取 ensemble spread 或 in-sample fit error；
  - 没有 legacy checkpoint/history reader、转换器或 compatibility fixture。
- Focused behavior tests:
  - trainer inputs 只由真实 rows 或 bootstrap indices 构成；
  - field/slot-balanced sampler 可复现、无 rank/window bias，在有限 step 内覆盖所有 slot
    及其 coordinates；query budget 边界和 cyclic reshuffle 行为明确；
  - per-slot macro loss 不因扩大另一个 slot 的 coordinate 数量而改变前一 slot 的权重；
  - full rawData reconstruction、member intervals、current-cost conversion、scheduler、
    workspace isolation 和 failure handling 保持；
  - bootstrap 只重采样真实 rows；ensemble mean/spread 继续可恢复和查看；修改 spread 或
    training-fit audit 不改变 GPSAF candidate selection；
  - removed config/hook 给出明确诊断；
  - 当前 checkpoint 可恢复；旧格式不可恢复且没有兼容分支；atomic failure injection
    不产生可发现的半成品。
- Acceptance:
  - 可报告 fixture 的 rawData/cost/ranking metrics 与训练时间，但没有旧指标回归门槛；
  - 构建并 force-reinstall wheel，确认 import 来自 `.venv/Lib/site-packages/yadof`；
  - 运行相关 surrogate/job-template/config/viewer tests 和完整 pytest；
  - 不启动真实 simulator 或 HTCondor，除非用户另行明确授权。

## Completion Rule

- conditional INR 的生产训练只使用真实 evaluation rows/targets（bootstrap 仅重采样真实
  rows），只使用一个 pointwise loss，并执行 field/slot-balanced、slot 内 seeded cyclic
  query training 和 per-slot macro loss。
- mixup、relative-loss、task-owned importance、floor/boost、weighted query sampling、
  rank-based forced queries 及其 config/API/state/checkpoint/test/doc surfaces 已从当前实现
  删除，没有 zero-default 死分支、silent compatibility alias 或重复实现。
- deep ensemble、真实-row bootstrap 和 member spread 输出保留；ensemble spread 与训练集内
  fit error 不影响 GPSAF candidate decision，未来 trust calibration 明确留给真实 benchmark。
- 只有带明确 format/method/policy 的新 checkpoint 可恢复，发布真正原子；没有旧 history/
  checkpoint compatibility，用户从空 workspace 或显式 clear 后开始新优化。
- 结构/数据流验收、所有文档和 blueprints、安装态完整 pytest 均通过；真实问题指标不作为
  本任务门槛。本 toDo 随完成变更记录移入 `dev_doc/obsolete/` 后，才开始 modular toDo。
