# 验证、迁移并渐进发布新 rawData 拟合器与 qNEHVI

## 背景和目的

新架构跨越 surrogate representation、联合 posterior、current-cost projection、acquisition、
strategy state、checkpoint 和 viewer。单元测试能够证明格式，却不能证明 1000--2000 个
真实设计时有更好的拟合或优化结果。本工作包定义统一验收与 opt-in 发布门槛，避免模块
仅因“能运行”就成为推荐方案。

用户的产品优先级是：

- 不要求小样本性能；
- 真实评估通常小于一核时，因此代理总开销必须实际测量；
- 必须利用完整 rawData，不接受生产 `parameters -> cost` 直拟合；
- 新拟合器和 qNEHVI 都作为新模块加入；现有 conditional-INR 和 GPSAF 保留。
- 重复评估随机性基本不大；首轮 posterior/acquisition 验收按近似确定性、固定真实
  Pareto baseline 和 zero-observation-noise 解释进行。

## 依赖和执行顺序

本验收工作不是最后才执行的串行尾项。按以下 gates 推进；每一 gate 都可以停止、修订
下一步或证明某个复杂结构不值得实现：

0. **先做 schema inventory 和 benchmark preregistration**：冻结代表性 fields、split、
   metrics、资源环境、接受/停止条件和对照矩阵。
1. **最小联合协议**：完成持久 function sampler、candidate chunk invariance，以及复用
   `CostInterpreter` 的薄 cost projector。
2. **最早垂直切片**：立即完成
   [conditional-INR adapter](20260827_082610_conditional-inr-posterior-adapter.md) 和 fake
   sample-backed qLogNEHVI backend spike，验证库/API/数值边界。
3. **最小 CAE**：per-field codecs + shared parameter predictor + predictor-only ensemble；
   首个 MVP 同时支持 stable-selector 显式分组，但不加入 attention/native Conv3d。
4. **full-grid 质量 gate**：1000/2000-design 表示与 current-cost 指标先过门槛，再实现
   coordinate trunk。
5. **校准/复杂 posterior gate**：只在 held-out decision evidence 要求时增加 full-model
   ensemble、attention 或连续 weight posterior。
6. **opt-in strategy/真实预算验证**：完成独立 qNEHVI strategy 和同预算真实比较。

对应的独立 handoffs 仍是：

- [联合 posterior 契约](20260827_082607_joint-rawdata-posterior-contract.md)
- [分层 CAE 拟合器](20260827_082608_hierarchical-cae-rawdata-surrogate.md)
- [posterior 抽样与校准](20260827_082609_coherent-posterior-sampling-calibration.md)
- [qNEHVI strategy](20260827_082611_qnehvi-acquisition-strategy.md)

可以先在 frozen recorded rawData 上离线推进。任何新的真实 simulator campaign 都受当时
user documentation 的成本/风险授权约束；本 TODO 不自动授权数千次真实评估。

## Gate 0 执行状态（2026-08-27）

Gate 0 已冻结为可校验的仓库工件：

- [入口与边界](../../benchmark_automation/preregistrations/20260827-new-surrogate-qnehvi/README.md)
  说明这些文件不是可执行 suite 或结果；
- [schema inventory](../../benchmark_automation/preregistrations/20260827-new-surrogate-qnehvi/schema_inventory.json)
  固定三个 case 的 selector、main key/shape/dtype、axis 值和 digest、字段/axis bytes、参数
  语义、objective width、天线 rank-3 layout、显式 S11/gain groups、task fingerprint 和直接
  source hash；
- [benchmark preregistration](../../benchmark_automation/preregistrations/20260827-new-surrogate-qnehvi/benchmark_preregistration.json)
  固定 design identity、2800 个 unique compatible designs/case 的 design-level split（嵌套
  1000/2000 train）、互斥 seeds、完整对照矩阵、指标、注册资源环境、停止条件和各 gate
  输入；
- [data availability audit](../../benchmark_automation/preregistrations/20260827-new-surrogate-qnehvi/data_availability_audit.json)
  固定合法 provenance 要求并明确当前缺口；
- [threshold template](../../benchmark_automation/preregistrations/20260827-new-surrogate-qnehvi/acceptance_thresholds.template.json)
  固定数值门槛的字段、取证分区、制定规则和 pass logic。数值有意保持 `null`，必须在
  validation/calibration/pilot 后、读取 test/formal results 前另行封印；
- `validate.py` 只读核对上述 hash、baseline/task/source、field/axis/parameter、split 和 seed
  契约，不启动 simulator。首次执行通过，且正确报告 `formal_test_ready=false`。

实际 automation 契约也已复核：当前 `performance` 仍只有 NSGA-III 与
GPSAF + conditional-INR 两个 arms、一个 seed、每 cell 100 × 20，总计 12000 次 attempted
evaluations；`structural-full` preflight 在安装的 yadof 0.4.1 上 13/13 通过。三个 editable
baseline manifest 都是 0 records/0 checkpoints，`history_snapshots/` 选择 `empty`；README
中的历史摘要在本 checkout 默认 runs root 没有可 inspect 的 run spec，因此不是可用训练
evidence。Gate 0 没有启动真实 simulator campaign，也没有把 smoke shape/cost 冒充设计行。

整个 TODO 仍保持 active，不能移入 obsolete。下一执行单元只能是
[联合 rawData posterior 契约](20260827_082607_joint-rawdata-posterior-contract.md)的轻量
sampler/projector 与 fake schema tests：开始前必须从 committed tree 通过 Gate 0 validator，
保持 inventory 不变（否则新建 preregistration 版本），并且不得作 1000/2000-design 拟合、
校准或优化性能结论。合法 frozen dataset 只在 Gate 4 前成为硬依赖；正式 test/真实比较
还必须先封印数值 thresholds 并获得对应 campaign 授权。

## 基准数据要求

### 代表性数据

- 首版 schema 直接参考当前 benchmark baselines。已核对的 main arrays 为：

  | case | fields / main key | shapes |
  |---|---|---|
  | SAW | `s21_db.npz/data`、`s11_db.npz/data` | 2 × `[1201]` |
  | Chrono | 9 个 scalar `*.npz/values`，7 个 phase-curve `*.npz/values` | 9 × `[]`，7 × `[513]` |
  | synthetic antenna | 3 个 S11、3 个 gain、3 个 axial-ratio，均为 `*.npz/data` | 3 × `[5]`，3 × `[1,73,73]`，3 × `[5,73,73]` |

  这些 main arrays 都是实数 `float64`；axes 由 baseline task 生成固定 regular grids。
- 天线 case 用于已知强、弱关系和显式 S11/gain group 消融；SAW 与 Chrono 提供不同 task
  family、标量和长 1-D 曲线，避免架构只对天线字段命名和网格形状有效。
- 使用 schema-compatible 完整 rawData，不提前裁成 cost windows。cost 仅在评估指标和
  acquisition projection 阶段通过当前 task callback 得到。
- 记录参数维度、连续/离散语义、每字段 shape/axes/bytes、设计数、生成成本、缺失/无效
  行处理和 task snapshot identity。
- baseline templates 自身记录数为零，`baseline.json` 的 smoke shapes 只是 schema 证据。
  1000/2000-design 数据必须来自合法 frozen recorded evidence 或另行获批的生成 campaign，
  不能把 template shape 清单误报成训练集。
- 首版兼容矩阵固定 selector set、shape、axis arrays 和 main dtype representation；complex、
  missing field、variable shape/axes 与 native Conv3d 是后续能力，不进入首轮上线门槛。

### Split 和规模

- 按 design row 固定 train/validation/calibration/test split；同一 design 的全部字段和
  坐标只能出现在一个 split。
- 主要验收点为约 1000 和 2000 个训练 designs；可增加 300--500 的 warm-up 诊断，但
  不要求新架构在小样本胜出。
- 所有模型使用相同兼容设计集合、相同 split、相同 current cost interpretation 和一组
  预登记 seeds。
- benchmark 在看 test 结果前冻结模型选择、calibration 和 acceptance thresholds。

## 对照矩阵

至少比较：

1. 当前 conditional-INR + GPSAF，作为不回归基线；
2. 新 hierarchical CAE 的确定性 mean prediction，用于隔离 representation 改善；
3. 新 CAE + joint posterior + qNEHVI，作为目标组合；
4. conditional-INR posterior adapter + qNEHVI，作为兼容性/有限支持消融，不作为默认
   推荐；
5. 现有 non-surrogate pymoo real search，在相同真实评估预算下作为优化基线；
6. PCA/SVD reconstruction baseline，仅用于表示难度、秩和数据管线 sanity check。

7. **新 CAE + GPSAF（必需消融）**，用于区分 representation 改善与 acquisition 改善；
   不能把它降为可选项，否则“新 CAE + qNEHVI”胜负无法归因。

不得把直接
`parameters -> cost` 模型作为生产候选；如研究人员以后希望把它加入离线参照，需单独
明确其只读诊断地位，不能改变 rawData-first 接受标准。

## 指标

### 拟合质量

- 每字段 physical-unit MAE/RMSE 和 standardized error；
- field-macro aggregate，不能按总网格点数加权；
- 对曲线/场的峰值位置、梯度、频谱或结构指标，仅在其 task-neutral 定义预先登记时使用；
- 完整 predicted rawData 经 current cost 后的 objective MAE/rank correlation；
- Pareto dominance/ranking consistency；
- global-only、global+explicit-group、完全独立字段和无 coordinate-consistency 的消融。
- rank-3 antenna fields 的显式 `Freq` channel + `Phi/Theta` Conv2d layout，与未声明 layout
  的拒绝行为；不默认把小轴猜成 channel。

### 后验质量

- rawData 与 cost 层的 held-out coverage/calibration curve；
- multivariate score 和跨字段 correlation/covariance preservation；
- finite posterior 的 `unique_support`、所有 posterior 的有效 draw 比例和 projection
  failure；
- 确定性任务中是否错误地产生 per-`x` 独立噪声；
- calibration 前后 qNEHVI decision quality，而不是只追求边际 coverage。

### 优化质量

- 相同真实 evaluation count 下的 cumulative hypervolume（默认 reference `(1,...,1)`）；
- 多 seed 的中位数、分散度和置信区间；
- 达到预登记 HV/目标阈值所需真实评估数；
- exploration 命中、重复候选、invalid/failed evaluation 和 fallback 频率；
- 对每个候选保存“采集前 prediction/acquisition，之后 real result”的紧凑配对诊断，
  但不保存 predicted rawData 为 durable evidence。

### 工程成本

- 数据装载、CAE 三阶段训练、posterior draw、rawData-to-cost projection、qNEHVI 选择的
  分项墙钟；
- CPU、GPU、RAM/VRAM 峰值、checkpoint 大小和恢复时间；
- 与一次真实评估和整代真实评估耗时的比例；
- candidate pool/draw count 扩展曲线，确认 streaming 后没有 rawData 乘积常驻内存。
- candidate chunk size/order 扩展曲线和逐点一致性，确认同一 sampler 的 draw identities
  不因分块而变化。

## 验收门槛的制定方式

在第一次正式 test/真实优化比较前，基于 validation/pilot 明确写下数值门槛。至少包括：

- 1000 和 2000 design 下，新 CAE 相对 conditional-INR 的 field-macro rawData 和
  current-cost error 门槛；
- 允许单个字段退化的最大幅度，避免平均值掩盖 S11 或 gain 崩溃；
- posterior coverage/score，以及 finite posterior 的最小有效 unique support；
- qNEHVI 相对 GPSAF/non-surrogate baseline 的 HV 改善或非劣门槛、seeds 数和统计规则；
- 训练/采集 wall-clock、内存和失败率上限。
- 显式 group 相对 `groups=()` 的收益/最大允许退化，以及 group head 的参数量、墙钟和内存
  开销；默认不分组不承担 group-state 成本。
- coordinate trunk 的独立启动条件：full-grid CAE 先通过，且 viewer/off-grid 指标与资源
  预算已登记；未达到条件时延期 trunk，不推翻 rawData/qNEHVI 垂直切片。

本 TODO 不凭空指定百分比，因为尚无数据分布和硬件基线。门槛必须在 test 集和正式真实
campaign 结果揭晓前登记；看过结果后调门槛视为新实验，不算原验收通过。

推荐上线必须同时满足：

- rawData representation 有实证收益；
- joint posterior 至少达到预登记的 decision/calibration 门槛；
- qNEHVI 在相同真实评估预算下达到预登记优化门槛；
- 总代理计算开销与该任务的一核时以内评估成本相称。

任一项未通过时，保留模块为 experimental 或回到相应架构 TODO，不用 mean/min/max 或
直接 cost model 绕过失败。

## 渐进集成和迁移

### Phase A：离线和 shadow mode

- 从 frozen recorded evidence 训练/评估，不改变 campaign selection。
- 在现有运行中可记录有界的 shadow candidate rankings，但不提交额外真实评估、不写
  predicted rawData、不影响 GPSAF。
- 验证 checkpoint、viewer、summary/audit 和 current-cost reinterpretation。

### Phase B：显式 opt-in strategy

- workspace 仅通过 `submit/optimization.py` 显式选择新 component/strategy。
- 新 strategy 使用独立 semantic namespace；切回 GPSAF 恢复其原有 artifacts。
- cold start、posterior support 不足、backend 缺失和数值失败都有可见 fallback/diagnostic。
- 首版明确拒绝 pending/outcome-constraint 配置，使用 fixed real Pareto baseline；有限
  `error_cost=1.0` 仍按有效最差 cost 处理。

### Phase C：是否推荐默认

- 当前工作没有授权替换 package template 的 GPSAF 默认。
- 即使基准通过，也只形成“可推荐 opt-in”结论。任何默认组合变化需要后续明确用户决定、
  user docs/模板迁移和兼容评审。

## 文档、工具和安装包验收

- architecture 更新 surrogate/posterior/acquisition 数据流，但保持 rawData source truth 和
  common real-evaluation/recording 边界。
- blueprints 覆盖新的 public factories、private packages、I/O shape、lazy imports、state 和
  viewer adapter。
- terminology 定义联合 rawData posterior、function draw、explicit rawData group、
  posterior-assisted/qNEHVI strategy 和 support diagnostics。
- user docs 说明如何在 `submit/optimization.py` 选择新组合、分组默认含义、依赖 extra、
  warm-up/fallback、计算开销和实验性质。
- surrogate viewer 的 stored-grid/off-grid 行为在新 checkpoint 上有视觉/数值测试；不要求
  修改现有 conditional-INR viewer 路径。
- 按开发指南完成 wheel build、force reinstall、import-origin、lazy optional dependencies、
  installed-package tests 和 artifact membership 检查。

## 自动 TODO 的范围检查

实施各阶段时，对实际进入范围的代码执行当时 active automatic toDo 的有界匹配检查；
不要因为本计划跨模块就主动扩大到无关 recorded-data 或全仓库清理。可靠 recording 的
population-boundary durability 仍是所有真实优化验收的硬契约。

## 完成规则

- 预登记 benchmark plan、数据 provenance、seeds、门槛和资源环境已保存；
- 所有对照在 1000--2000 design 目标规模完成，结果可复现并区分 representation、
  posterior 和 acquisition 的贡献；
- 新组合满足已登记的拟合、校准、优化和工程成本门槛，或被明确保留为 experimental/
  不推荐并记录失败原因；
- 现有 conditional-INR + GPSAF 行为无回归；
- 选择、回退、viewer、checkpoint、strategy switch 和 installed wheel 完成验收；
- 相关实现 TODO 均已完成或根据证据修订，随后把本 TODO 及已完成工作包移入 obsolete。
