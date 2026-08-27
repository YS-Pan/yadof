# 实现跨候选、跨字段自洽的后验抽样与校准

## 背景

- qNEHVI 需要联合 posterior samples，而不是 rawData 均值、字段逐点误差或 ensemble
  min/max。一个 draw 必须对应一个完整的可能函数。
- 目标任务通常是确定性或近似确定性的昂贵计算；在没有重复观测证据时，代理不确定性
  主要应解释为 epistemic uncertainty。简单地在每个 `x` 上独立加入 Gaussian latent
  noise 会制造不存在的 aleatoric noise，并破坏候选间相关性。
- 用户已确认重复评估的随机性基本不大。首版因此明确采用 zero-observation-noise/近似
  确定性解释；这不是从 ensemble spread 猜出的假设，也不要求为了 qNEHVI 重复采样同一
  设计来估计测量噪声。
- 新拟合器采用 global/group/private latent，从而有能力保持不同形状字段之间的联合
  变化；该能力只有在后验抽样保持同一 draw 身份时才有意义。
- 当前 conditional-INR 默认只有 3 个 ensemble members，其 min/max 是未校准诊断。
  新模型需要更诚实、可扩展的 posterior 支持和 held-out 校准证据。

## 依赖和目标

本工作依赖：

- [联合 rawData posterior 契约](../obsolete/20260827_082607_joint-rawdata-posterior-contract.md)
- [分层 CAE rawData 拟合器](20260827_082608_hierarchical-cae-rawdata-surrogate.md)

目标是为新拟合器提供一组联合、自洽、可复现且明确标注近似性质的 rawData function
draws，并通过 design-level held-out evidence 校准其用于采集的可靠性。

## 后验含义

### 函数抽样而不是逐点噪声

每个 draw 先抽取一个模型/权重状态，再用它一次性预测完整候选 batch：

```text
draw s:
  sampled model state theta_s
  X_all -> latent_s(X_all) -> all rawData fields_s(X_all)
```

`theta_s`、dropout/weight sample、global/group coupling 和 decoder 状态在同一 draw 的全部
候选间共享。禁止为每个候选重新选择 ensemble member，或用普通逐样本 dropout mask 冒充
联合函数抽样。

“一次性”描述的是同一函数状态，不要求把候选池同时放进内存。实现使用
[联合契约](../obsolete/20260827_082607_joint-rawdata-posterior-contract.md)中的持久 sampler：先固定
`theta_s`/member identities，再对任意 candidate chunks 调用 `predict()`。改变 chunk size、
顺序或候选排列不得改变同一 `x/draw_id` 的函数值。

同一 draw 中：

- `z_global` 共同驱动所有字段；
- 每个显式 `z_group` 共同驱动组内字段；
- `z_private[i]` 保持字段残差；
- 完整 rawData 经一次 current cost projection 后产生所有 objectives/constraints。

不得对每个目标分别挑“最好/最坏 member”；那会拼出任何模型都没有预测过的虚假样本。

### 确定性与观测噪声分开

- 默认假设真实 workflow 在给定参数下是确定性的，posterior 表示有限数据和模型不确定性。
- 只有 task contract 将重复评估或测量噪声明确建模后，才能增加 observation-noise 层。
- per-`x` 独立 latent residual 不能默认启用。如果引入 latent residual process，其随机系数
  必须在整个 candidate batch 中共享并定义清楚跨 `x` covariance。
- posterior diagnostics 明确记录是否包含 observation noise，qNEHVI 不得自行添加 jitter
  并把它解释为物理噪声；纯数值 jitter 必须单独标注。

## 推荐分阶段实现

### 第一阶段：predictor-only 经验 ensemble

- 先训练一套共享的 per-field encoders/decoders（codecs），再让每个 ensemble member 拥有
  独立初始化的 shared parameter-predictor backbone 及 global/group/private heads；必要时对
  完整 design rows 做 seeded bootstrap。一个 design 的所有 rawData 字段必须一起进入或
  一起离开 bootstrap sample。
- 一个 predictor member 通过同一套确定性 codecs 同时生成所有 fields，因此 member 本身
  仍是联合函数 draw。sampler 在创建时选择/固定 member，之后所有 candidate chunks 复用
  该 member；不能在每次 `predict()` 时重选。
- ensemble 大小不在本 TODO 中硬编码。实现 benchmark 应比较若干受控值，并同时报告训练
  墙钟、显存/内存、有效支持度和采集收益；不能只通过重采样 3 个 member 制造表面上的
  128 个独立 draws。
- 首版可把有限 member 均匀经验分布作为生产 posterior，只要 `unique_support` 如实报告，
  acquisition 对支持度不足有显式策略。

predictor-only ensemble 是首版工程取舍，不是假定 codec 没有 epistemic uncertainty。只有
held-out calibration、rawData error 或 acquisition ablation 证明共享 codec 明显低估不确定
性时，才比较“每个 member 一套完整 CAE”的 full-model ensemble；不要在没有证据时先把
训练/存储成本乘以 ensemble size。

### 第二阶段：需要时扩大模型支持或增加连续权重后验

只有第一阶段 benchmark 表明有限支持明显限制 qNEHVI 时，才审计并加入一种能够抽取
完整函数的成熟方法，例如：

- full-model CAE ensemble（当共享 codec 的不确定性确有影响时）；
- Bayesian/linearized last-layer posterior；
- SWAG 或等价的全局 weight posterior；
- 明确定义共享 mask 的 variational dropout；
- 其他可生成整批共同权重 draw 的受支持 posterior backend。

实现前建立 backend reuse matrix：版本、许可证、checkpoint 大小、抽样成本、是否能复用
CAE decoder、跨候选相关性、seed、device、恢复以及 calibration 能力。不要同时实现多种
未经 benchmark 的 posterior 变体。

普通 MC dropout 若对 batch 中每行独立生成 mask，不满足本契约；必须证明一个 draw 中
mask/weights 确实定义同一个函数。

## 校准数据和指标

- train/validation/calibration/test 按 design row 切分，所有字段和坐标跟随所属 design；
  不允许 coordinate-level leakage。
- 超参数和 early stopping 使用 validation；posterior scaling/calibration 只使用独立
  calibration designs；最终 test 在所有决策冻结后评估。
- 样本规模重点为约 1000 和 2000 个设计。可以记录 300--500 的 warm-up 行为，但不把
  小样本胜负作为生产验收门槛。
- rawData 层至少报告每字段标准化误差、样本能量分数或等价 multivariate score、边际覆盖
  与跨字段相关结构误差。
- cost 层必须把每个完整 rawData draw 通过当前 `calc_cost.py`，报告 objective coverage、
  calibration curve、rank/ranking quality 和 Pareto decision quality。
- 采集层报告相同真实评估预算下的最终/随代 hypervolume、失败率和重复候选率。仅有良好
  rawData RMSE 不能证明 posterior 适合 qNEHVI。
- 校准必须使用 out-of-sample 或在线“预测先于真实结果”的证据。training-fit error、
  member min/max 和同一数据上的重构残差不能成为信任规则。

## 校准动作的限制

- 允许在 held-out 证据支持下对 posterior spread 做一个全局或按字段的保守缩放；其拟合
  数据、参数和适用 signature 必须保存。
- 不允许为了达到名义 coverage 而改变 posterior mean 或直接拟合 cost。
- 字段级 calibration 不能破坏同一 draw 的联合身份。禁止分别重排各字段/目标的 sample
  index。
- 如果 calibration 样本不足或 signature 不兼容，应回到明确标记的 uncalibrated
  posterior 或禁用 posterior acquisition，不能静默沿用旧系数。

## 调度、状态和资源

- posterior trainer 遵守 workspace/strategy/component namespace、generation snapshot、
  单 workspace 最多一个训练任务和 retained inactive artifacts 的现有约束。
- checkpoint 保存生成函数 draw 所需的状态、calibration parameters 和 method version，
  不保存预测 population 或复制历史 rawData。
- 为 training、每个 posterior draw、rawData-to-cost projection 分别记录墙钟和峰值内存；
  采集前应能基于配置拒绝明显超出内存预算的物化计划。
- candidate-chunked streaming cost projection 后只保留
  `[draw, candidate, objective]`，以避免 rawData 样本数乘积常驻内存。
- 公共 diagnostics 对 posterior 类型保持中立：所有实现报告 kind、requested/actual draws、
  seed/state signature 和失败数；只有 `support_kind="finite"` 的实现报告整数
  `unique_support`，连续或未知支持使用 `None`。

## 验证要求

- 构造两个候选共享同一随机函数、但逐点独立抽样会改变联合概率的测试，锁定
  cross-candidate coherence。
- 构造 S11/gain 强相关、S11/axial-ratio 弱相关数据，检查同一 draw 中的跨字段相关性；
  禁止只比较边际方差。
- 检查同 member/weight draw 贯穿所有待预测 candidates、字段和目标；首版 fixed real
  baseline 不重采样，未来若引入 pending points，它们必须复用同一 sampler。
- 检查 seed、draw order、resampling、finite-posterior `unique_support` 和 checkpoint
  recovery。
- 检查同一 sampler 跨 candidate chunks 固定 member/weights，且 permutation/chunk
  invariance 成立。
- 检查 observation-noise-disabled 默认不引入逐 `x` 独立噪声。
- 检查 calibration split 无泄漏、过期 signature 不复用、字段缩放不打乱 sample pairing。
- 用现有 current-cost 路径验证 rawData sample 到 cost sample 的数值一致性。

## 非目标

- 不声称 deep ensemble 是精确 Bayesian posterior。
- 不以更多重复抽样替代真实 unique posterior support。
- 不让 qNEHVI 读取训练 loss 或 min/max 作为隐式置信度。
- 不修改 conditional-INR 训练；其有限适配工作由单独 TODO 负责。

## 完成规则

- 新 CAE 拟合器能生成满足联合 posterior 协议的 function draws，并如实报告支持度；
- predictor-only ensemble 已先通过工程和 decision benchmark；只有证据要求时才把
  full-model ensemble 或连续后验留作必需后续；
- 确定性任务默认不存在逐候选伪噪声；
- calibration/test pipeline 在 1000--2000 design operating envelope 上完成预登记评估；
- qNEHVI 所用 posterior 版本通过相应 acquisition benchmark，而不是只通过单元测试；
- checkpoint、metadata、architecture、blueprints、terminology 和用户说明已同步，随后将
  本 TODO 移入 obsolete。
