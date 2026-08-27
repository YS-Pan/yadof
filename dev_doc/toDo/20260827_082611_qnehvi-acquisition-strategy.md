# 新增 qNEHVI 采集模块和独立 posterior-assisted 策略

## 背景与产品决定

- 用户要求将 qNEHVI 作为新模块加入 yadof，不替换、重写或嵌入现有 GPSAF。
- qNEHVI 应利用由完整 rawData posterior draws 经当前 `calc_cost.py` 得到的联合 cost
  samples；不能直接拟合 `parameters -> cost`。
- 用户确认重复评估随机性通常很小。首版按近似确定性、zero-observation-noise 问题实现，
  已完成真实历史是固定 baseline truth，而不是需要 surrogate 再采样的 noisy observation。
- 当前 task cost 可以是任意 Python/NumPy 逻辑，通常不可微。即使 CAE/parameter
  predictor 可微，也不能假装整条 rawData-to-cost 路径支持 autograd。
- yadof 的完整策略由 workspace `submit/optimization.py:build_optimization()` 组合；package
  不增加第二个全局方法 selector 或 config registry。

## 依赖

- [联合 rawData posterior 契约](../obsolete/20260827_082607_joint-rawdata-posterior-contract.md)
- 至少一个实现该协议的 surrogate：推荐
  [分层 CAE 拟合器](20260827_082608_hierarchical-cae-rawdata-surrogate.md) 和
  [校准 posterior](20260827_082609_coherent-posterior-sampling-calibration.md)；
  [conditional-INR adapter](../obsolete/20260827_082610_conditional-inr-posterior-adapter.md) 作为先完成
  backend spike 的有限兼容路径，而不是生产推荐模型。

## 目标模块边界

增加两个窄组件，而不是通用插件图：

```python
posterior_assisted(
    search=pymoo_nsga3(),
    surrogate=hierarchical_cae(...),
    acquisition=qnehvi(...),
)
```

- `qnehvi()`：首版只负责从联合 objective samples 计算采集值和选择 batch；未来明确增加
  outcome-constraint sample 契约后再扩展。
- `posterior_assisted()`：负责 generation orchestration、候选池、surrogate freshness、
  posterior/cost projection、exploration quota 和 common real evaluation。
- `pymoo` 继续拥有 variation/search/population/duplicate 等成熟机制；qNEHVI 不复制
  NSGA-III 或 GPSAF phase。
- GPSAF factory、private `optimize/gpsaf/`、现有 candidate records 和选择测试保持不变。

名称是工作建议；实现时可以在保持上述职责的前提下选择更清楚的公开名称，但不得把
qNEHVI 包装成 GPSAF 参数。

## 算法与库归属

### Library-first 审计

实现前审计当时受支持的 BoTorch 或其他成熟实现，形成 reuse matrix：

- distribution/version/license 和 Python/Torch 兼容性；
- qNEHVI 定义、baseline/pending/constraints 支持；
- 是否能消费自定义 sample-backed posterior；
- discrete candidate optimization 和 batch selection 能力；
- deterministic seed、device、memory、异常和 diagnostics；
- 哪些部分必须由 yadof 适配，哪些数值循环由 backend 拥有。

优先使用成熟 backend 的 hypervolume、partitioning 和 qNEHVI 数值实现。若其模型接口无法
接受 yadof 的 sample-backed posterior，应先写薄的 model/posterior adapter。只有在有
明确不兼容证据时，才实现一个小型 empirical Monte Carlo estimator；此时名称和文档必须
明确为 `discrete/empirical qNEHVI`，并用成熟实现的可比小问题做等价测试。

BoTorch 当前不是 yadof 依赖。若选用它，应加入独立可选 extra 和 lazy import，不得让
普通 `yadof.optimize`、real search 或 GPSAF 导入它；具体版本范围以实施时审计为准，不能
依赖未经声明的 transitive package。

最近一次计划审计中，BoTorch 官方文档已推荐数值更稳定的 log-improvement 版本。首版
公开能力仍称 `qnehvi()`（表示用户选择的 qNEHVI acquisition family），但 backend spike
优先验证 `qLogNoisyExpectedHypervolumeImprovement` 或实施时官方等价继任 API，而不是
直接固化 legacy `qNoisyExpectedHypervolumeImprovement`。具体类名、版本和 sample-backed
posterior 适配能力必须在实现当日重查并记录。

### 后端 spike 先于完整策略

在实现 CAE 或 generation orchestration 前，先用 fake sample-backed posterior 和
conditional-INR adapter 完成一个小型 backend spike：

- 证明 BoTorch `Model.posterior()` / `Posterior.rsample()` 薄适配可以消费 yadof 的联合
  cost samples，或记录具体不兼容点；
- 对解析小问题核对 minimization/maximization、reference point、fixed baseline、batch
  shape、seed 和 qLogNEHVI 数值；
- 测量 candidate pool × draw × objective 的时间/内存；
- 失败时只调整 adapter/模块边界，不先写一套自有 hypervolume 数值层。

该 spike 是实现 gate，不要求先有 1000--2000 条 CAE 训练数据。

## Gate 2 backend spike 执行状态（2026-08-27）

Gate 2 的 library/API spike 已完成，详细审计、ownership matrix、数值对照和
pool × draw × objective 测量见
[change record](../change_records/20260827_152421_conditional-inr-posterior-and-qlognehvi-spike.md)：

- 选择 MIT BoTorch 0.18.1 的
  `qLogNoisyExpectedHypervolumeImprovement`，声明独立 `qnehvi` extra，并保持普通
  `yadof.optimize`/GPSAF/real-search import 不加载 Torch/BoTorch；
- fake sample-backed `EnsembleModel`/`EnsemblePosterior` 与 conditional-INR adapter
  的 current-cost samples 均可进入同一 backend；fixed real baseline、zero observation
  noise、minimization 只取反一次、默认 reference `(1, ..., 1)`、q=1/q=2 和 seed 已验证；
- zero-noise fixed-baseline 结果与 BoTorch qLogEHVI 对照在 `1e-4` 内；独立打乱一个
  objective 的 draw 会改变结果，证明实现保留联合 sample pairing；
- invalid candidate 采用整 MC draw 拒绝，有限 `1.0` 仍有效；有限有效支持度可显式
  `warn` 或 `reject`；
- mature backend spy 证明 hypervolume/partitioning/log-improvement 数值循环仍归 BoTorch；
  yadof 只拥有输入验证、lookup/sample adapter、方向转换、mask/support policy 和 compact
  diagnostics；
- CPU warm-process 测量已覆盖 64×16×2、256×32×2、128×32×3，未保存 predicted
  rawData，也未启动真实 simulator campaign。

本次仅完成本 TODO 的 backend spike gate。尚未实现 `qnehvi()` factory、candidate-pool
复用、`posterior_assisted()` generation orchestration、exploration/fallback、common real
evaluation/recording、完整 strategy identity/state 或同预算 benchmark，因此本 TODO 保持
active，不得归档。

### 离散候选池是首版边界

由于 current `calc_cost.py` 通常不可微，首版不进行 gradient-based `optimize_acqf`。采用：

```text
pymoo/history-informed candidate pool
  -> one persistent joint rawData sampler evaluated in candidate chunks
  -> streaming current-cost projection
  -> empirical/discrete qNEHVI batch selection
  -> common real evaluation
```

候选池大小、posterior draw 数、batch size 和 greedy/restart 策略为显式受控参数并进入
semantic identity。初始 benchmark 可以探索数百至数千个 pool rows，但这些是调优范围，
不是硬默认或性能保证。实现必须先测量 rawData projection 时间和内存。

首版直接复用 private pymoo candidate-pool mechanics 及其现有 duplicate/refill 语义，在新
strategy 内增加窄 adapter；不新增通用 public `search.propose_pool()` 协议。只有第二个
非-pymoo 真实消费者出现时再提炼公开 search capability，避免为了一个调用方扩大架构。

### 首个 MVP 的明确功能边界

- 支持至少两个 objectives、离散候选池、batch selection、fixed real Pareto baseline 和
  candidate posterior samples。
- 不增加 pending-state API。当前 `GenerationContext` 没有 pending 字段，当前 generation
  evaluation 也是同步边界；将来出现真正异步未完成点时，再把 pending 与同一 function
  sampler 的联合语义作为独立扩展。
- 不支持 task outcome constraints。现有 parameter/duplicate feasibility 继续由 search/task
  机制处理；只有出现明确的随机 outcome-constraint rawData 契约后，才扩展 acquisition
  samples。
- 当前 cost helper 产生的有限 `error_cost=1.0` 是有效最差 task cost；不能从数值猜测它
  来自 fallback。schema/callback/width/non-finite failure 才进入 invalid sample policy。

## 一代的建议流程

1. 从 `GenerationContext` 取得 current real history、problem、snapshot 和 seed。
2. 使用既有 search backend 生成归一化候选池，并应用参数语义、constraints、history/current
   population duplicate keys 和 refill limits。
3. 在 model 尚未达到已批准 warm-up/新鲜度要求时，使用明确的 real-search cold-start，
   同时按现有 after-submit scheduling 训练；不让 prediction 自动触发隐藏训练。
4. 从完成的 real history 计算并冻结当前真实 Pareto baseline；不让 surrogate 重采样这些
   已观测 rows。为候选池创建一个持久 function sampler。
5. sampler 逐 candidate chunk 生成完整 rawData，使用 generation snapshot 的
   `CostInterpreter` 薄 projector 立即缩减并拼成 `[draw, candidate, objective]`，随后释放
   predicted rawData；所有 chunks 复用相同 draw identities。
6. qNEHVI acquisition 选择 exploitation batch，同时保留显式 exploration fraction；禁止
   整代候选都来自未经校准的 posterior preference。
7. 通过 common `evaluate_population()` 做真实评估。只有真实 rawData 进入 campaign
   session/recorder；预测 samples 和 acquisition values 只作有界 diagnostics。
8. 保存 compact strategy/acquisition metadata：backend/version、pool/draw/support sizes、
   seed、reference point、baseline count、timings、fallback 和失败统计。

### Applicability exploitation gate handoff（来自 082608 Gate 0 v5）

当前前置条件未满足：082608 v5 的 full-grid/quality gate 失败，coordinate/offline-test 被阻塞，
082609 尚未在独立 calibration designs 上产出可用 probability capability。因此这里不得先把
当前 experimental head 接入 exploitation，也不得用 v5 validation diagnostics 临时决定阈值。

- 低 `P(smooth)` 候选不得无条件进入 qNEHVI exploitation pool；按实现前封存的 policy 将其
  排除或作保守处理。该 policy、概率版本和阈值属于 strategy semantic identity。
- 必须保留显式、可审计的真实 exploration quota，可探索低 applicability/分类边界区域，
  防止分类器形成永久盲区；探索结果仍走 common real evaluation/recording。
- 禁止仅扩大低 applicability 候选的 posterior variance：risk-neutral qNEHVI 可能反而偏爱
  高方差 chatter 区。也禁止用 training loss、cost 或 member min/max 替代校准概率。
- applicability gate 只消费 082609 产出的显式 typed capability；本 TODO 不重新训练分类器，
  不改变 zero-observation-noise 与 persistent function-draw identity。
- 只有后续 architecture 通过 082608 successor gate、082609 校准并冻结 signature/threshold
  后，本 TODO 才能预注册低 `P(smooth)` 的排除/保守规则和真实 exploration quota；所有低
  applicability/boundary exploration 仍必须走真实公共 evaluator，以免分类器形成永久盲区。

## qNEHVI 语义细节

### 多目标和 reference point

- qNEHVI factory 至少要求两个 objectives；单目标显式报错或由 workspace 使用现有
  objective-count composition 选择另一个获批组件，不能在内部静默换算法。
- yadof 新 task objectives 是 `[0, 1]` minimization cost，默认 hypervolume reference
  point 可使用 `(1, ..., 1)`，与 cost viewer 一致。任何 override 必须显式、验证、进入
  identity，并保持 minimization/maximization 转换只发生一次。
- 含 `inf`、NaN 或超出有效 task-cost contract 的行不进入 baseline front；诊断必须说明
  排除原因。

### baseline、pending 与噪声

- 已完成真实 history 的 rawData/current costs 是观测证据，不应用 surrogate mean 替换。
- 首版从这些有限、合法 rows 中构造固定 nondominated Pareto baseline。`error_cost=1.0`
  仍是合法最差 row；带 `inf`/NaN 或宽度错误的 rows 排除并报告。
- qNEHVI 中的“noisy”不能被误解为任意 epistemic spread。默认确定性任务不虚构观测
  噪声；qLogNEHVI adapter 必须验证 zero-observation-noise limit 与对应 qLogEHVI/qEHVI
  固定 baseline 计算一致。若成熟 backend 的特定 API 要求 baseline posterior，薄 adapter
  只能提供 deterministic samples 或使用其正式等价路径，不能注入伪噪声。
- 若未来 task 明确声明 measurement noise，baseline latent truth/noise conditioning 必须有
  独立协议和测试；不能从 ensemble spread 猜测观测噪声。
- pending points 延后。首版 batch 内的 q 个候选仍由同一个 joint acquisition/duplicate
  policy 选择，避免相同或过度相似建议。

### 参数约束、失败和支持度

- 复用当前 task/optimizer 的参数和可行性语义；首版不声明 outcome-constraint sample。
- 当 `support_kind="finite"` 时，posterior `unique_support` 低于 acquisition policy 才执行
  预先配置的 warn/fallback/reject；连续或未知支持不能伪造有限 support，也不能套用该
  整数阈值。有限 ensemble 不得通过重复抽样伪装支持度。
- 某些 draw/candidate 的 rawData 或 cost 投影失败时，采用预先测试的 conservative mask
  或整 draw 拒绝策略。不能把失败当成优秀 hypervolume improvement。
- qNEHVI 数值失败只影响本次 surrogate-assisted selection；fallback 必须仍通过正常
  real-search 和 real evaluation，不得返回预测 cost 作为结果。

## 状态和模块隔离

- 新 strategy identity 包含 search、surrogate、posterior/acquisition backend、所有受控
  参数和 objective names。切换 GPSAF/qNEHVI 激活不同 strategy namespace，但保留历史
  真实证据和 inactive component artifacts。
- qNEHVI 自身只需轻量可恢复 diagnostics/seed 状态；不要复制完整 posterior rawData 或
  建立第二份 history。
- generation source fingerprints 是 provenance/cache 边界，不是自动丢弃旧真实 evidence
  的科学判定。
- 与现有训练调度集成时保持每 workspace 最多一个 surrogate trainer，并在 strategy
  切换时等待/释放相应内存状态。

## 验证要求

- 用解析小问题或成熟 backend 对照验证 qNEHVI 数值、minimization 方向、reference point、
  batch、fixed real baseline 和 zero-noise limit。
- 构造相关 candidate/objective samples，证明逐候选或逐目标独立重排会失败，而实现保留
  联合 draw。
- multiobjective-only 验证、parameter constraints、outcome-constraint/pending capability
  rejection、invalid samples、有限 `1.0` valid semantics、finite posterior 的低
  `unique_support`、空/重复 candidate pool、backend missing 和 deterministic seed。
- spy/fake backend 证明成熟库拥有核心数值循环，yadof 只做适配和 orchestration。
- 证明 rawData 按 draw 投影后立即释放，保存状态中没有 predicted rawData。
- 证明所有选中点都经过 common real evaluator/finalizer/recorder；recording failure 仍按
  当前契约中止 campaign。
- 测试低 applicability exploitation 排除/保守路径、显式 real exploration quota、边界探索
  诊断，以及“只增大 variance”不会被当成合法 gate。
- 现有 GPSAF 和 real-search 回归测试逐项不变，普通 import 不加载新可选依赖。

## 非目标

- 不替换 GPSAF，不把 qNEHVI 加成 GPSAF phase。
- 不建立直接 cost surrogate，也不要求 task cost 支持 autograd。
- 首版不做连续 gradient acquisition optimization。
- 不以 surrogate prediction 接受一个候选或写入 durable history。
- 不在没有 benchmark 的情况下把 qNEHVI 设为默认 strategy。
- 首版不实现 pending points、outcome constraints 或通用 public candidate-pool protocol。

## 完成规则

- workspace 可以显式组合并运行独立 qNEHVI posterior-assisted strategy；
- acquisition 消费联合 rawData-derived cost samples，并通过真实评估验证全部结果；
- mature backend 复用、zero/noisy semantics、支持度和 fallback 有明确文档与测试；
- 同预算 benchmark 达到
  [验收 TODO](20260827_082612_validate-new-surrogate-and-qnehvi.md) 的预登记门槛；
- architecture、optimize/surrogate blueprints、terminology、user docs、optional dependency、
  artifact 和 installed-wheel tests 已更新，随后将本 TODO 移入 obsolete。
