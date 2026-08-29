# Hierarchical CAE、posterior、qNEHVI 与发布的剩余工作

## 本文的角色

- 本文短名为 **Hierarchical CAE/qNEHVI 总控**，是 2026-08-27 六份
  Hierarchical CAE/qNEHVI TODO 的唯一活动汇总和后续执行入口。
- 本文标题中的具体 surrogate 是实验性 `HierarchicalCAEComponent`，公开 factory 为
  `hierarchical_cae()`。`conditional_inr()` 是现有生产基线，
  `conditional_inr_posterior()` 是未校准 compatibility adapter，`pca_svd()` 是独立确定性
  基线；三者都不是标题中“Hierarchical CAE”的别名。
- 用户于 2026-08-28 明确要求把六份旧计划全部迁入 `dev_doc/obsolete/`，避免每次
  `dev_doc` context pass 都读取约十万字符的实施历史。本文保留完成情况、当前 blocker、
  后续依赖和验收规则；实施者不需要读取旧文件才能继续工作。
- 六份旧文件现在只作可选历史资料。按 obsolete contract，不应默认读取；只有调查精确历史
  决策、冻结 preregistration/receipt、旧阈值来源或文档 provenance 时才定向打开：
  1. [联合 rawData posterior 契约](../obsolete/20260827_082607_joint-rawdata-posterior-contract.md)
  2. [hierarchical CAE rawData surrogate](../obsolete/20260827_082608_hierarchical-cae-rawdata-surrogate.md)
  3. [coherent posterior sampling/calibration](../obsolete/20260827_082609_coherent-posterior-sampling-calibration.md)
  4. [conditional-INR posterior adapter](../obsolete/20260827_082610_conditional-inr-posterior-adapter.md)
  5. [qNEHVI acquisition strategy](../obsolete/20260827_082611_qnehvi-acquisition-strategy.md)
  6. [integrated validation/release](../obsolete/20260827_082612_validate-new-surrogate-and-qnehvi.md)
- 归档旧计划不改变任何代码、科学结论、冻结阈值、receipt/hash、readiness 或发布状态。旧
  文件中未完成的工作由本文承接，而不是因移动到 obsolete 被视为完成。

## 当前实现快照

### 当前用户优先级决定

- 2026-08-29 用户明确决定暂时搁置
  [抗噪声 Hierarchical CAE successor](20260828_082308_noise-robust-regime-specialized-surrogate.md)。
  该 TODO 保持 `PARKED`，不执行其 regime-specialized/MoE、simulator、blind evidence、
  calibration 或 formal qNEHVI gates。
- 当前 Hierarchical CAE 的数据筛选接口已经独立收敛：`hierarchical_cae()` 默认
  `data_filter_mode="none"`；频率筛选只通过显式
  `data_filter_mode="frequency"` 与 `frequency_filter=FrequencyFilter(...)` 启用。这是已验收的
  组件接口事实，不是抗噪声 successor 的性能证据或重新激活。
- 暂停没有反转 v5/v8 失败，也不创建 performance-accepted checkpoint、transferable
  calibration artifact 或 typed exploitation readiness。Hierarchical CAE 仍是
  `experimental / performance-not-accepted`，真实 qNEHVI 仍只能 fail closed 到 full-real
  fallback。
- 当前可独立推进的是 PCA/SVD 三 case measured evidence、formal-suite 结构接入和不依赖新
  Hierarchical CAE 科学结论的工程改进。Hierarchical CAE performance/calibration/eligible
  qNEHVI/完整发布链保持有意阻塞，直到用户明确恢复抗噪声路线或批准另一条具体 successor。

### 已完成并可依赖的基础设施

- 后端无关的 joint rawData posterior protocol 已完成：persistent sampler 固定 function-draw
  identity，跨 candidates、fields、objectives、permutation 和 chunks 保持一致；structured
  rawData 使用稳定 selector `(direct NPZ basename including .npz, resolved values/data key)`。
- `RawDataCostProjector` 已完成：对完整预测 rawData 做冻结 schema 校验，复用 generation
  snapshot 的当前 `CostInterpreter`，流式生成 joint objective samples/validity diagnostics，
  predicted rawData 不进入 recorder。
- conditional-INR 的显式 posterior adapter 已完成：有限 ensemble member draw、full-grid
  reconstruction、nominal/effective support、member failure isolation、lazy Torch import 和
  unchanged legacy `conditional_inr()`/GPSAF behavior 均有测试。该 adapter 仍是 uncalibrated
  compatibility path，不具备 exploitation 授权。
- public discrete `qnehvi()` acquisition 和 `posterior_assisted()` complete strategy 已实现。
  它们具备 fixed real Pareto baseline、chunked projection、显式 real exploration、common real
  evaluator、typed readiness、soft full-real fallback 与 hard-stop 边界；BoTorch 只拥有
  qLogNEHVI 数值循环。
- integrated preregistration/release historical framework 已完成；其可执行 hash validators
  已退役，计划/回执仍记录原结论。结构化验收 run 完成 9/9
  cells、99/99 attempts、96 completed records、3 个显式 Chrono error-cost records，结构
  contract 通过；它只证明机制和记录链，没有形成 optimization-performance 接受结论。
- 当前组件专用配置已经迁移到 workspace `submit/optimization.py` 的显式 factory kwargs 与
  component-owned immutable settings。后续新 Hierarchical CAE/acquisition 参数遵循这一现行边界，
  不新增中央 algorithm uppercase keys。

### 已实现但科学验收失败的部分

- hierarchical CAE experimental component 已包含 scalar/Conv1d/Conv2d codecs、global/group/
  field-private latent、shared-codec predictor ensemble、完整 rawData/current-cost inference、
  atomic checkpoint/recovery、finite posterior draws、all-axis coordinate readout 和 viewer
  adapter。
- 当前 Hierarchical CAE 已提供默认关闭的 component-local 数据筛选接口及显式 `frequency`
  模式。历史 quality/regime 抗噪声 MVP 已包含 versioned task policy、design × field robust
  aggregation、shared-token isolation、gated field-private residual 和 uncalibrated applicability
  head；后者的 successor 现已暂停。
- Gate 0 v5 冻结的结论仍为：
  - `representation_passed=false`；
  - `quality_regime_passed=false`；
  - `full_grid_gate_passed=false`。
- 代表性失败包括：Chrono clean-target leakage `0.37714/0.36857` 高于 `0.35` guard，smooth
  roughness inflation `2.4013/2.3137` 高于 `2.0`，gated residual 的泄漏比 shared isolation
  高 `5.60%/2.38%`，Chrono 最差字段 RMSE ratio 达 `2.64995/3.85268`。
- v6/v7 coordinate/viewer/offline path 只获得 `experimental / performance-not-accepted` 的机制
  结论，不能反转 v5，也不能成为生产 recommendation。

### 校准、readiness 与发布的当前状态

- exact-signature calibration artifact、field-spread scaling、coherent calibrated sampler wrapper
  和 applicability calibration framework 已实现。
- v8 使用 600 个独立 calibration designs 完成 6/6 cells，但六个 rawData artifacts 都至少
  失败一个冻结 gate，最终均为 `uncalibrated`、identity scaling、`transferable=false`。
- Chrono labels 为 19 smooth / 181 chatter-or-failure，不能满足预注册两折 minimum-class
  support；两个 applicability fits 均失败。当前没有可供 qNEHVI 使用的 calibrated
  probability capability。
- shipped `HierarchicalCAEComponent` 与 `ConditionalINRPosteriorAdapter` 都返回 blocked typed
  exploitation readiness。真实组件进入 `posterior_assisted()` 时只能走可见的 full-real
  fallback；eligible exploitation path 目前只由 fake/mechanism tests 覆盖。
- 正式七臂 runner 当前仍只有 real NSGA-III 和 conditional-INR + GPSAF。独立 v11
  recorded-data runner 已补齐 PCA/SVD oracle 与 deployable ridge 的可执行结构，但尚未接入
  formal suite，也没有权限执行三个 case 的 measured cells。formal matrix 仍缺：
  - hierarchical-CAE mean；
  - hierarchical-CAE + qNEHVI；
  - conditional-INR adapter + qNEHVI；
  - PCA/SVD reconstruction 的 formal-suite 接入与合法 measured evidence；
  - hierarchical-CAE + GPSAF。
- formal optimization/posterior-decision/总工程成本阈值尚未全部封印，formal benchmark start
  仍为 false。Phase A 只允许冻结证据上的实验/诊断；Phase B public opt-in 必须 full-real
  fallback；Phase C 仍是 `blocked-not-recommended-no-default-change`。

## 当前活动范围与未来恢复顺序

### 1. 补齐 PCA/SVD 基线和可复用模块（当前 active）

- [PCA/SVD 基线 TODO](20260828_081523_pca-svd-baseline-surrogate-module.md)
  的工程部分已完成；其 active remainder 仅为需单独授权的三 case measured evidence 和
  formal-suite 接入。
- 必须区分 oracle reconstruction 与 deployable
  `normalized parameters -> coefficients -> complete rawData` predictor；oracle validation/test
  projection 不能冒充 candidate prediction 或 optimization arm。
- 新 module 使用 component-owned settings、独立 identity/checkpoint，并可显式组合进 GPSAF；
  不设为默认、不伪造 posterior readiness。
- 这一步补齐 formal matrix 的 PCA/SVD 结构缺口，同时帮助判断 Hierarchical CAE 的问题位于
  表示空间还是 parameter-to-latent mapping。
- 抗噪声 Hierarchical CAE successor 的暂停不阻塞这一步；但 PCA/SVD 通过也不能替代
  Hierarchical CAE performance、posterior calibration 或 qNEHVI readiness。

### 2. 保持 Hierarchical CAE 当前状态与 fail-closed 边界（当前 active）

- 不再继续调旧 v5 checkpoint，也不把默认 `none` 或显式 `frequency` 筛选接口当作性能改善。
  旧结果已经被查看并冻结，任何 architecture/routing/rank/threshold 变化都需要用户批准的
  successor、独立 preregistration 和新 semantic namespace。
- 抗噪声 Hierarchical CAE successor 暂停期间，不运行其 Gate 0--5，不访问新的 blind test 或
  calibration locator，不把失败的 v8 artifact 迁移到当前 checkpoint。
- `HierarchicalCAEComponent` 和 `ConditionalINRPosteriorAdapter` 继续返回 blocked readiness；
  `posterior_assisted()` 的安全 full-real fallback 保持当前可用行为。

### 3. 建立 performance-accepted Hierarchical CAE（等待用户重新授权）

- 用户如果恢复抗噪声路线，按 PARKED TODO 重新审计当前 `frequency` API、冻结新计划，并比较
  simple shared isolation、一个有界 regime-specialized/MoE 主候选、conditional-INR 和必要的
  PCA/SVD 简单对照。
- 用户如果批准不同的 Hierarchical CAE successor，先建立独立、自足的 TODO 和预注册，再把
  它接回本文；不得默认继承抗噪声 TODO 的 architecture、阈值或授权。
- 任何路线都必须保持 rawData-first、zero observation noise、field-macro、最差字段 guard 和
  适用的 clean leakage/roughness 约束。只有新的 blind evidence 同时通过 representation、
  quality/regime（若适用）、worst-field、coordinate 和资源 gate，精确 checkpoint 才可标记
  `performance_accepted=true`。

### 4. 对接受的 Hierarchical CAE exact checkpoint 重新校准并验证 qNEHVI

- performance gate 通过后，再建立新的 pre-access calibration plan。旧 v8 artifact 只绑定
  失败的 experimental state，不能迁移给 successor。
- calibration/test 按 design row 独立；Chrono 需通过预先声明的 stratified/boundary design
  acquisition 改善 19/181 类别失衡，不能事后按 outcome 删除样本或把 oversampling 当成新增
  独立证据。
- 必须通过 rawData coverage/energy、current-cost coverage/ranking/Pareto、bounded acquisition
  decision proxy、AUPRC/Brier/ECE/reliability、minimum-class support 和 exact-signature checks。
- 失败继续发布 `uncalibrated`、`transferable=false`，不暴露概率系数，不允许 exploitation。
- 将 performance acceptance、exact transferable calibration、zero observation noise、state/
  artifact signatures 和 calibrated/not-applicable applicability 组合为真实
  `PosteriorExploitationReadiness`；member variance、training loss 或 residual 不是替代条件。
- 在新 preregistration 中冻结 applicability threshold、boundary width、低/边界 real exploration
  顺序、support policy、candidate pool、draw/chunk、q/restart、seed、fallback 和 hard stops。
- 先运行 bounded eligible-path integration/canary，证明真实 sampler/projection/qNEHVI selection/
  common evaluator/recorder 全链；再申请同预算正式实验权限。
- 当前只有一个真实 acquisition，实现工作不应提前触发
  [Acquisition Capability Protocol TODO](20260828_091749_acquisition-capability-protocol.md)。只有
  第二个获批准实现或真实调用方受具体类型阻塞时才提炼通用 protocol。

### 5. 补齐七臂 formal benchmark 与发布决定（当前 blocked）

- 在首次 formal result access 前封印所有剩余数值 threshold：coordinate/resource、posterior
  decision/calibration、optimization/HV/noninferiority、engineering cost 和 stop conditions。
- runner 必须能执行完整七臂、相同真实评估预算和冻结 seeds/splits；
  `Hierarchical CAE + GPSAF` 是必需的 attribution ablation，不能省略。
- 报告 final/trajectory hypervolume、evaluation-normalized HV AUC、failure/duplicate rate、
  training/inference/acquisition wall time、CPU/GPU memory、checkpoint size 和总工程成本。
- formal run 需要真实 simulator/长时间资源时，先向用户报告准确 command、cell/design 数、
  预计时间与风险并取得授权。结构 preflight 或单元测试不能替代科学结果。
- PCA/SVD arm 可在自身 TODO 和权限下先取得 measured evidence；完整七臂 formal benchmark
  仍等待 performance-accepted、exact-calibrated Hierarchical CAE 与 eligible typed readiness，
  不能把抗噪声路线暂停解释为允许省略 Hierarchical CAE arms。
- 只有完整 matrix 通过预注册 gate，才可推荐 Phase B opt-in；默认 GPSAF + conditional-INR
  的 Phase C 迁移需要独立、明确的用户决定。不得自动修改 template default。

## 工程与证据改进

- 八个 legacy `hierarchical_cae_*.py` runner 与 v1-v10 可执行 hash validators 已从当前树
  退役；历史实现通过对应 Git revision 查阅，冻结 plans/receipts 保持原结论。
- 新 benchmark workspace 直接使用已安装 driver，并在执行前一次性记录版本；每个
  workspace 只承载一次执行，不设计 resume 或代码快照。baseline 仅为隔离 yadof cell 而
  物化。未来算法继续作为完整 `submit/optimization.py` 输入，不建立专项 runner、算法
  注册点或薄 adapter。
- 大型权威 evidence 目前主要在 ignored `temp/`，tracked receipts 保存 hashes。正式 release
  前建立内容寻址、只读、可跨身份读取的 artifact export；不要把全部原始数据提交进 Git。
- acquisition soft fallback 保持安全，但开发/preflight 诊断应持久记录 exception type、阶段和
  traceback digest，避免宽泛异常长期掩盖实现 bug；生产路径仍不得把 recorder/finalizer
  failure 降级为 fallback。
- BoTorch fused qLogEHVI extension 当前可能因缓存目录不可写而退回 pure Python。正式资源
  gate 前配置可写且隔离的 extension cache，或显式采用 no-compile 模式，并测量真实 wall
  clock；correctness fallback 不等于性能接受。

## 不变边界

- real rawData/variables 和 lifecycle provenance 是 durable truth；cost、predictions、posterior
  draws、acquisition values 都是 derived/transient。
- 不新增直接 `parameters -> cost` 的生产真值路径，不记录 predicted rawData，不把 task
  `error_cost=1.0` 与 execution `inf` 混淆。
- posterior draw identity 跨 candidate/field/objective 保持一致；calibration 不重排成员或为
  每个 x 注入独立伪噪声。
- real evaluation 始终经过 common finalizer 和 reliable recorder；recording failure
  campaign-fatal。
- 新组件通过 workspace factory 显式组合；不建立全局完整算法 selector、registry 或自动
  discovery。
- frozen v1--v10 plans、thresholds、receipts、hashes 和失败结论不可修改。任何后继实验创建
  新版本。

## 完成规则

抗噪声路线暂停本身不是本文完成条件。只有同时满足以下条件，本文才可移入
`dev_doc/obsolete/`：

- 一个用户明确批准的 Hierarchical CAE successor 在新的 blind evidence 上通过
  representation、适用的 quality/regime、worst-field、coordinate 和资源 gate；
- 该 exact Hierarchical CAE checkpoint 获得独立、可迁移的 posterior/applicability
  calibration artifact；
- `HierarchicalCAEComponent` 通过 typed readiness 进入 eligible qNEHVI 路径，并保留明确
  real exploration、
  soft fallback 和 hard-stop 边界；
- 七臂同预算 formal benchmark 完成并通过预注册的科学与总工程成本门槛；
- release decision、默认策略决定和所有失败/限制如实记录，未通过结构测试替代科学验收；
- architecture、blueprints、terminology、适用 user docs、外部 benchmark studies/strategies、tests 和 change
  records 与最终实现同步；
- 按届时开发指南完成 wheel build、force reinstall、import-origin、focused/full package 与
  benchmark automation 验收；
- 如果其中一部分被拆到新的独立活动 TODO，本文必须更新成仍然自足的剩余状态，确认没有
  遗漏后才能归档，不能仅因六份旧计划已进 obsolete 而宣称工作完成。
