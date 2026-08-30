# Posterior-assisted EHVI/qNEHVI 优化与发布证据

## 本文角色与当前状态

- 本文是手动 TODO，拥有 joint rawData posterior、exact-state calibration、typed
  readiness、离散 qNEHVI、posterior-assisted strategy、同预算优化比较和发布决定。
  当前实现名称是 `qnehvi()`；标题使用 EHVI/qNEHVI，是为了说明研究对象是基于期望
  hypervolume improvement 的 batch/noisy 变体，而不是新增另一个 acquisition。
- Hierarchical CAE 的 architecture、训练、确定性 full-grid 预测、coordinate readout、资源
  诊断和表示研究由
  [Hierarchical CAE 证据驱动研究 TODO](20260830_120818_hierarchical-cae-evidence-led-research.md)
  独立拥有。本文消费该组件能够诚实提供的 posterior capability，但不再用一个跨 case、跨
  指标的 CAE performance gate 决定它是否有研究价值或是否允许继续改进。
- [抗噪声 Hierarchical CAE 扩展](20260828_082308_noise-robust-regime-specialized-surrogate.md)
  继续 `PARKED`。它既不是基础 CAE 的前置，也不是本文的前置；只有未来明确选择该变体参与
  posterior/EHVI 时，才作为额外 component arm 进入本文。
- 本文继承 2026-08-27 六份已归档计划中仍未完成的 posterior/EHVI 工作。旧 v1--v10
  preregistration、threshold、receipt、hash 和失败结论保持历史原样；新的实验或判断创建新
  版本，不追溯修改旧结论。

## 已实现且可依赖的机制

- 后端无关的 joint rawData posterior protocol 已实现：一个 persistent sampler 固定
  function-draw identity，并在 candidates、fields、objectives、permutation 和 chunks 之间
  保持一致。
- `RawDataCostProjector` 会验证完整 named rawData、复用 generation snapshot 的当前
  `CostInterpreter`，只保留 joint objective samples、validity 和有界诊断；predicted rawData
  不进入 recorder。
- `conditional_inr_posterior()` 已提供有限 ensemble compatibility adapter，但仍是
  uncalibrated capability。`hierarchical_cae()` 已有 coherent finite member draws；旧 exact
  states 的 calibration artifacts 均为 `uncalibrated`、`transferable=false`。
- public `qnehvi()` 和 `posterior_assisted()` 已实现 fixed real Pareto baseline、candidate
  chunk projection、显式 real exploration、common real evaluator、typed readiness、soft
  full-real fallback 与 hard-stop 边界。BoTorch 只拥有 qLogNEHVI 数值计算。
- 当前 shipped conditional-INR adapter 与 Hierarchical CAE 都返回 blocked readiness，因此
  真实运行只会走可见的 full-real fallback。eligible path 目前只有 synthetic/fake mechanism
  evidence，没有形成真实 surrogate 的 optimization-quality 结论。
- `pca_svd()` 是确定性 GPSAF 基线，输出 zero-width intervals，没有 posterior/readiness
  capability；它可以进入确定性同预算比较，但不能伪装成 EHVI posterior arm。

## 决策原则：不用全局性能 gate

### 连续证据与用途决定

- surrogate 与优化算法的表现按 case、预算、seed、训练量、指标和工程成本连续报告。不得把
  多个非等价指标合成“所有 cell 全过才成功”的黑白结论，也不得用一个失败字段抹去其他
  case 的有效收益。
- 新 study 在访问结果前冻结数据用途、预算、seeds、arms、metric definitions、exclusion、
  stopping 和报告规则；不需要预先冻结一个通用 pass/fail 数值集合。阈值只有在某个具体
  deployment/use case 确有最低服务要求时才定义，并明确其适用范围。
- 缺失、尚未可用或运行失败的 arm 记为 unresolved/failed arm；它不使已经有效配对的其他
  arm 证据失效。旧“七臂必须完整且全部满足门槛”的发布 gate 降为目标比较矩阵，不再是单次
  科学判断的原子条件。

### Capability eligibility 不是 CAE 性能判决

EHVI 使用某个 exact surrogate posterior 前仍需满足该运算本身的能力条件：

- state、schema、strategy、calibration artifact 和 checkpoint identity 精确绑定；
- draw identity 连贯，完整字段可投影，observation-noise 语义诚实；
- finite support、有效 draw 数和失败 mask 能被 acquisition 正确解释；
- calibration/decision diagnostics 足以说明该 posterior 在当前候选选择用途上的限制；
- 任何选择仍进入 common real evaluator/finalizer/recorder。

这些是“能否把这组 samples 当作 qNEHVI 输入”的 capability decision，不是对 CAE 表示性能
的全局评级。当前 `PosteriorExploitationReadiness` 中的笼统
`performance_accepted` 语义在执行本文时应重新审查：如果它仍把多 case 非劣 gate 当作必要
布尔输入，应拆成 exact-state、use-case-specific 的 evidence/capability 字段；不得只是把旧
gate 换个名字。

### 保留的安全边界

以下边界仍可产生二元可用/不可用结果，因为违反它们会让计算语义错误或证据不可靠，而不是
因为模型“分数不够好”：

- schema/signature 不匹配、非有限 objective samples、candidate/draw 对齐破坏、配置为
  reject 的 support 不足；
- evaluator/finalizer/recorder failure，尤其是 recording failure；
- predicted rawData/cost 进入 durable history，或 acquisition 绕过真实评估；
- calibration artifact 被迁移到不相同的 exact state。

普通 projection、selection、backend 或 readiness 不可用继续 soft fallback 到完整 real
search；可靠记录和显式 hard-stop 错误不得被 fallback 吞掉。

## 当前证据输入

- PCA/SVD 三 case measured study 已完成 24 个 oracle/deployable logical cells。其主要结论是
  linear ridge `parameters -> latent` 为共同瓶颈；oracle 不参与 selection/HV。详情见
  [完成记录](../change_records/20260830_074344_complete-pca-svd-measured-evidence.md)。
- 新的基础 CAE benchmark 已完成 24/24 logical cells，所有 mechanics/resource/reload checks
  可执行，但端到端表现高度依赖 case。旧 all-cell gate 为 false 只保留为该 sealed plan 的
  历史输出，不再升级成全局 CAE 判决；定量解释由 CAE TODO 保存。
- v8 的六个 exact-state calibration artifacts 均失败关闭，因而不能迁移到新的 CAE state；
  conditional-INR adapter 同样没有可迁移 calibration。
- 正式 optimization benchmark 尚未运行。已有结构 run 只证明 9/9 cells、99/99 attempts 和
  recorder/fallback mechanics，不证明 EHVI 带来优化收益。

## 剩余工作

### 1. 重写 posterior suitability evidence

- 为每个拟用于 EHVI 的 exact component state 建立新的 pre-access plan。按 design row 隔离
  training/model-selection、calibration 和 decision test；不按 outcome 删除样本或把重复采样
  当成独立 evidence。
- 报告 rawData coverage/energy、current-cost error/ranking/Pareto、spread reliability、有效
  support、失败 draw、候选选择 decision proxy 和工程成本。任何 applicability probability
  只在组件明确提供且数据支持时评估；基础 CAE 不默认继承抗噪声 classifier 或 class-balance
  指标。
- 以 reliability curves、effect sizes、uncertainty intervals 和失败模式形成用途说明。若结果
  不支持 EHVI，发布诚实的 unavailable capability 并保留 full-real path；这不终止 CAE 研究。

### 2. 真实 eligible-path canary

- 选择第一个具备可解释 posterior capability 的 exact state，冻结 candidate pool、draws、
  chunks、q、restarts、seed、support policy、fallback 和 hard stops。
- 用小而完整的 real-evaluation canary 证明 sampler -> projector -> qNEHVI -> exploration ->
  common evaluator -> recorder 全链。canary 只回答机制和局部选择行为，不自动形成默认推荐。
- 持久记录 selection exception type、阶段、traceback digest、support 和时间/内存诊断；避免
  宽泛 fallback 长期掩盖实现错误。

### 3. 模块化同预算 optimization study

目标矩阵包含：

1. real NSGA-III；
2. conditional-INR + GPSAF；
3. PCA/SVD deployable + GPSAF；
4. Hierarchical CAE + GPSAF；
5. Hierarchical CAE mean/no-acquisition attribution arm（若与第 4 项语义不同）；
6. conditional-INR posterior + qNEHVI（仅在 exact capability 可用时）；
7. Hierarchical CAE posterior + qNEHVI（仅在 exact capability 可用时）。

矩阵是可扩展比较集合，不是必须同时解锁的七臂 gate。每个有效 pair 使用相同真实评估预算、
冻结 seed/split/initial population；新增或暂不可用 arm 不改变已完成 pair 的有效性。报告：

- final/trajectory hypervolume 与 evaluation-normalized HV AUC；
- failure、non-finite、duplicate 和 fallback rate；
- training、prediction、projection、acquisition 与真实 evaluation wall time；
- CPU/GPU memory、checkpoint size、总工程成本和结果跨 seed 变异；
- CAE + GPSAF 与 CAE + qNEHVI 的 attribution，以及 deterministic baselines 的相对价值。

真实 simulator/长时间运行前，按届时用户文档报告精确 command、case/arm/cell/evaluation 数、
预计时间与资源并取得授权。结构 preflight、smoke 或 synthetic test 不能替代 optimization
quality evidence。

### 4. 分层发布决定

- **机制可用：** public opt-in strategy 与 full-real fallback 可在其结构测试范围内保留。
- **component-specific EHVI：** 只对 exact posterior capability 和已运行的 cases 作有限
  推荐；不能外推为所有 CAE/conditional-INR state。
- **默认迁移：** 必须由用户单独决定，并综合优化收益、鲁棒性、总工程成本和失败体验；TODO
  完成不会自动修改默认 GPSAF + conditional-INR。
- 允许最终结论是：保留实验 opt-in、仅对某些 case 启用、继续 full-real fallback，或停止
  某个 posterior arm。无需制造一个全局 passed/failed 标签。

## 工程改进与约束

- BoTorch fused qLogEHVI extension 若因缓存不可写而退回 pure Python，应在性能测量前配置
  workspace/task-specific 可写 cache，或明确采用 no-compile 模式；correctness fallback 不是
  性能数据。
- 大型 evidence 需要内容寻址、只读、可跨身份读取的 export；tracked receipt 保存 digest 和
  解释，不把全部 raw artifacts 提交 Git。
- 当前只有一个真实 acquisition。除非出现第二个获批准实现或真实调用方被 concrete type
  阻塞，不触发
  [Acquisition Capability Protocol TODO](20260828_091749_acquisition-capability-protocol.md)。
- 新组件继续通过 workspace `submit/optimization.py` factory 显式组合；不建立全局算法
  registry、字符串 selector 或自动 discovery。

## 完成规则

本文在以下条件满足后可以归档，不要求所有七个 arm 同时存在或达到统一阈值：

- 至少一个真实 exact posterior component 完成 suitability 说明，并在 eligible 或明确
  unavailable 两种结果之一上留下可复核 evidence；
- 至少一个真实 eligible component 完成 bounded qNEHVI canary，或有充分证据决定暂不提供
  eligible path，同时 full-real fallback/hard-stop/recorder 边界经过验证；
- 所有当前可用的核心 deterministic/posterior arms 在获批预算内完成代表性同预算 pairwise
  比较；暂不可用 arms、失败 runs 和未决外推被明确记录；
- 针对每个 component/use case 作出保留、限制、继续研究或停止的决定，并单独记录默认策略
  是否改变；
- 适用的 source/tests、architecture、blueprints、terminology、user docs、benchmark studies
  和 change records 同步，按届时开发指南完成 installed-wheel 验收。

Hierarchical CAE 表示研究可以在本文完成后继续，也可以先完成；两者互不以黑白性能 gate
作为归档前置。
