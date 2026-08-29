# PARKED — 抗噪声 Hierarchical CAE 扩展与独立验收

## 状态、来源与当前结论

- 本文是已暂停的手动 TODO，同时补录一项此前只通过 Codex session 转交、没有独立 TODO
  落盘的用户要求。原要求由 session `01a04242-14f1-7162-8c38-c44a8b02fe12` 发送给
  hierarchical CAE 实施 session；session ID 只作补充 provenance，本文必须在没有聊天记录时
  也能独立执行。
- 2026-08-29 用户明确决定暂时搁置抗噪声扩展。暂停期间不得执行本文 Gate 0--5、
  新建 regime-specialized/MoE 实现、启动 simulator/长训练、访问新的 blind evidence、重新校准
  或进入 formal qNEHVI benchmark。阅读本文不构成重新激活授权。
- 用户随后进一步明确：抗噪声路线只考察 Hierarchical CAE 的可选扩展性，不是基础
  Hierarchical CAE 的 performance acceptance、posterior readiness、qNEHVI 或发布指标。
  本文的暂停、失败、缺少证据或未完成状态都不得阻塞基础 Hierarchical CAE 路线；本文通过
  也不得替代基础路线自己的验收。
- 相邻的 Hierarchical CAE 数据筛选重构已经完成：`hierarchical_cae()` 默认
  `data_filter_mode="none"`，当前显式可选机制是
  `data_filter_mode="frequency"` 与 `frequency_filter=FrequencyFilter(...)`。该重构只建立
  component-local 可选接口和当前实现身份，不构成抗噪声扩展恢复、扩展验收或该变体的
  posterior exploitation 授权。
- 原要求不是“把曲线平滑一下”。1929-row Chrono 描述性审计显示 roughness 与高 cost、未
  release、反复 contact/recontact 等状态相关，更符合**参数诱发的 chatter/failure regime**，
  不是独立同分布 measurement noise。审计中的 four-cost mean 与 curve roughness Spearman
  相关约为 `0.4694`；这些数值只解释工作动机，不是验收阈值，也不能证明 roughness 导致
  cost 变差。
- 原要求中的抗噪声扩展 MVP 已经并入
  [archived hierarchical CAE plan](../obsolete/20260827_082608_hierarchical-cae-rawdata-surrogate.md)、
  代码、测试和
  Gate 0 v2--v5 预注册：版本化 quality/regime policy、design × field 稳健聚合、shared-token
  隔离、gated field-private residual、未校准 applicability head，以及对 calibration/qNEHVI/
  release 的 handoff 都已实现。
- 但工程完成不等于扩展能力的科学完成。Gate 0 v5 已冻结
  `representation_passed=false`、`quality_regime_passed=false`、
  `full_grid_gate_passed=false`：gated MVP 对 clean target 的泄漏和 smooth roughness 均超限，
  且比 shared-latent isolation 更差。因此本文以 `PARKED` 状态保持 active，保存未来可能恢复
  的独立扩展 handoff；不得重复声称现有 MVP 尚未实现，也不得把失败结果改写成成功，更不得
  把这些扩展指标追溯为基础 Hierarchical CAE 的 blocker。

## 扩展边界、暂停与重新激活条件

- 暂停不是完成或取消。本文管理的抗噪声扩展仍未通过；其 v8 calibration 继续为
  `uncalibrated`、`transferable=false`，因此这个抗噪声变体自身没有 exploitation readiness。
  基础 Hierarchical CAE 当前仍为 `experimental / performance-not-accepted`，但那是由其独立
  representation/prediction、worst-field、coordinate、resource 和 posterior 证据决定，不是
  由本文状态决定。
- [Hierarchical CAE/qNEHVI 总控 TODO](20260828_121904_surrogate-qnehvi-remaining-work.md)
  不把本文列为当前执行步骤，也无需等待本文恢复或通过。总控仍须为基础 Hierarchical CAE
  取得独立的 performance-accepted checkpoint、exact-state calibration 和 typed readiness，
  但其中不得包含本文的 clean leakage、smooth roughness、regime classification 或 class-support
  gate，除非用户以后为某个抗噪声变体单独批准这些扩展指标。
- 只有用户以后明确要求恢复抗噪声扩展，本文才重新成为执行入口。恢复时必须先复核届时
  `frequency` 筛选 API、current architecture、已有数据/receipt 和其他活动 TODO，并在访问
  新 test/calibration evidence 前建立新的 preregistration 与 semantic namespace。
- 如果用户以后批准另一种抗噪声 architecture，应在本文的新预注册或独立扩展 TODO 中明确
  身份；不得静默把它当作基础 Hierarchical CAE 的必要后继，也不得把默认无筛选接口
  当作抗噪声扩展证据。
- 除“状态、暂停边界、当前基线和冻结失败结论”外，下文目标、候选、gates 与验证要求均为
  **重新激活后**的保留计划，不是当前执行指令。

## 原始用户要求的完整补录

以下要求是已经确定的抗噪声扩展边界；重新激活后的实现必须继续遵守：

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
9. 只有在重新激活范围明确要求把抗噪声变体用于 posterior/qNEHVI 或单独发布时，抗噪声结果
   才需要交接给该变体自己的 calibration、applicability/exploration 和 release gate；任何
   扩展上游失败都必须对该变体 fail closed，但不得传播为基础 Hierarchical CAE blocker。

## 已完成、必须保留的当前基线

以下内容已经实现，是未来扩展工作的对照和复用输入，而不是待重新发明的范围：

- `yadof.surrogate.hierarchical_cae.data_filtering` 的 component-local
  `frequency` filter/assessment、显式 assessment 优先级、声明式
  diagnostic rules、可选 frequency/morphology fallback、field/shared weights、regime labels 和
  applicability 类型；
- hierarchical CAE 的 design-by-field loss、shared-token masking、field-private base/residual
  decoder、regime-gated residual、predictor applicability head、完整 rawData/current-cost 路径、
  checkpoint identity 和 coherent finite member draws；
- `无门控 / 仅稳健加权 / shared-latent 隔离 / gated-private-residual` 四臂消融；
- Gate 0 v2 的抗噪声预注册、v3 dataset seal、v4 116-cell plan、v5 development-validation
  thresholds/result，以及 v8 的独立 calibration framework；
- 已封存的 3-case 数据：每个 case 2800 designs，合计 development 6600、calibration 600、
  offline-test 1200；现有 partition 和 receipt 不得重写。

当前失败证据是未来抗噪声扩展设计的最低诊断输入：

| 指标 | train=1000 | train=2000 | v5 guard |
|---|---:|---:|---:|
| Chrono clean-target 高频泄漏率 | 0.37714 | 0.36857 | 最大 0.35 |
| smooth predicted/real roughness median ratio | 2.4013 | 2.3137 | 最大 2.0 |
| gated 相对 shared-isolation 泄漏改善 | -5.60% | -2.38% | 不得小于 0 |
| Chrono 最差单字段 RMSE ratio vs conditional-INR | 2.64995 | 3.85268 | 最大 1.25 |

classifier validation diagnostics 自身曾通过 AUPRC/Brier/ECE 门槛，但不能抵消上述表示、泄漏
和 roughness 失败。v8 又显示 Chrono calibration labels 只有 19 smooth / 181
chatter-or-failure，预注册的两折 minimum-class-count 无法满足，两个 applicability fits 均
fail closed。未来抗噪声变体如果声称提供相应能力，必须同时解决 representation
contamination 和独立概率校准证据不足，不能只优化 classifier 分数；这些结论不参与基础
Hierarchical CAE 的验收。

## 重新激活后的目标

1. 建立一个有界、可解释、重新预注册的 regime-specialized 扩展变体，使 smooth/clean
   表示不再因 chatter/failure 训练发生负迁移，同时完整保留异常 regime 的物理 rawData。
2. 用相同 design-level split 和 field-macro 口径证明改善来自 architecture，而不是删除困难
   样本、改变 cost、泄漏 test、少报失败 arm 或更换统计口径。
3. 获得一个抗噪声扩展自身接受的 checkpoint；只有恢复范围包含该变体的 posterior/qNEHVI
   使用时，才在新的独立 calibration designs 上要求 exact-state-bound、可迁移的
   applicability capability，失败时继续显式 uncalibrated。
4. 向
   [Hierarchical CAE/qNEHVI 总控 TODO](20260828_121904_surrogate-qnehvi-remaining-work.md)
   提供可选抗噪声变体 typed readiness 所需的真实证据，但不在本文中绕过 qNEHVI 自己的
   acquisition/optimization gate，也不改变基础 Hierarchical CAE 的 readiness。
5. 如果证据表明简单 shared isolation 或其他较简单基线优于 MoE/gated residual，允许选择
   更简单方案并退役无效复杂度；目标是稳健性和可验证性，不是必须保留某种网络结构。

## 重新激活后的扩展 architecture 有界方向

### 1. Regime-specialized / Mixture-of-Experts 候选

- v5 已满足原预注册中的 MoE 比较触发条件。重新激活后的下一 gate 可以比较一个有界候选，
  而不是并行
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
- 既有 development data 可以在新预注册允许时用于扩展变体 training/validation；已经访问过
  的 v6/v7 offline-test 只能作历史描述，不能再被称为新 architecture 的 blind final test。
- 扩展变体的最终科学验收需要新的、在 architecture/rank/routing/threshold 冻结后才访问的
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
  noninferiority 等历史门槛不得被修改。新扩展变体可以在新文件中沿用或制定更严格门槛；
  若因新数据/metric 语义确需不同门槛，必须在独立 test access 前给出非结果导向的物理/统计
  理由，且不能用它改写 v5 结论。
- 新增 MoE/router 专用诊断：expert utilization、collapse rate、routing entropy/confidence、
  smooth-to-failure 和 failure-to-smooth confusion、boundary calibration、每 expert 的字段误差
  与跨 regime degradation。不得只报总体平均来隐藏少数 regime 崩溃。
- 资源指标至少包括训练/推理墙钟、CPU/GPU 峰值内存、checkpoint 大小、每次 candidate
  inference 成本和相对真实评估成本。复杂架构必须证明其收益值得新增工程成本。
- missing/non-finite evidence、缺少必要 class、signature drift 或任一必需 arm 缺失均 fail
  closed。不得通过降低门槛、合并 strata 或隐藏失败 seed 完成 TODO。

## 重新激活后的实施阶段与 gates

### Gate 0：补录验证与扩展变体预注册

- 用只读检查复核本文列出的当前 code、v2--v5/v8 receipts、hash、数据 locator 状态和已知
  19/181 imbalance；将任何已经变化的事实显式更新为新版本，而不是修改旧文件。
- 在首次扩展变体 test/calibration access 前冻结：主 architecture、对照臂、训练规模、
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
  预注册 stop rule 决定接受、拒绝或启动一个新的扩展版本。
- 如果主候选仍发生 clean leakage、roughness inflation、expert collapse 或 worst-field
  failure，冻结失败并停止；不得在同一预注册中反复调到通过。

### Gate 3：独立 test 与 architecture acceptance

- 只有 Gate 2 通过预先冻结的 development 门槛后，才访问新的 blind test designs。
- test 只做一次冻结模型评估，不再调 architecture、rank、router 或 threshold。必须同时满足
  representation、quality/regime、worst-field 和资源 gate，才能记录该抗噪声扩展的独立接受
  结论；该结论不是基础 Hierarchical CAE 的 `performance_accepted` 状态。
- 失败时保留 module 作为 experimental extension，只有该变体自己的 readiness 保持 blocked；
  后续变化创建新的 preregistration/TODO 版本。

### Gate 4：可选的独立 applicability/posterior calibration

- 仅当恢复范围包含该抗噪声变体的 posterior/qNEHVI 使用时，才按
  [Hierarchical CAE/qNEHVI 总控 TODO](20260828_121904_surrogate-qnehvi-remaining-work.md)
  的 exact-state 契约，
  为扩展验收通过的 exact checkpoint 建立新的 pre-access plan，使用未参与训练/模型选择的
  calibration designs。若扩展目标只包含确定性预测/诊断，本 Gate 明确记为不适用即可，不得
  因此阻塞基础 Hierarchical CAE 或扩展自身已批准的较窄目标。
- 证明每 fold/class 支持度、AUPRC、Brier、ECE/reliability、boundary behavior、member pairing
  和 rawData/current-cost posterior metrics。artifact 绑定 state/strategy/schema/policy/label/
  head/loss/training provenance。
- calibration 失败时只发布 `uncalibrated`、identity scaling 和 `transferable=false`；不得复用
  v8 失败 artifact 或把它迁移到新扩展变体。

### Gate 5：可选的扩展 qNEHVI/release handoff

- 只有重新激活范围包含该抗噪声变体的 qNEHVI/release 使用时，才向 Hierarchical CAE/qNEHVI
  总控 TODO 提供该变体的 typed performance/calibration/applicability capability，并为其另行
  冻结 threshold、boundary width、低/边界 real exploration 和 acquisition benchmark。
- 即使本文通过，也不自动改变 default GPSAF + conditional-INR，不自动运行 formal seven-arm
  suite；基础 Hierarchical CAE 的同预算 optimization、总工程成本和 Phase B/C release 决定
  可在没有本文扩展 arm 的情况下独立完成。

## 重新激活后的验证要求

### 通用软件合同

- policy/version/diagnostic path/labels/weights/router/expert/loss 配置全部进入 semantic identity；
  task-specific callback 或未追踪阈值不能绕过 identity。
- no-policy 行为保持普通等权 field macro；未选择抗噪声扩展不加载其 optional backend，也不
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

- 不做 rawData smoothing、按物理频率轴截取/删除 rawData、outlier deletion 或按 current cost
  剔除设计。
- 不把 chatter/failure 当作需要修复的记录错误，也不改变 task `error_cost=1.0` 或 execution
  `inf` 语义。
- 不在 core 硬编码 Chrono field names、contact physics、release cutoff 或具体 design ranges。
- 不把未校准 classifier 分数、training loss、member variance、reconstruction residual 或 cost
  当成 exploitation readiness。
- 不修改 v2--v10 冻结文件、receipt/hash 或历史失败结论，不复用已访问的 offline-test 作为
  扩展变体 blind test。
- 不同时实现无界数量的 denoiser、MoE、diffusion、GP、full-model ensemble 或 posterior
  backend；每个新增候选必须由前一 gate 的证据和新预注册触发。
- 不因本文创建而授权真实 simulator campaign、长训练、formal qNEHVI benchmark、默认配置
  迁移或发布推荐。

## 与其他 TODO 的关系

- [Hierarchical CAE/qNEHVI 总控 TODO](20260828_121904_surrogate-qnehvi-remaining-work.md)
  独立拥有基础 Hierarchical CAE 的 representation/prediction、worst-field、coordinate、resource、
  exact-state calibration、qNEHVI exploitation/exploration 和正式同预算 release 链。本文只拥有
  抗噪声扩展、regime-specialized architecture 和 clean-vs-abnormal 验收；它不是总控的执行
  前置，也不是解除总控 blocker 的候选步骤。本文暂停、失败、通过或取消都不改变基础链的
  gate 状态。
- 基础 Hierarchical CAE 不得把 clean leakage、smooth roughness、regime classification、
  applicability class balance 或本文的 MoE/router 指标列为必需验收条件。若未来 formal study
  主动加入一个抗噪声扩展 arm，它必须作为额外扩展比较单独报告，不得替换或阻塞基础七臂。
- 两个 TODO 共享某次底层 evidence 时必须引用同一 receipt，不能给同一次实验两个矛盾的事实
  结论；但各自基于不同预注册指标形成独立的验收结论。旧 082608/082609/082611/082612 文件
  仅是可选历史资料。
- [PCA/SVD TODO](20260828_081523_pca-svd-baseline-surrogate-module.md) 提供简单表示和 deployable
  predictor 对照，保持独立 active，不承担 regime probability 或 posterior 授权，也不因本文
  暂停而暂停。
- [Acquisition Capability Protocol TODO](20260828_091749_acquisition-capability-protocol.md)
  仍只由第二个真实 acquisition 或具体类型阻塞触发；本文暂停不是它的触发条件。

## 完成规则

暂停本身不是完成。本 TODO 只有满足以下两条路径之一才可移入 `dev_doc/obsolete/`：

1. 用户明确取消而不再只是暂时搁置这条抗噪声路线，且当前文档完整保留已实现机制、v5/v8
   失败和取消原因；由于本文不是基础路线 blocker，不要求 Hierarchical CAE/qNEHVI 总控先
   完成或接管本文范围；
2. 用户明确重新激活本文；此时只有同时满足下列完成条件，才能归档。

重新激活路径的完成条件：

- 原始抗噪声要求、当前已实现 MVP、v5/v8 失败和扩展范围在 current docs/change
  records 中保持一致，不再依赖聊天记录解释；
- 一个重新预注册的 simple baseline 或 regime-specialized 扩展变体在新的 blind evidence 上
  同时通过 representation、clean leakage、smooth roughness、worst-field、strata 和资源 gate；
- 所有必需四臂、simple baselines、主扩展变体、seeds 和失败结果均公开，未通过删除样本、
  修改 rawData/cost、test 调参或放宽历史门槛制造成功；
- 如果重新激活范围包含该变体的 posterior/qNEHVI 使用，扩展验收通过的 exact checkpoint 在
  独立、类别支持充分的 calibration designs 上获得可验证 applicability artifact；如果范围不
  包含，则明确记录 calibration/readiness 不适用；
- 扩展变体的 public component/state/checkpoint/identity、lazy dependency、rawData round trip、
  posterior coherence（若提供）、recovery 和 recorder non-entry 已通过 generic tests；
- architecture、surrogate/project/test blueprints、terminology、适用 user docs、外部 benchmark
  study requests/完整 optimization strategies 和 change records 与最终实现同步；benchmark 不得
  包含算法注册表或专项 adapter，validator 不得比较当前 source/wheel/artifact digest；
- 按届时开发指南完成 wheel build、force reinstall、import-origin、focused/full package tests
  和 benchmark automation tests；真实/长时间执行另有明确授权与结果记录；
- 若重新激活范围包含该抗噪声变体的 acquisition/release，向 Hierarchical CAE/qNEHVI 总控
  TODO 的可选扩展 handoff 已更新；否则明确记录该 handoff 不适用。无论哪种情况，都不得把
  本文完成状态传播成基础 Hierarchical CAE 的通过或失败。
