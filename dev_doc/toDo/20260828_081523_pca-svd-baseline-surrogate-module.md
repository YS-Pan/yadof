# 添加 PCA/SVD rawData 基线与可组合 surrogate 模块

## 状态与起因

- 2026-08-28 工程实现已完成：package 现提供显式 opt-in `pca_svd()`、分离的 oracle codec 与
  deployable ridge predictor、GPSAF 生命周期、原子恢复、可组合的完整 optimization strategy、测试和
  文档。本文仍保留在 active TODO，因为权限边界不授权启动 simulator、正式 benchmark 或
  长时间训练，三个代表性 case 的合法 1000/2000-design measured results 尚未产生。
- 已封存的 solver audit 只使用 seeded synthetic `1000/2000 x 26645` 矩阵选择实现 backend，
  不属于科学 case evidence。`plan`/`preflight` 可安全运行；measured `run` 仍要求单独权限和
  合法的显式 design partition。
- 用户于 2026-08-28 明确要求：添加 PCA/SVD 基线，并把它们作为可复用算法模块加入 yadof。
  这构成
  [archived hierarchical CAE plan](../obsolete/20260827_082608_hierarchical-cae-rawdata-surrogate.md)
  中“只有后续用户单独批准才增加 PCA surrogate factory”条件所要求的单独批准。该批准只
  允许实现显式 opt-in 模块，不代表允许把它设为生产默认、宣称性能通过或打开 posterior
  exploitation。
- 冻结证据中的 `pca-svd-reconstruction` 诊断逐字段使用训练集均值和
  `torch.pca_lowrank(..., center=False)` 建立 rank-32 子空间，再把**验证样本自身的 rawData**
  投影和重建。它适合回答“该字段是否可低秩压缩”和“schema/metric 管线是否合理”，但没有
  学习 `parameters -> coefficients`，因此不是可部署 surrogate，也不能用于给未评估候选生成
  rawData。
- 上述诊断已经参与冻结的先前证据。不得重写或重新解释旧计划及结果；package 模块必须在
  新的外部研究计划中做数值 parity，并由新 strategy identity 产生后续证据。
- [Hierarchical CAE/qNEHVI 总控 TODO](20260828_121904_surrogate-qnehvi-remaining-work.md)
  承接的七臂矩阵要求
  `pca-svd-reconstruction`，但 Gate 0 v10 记录它仍没有 current runner arm。新增模块应补齐
  这个可执行缺口，同时把 oracle reconstruction 与真实参数预测的结论严格分开。
- 2026-08-29 用户决定暂时搁置
  [抗噪声扩展 TODO](20260828_082308_noise-robust-regime-specialized-surrogate.md)，并进一步明确
  抗噪声路线只是扩展能力，不是 Hierarchical CAE 的验收指标或 blocker。该决定不暂停本
  TODO：PCA/SVD 的合法 measured evidence、formal-suite 接入和独立基线结论仍可按其自身权限
  继续；PCA/SVD 仍可为基础 Hierarchical CAE 提供 representation ceiling 与
  parameter-to-latent 难度诊断。

## 目标

1. 在 `yadof.surrogate` 下增加独立、可复用、显式选择的 PCA/SVD 低秩 rawData 模块，而
   不是继续把算法埋在一个 benchmark runner 函数中。
2. 同时提供两个边界清晰的能力：
   - **oracle reconstruction diagnostic**：对已知 rawData 做低秩 encode/decode，只衡量表示
     上限、有效秩和重建管线；
   - **deployable rawData surrogate**：仅从训练 real evidence 学习低秩基底和
     `normalized parameters -> coefficients` 映射，再为未评估候选重建完整 rawData。
3. 让 deployable 模块可以作为 workspace-owned optimization composition 的 surrogate
   component 显式传给 GPSAF；它不是第二个完整 optimizer，也不增加 package 全局完整算法
   selector。
4. 用该模块诊断 hierarchical CAE 的失败究竟主要来自 rawData 表示能力，还是来自
   `parameters -> latent` 学习；不能把 oracle 重建的好成绩记成候选预测或优化成绩。
5. 保持 rawData-first、当前 cost 动态解释、稳定 selector、workspace/state 隔离、可靠记录和
   optional-backend lazy import 等现有契约。

## 已确定的设计决定

### 1. 模块身份与 public surface

- 建立独立私有实现包，建议命名为 `src/yadof/surrogate/linear_subspace/`；不要把实现塞进
  `hierarchical_cae/`，因为 PCA/SVD 是独立基线和可组合模块，不是 CAE 内部训练技巧。
- 从 `yadof.surrogate` 暴露一个轻量 factory。首选 surface 为：

  ```python
  pca_svd(
      decomposition="pca",       # "pca" 或 "svd"
      rank=32,
      predictor="ridge",
      ridge_alpha=...,
      field_mode="per-field",
  )
  ```

  实施前可在 Gate 0 将命名收敛为 `linear_subspace(...)` 或两个薄 convenience factories，
  但只能保留一个无歧义的权威配置路径，并在 change record 中说明理由。不得同时维护互相
  漂移的几套默认值。
- `decomposition="pca"` 的首版语义固定为：逐字段、逐坐标训练均值中心化后做截断 SVD，
  coefficient 和 inverse transform 都绑定该训练均值。
- `decomposition="svd"` 的首版语义固定为：逐字段对未中心化训练矩阵做截断 SVD。不得把
  PCA 和未中心化 SVD 作为只有名字不同、数学完全相同的两个 arm。
- 首版 `field_mode` 只要求 `per-field`。不同字段分别拟合 rank、均值/尺度和 basis，最终按
  selector 重组完整 structured rawData。拼接所有字段的 joint matrix、跨字段共享 basis 或
  task-specific weighting 只能作为以后另行预注册的扩展，不能悄悄改变首版含义。
- 模块必须拥有独立 component name、method/version、semantic identity、checkpoint namespace
  和训练策略身份；不得复用或覆盖 `conditional-inr`、`hierarchical-cae` 的状态。

上面的 `rank=32` 只是与现有冻结诊断臂做 parity 的初始示例，不是公共硬默认、最佳值或
验收门槛。实际 factory 默认值和可选 rank policy 必须在看到新 test 结果前预注册，并明确
`rank` 超过样本秩或字段宽度时是 clamp、reject 还是按阈值选秩。

### 2. Oracle reconstruction 与 deployable prediction 分离

- 公共低层 codec 可以复用相同的 `fit/transform/inverse_transform` 数学，但 benchmark
  report、类型和 arm ID 必须区分：
  - `pca-reconstruction-oracle` / `svd-reconstruction-oracle`；
  - `pca-ridge-rawdata-surrogate` / `svd-ridge-rawdata-surrogate`。
- oracle arm 可以 encode validation/test rawData，因为它明确测量“已知样本落在训练子空间
  中的程度”；它不得进入候选选择、GPSAF、qNEHVI、current-generation prediction 或任何
  optimization-quality 表格。
- deployable arm 在 fit 后只能接收 normalized candidate parameters。validation/test rawData
  只能用于事后 metric，不能参与 coefficient、rank、basis、mean/scale、ridge alpha、early
  stopping 或模型选择。
- deployable 首版使用确定性的 multi-output ridge 映射
  `normalized parameters -> per-field coefficients`。这是为了让基线保持低复杂度和可解释，
  不要在同一 arm 中加入 MLP、GP、MoE 或 task-specific feature engineering。ridge 求解应复用
  NumPy/Torch 的稳定线性代数，不因便利新增 scikit-learn 核心依赖。
- 若 ridge alpha 或 rank 需要选择，只能使用 training 内部 split 或冻结 validation；选择
  集合、tie-break 和 seed 必须在访问对应 test evidence 前固定。报告中同时给出实际有效
  rank 和被 clamp/reject 的原因。

### 3. rawData 与 cost 契约

- basis、coefficient predictor 和 reconstruction 只从 schema-compatible recorded real rawData
  训练。predicted rawData 是 transient derived state，永远不能进入 recorder 或冒充真实证据。
- 字段身份使用稳定的 `(direct NPZ basename including .npz, resolved values/data main key)`；
  checkpoint 必须绑定 selector、main shape/dtype representation、axes、units、metadata、参数
  名称/归一化含义、训练设计 provenance 和 decomposition/predictor 配置。
- 输出必须重建每个冻结字段的完整 main array，并保留原 axis、unit、metadata 和 dtype 表示，
  再通过当前 generation snapshot 的 `CostInterpreter`/现有 surrogate cost 路径计算 cost。
  不允许增加直接 `parameters -> cost` 的权威旁路。
- 每个字段先独立计算 reconstruction/prediction loss 和 metric，再 field-macro 聚合；长曲线或
  大二维场不能仅因点数多而压倒标量/短字段。task-specific 权重不进入 package 默认。
- finite task fallback `1.0` 与 execution `inf` 的现有语义保持不变。schema、projection 或
  current-cost 失败应沿用 surrogate 的可诊断失败边界，不得写入真实 history。

### 4. optimization 与 posterior 边界

- deployable component 应实现 GPSAF 已使用的窄生命周期：`validate()`、
  `semantic_identity()`、训练 freshness/scheduling、`predict_population()` 和独立 checkpoint
  recovery。预测返回完整 rawData 经 current cost 得到的 mean costs；若首版没有 ensemble，
  member spread 明确为零或不可用，不能伪造不确定性。
- 首版不要求 PCA/SVD 实现联合 rawData posterior，也不允许用线性回归残差临时伪造
  `PosteriorExploitationReadiness`。没有另行预注册的独立校准、transferability 和性能接受
  之前，它不能控制 qNEHVI exploitation。
- 可以在新的 benchmark 中增加显式 `GPSAF + PCA/SVD surrogate` 诊断臂，以验证模块确实可
  组合；这不是现有七臂中 oracle reconstruction arm 的替代品，也不自动获得默认推荐。
- package workspace template、`conditional_inr()`、hierarchical CAE、GPSAF 默认组合和
  posterior-assisted fail-closed 行为保持不变。

### 5. 数值、依赖与可复现性

- 普通 `import yadof.surrogate` 继续轻量。若实现使用 Torch randomized low-rank solver，
  Torch 只能在选择该 component 后 lazy import，并沿用 `surrogate` extra；若 NumPy 精确 SVD
  在目标规模上足够，则优先不增加新依赖。最终选择以 Gate 0 的时间、内存和稳定性测量为准。
- solver、device、dtype、seed、power iterations、rank policy、centering/scaling、ridge alpha、
  coefficient intercept 和 field mode 都是 semantic identity 的一部分。日志路径、墙钟和
  provenance 展示字段不是数学 identity。
- 对 basis 的符号不定性制定确定性 canonicalization，例如每个向量绝对值最大载荷为正；
  同时承认重复/近重复 singular values 的子空间旋转不唯一，验收应优先比较 projection、
  reconstruction 和子空间，而不是要求不合理的逐元素 basis 永久相等。
- constant、near-constant、单点、rank-0、rank 超界、非有限训练行、缺字段和不兼容 axes 必须
  有显式策略及测试。不得用 silent field drop 让一个不完整样本看起来成功。

### 6. 配置所有权

- 当前架构已经把算法/代理专用参数迁移到 `submit/optimization.py` 的显式 factory kwargs 和
  component-owned immutable settings。新模块必须直接使用这一模式，不新增一组中央
  `SURROGATE_PCA_*` uppercase keys，也不增加 `settings=`、ambient override、legacy alias 或
  runtime fallback 等第二配置入口。
- 不允许 component 在运行中任意读取完整 ambient `LoadedConfig` 来获取自己的算法参数；
  workspace path、device policy 等真正共享的 framework value 可以通过现有窄边界传入。

## 实施阶段与 gates

### Gate 0：现状 inventory 与新预注册

- 复核当前 `_pca_cell()`、冻结 v4/v5 plan/result、v10 formal matrix、三个代表性 case 的
  selectors/shapes 和届时 current surrogate component seam。
- 在不修改旧 evidence 的前提下冻结新计划，明确 PCA 与 SVD 的数学差异、rank/alpha 候选、
  split、oracle/deployable arm IDs、metrics、resource envelope 和 stop conditions。
- 测量 NumPy exact SVD 与可选 Torch low-rank solver 在 1000/2000 designs、当前最大字段上的
  CPU/GPU 时间与峰值内存，再决定首版 backend。Gate 0 不访问新的 test 结果，也不改变
  public behavior。

### Gate 1：低层分解/重建模块

- 实现逐字段 schema adapter、PCA 和 truncated-SVD codec、rank policy、canonicalization、
  transform/inverse transform、JSON-safe metadata 和 checkpoint payload。
- 用现有冻结输入重现旧 `pca-svd-reconstruction` 数学到预注册容差；差异必须作为新 solver/
  dtype/algorithm 变化解释，不能回写旧 receipt。
- 提供只读 oracle diagnostic API，类型和报告明确带 `oracle`/`diagnostic_only` 标识。

### Gate 2：可部署参数预测

- 在训练 designs 上拟合每字段 coefficient，再拟合确定性 multi-output ridge predictor。
- 仅凭 normalized parameters 为 validation/test candidates 重建完整 rawData，走当前 cost
  解释并输出可复算 metrics。
- 证明测试 rawData 未进入 fit、rank/alpha selection 或 checkpoint，并记录 training design
  partition 与 task/state signatures。

### Gate 3：component 生命周期与公开组合

- 增加独立 runtime、scheduler、checkpoint 和 public factory；保持每 workspace/strategy/
  component namespace 隔离、原子发布、恢复兼容性和 generation snapshot coherence。
- 让组件能够显式用于 `gpsaf(search=..., surrogate=pca_svd(...))` 或最终批准的等价 factory
  surface；不改变 template 默认。
- 普通 import、未选择组件、缺少 optional backend、切换策略和回切恢复全部通过测试。

### Gate 4：外部 benchmark study 与科学比较

- 在 benchmark 目录之外冻结一个 study request；每个比较项提供独立、完整的
  `submit/optimization.py`，分别覆盖 oracle PCA、oracle SVD、deployable PCA-ridge 和
  deployable SVD-ridge。如加入 GPSAF composition，使用独立 strategy ID 和相同真实评估预算。
- study 只引用 baseline semantic ID 与这些外部 strategy 文件；不得向 benchmark runtime
  增加算法注册表、角色判断、专项 adapter 或算法特有报告字段。
- 在 SAW、Chrono、synthetic antenna 的相同 design split、1000/2000 train size、current cost
  和预登记 seeds 上报告：
  - 每字段 physical/standardized MAE、RMSE 与 field-macro aggregate；
  - explained variance、singular spectrum、effective rank 和 reconstruction ratio；
  - deployable rawData/current-cost error、rank correlation、Pareto consistency；
  - fit/predict wall time、CPU/GPU peak memory、checkpoint size；
  - oracle 与 deployable 的差距，用于分离 representation ceiling 和参数映射难度。
- 只有 deployable arm 可以与 conditional-INR/hierarchical CAE 的未评估候选预测比较；只有
  同预算 GPSAF arm 可以形成 optimization-quality 结论。

### Gate 5：集成与当前文档同步

- 更新 architecture、surrogate/project/test blueprints、terminology、user docs/API examples、
  artifact membership 和 change record，使其描述已实现状态而不是引用本 TODO 作为 current
  truth。
- 将新 strategy 接入
  [Hierarchical CAE/qNEHVI 总控 TODO](20260828_121904_surrogate-qnehvi-remaining-work.md)
  后续冻结的正式 study；一个 PCA/SVD strategy 可执行只消除
  该结构缺口，不会解除 Hierarchical CAE performance、posterior calibration、qNEHVI 或其他
  阈值 blocker。
- 按届时开发指南完成 wheel build、force reinstall、import-origin、focused tests、benchmark
  automation tests 和 full installed-wheel suite。需要 simulator/长时间 measured suite 时另行
  按权限请求用户授权。

## 验证矩阵

### 数学与数据泄漏

- 人工精确低秩矩阵在足够 rank 下近机器精度重建，降 rank 后误差与遗漏 singular energy
  一致；PCA 中心化、SVD 非中心化的预期差异有独立测试。
- train-only mean/basis/ridge fit；改变 validation/test rawData 不影响已发布 checkpoint 或对
  固定 candidate 的预测。
- basis 符号、seed、solver 和 candidate chunk/order 的合理确定性；重复 candidate 给出相同
  mean rawData/cost。
- rank 上下界、样本数小于字段宽度、constant/near-constant 字段和奇异 ridge system 均有
  稳定、可诊断行为。

### rawData 与 component

- 混合 scalar、1-D、2-D、显式 rank-3 layout 的 selector/shape/dtype/axes/unit/metadata
  round trip；字段顺序变化不改变 identity-based mapping。
- prediction 经过当前 `calc_cost.py`，cost-policy 改变时复用 rawData prediction 并重新解释，
  不把旧 cost 固化进 checkpoint。
- checkpoint 原子发布、相同 state 恢复、rank/decomposition/predictor/schema/parameter
  normalization 不兼容时冷训练；不同 workspace/strategy/component 不碰撞。
- GPSAF 公共组合能运行 bounded synthetic test；默认 template、conditional-INR 和 CAE 状态
  不变；没有 posterior readiness 时 qNEHVI 继续 fail closed。
- predicted rawData 不进入 `recorded_data`，real evaluation 仍通过 common finalizer/recorder。

### 包与 benchmark

- parent import 不加载未选择的 Torch backend；缺 extra 时给出可操作错误；wheel/sdist 成员
  与 blueprint 一致。
- oracle 与 deployable 语义由各自完整 strategy 的 identity 和命名空间元数据表达；benchmark
  原样保存扩展元数据，但不解释、分类或据此改变比较流程。
- 已冻结的计划、hash、receipt 和失败结论不变；新证据进入独立 run。
- `yadof-benchmark` focused tests、代码式 workspace 无写入 plan 和两个 installed-wheel
  package suite 全部通过；真实 measured run 的权限和结果单独记录。

## 非目标

- 不把 PCA/SVD 设为 package template 默认、生产推荐或 hierarchical CAE 的自动替代品。
- 不通过本 TODO 修改旧 v5 失败结论、v8 校准结论、v9 fallback 或 v10 release gate。
- 不让 oracle reconstruction 参与候选选择，也不把 validation/test rawData 当作 surrogate 输入。
- 首版不实现 kernel PCA、sparse PCA、robust PCA、NMF、auto rank search、joint-field basis、
  nonlinear coefficient predictor 或 task-specific denoising。
- 不直接训练 `parameters -> cost`，不记录 predicted rawData，不改变 real evidence、current cost
  或 reliable recording 语义。
- 不因实现方便增加完整算法 registry、全局 selector、中央 PCA 配置字段或 scikit-learn 核心
  依赖。
- 不宣称 deterministic low-rank predictor 具有已校准 posterior，不为 qNEHVI 伪造 observation
  noise、member support 或 applicability probability。

## 与现有 TODO 的关系

- 本文是对 082608 中“后续需单独批准 PCA surrogate factory”的明确后继批准；082608 的
  Hierarchical CAE 性能 gate 仍独立有效，PCA/SVD 完成不能代替 Hierarchical CAE 通过。
- 本文应为 Hierarchical CAE/qNEHVI 总控 TODO 补齐可执行的
  `pca-svd-reconstruction` 结构 arm，并提供额外
  deployable predictor 诊断；其余六个正式 arm 和所有科学门槛仍由该汇总 TODO 管理。
- 若未来 PCA/SVD 需要 posterior calibration 或 qNEHVI，必须遵守
  [Hierarchical CAE/qNEHVI 总控 TODO](20260828_121904_surrogate-qnehvi-remaining-work.md)
  中的 exact-state/readiness
  契约并建立新预注册，不能从 reconstruction residual 直接推导授权。旧 082609/082611 计划
  仅保留在 `obsolete/` 作为可选历史细节。
- 抗噪声扩展的暂停、失败或通过都不阻塞 PCA/SVD，也不参与基础 Hierarchical CAE 的
  performance acceptance。PCA/SVD 完成仍不能替代基础 Hierarchical CAE 自己的
  representation/prediction gate、posterior calibration 或 qNEHVI readiness。
- 模块配置直接遵循当前 component-owned settings/factory 边界；低层 codec/parity 与公开
  component 使用同一权威参数来源，不再安排二次配置迁移。

## 完成规则

只有同时满足以下条件，本 TODO 才可移入 `dev_doc/obsolete/`：

- PCA 与 truncated SVD 的数学语义、public factory 和 component identity 已实现并文档化；
- oracle reconstruction 与 deployable parameter-to-rawData prediction 在代码、类型、arm ID、
  report 和结论中不可混淆；
- deployable module 能从 real training evidence 拟合、为未评估 normalized candidates 重建
  完整 rawData、经 current cost 解释，并显式组合进 GPSAF；
- rank/solver/centering/predictor/schema/parameter identity、checkpoint 原子性、恢复、workspace
  隔离、lazy dependency 和 failure behavior 已由 generic tests 覆盖；
- 外部 benchmark study 中的 oracle PCA/SVD 和 deployable PCA/SVD strategies 可执行，且冻结 evidence
  未被修改；
- 三个代表性 cases 的合法 benchmark 结果清楚报告 representation ceiling、deployable gap
  和资源成本；未达到的性能门槛保留为失败结果，不能通过改名归档；
- architecture、blueprints、terminology、适用的 user docs/API examples、tests 和 change
  records 与最终实现同步；
- 已完成届时要求的 installed-wheel 验收；任何需要用户授权的真实 measured suite 要么已经
  获批并完成，要么被拆成新的 standalone TODO，不能随本文一起静默丢弃。
