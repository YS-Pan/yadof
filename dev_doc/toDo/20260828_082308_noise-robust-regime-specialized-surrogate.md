# 补录抗噪声 quality/regime 稳健 surrogate 与后继验收

## 状态、来源与当前结论

- 本文是待执行的手动 TODO，同时补录一项此前只通过 Codex session 转交、没有独立 TODO
  落盘的用户要求。原要求由 session `01a04242-14f1-7162-8c38-c44a8b02fe12` 发送给
  hierarchical CAE 实施 session；session ID 只作补充 provenance，本文必须在没有聊天记录时
  也能独立执行。
- 原要求不是“把曲线平滑一下”。1929-row Chrono 描述性审计显示 roughness 与高 cost、未
  release、反复 contact/recontact 等状态相关，更符合**参数诱发的 chatter/failure regime**，
  不是独立同分布 measurement noise。审计中的 four-cost mean 与 curve roughness Spearman
  相关约为 `0.4694`；这些数值只解释工作动机，不是验收阈值，也不能证明 roughness 导致
  cost 变差。
- 原要求中的工程 MVP 已经并入
  [archived hierarchical CAE plan](../obsolete/20260827_082608_hierarchical-cae-rawdata-surrogate.md)、
  代码、测试和
  Gate 0 v2--v5 预注册：版本化 quality/regime policy、design × field 稳健聚合、shared-token
  隔离、gated field-private residual、未校准 applicability head，以及对 calibration/qNEHVI/
  release 的 handoff 都已实现。
- 但工程完成不等于科学完成。Gate 0 v5 已冻结
  `representation_passed=false`、`quality_regime_passed=false`、
  `full_grid_gate_passed=false`：gated MVP 对 clean target 的泄漏和 smooth roughness 均超限，
  且比 shared-latent isolation 更差。因此本文保持 active，负责把原抗噪声意图推进到一个
  重新预注册、通过独立证据的后继方案；不得重复声称现有 MVP 尚未实现，也不得把失败结果
  改写成成功。

## 原始用户要求的完整补录

以下要求是已经确定的产品/科学边界，后继实现必须继续遵守：

1. 在接触 future offline/formal test 前，先建立新版本预注册，冻结数据用途、质量状态定义、
   训练/消融、指标、阈值生成规则、失败规则和允许的后续动作。
2. quality/regime policy 必须是版本化、JSON-safe、可验证并进入 semantic identity/checkpoint
   的声明。Chrono 的 release、cutoff、contact、recontact 等诊断属于 task-owned policy；core
   不得硬编码 Chrono 字段名、物理阈值或任意未追踪 callback。
3. 保留原始 rawData 和当前 `calc_cost.py` 解释：
   - 不平滑、覆写或丢弃 chatter/failure 曲线；
   - 不按 cost 过滤设计或把 cost 当作 quality/applicability label；
   - 不把物理 failure evidence 降格成可以忽略的随机噪声；
   - 不把 predicted/denoised rawData 写入真实 recorder。
4. loss 先形成 design × field 矩阵，再做 capped/weighted field-macro aggregation。一个低可信
   曲线不能导致同一 design 的有效 scalar 字段被整体丢弃，长字段也不能凭网格点数支配
   训练。
5. 低可信字段在 shared teacher/latent fusion 前必须 mask 或 downweight；异常高频残差只能
   经过 field-private 路径，不能污染共享表示。
6. clean/smooth target 的异常 residual 路径应被结构性关闭或受到等价的可验证约束，防止
   chatter 纹理泄漏到 clean prediction。
7. predictor 可以提供 member-level `P(smooth)`/applicability score，但在独立 calibration
   通过前只能称为未校准诊断。它描述 epistemic/structural regime state，不是逐候选独立
   Gaussian observation noise。
8. 同一 posterior member/function draw 的 applicability 与 rawData prediction 必须跨
   candidates/fields 保持同一身份；不得分别重排字段或把 regime uncertainty 加成独立噪声。
9. 抗噪声结果必须分别交接给 posterior calibration、qNEHVI applicability/exploration 和最终
   release gate；任何上游失败都必须 fail closed。

## 已完成、必须保留的当前基线

以下内容已经实现，是后继工作的对照和复用输入，而不是待重新发明的范围：

- `yadof.surrogate.quality` 的通用 policy/assessment、显式 assessment 优先级、声明式
  diagnostic rules、可选 morphology fallback、field/shared weights、regime labels 和
  applicability 类型；
- hierarchical CAE 的 design-by-field loss、shared-token masking、field-private base/residual
  decoder、regime-gated residual、predictor applicability head、完整 rawData/current-cost 路径、
  checkpoint identity 和 coherent finite member draws；
- `无门控 / 仅稳健加权 / shared-latent 隔离 / gated-private-residual` 四臂消融；
- Gate 0 v2 的抗噪声预注册、v3 dataset seal、v4 116-cell plan、v5 development-validation
  thresholds/result，以及 v8 的独立 calibration framework；
- 已封存的 3-case 数据：每个 case 2800 designs，合计 development 6600、calibration 600、
  offline-test 1200；现有 partition 和 receipt 不得重写。

当前失败证据是后继设计的最低诊断输入：

| 指标 | train=1000 | train=2000 | v5 guard |
|---|---:|---:|---:|
| Chrono clean-target 高频泄漏率 | 0.37714 | 0.36857 | 最大 0.35 |
| smooth predicted/real roughness median ratio | 2.4013 | 2.3137 | 最大 2.0 |
| gated 相对 shared-isolation 泄漏改善 | -5.60% | -2.38% | 不得小于 0 |
| Chrono 最差单字段 RMSE ratio vs conditional-INR | 2.64995 | 3.85268 | 最大 1.25 |

classifier validation diagnostics 自身曾通过 AUPRC/Brier/ECE 门槛，但不能抵消上述表示、泄漏
和 roughness 失败。v8 又显示 Chrono calibration labels 只有 19 smooth / 181
chatter-or-failure，预注册的两折 minimum-class-count 无法满足，两个 applicability fits 均
fail closed。后继方案必须同时解决 representation contamination 和独立概率校准证据不足，
不能只优化 classifier 分数。

## 目标

1. 建立一个有界、可解释、重新预注册的 regime-specialized 后继 surrogate，使 smooth/clean
   表示不再因 chatter/failure 训练发生负迁移，同时完整保留异常 regime 的物理 rawData。
2. 用相同 design-level split 和 field-macro 口径证明改善来自 architecture，而不是删除困难
   样本、改变 cost、泄漏 test、少报失败 arm 或更换统计口径。
3. 获得一个 performance-accepted checkpoint，并在新的独立 calibration designs 上得到
   exact-state-bound、可迁移的 applicability capability；失败时继续显式 uncalibrated。
4. 向[当前汇总 TODO](20260828_121904_surrogate-qnehvi-remaining-work.md) 提供 typed readiness
   所需的真实证据，但不在本文中绕过 qNEHVI 自己的 acquisition/optimization gate。
5. 如果证据表明简单 shared isolation 或其他较简单基线优于 MoE/gated residual，允许选择
   更简单方案并退役无效复杂度；目标是稳健性和可验证性，不是必须保留某种网络结构。

## 后继 architecture 的有界方向

### 1. Regime-specialized / Mixture-of-Experts 候选

- v5 已满足原预注册中的 MoE 比较触发条件。下一 gate 可以比较一个有界候选，而不是并行
  发散实现多种复杂架构：
  - smooth/clean expert：优先保持正常物理结构、低泄漏和合理 roughness；
  - chatter/failure expert：学习异常/失效 regime 的真实结构，不把它平滑成 clean；
  - task-neutral router/gate：只消费版本化 quality/applicability features 或 predictor state，
    不消费 current cost 作为标签；
  - 明确的 shared base 或共享低层 codec，只有预注册消融证明不会重新引入负迁移时才保留。
- 首轮必须在 pre-access plan 中选择 hard routing、soft mixture 或 shared-base-plus-experts 的一项
  主候选，并冻结 routing temperature、capacity/fallback 和 expert-collapse 诊断。不要看到
  test 后在这些形式之间切换。
- router 低置信度、缺少合法 diagnostics 或遇到未知 regime 时必须有 fail-closed 行为。可选
  方案包括输出共享保守基线并禁止 exploitation，不能静默把所有样本路由到最乐观 expert。
- smooth/chatter/failure 标签仍由 task policy 产生；package core 只实现通用多 regime、权重、
  routing 和 identity 机制。不得把两个 Chrono 类别永久写成全项目唯一 taxonomy。

### 2. 必需的简单对照

- 继续保留 v5 四臂，至少把 `shared-latent-isolation` 作为直接基线；新 MoE 不得只与失败的
  gated arm 比较。
- 使用
  [PCA/SVD 基线模块 TODO](20260828_081523_pca-svd-baseline-surrogate-module.md)
  中严格区分的 oracle reconstruction 与 deployable predictor，诊断“字段本身可低秩表示但
  parameter-to-latent 不可学”与“表示空间本身不合适”。oracle 结果不能进入候选选择。
- conditional-INR 继续作为生产非劣基线；所有 case/train-size 使用相同 real design 集、
  current cost、seed registry 和 metric implementation。
- 若 shared isolation 或 PCA/SVD deployable baseline 已满足门槛，而 MoE 没有，完成路线可以
  选择较简单模型；不得为证明 MoE 必要而删除更强的简单 arm。

### 3. 数据与 label 计划

- 1929-row noise audit 永远只是描述性动机证据，不能回填阈值、训练 router 或充当最终 test。
- 既有 development data 可以在新预注册允许时用于 successor training/validation；已经访问过
  的 v6/v7 offline-test 只能作历史描述，不能再被称为新 architecture 的 blind final test。
- successor 的最终科学验收需要新的、在 architecture/rank/routing/threshold 冻结后才访问的
  independent test designs。需要真实 simulator 生成时，必须先给出精确 cell/design 数、预计
  时间和资源，并按用户运行权限另行获批。
- Chrono applicability calibration 必须改善 19/181 的严重不平衡。优先采用在 design space
  中预先声明、与结果隔离的 stratified/boundary acquisition，主动覆盖 release transition、
  contact/recontact 边界和 smooth 区域；不能跑完后按 outcome 丢弃 chatter 样本来伪造平衡。
- train/validation/calibration/test 都按 design row 分割，同一 design 的所有字段/坐标只属于
  一个 partition。任何 oversampling/weighting 只改变训练贡献，不把重复行计作新增独立证据。

### 4. 指标与阈值政策

- 继续报告 v5 的全部 representation 与 quality/regime 指标：field-macro MAE/RMSE、current-cost
  MAE、最差字段 guard、clean leakage、roughness inflation、四个 strata、AUPRC、Brier、ECE
  和全部消融。
- v5 的 `0.35` leakage、`2.0` roughness、`>=0` gated-vs-shared improvement、representation
  noninferiority 等历史门槛不得被修改。新 successor 可以在新文件中沿用或制定更严格门槛；
  若因新数据/metric 语义确需不同门槛，必须在独立 test access 前给出非结果导向的物理/统计
  理由，且不能用它改写 v5 结论。
- 新增 MoE/router 专用诊断：expert utilization、collapse rate、routing entropy/confidence、
  smooth-to-failure 和 failure-to-smooth confusion、boundary calibration、每 expert 的字段误差
  与跨 regime degradation。不得只报总体平均来隐藏少数 regime 崩溃。
- 资源指标至少包括训练/推理墙钟、CPU/GPU 峰值内存、checkpoint 大小、每次 candidate
  inference 成本和相对真实评估成本。复杂架构必须证明其收益值得新增工程成本。
- missing/non-finite evidence、缺少必要 class、signature drift 或任一必需 arm 缺失均 fail
  closed。不得通过降低门槛、合并 strata 或隐藏失败 seed 完成 TODO。

## 实施阶段与 gates

### Gate 0：补录验证与 successor 预注册

- 用只读检查复核本文列出的当前 code、v2--v5/v8 receipts、hash、数据 locator 状态和已知
  19/181 imbalance；将任何已经变化的事实显式更新为新版本，而不是修改旧文件。
- 在首次 successor test/calibration access 前冻结：主 architecture、对照臂、训练规模、
  split、seeds、router/experts、metrics、门槛、资源限制、stop/failure rule 和允许的迭代次数。
- Gate 0 只允许读取既有 development/历史描述性 evidence；不启动 simulator，不打开新的
  blind test locator。

### Gate 1：通用 regime-specialized 机制

- 在 `yadof.surrogate` 的现有 quality/schema/semantic identity 边界上实现通用 experts/router，
  复用当前 design-by-field loss、structured rawData 和 checkpoint machinery。
- 增加 synthetic neutral tests，证明 expert 隔离、clean path 不受 abnormal residual 影响、
  router fallback、field completeness、member identity、checkpoint recovery 和 lazy import。
- 不删除现有 MVP；新 component/method version 与其 state 分离，便于冻结消融和恢复。

### Gate 2：development-only 模型选择

- 只在合法 training/development-validation designs 上执行预注册矩阵；所有 arm 保持同 split/
  seeds，failed arm 也发布结果。
- 先判断 simple shared isolation/PCA-SVD/conditional-INR 与一个主 MoE 候选的相对表现，再按
  预注册 stop rule 决定接受、拒绝或启动一个新的 successor 版本。
- 如果主候选仍发生 clean leakage、roughness inflation、expert collapse 或 worst-field
  failure，冻结失败并停止；不得在同一预注册中反复调到通过。

### Gate 3：独立 test 与 architecture acceptance

- 只有 Gate 2 通过预先冻结的 development 门槛后，才访问新的 blind test designs。
- test 只做一次冻结模型评估，不再调 architecture、rank、router 或 threshold。必须同时满足
  representation、quality/regime、worst-field 和资源 gate 才能标记
  `performance_accepted=true`。
- 失败时保留 module 作为 experimental baseline，readiness 继续 blocked；后续变化创建新的
  preregistration/TODO 版本。

### Gate 4：独立 applicability/posterior calibration

- 按[当前汇总 TODO](20260828_121904_surrogate-qnehvi-remaining-work.md) 的 exact-state 契约，
  为 performance-accepted exact checkpoint 建立新的 pre-access plan，使用未参与训练/模型
  选择的 calibration designs。
- 证明每 fold/class 支持度、AUPRC、Brier、ECE/reliability、boundary behavior、member pairing
  和 rawData/current-cost posterior metrics。artifact 绑定 state/strategy/schema/policy/label/
  head/loss/training provenance。
- calibration 失败时只发布 `uncalibrated`、identity scaling 和 `transferable=false`；不得复用
  v8 失败 artifact 或把它迁移到 successor。

### Gate 5：qNEHVI/release handoff

- 向当前汇总 TODO 提供 typed performance/calibration/applicability capability，由其另行冻结
  threshold、boundary width、低/边界 real exploration 和 acquisition benchmark。
- 即使本文通过，也不自动改变 default GPSAF + conditional-INR，不自动运行 formal seven-arm
  suite；当前汇总 TODO 仍负责同预算 optimization、总工程成本和 Phase B/C release 决定。

## 验证要求

### 通用软件合同

- policy/version/diagnostic path/labels/weights/router/expert/loss 配置全部进入 semantic identity；
  task-specific callback 或未追踪阈值不能绕过 identity。
- no-policy 行为保持普通等权 field macro；未选择 successor 不加载其 optional backend，也不
  改变 conditional-INR、现有 CAE、GPSAF、viewer 或 checkpoint recovery。
- scalar、1-D、2-D 和显式 rank-3 fields 保持完整 selector/shape/dtype/axis/unit/metadata
  round trip；任何 expert 都不能只预测自己喜欢的字段再由别的 member 拼接。
- 同一 persistent posterior draw 中 router/applicability/expert/rawData identity 跨 candidate
  chunks、字段和 objectives 一致；permutation/chunk 只重排或分割结果。
- predicted rawData 不进入 recorder；真实候选继续走 common evaluator/finalizer，recording
  failure 保持 campaign-fatal。

### 科学与数据合同

- clean/chatter/failure/boundary 每层都有样本计数、设计 identity、字段覆盖和置信区间；不足
  时明确不可判定，不用总体均值代替。
- 所有必需 arm、seeds、1000/2000 train sizes 和三个代表性 cases 可复算；任何 exclusion 都
  带预注册原因。
- 训练和模型选择不读取 independent calibration/final test；artifact/receipt 记录 locator
  首次访问顺序、source/wheel/state hashes 与 simulator launch 情况。
- architecture acceptance、probability calibration、posterior decision 和 optimization quality
  是四个独立结论；一个通过不能替代另一个。

## 非目标

- 不做 rawData smoothing、frequency filtering、outlier deletion 或按 current cost 剔除设计。
- 不把 chatter/failure 当作需要修复的记录错误，也不改变 task `error_cost=1.0` 或 execution
  `inf` 语义。
- 不在 core 硬编码 Chrono field names、contact physics、release cutoff 或具体 design ranges。
- 不把未校准 classifier 分数、training loss、member variance、reconstruction residual 或 cost
  当成 exploitation readiness。
- 不修改 v2--v10 冻结文件、receipt/hash 或历史失败结论，不复用已访问的 offline-test 作为
  successor blind test。
- 不同时实现无界数量的 denoiser、MoE、diffusion、GP、full-model ensemble 或 posterior
  backend；每个新增候选必须由前一 gate 的证据和新预注册触发。
- 不因本文创建而授权真实 simulator campaign、长训练、formal qNEHVI benchmark、默认配置
  迁移或发布推荐。

## 与其他 TODO 的关系

- [当前 surrogate/qNEHVI 汇总 TODO](20260828_121904_surrogate-qnehvi-remaining-work.md) 拥有
  hierarchical CAE 的整体 representation/coordinate gate、exact-state calibration、qNEHVI
  exploitation/exploration 和正式同预算 release 链。本文单独拥有最初未落盘的抗噪声意图、
  regime-specialized successor 和 clean-vs-abnormal 验收；两者共享证据时必须引用同一 receipt，
  不能给同一次实验两个矛盾结论。旧 082608/082609/082611/082612 文件仅是可选历史资料。
- [PCA/SVD TODO](20260828_081523_pca-svd-baseline-surrogate-module.md) 提供简单表示和 deployable
  predictor 对照，不承担 regime probability 或 posterior 授权。

## 完成规则

只有同时满足以下条件，本 TODO 才可移入 `dev_doc/obsolete/`：

- 原始抗噪声要求、当前已实现 MVP、v5/v8 失败和 successor 范围在 current docs/change
  records 中保持一致，不再依赖聊天记录解释；
- 一个重新预注册的 simple baseline 或 regime-specialized successor 在新的 blind evidence 上
  同时通过 representation、clean leakage、smooth roughness、worst-field、strata 和资源 gate；
- 所有必需四臂、simple baselines、主 successor、seeds 和失败结果均公开，未通过删除样本、
  修改 rawData/cost、test 调参或放宽历史门槛制造成功；
- performance-accepted exact checkpoint 在独立、类别支持充分的 calibration designs 上获得
  可验证 applicability artifact，或项目明确决定不需要 applicability 并用证据说明替代边界；
- successor 的 public component/state/checkpoint/identity、lazy dependency、rawData round trip、
  posterior coherence（若提供）、recovery 和 recorder non-entry 已通过 generic tests；
- architecture、surrogate/project/test blueprints、terminology、适用 user docs、benchmark
  preregistration plans/thin adapters 和 change records 与最终实现同步；validator 不得比较
  当前 source/wheel/artifact digest；
- 按届时开发指南完成 wheel build、force reinstall、import-origin、focused/full package tests
  和 benchmark automation tests；真实/长时间执行另有明确授权与结果记录；
- 向当前 surrogate/qNEHVI 汇总 TODO 的剩余 handoff 已更新。若 anti-noise architecture 已完成但后续
  acquisition/release 仍未完成，只能在对应 TODO 中保留剩余工作，不能把它们从文档链中
  静默删除。
