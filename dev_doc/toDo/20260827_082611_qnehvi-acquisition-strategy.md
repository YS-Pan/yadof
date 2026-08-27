# 新增 qNEHVI 采集模块和独立 posterior-assisted 策略

## 背景与产品决定

- 用户要求将 qNEHVI 作为新模块加入 yadof，不替换、重写或嵌入现有 GPSAF。
- qNEHVI 应利用由完整 rawData posterior draws 经当前 `calc_cost.py` 得到的联合 cost
  samples；不能直接拟合 `parameters -> cost`。
- 当前 task cost 可以是任意 Python/NumPy 逻辑，通常不可微。即使 CAE/parameter
  predictor 可微，也不能假装整条 rawData-to-cost 路径支持 autograd。
- yadof 的完整策略由 workspace `submit/optimization.py:build_optimization()` 组合；package
  不增加第二个全局方法 selector 或 config registry。

## 依赖

- [联合 rawData posterior 契约](20260827_082607_joint-rawdata-posterior-contract.md)
- 至少一个实现该协议的 surrogate：推荐
  [分层 CAE 拟合器](20260827_082608_hierarchical-cae-rawdata-surrogate.md) 和
  [校准 posterior](20260827_082609_coherent-posterior-sampling-calibration.md)；
  [conditional-INR adapter](20260827_082610_conditional-inr-posterior-adapter.md) 仅作为有限
  兼容路径。

## 目标模块边界

增加两个窄组件，而不是通用插件图：

```python
posterior_assisted(
    search=pymoo_nsga3(),
    surrogate=hierarchical_cae(...),
    acquisition=qnehvi(...),
)
```

- `qnehvi()`：只负责从联合 objective/constraint samples 计算采集值和选择 batch。
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

### 离散候选池是首版边界

由于 current `calc_cost.py` 通常不可微，首版不进行 gradient-based `optimize_acqf`。采用：

```text
pymoo/history-informed candidate pool
  -> joint rawData posterior over the whole pool and pending points
  -> streaming current-cost projection
  -> empirical/discrete qNEHVI batch selection
  -> common real evaluation
```

候选池大小、posterior draw 数、batch size 和 greedy/restart 策略为显式受控参数并进入
semantic identity。初始 benchmark 可以探索数百至数千个 pool rows，但这些是调优范围，
不是硬默认或性能保证。实现必须先测量 rawData projection 时间和内存。

## 一代的建议流程

1. 从 `GenerationContext` 取得 current real history、problem、snapshot、pending 状态和 seed。
2. 使用既有 search backend 生成归一化候选池，并应用参数语义、constraints、history/current
   population duplicate keys 和 refill limits。
3. 在 model 尚未达到已批准 warm-up/新鲜度要求时，使用明确的 real-search cold-start，
   同时按现有 after-submit scheduling 训练；不让 prediction 自动触发隐藏训练。
4. 对 acquisition 所需的候选、pending 和需要建模的 baseline 一次构造联合 posterior。
5. 按 draw 生成完整 rawData，使用 generation snapshot 的 current cost projector 立即
   缩减为 `[draw, point, objective]`，随后释放 predicted rawData。
6. qNEHVI acquisition 选择 exploitation batch，同时保留显式 exploration fraction；禁止
   整代候选都来自未经校准的 posterior preference。
7. 通过 common `evaluate_population()` 做真实评估。只有真实 rawData 进入 campaign
   session/recorder；预测 samples 和 acquisition values 只作有界 diagnostics。
8. 保存 compact strategy/acquisition metadata：backend/version、pool/draw/support sizes、
   seed、reference point、pending/baseline counts、timings、fallback 和失败统计。

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
- qNEHVI 中的“noisy”不能被误解为任意 epistemic spread。默认确定性任务不虚构观测
  噪声；实现应验证 zero-observation-noise limit 与对应 qEHVI/固定 baseline 计算一致。
- 若未来 task 明确声明 measurement noise，baseline latent truth/noise conditioning 必须有
  独立协议和测试；不能从 ensemble spread 猜测观测噪声。
- pending points 与 candidates 必须位于同一次 function draws 中，避免重复或过度相似的
  batch 建议。

### 约束、失败和支持度

- 复用当前 task/optimizer 的参数和可行性语义；如 qNEHVI backend 支持约束 sample，转换
  方式必须显式。
- posterior `unique_support` 低于 acquisition policy 时，执行预先配置的 warn/fallback/
  reject，不得重复抽样伪装支持度。
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
  batch/pending 和 zero-noise limit。
- 构造相关 candidate/objective samples，证明逐候选或逐目标独立重排会失败，而实现保留
  联合 draw。
- multiobjective-only 验证、constraints、invalid samples、低 `unique_support`、空/重复
  candidate pool、backend missing 和 deterministic seed。
- spy/fake backend 证明成熟库拥有核心数值循环，yadof 只做适配和 orchestration。
- 证明 rawData 按 draw 投影后立即释放，保存状态中没有 predicted rawData。
- 证明所有选中点都经过 common real evaluator/finalizer/recorder；recording failure 仍按
  当前契约中止 campaign。
- 现有 GPSAF 和 real-search 回归测试逐项不变，普通 import 不加载新可选依赖。

## 非目标

- 不替换 GPSAF，不把 qNEHVI 加成 GPSAF phase。
- 不建立直接 cost surrogate，也不要求 task cost 支持 autograd。
- 首版不做连续 gradient acquisition optimization。
- 不以 surrogate prediction 接受一个候选或写入 durable history。
- 不在没有 benchmark 的情况下把 qNEHVI 设为默认 strategy。

## 完成规则

- workspace 可以显式组合并运行独立 qNEHVI posterior-assisted strategy；
- acquisition 消费联合 rawData-derived cost samples，并通过真实评估验证全部结果；
- mature backend 复用、zero/noisy semantics、支持度和 fallback 有明确文档与测试；
- 同预算 benchmark 达到
  [验收 TODO](20260827_082612_validate-new-surrogate-and-qnehvi.md) 的预登记门槛；
- architecture、optimize/surrogate blueprints、terminology、user docs、optional dependency、
  artifact 和 installed-wheel tests 已更新，随后将本 TODO 移入 obsolete。
