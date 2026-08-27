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

## 依赖和执行顺序

依次完成或达到可测试状态：

1. [联合 posterior 契约](20260827_082607_joint-rawdata-posterior-contract.md)
2. [分层 CAE 拟合器](20260827_082608_hierarchical-cae-rawdata-surrogate.md)
3. [posterior 抽样与校准](20260827_082609_coherent-posterior-sampling-calibration.md)
4. [conditional-INR adapter](20260827_082610_conditional-inr-posterior-adapter.md)
5. [qNEHVI strategy](20260827_082611_qnehvi-acquisition-strategy.md)

可以先在 frozen recorded rawData 上离线推进 1--4。任何新的真实 simulator campaign 都受
当时 user documentation 的成本/风险授权约束；本 TODO 不自动授权数千次真实评估。

## 基准数据要求

### 代表性数据

- 至少包含一个同时有 1-D 和 2-D rawData 的任务，且已知存在强、弱和近似独立的字段
  关系；天线示例应覆盖 S11、gain 和 axial ratio（若届时有可合法使用的数据）。
- 再包含至少一个不同 task family，避免架构只对天线字段命名和网格形状有效。
- 使用 schema-compatible 完整 rawData，不提前裁成 cost windows。cost 仅在评估指标和
  acquisition projection 阶段通过当前 task callback 得到。
- 记录参数维度、连续/离散语义、每字段 shape/axes/bytes、设计数、生成成本、缺失/无效
  行处理和 task snapshot identity。

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

可以增加“新 CAE + GPSAF”来区分拟合器和 acquisition 的贡献。不得把直接
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

### 后验质量

- rawData 与 cost 层的 held-out coverage/calibration curve；
- multivariate score 和跨字段 correlation/covariance preservation；
- `unique_support`、有效 draw 比例和 projection failure；
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

## 验收门槛的制定方式

在第一次正式 test/真实优化比较前，基于 validation/pilot 明确写下数值门槛。至少包括：

- 1000 和 2000 design 下，新 CAE 相对 conditional-INR 的 field-macro rawData 和
  current-cost error 门槛；
- 允许单个字段退化的最大幅度，避免平均值掩盖 S11 或 gain 崩溃；
- posterior coverage/score 和最小有效 unique support；
- qNEHVI 相对 GPSAF/non-surrogate baseline 的 HV 改善或非劣门槛、seeds 数和统计规则；
- 训练/采集 wall-clock、内存和失败率上限。

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
