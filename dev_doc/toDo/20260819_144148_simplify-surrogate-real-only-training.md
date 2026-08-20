# 简化 Surrogate：真实仿真与 Field-Balanced 训练

## Execution Order

- 这是手工触发、一次性的第一阶段任务。
- 本 toDo 可以分阶段实现；删除确定无效的 GPSAF trust surface、建立 atomic publication、
  准备 benchmark 等安全工作不必等待全部 benchmark 就绪。但简化后的训练不得成为 production
  baseline，本 toDo 也不得归档，直到用户确认真实 benchmark suite、metrics、thresholds 并
  通过 gate。两份协调 toDo 只能在这个 production gate 之后完成最终迁移与验收。
- 本任务直接在当前 `surrogate/`、`optimize/` 文件布局中建立最终训练语义。后续目录重构
  只能移动和解耦已经简化的实现，不得先迁移再删除 mixup、task-owned query weights、
  相对损失、rank-based forced queries 或旧 checkpoint compatibility。
- 本任务也在当前 workspace 布局中删除
  `job_template/calc_cost.py:rawdata_importance_weights()`。后续协调任务再把精简后的 cost
  policy 移到 `submit/`，但 canonical `parameters_constraints.py` 继续留在 worker-facing
  `job_template/`；不得为了预适配新路径引入双位置 loader、compatibility wrapper 或重复
  hook removal。
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
- recorded variables/rawData 是长期真实 evidence，算法切换或本次训练策略升级都不得自动
  删除。旧 surrogate checkpoint/权重也保留在 inactive run/component namespace；只有语义
  兼容的 active strategy 可恢复它们，否则从保留的真实 evidence cold retrain。无需空
  workspace，也不要求 `history clear`。
- 简化同时遵守 library-first 原则：标准 tensor/loss/optimizer/serialization 行为直接使用
  PyTorch/NumPy 等成熟实现；yadof 只实现 field-level sampling、rawData reconstruction、
  campaign adaptation 和 checkpoint provenance 等自身契约。后续 modular toDo 再审计并
  收缩 package 边界，本任务不能新建自有通用 trainer/surrogate framework。

## Goal

- conditional INR 的每个训练 `(X, Y)` 都来自 recorded/campaign-hot 的真实 evaluation
  row 及其真实 rawData，不构造 synthetic parameter/target pairs。这是不可让步的设计原则；
  benchmark 失败只能推动 real-only 方案继续迭代，不能恢复 synthetic target。
- 每个 numeric rawData field 获得相同总 sampling/loss 权重。用户必须保证 objective-irrelevant
  numeric data 不写入 rawData；yadof 不根据 task、curve shape、objective window、field size、
  rawData rank 或 importance mask 猜测字段价值。
- 训练 objective 收敛为一个直接、清楚的 pointwise loss。删除额外 relative-loss 与
  mixup-loss 分支；每个 field 内对其全部被采样 scalar/slot 的 pointwise loss 求平均，再对
  field loss 做等权 macro average。slot 只是 field 内坐标，不能各自获得一份 field 权重。
- 保留 conditional-INR deep ensemble、真实 row bootstrap、member mean 和 member min/max
  spread 输出；保持并明确 ensemble spread 与训练集内 fit error 不影响 GPSAF candidate
  decision，删除暗示或试图实现这种影响的死路径，等真实 benchmark 后再单独设计 trust
  policy。
- 删除不再需要的配置、task hook、job-template API、checkpoint/state 字段、示例、测试
  和有效文档，不保留静默忽略的 compatibility wrapper。
- 删除自写但可由当前受支持成熟 package 等价承担的通用数值 helper；保留的自写训练逻辑
  必须能指向 yadof-specific field/rawData/campaign 语义，而不是重复标准算法。
- 建立职责清楚的 checkpoint schema 和真正的原子发布；不实现旧 checkpoint/history
  reader、转换器或 viewer compatibility。
- production 验收必须通过用户确认的真实 benchmark gate。现有 SAW/`test_com` 等问题可先
  用于开发，但用户尚未准备好全部 benchmark，因此它们不是最终 suite 的默认替代。gate
  至少覆盖 rawData/objective prediction error、必要时的 ranking、训练时间/资源，以及固定
  real-evaluation budget 下的 optimization efficiency；metrics、thresholds 与可接受 tradeoff
  必须由用户在实施时确认，不能由开发者事后挑选。

## Non-Goals

- 不在本任务中校准或重新启用 ensemble trust decision。
- 不为追平旧结果重新引入 curve/window/rank-specific heuristic。
- 不实现新的 surrogate 模型，不调整 GPSAF/GA/NSGA-III 的其他数值策略。
- 不在本阶段选择新的 backend、升级依赖或完成 package adapter 重构；这些决策由后续协调
  toDo 的 dependency-reuse audit 处理。本阶段仍不得新增可被成熟 primitive 替代的代码。
- 不为旧 checkpoint 实现格式兼容 reader/converter，也不保证未来版本能读取所有 inactive
  artifacts；但不得自动删除旧 history、权重或 checkpoint。

## Required Removals

### 1. Remove mixup completely

- 删除 `SURROGATE_INR_MIXUP_WEIGHT` 默认值、验证和用户配置入口。
- 删除 `INRTrainConfig.mixup_weight`、mixup pair/`lambda` 生成、synthetic `x_mix`/
  `y_mix`、mixup loss、coefficient normalization 和 mixup training-history 字段。
- 新训练和恢复路径都不能调用或重建 mixup。不要把默认值改成零后保留死分支。

### 2. Remove curve/window-specific importance training

- 删除当前 workspace
  `job_template/calc_cost.py:rawdata_importance_weights()` surrogate hook；后续新标准中的
  `submit/calc_cost.py` 也不得重新提供或消费该 hook。
- 删除 `SURROGATE_RAWDATA_IMPORTANCE_FLOOR`、
  `SURROGATE_RAWDATA_IMPORTANCE_BOOST`。
- 删除 `job_template.api.get_rawdata_importance_weights()`、
  `calculate_rawdata_importance_weights()` 及 package exports。
- 删除 `build_rawdata_importance_weights()`；对 `mark_axis_range()`、
  `mark_axis_points()` 做直接调用检查，如果 importance 机制移除后没有独立 cost/rawData
  contract 调用方，也一起删除，不能仅为旧示例保留。
- 删除 conditional-INR state/checkpoint 中的 `query_weights`，删除 weighted loss 和
  importance-weighted query-sampling 代码。query minibatch 改为 field-balanced sampling。
- 删除基于 rawData rank 的 `_always_include_query_indices()` 或重构后的同类逻辑；scalar、
  curve、surface 不再因为 shape 获得不同的强制采样待遇，而是按所属 field 参与同一
  sampling contract。

### 3. Use one direct real-data loss

- 删除 `SURROGATE_INR_RELATIVE_LOSS_WEIGHT` 与
  `SURROGATE_INR_RELATIVE_LOSS_EPS`，以及 normalized-target relative-loss 分支和相应
  history 字段。
- 保留一个标准 pointwise loss，并在 method 内清楚命名。Smooth L1 及其通用数值参数
  可以保留，并应直接调用 PyTorch 的成熟实现；不要复制 loss 数学，也不要再组合
  value/relative/mixup 三种目标或暴露 task-specific loss knobs。
- 每个被采样 field 内先对其全部被采样 scalar/slot 求 pointwise Smooth L1 平均值，再对
  field loss 做等权 macro average。full-query 与 minibatch 路径必须使用相同语义；增加
  field 内 slot 数不得增加该 field 的总权重。
- 不得从 current cost、objective threshold、field size、rawData rank 或 curve metadata
  生成额外训练权重。

### 4. Replace global query sampling with field-balanced sampling

- 每个 modeled numeric rawData field 是一个 sampling stratum；field 内的 scalar/slot/coordinate
  共享该 field 的总预算。schema 中没有 numeric query 的 field 不参与。
- 每个 training step 尽可能均匀分配 field budget。若 budget 小于 active field 数，使用由
  seed 决定的 shuffled rotation 跨 step 轮换 field，保证没有 field 永久缺席。
- field 内使用 NumPy/PyTorch 的标准、seeded、without-replacement sampling；需要继续覆盖时
  再生成确定性 permutation。不要预建持久 per-slot cyclic scheduler 或自有随机算法；只有
  真实 benchmark 证明简单方案不足时才增加状态。
- sampler seed 由现有优化 seed、generation、ensemble member 和明确的训练阶段索引稳定
  派生；相同输入/config/seed 产生相同 sequence。
- 测试必须证明 field 总预算等权、field 内 slot 数不放大总权重、sampling 可复现且无
  rank/window bias，并覆盖 budget 小于、等于和大于 active field 数的情况。

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
- field-balanced seeded query minibatching、sample batching、query chunking、device
  selection、optimizer、gradient clipping 和 resource controls；其中通用 tensor/optimizer/
  clipping primitives 继续由 PyTorch 提供，yadof 只拥有 field-balanced policy 与边界 glue；
- conditional INR 的 coordinate representation、Fourier features、network capacity 参数；
- deep ensemble 与 bootstrap。bootstrap 只从真实 evaluation rows 有放回抽样，不构造
  synthetic coordinate/target，因此仍满足 real-only training；
- ensemble mean 与 member min/max spread 的 inference、checkpoint 和 viewer 输出；
- inference-time continuous-variable prediction和 viewer off-grid query。它们是推理，不是
  training evidence。

checkpoint 发布不是现有可直接“保留”的行为：当前 JSON/NPZ 直接写入并不原子。本任务
必须建立一个经 Windows interruption/failure injection 验证的 publication boundary。可以在
实测后选择 manifest-last、commit marker 或同文件系统 temporary-directory rename；checksum
只在实际 failure model 需要时增加，不能把某个未经验证的机制预先写死为正确答案。

如果实现时发现上述保留项中也存在 task/curve-specific 特例，应先提供具体数据流证据，
再决定是否纳入本任务；不要凭名称进行大范围删除。

## Target Training Contract

```text
completed real evaluations
  -> normalized variables + schema-valid real rawData
  -> generic filtering / constant handling / target scaling
  -> real rows or bootstrap resamples of real rows
  -> equal field budgets + seeded within-field rawData queries
  -> one pointwise loss, averaged within each field, then macro-averaged across fields
  -> conditional-INR ensemble + diagnostic member spread
  -> predicted full rawData
  -> current workspace cost
  -> real evaluation validation by optimizer
```

必须可从代码和测试证明：

- model training 没有接收两个真实 rows 的 convex combination 或任何 fabricated target；
- 每个被训练的 target 都能追溯到一个真实 rawData scalar；
- 所有 numeric rawData fields 以相同认真程度建模；objective-irrelevant numeric data 由用户
  保证不进入 rawData；
- query subsampling 对 field 均衡，并在 field 内使用可复现的无放回抽样；
- field 的训练贡献不随其 scalar/slot 数量线性放大；
- training code 不导入或调用 task cost-window/importance API；
- objective semantics 只在 predicted rawData 转 current cost 时出现；
- ensemble spread 与训练集内 fit error 不参与 GPSAF candidate comparison、noise 或排序。

## Checkpoint, Retention, And Discovery Policy

- 新 manifest 分开记录：
  - `format_version`：manifest/artifact schema 的显式格式号；
  - `surrogate_method = "conditional_inr"`；
  - `training_policy = "real_field_balanced"`；
  - deterministic semantic state signature 与 run/component namespace。
- 新 checkpoint 写入 active run/component namespace；具体目录布局由 workspace composition
  toDo 的最终 state design 决定，本任务不写死一个会妨碍算法切换的 method-only path。
- artifacts 不再写 `query_weights`、mixup/relative-loss config、旧 historical trust fields
  或对应 training-history 字段；继续写 bootstrap config 和 ensemble member artifacts。
- writer 使用经 Windows failure injection 选定的 atomic publication protocol。异常和进程
  中断不得留下可被 discovery 当作完整 checkpoint 的半成品，也不得让 active generation
  混合读取两个 publication。
- 不实现旧 flat checkpoint、旧 synthetic/weighted checkpoint 或旧 history 的读取、转换、
  viewer compatibility。测试无需保存 legacy fixture；这不授权删除磁盘上的旧 artifact。
- algorithm/policy switch 会停止或等待 pending training、释放 active in-memory state，再激活
  新 namespace。旧 conditional-INR weights/checkpoints 保留为 inactive；active discovery
  只能读取匹配 semantic signature 的 state，绝不能因目录扫描加载不兼容旧权重。
- compatible return 可以恢复 retained state；不兼容 return 必须用保留的真实 evaluation
  evidence cold retrain，同时留下旧 artifact。系统不自动 prune；`history clear`/state prune
  均为独立显式破坏性操作，不是开始新优化或切换算法的前置条件。
- retention 不等于永久格式兼容承诺；未来版本可以拒绝读取旧 artifact，但仍不得自动删除。
- workspace 中已删除的 config names 应按未知配置明确失败。task 中遗留的
  `rawdata_importance_weights()` 不再参与 surrogate，且 `yadof check` 应给出可操作诊断。

## Expected Current Files

本任务先在当前布局中实现最终训练语义，预计影响：

- `src/yadof/surrogate/modeling.py`：删除 mixup、relative loss、weighted loss/sampling，
  实现 field-balanced sampler 与 field macro loss；
- `src/yadof/surrogate/runtime.py`：删除 task importance 获取、rank-based forced queries、
  query-weight state 和 optimizer-facing in-sample historical error；
- `src/yadof/surrogate/types.py`、`checkpoints.py`：精简 train config/state/artifact，保留
  ensemble/bootstrap/spread，并实现最终 schema、method namespace 和 atomic publication；
- `src/yadof/optimize/gpsaf_phases.py`：删除使用 ensemble spread 与训练集 error 的死
  noise/noisy-comparison 路径；
- `src/yadof/config.py`、`src/yadof/job_template/api.py`、
  `job_template/__init__.py`、`job_template/rawdata_contract.py`；
- 当前布局的 `examples/hfss-newchoke/job_template/calc_cost.py` 及任何后续新增的 reference
  workspace；后续 workspace 标准任务负责把已经精简的文件迁移到 `submit/calc_cost.py`；
- optimizer-facing surrogate tests、rawData contract tests、config tests、checkpoint/viewer
  tests和 artifact tests；
- root architecture、terminology、surrogate module/file blueprints、user workflow/cost/config
  docs，以及 surrogate-viewer nested documentation 中受 checkpoint policy 影响的部分。

完成后由 workspace/composition 与 modular 两份协调 toDo 移动这些文件并建立 component
boundary；本任务不提前创建完整 method registry、workspace plan loader 或新目录，也不为
将来的路径保留双实现/转发层。

## Implementation Plan

### Phase 0 - Characterize The Data Flow

- [ ] 准备固定、可重复的 real-row fixture；不得通过 mixup 或其他插值扩充它。
- [ ] 记录当前 synthetic target、importance weighting、rank-based query inclusion、
  ensemble/historical-error GPSAF noise path 和非原子 checkpoint 写入的准确调用面。
- [ ] 与用户确认 production benchmark suite、metrics、thresholds 和 tradeoff。当前 SAW、
  `test_com` 及其它已就绪问题只作为候选；用户尚未准备好全部 benchmark，不能擅自把现有
  集合当作完整 gate。
- [ ] benchmark 至少记录 rawData/objective prediction error、必要时的 ranking、训练时间/
  资源，以及固定真实 evaluation budget 下的 optimization efficiency；bitwise equality 不是
  目标，但用户确认的 thresholds 是完成门槛。
- [ ] 用失败注入确认当前 checkpoint 哪些写入顺序会暴露半成品，为 atomic publication
  regression test 建立基线。

### Phase 1 - Simplify Conditional-INR Training

- [ ] 先删除 mixup 和 relative-loss 分支，使训练只剩真实 target 的一个 loss。
- [ ] 再删除 query weights、importance sampling 和 forced query indices，实现 equal field
  budget + seeded within-field without-replacement sampler；budget 小于 field 数时跨 step 做
  deterministic shuffled rotation。
- [ ] full-query 和 minibatch 都改为 per-field pointwise mean + equal macro average；验证
  field 内增加 slot/scalar 数不放大该 field 的总权重。
- [ ] 精简 method config/state/train history；删除不再使用的函数、参数、imports 和
  defensive fallback，不增加新的调权抽象。
- [ ] 审计本阶段触及的 numerical helpers：标准 loss/optimizer/tensor/serialization 直接
  委托受支持 package；只为 field/rawData/campaign-specific 语义保留自写代码并在完成
  change record 中说明边界。
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

### Phase 4 - Publish And Isolate Retained State

- [ ] 写入独立的 `format_version`、`conditional_inr` method ID 与
  `real_field_balanced` training policy、semantic state signature 与 run/component namespace。
- [ ] 在 Windows 上比较适用的 manifest-last、commit-marker、temporary-directory rename 等
  方案，选取并实现一个经过 interruption/failure injection 验证的 publication boundary；
  证明半成品不可发现，重试不会混合两个 generation artifact。
- [ ] recovery 只接受当前 schema/method/policy；删除所有 legacy reader/fixture/compatibility
  分支，不访问或改写旧 rawData/history。
- [ ] 更新 viewer discovery/summary/audit 只读取新 checkpoint，继续显示 ensemble member
  与 spread，但不把 spread 命名为 calibrated confidence interval。
- [ ] 证明算法切换保留旧 weights/artifacts 和真实 evidence；active discovery 不 cross-load；
  compatible return 可恢复，不兼容 return 从 retained evidence cold retrain；无自动 prune。

### Phase 5 - Documentation And Verification

- [ ] 从有效 architecture、terminology、blueprints 和 user docs 删除 mixup/importance/
  relative-loss 作为当前能力的说明；历史 change records 保持不改。
- [ ] 更新 tests，删除只验证旧旋钮存在的断言，新增 real-only/field-balanced-training
  断言。
- [ ] 把测试/文档中的 `uniform` 准确改为 field-balanced seeded sampling；synthetic
  fixture 指标仅供调试，不因下降而恢复 task-specific heuristic。
- [ ] 在用户确认 suite/metrics/thresholds 后运行真实 benchmark gate；失败则保持本 toDo
  active，并在 real-only 原则内调整 sampling/model/training。不得恢复 synthetic target、
  task-specific importance 或用较容易的问题替换失败结果。
- [ ] benchmark gate 不等于 ensemble trust calibration；后者仍不在本任务范围。
- [ ] 按开发文档完成 wheel build、force-reinstall、import-origin check、focused tests 和
  完整 pytest，随后更新 change record 并归档本 toDo。

## Verification Plan

- Static/source checks:
  - active `src/`、tests、user docs、architecture、blueprints 和 examples 中不再存在
    `mixup`、rawData importance API/config、`query_weights` 或 relative-loss active path；
  - 历史 `change_records/` 和 `obsolete/` 允许保留事实记录；
  - GPSAF active candidate-decision path 不读取 ensemble spread 或 in-sample fit error；
  - 没有 legacy checkpoint/history reader、转换器或 compatibility fixture。
  - 没有 yadof-owned 标准 loss/optimizer/tensor/serialization 算法副本或新增通用 trainer
    framework；保留 helper 都有 yadof-specific contract caller。
- Focused behavior tests:
  - trainer inputs 只由真实 rows 或 bootstrap indices 构成；
  - field-balanced sampler 可复现、无 rank/window bias，equal field budget 与 budget 小于
    field 数时的 deterministic shuffled rotation 明确；
  - per-field macro loss 不因扩大 field 内 slot/coordinate 数量而放大该 field 的总权重；
  - full rawData reconstruction、member intervals、current-cost conversion、scheduler、
    workspace isolation 和 failure handling 保持；
  - bootstrap 只重采样真实 rows；ensemble mean/spread 继续可恢复和查看；修改 spread 或
    training-fit audit 不改变 GPSAF candidate selection；
  - removed config/hook 给出明确诊断；
  - 当前 compatible checkpoint 可恢复；旧格式/不兼容 state 不会被 active discovery
    cross-load，且不自动删除；atomic failure injection 不产生可发现的半成品。
- Acceptance:
  - 用户确认的真实 benchmark suite/metrics/thresholds 全部通过；报告 rawData/objective
    error、适用的 ranking、训练时间/资源和固定 real-evaluation budget optimization efficiency；
  - benchmark 失败保持任务未完成，只允许在 real-only 原则内迭代；
  - 构建并 force-reinstall wheel，确认 import 来自 `.venv/Lib/site-packages/yadof`；
  - 运行相关 surrogate/job-template/config/viewer tests 和完整 pytest；
  - 不启动真实 simulator 或 HTCondor，除非用户另行明确授权。

## Completion Rule

- conditional INR 的生产训练只使用真实 evaluation rows/targets（bootstrap 仅重采样真实
  rows），只使用一个 pointwise loss，并执行 equal field budget、seeded within-field sampling、
  per-field mean + equal field macro loss。每个 numeric rawData field 获得相同总权重；slot
  数量不放大 field 权重。
- mixup、relative-loss、task-owned importance、floor/boost、weighted query sampling、
  rank-based forced queries 及其 config/API/state/checkpoint/test/doc surfaces 已从当前实现
  删除，没有 zero-default 死分支、silent compatibility alias 或重复实现。
- 通用训练数值 primitives 委托成熟 package；yadof 的剩余实现只服务明确的 field、
  rawData、campaign 和 checkpoint/provenance 契约，并为后续 modular 收缩提供干净基线。
- deep ensemble、真实-row bootstrap 和 member spread 输出保留；ensemble spread 与训练集内
  fit error 不影响 GPSAF candidate decision，未来 trust calibration 明确留给真实 benchmark。
- 只有带明确 format/method/policy/signature 的 compatible checkpoint 可恢复，发布真正
  原子；旧 history、权重和 checkpoint 可保留为 inactive 但绝不 cross-load 或自动删除，
  切换不要求空 workspace/clear。
- 用户保证 objective-irrelevant numeric data 不进入 rawData；yadof 同等认真建模所有 numeric
  rawData fields，不从 objective/window 猜测 importance。
- 用户确认的真实 benchmark gate、结构/数据流验收、所有文档和 blueprints、安装态完整
  pytest 均通过。本 toDo 随完成变更记录移入 `dev_doc/obsolete/` 后，两份协调 toDo 才能
  完成最终迁移与验收。
