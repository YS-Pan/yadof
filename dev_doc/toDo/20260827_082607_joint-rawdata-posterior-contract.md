# 增加联合 rawData 后验组件契约

## 背景与当前证据

- yadof 当前坚持 `normalized variables -> rawData -> current cost`。真实评估和代理
  模型都不应建立权威的 `variables -> cost` 捷径；历史中的 rawData 是证据，cost 是由
  当前 generation task snapshot 中的 `submit/calc_cost.py` 动态解释得到的派生量。
- 当前 `ConditionalINRComponent.predict_population()` 面向 GPSAF 返回每个候选的
  `(mean_costs, member_min_max_intervals)`。这足以维持现有 GPSAF 行为，但无法表达
  qNEHVI 所需的候选间、字段间和目标间联合后验。
- 用户明确要求未来拟合器学习 `parameters -> rawData`，因为完整 rawData 的信息量远高于
  cost；不接受用直接 `parameters -> cost` 拟合替代该路径。
- 目标真实评估通常不超过一核时，训练样本目标规模约为 1000--2000 个设计；不以小样本
  性能为目标。rawData 可能同时包含不同坐标和维度的字段，例如 1-D S11、2-D gain 和
  axial ratio。

## 目标

定义一个与具体不确定性实现无关的、rawData-first 的联合 posterior 能力，让新拟合器、
conditional-INR 兼容适配器以及未来 posterior 方法可以被 qNEHVI 等采集组件统一消费。
样本是基础能力；均值、分位数和区间都是派生的诊断视图。

本文件是以下工作包的首要依赖：

1. [分层 CAE rawData 拟合器](20260827_082608_hierarchical-cae-rawdata-surrogate.md)
2. [自洽后验抽样与校准](20260827_082609_coherent-posterior-sampling-calibration.md)
3. [conditional-INR 后验兼容适配器](20260827_082610_conditional-inr-posterior-adapter.md)
4. [qNEHVI 采集与独立策略](20260827_082611_qnehvi-acquisition-strategy.md)
5. [基准、验收与渐进发布](20260827_082612_validate-new-surrogate-and-qnehvi.md)

## 已确定的契约

### 1. 以整个候选集合为抽样单位

核心接口不能是逐点独立调用的 `sample_rawdata(x, n)`。qNEHVI 的一次 Monte Carlo
draw 必须表示同一个可能的函数，并同时作用于该次采集所需的：

- 所有候选点；
- baseline 和 pending points；
- 所有 rawData 字段；
- 由这些字段导出的所有目标和约束。

建议的概念接口为：

```python
posterior = surrogate.posterior(context, population)

for draw in posterior.iter_rawdata_draws(
    draw_count=sample_count,
    seed=random_seed,
):
    # draw.raw_samples 的候选顺序与 population 完全一致。
    # 同一个 draw_id 下的全部候选和字段属于同一个函数抽样。
    ...
```

完整物化时的概念形状为：

```text
[posterior_draw, candidate, structured RawSample]
```

`sample_rawdata(x, n)` 可以作为单候选便利包装，但不得成为采集组件依赖的基础协议。

### 2. rawData 保持现有结构和证据语义

- 每个 `RawSample` 必须能够通过现有 rawData schema/template 还原为当前
  `calc_cost.py` 可消费的完整、结构化 rawData；不能只返回扁平向量、均值、min/max 或
  目标级独立样本。
- posterior 抽样是短期派生状态，不得写入 recorded-data segment，也不得被当作真实评估
  证据。
- 不修改 worker、`rawData/*.npz`、`rawData.zip`、recorded-data segment 或历史查询的
  持久化格式。变化只发生在 submit-side surrogate/acquisition 组件边界。
- 每次训练、恢复、抽样和 cost 投影都使用同一个 generation task snapshot；任务修改在
  下一代边界生效，不能把一批采集样本分割到不同 cost 解释下。

### 3. 抽样协议必须暴露真实性而不是伪造支持度

posterior 诊断至少应包含：

- `posterior_kind`，例如 `empirical_ensemble`、`weight_posterior` 或明确标记的组合；
- `requested_draw_count`；
- `unique_support`，有限 ensemble 重采样时不得谎报为新的独立支持；
- 稳定的调用内 `draw_id` 和可复现 seed；
- schema/state/strategy signature；
- 是否为近似后验及适用限制；
- 支持的字段集合、候选数和失败统计。

相同 seed、状态、输入顺序和配置应产生相同 draw 顺序。改变候选顺序不得被静默解释为
相同 posterior 对象。

### 4. 流式缩减而不是保留全部预测 rawData

rawData 可能远大于 cost。默认实现应按 posterior draw 流式执行：

```text
one coherent rawData draw for all candidates
  -> current RawDataCostProjector
  -> one [candidate, objective] cost draw
  -> discard predicted rawData draw
```

最终只需要保留小得多的 `[draw, candidate, objective]` 张量。首版不必定义任意字段/坐标
分块协议；若单个联合 draw 也无法容纳内存，再增加能够保持 `draw_id` 的分块扩展，不能
先用逐候选独立抽样规避内存问题。

### 5. cost 投影是独立适配层

增加 task-neutral 的 `RawDataCostProjector` 或等价窄接口：

- 输入一个联合 rawData draw、对应 normalized population 和已冻结的 task snapshot；
- 对每个候选调用与真实/现有代理路径相同的当前 cost 解释；
- 输出联合 objective/constraint samples、有效掩码和有界诊断；
- 保持目标顺序、宽度和 normalized population 顺序；
- 明确处理某个 draw/candidate 的 schema 或 cost 失败，不能悄悄把失败转换成“高不确定
  性”或有利采集值。

qNEHVI 只消费投影后的联合 cost samples，不了解 CAE、INR、NPZ template 或
`calc_cost.py` 内部细节；这不构成直接 cost 拟合，因为每个 cost draw 都来自一份完整
rawData draw。

### 6. 采用增量能力协议

- 保留现有 `predict_population()` 返回值和 GPSAF 调用链，避免为新消费者改变旧 tuple
  的含义。
- 新增 `RawDataPosteriorSurrogate`/`RawDataPosterior` 协议或语义等价的窄类型；不要用
  `hasattr` 散布隐式能力判断。
- 新拟合器直接实现 posterior 协议；conditional-INR 通过独立适配器提供有限经验后验。
- posterior/acquisition 能力、后端版本和所有有效参数必须进入 strategy/component semantic
  identity。不得因只增加适配器而让现有 conditional-INR GPSAF checkpoint 冷失效。
- parent `yadof.surrogate` 和 `yadof.optimize` 导入仍必须保持 Torch、BoTorch/pymoo 等
  可选依赖的 lazy-loading 边界。

## 建议代码边界

- `src/yadof/surrogate/api.py`：轻量公开 component factory 与 posterior protocol 导出。
- 新的轻量 posterior 类型文件：只放协议、JSON-safe diagnostics 和结构化抽样容器，不
  导入 Torch。
- private surrogate package：各模型实现自己的 posterior 对象和 draw 生成。
- `src/yadof/job_template/` 或邻近的 submit-side 公共层：复用现有 rawData 到 current cost
  的解释，不复制 task cost 逻辑。
- `src/yadof/optimize/`：采集组件接收 cost draw，不反向导入具体 surrogate 实现。

最终放置需以执行时的 current architecture/blueprints 为准，但依赖方向必须保持：

```text
optimization strategy -> posterior protocol <- concrete surrogate
optimization strategy -> cost projector -> current task cost interpreter
```

## 验证要求

- 用带至少两个候选、两个不同形状 rawData 字段和两个目标的 fake posterior，证明一次
  draw 在候选/字段/目标之间保持联合身份。
- 构造“逐点独立抽样会得到错误结果”的相关样例，锁定 batch-joint 语义。
- 验证同 seed 可复现、不同 seed 可变化、候选顺序稳定、空 population 和失败诊断。
- 验证按 draw 流式投影与完整物化所得 cost samples 完全一致。
- 验证 posterior rawData 通过当前 schema/cost 路径，但从不进入 recorder。
- 验证导入 `yadof.surrogate`/`yadof.optimize` 不加载可选数值后端。
- 验证现有 conditional-INR + GPSAF 的返回格式、选择行为和 checkpoint 恢复不变。

## 非目标

- 不在本工作中选择某一种不确定性算法或修改 conditional-INR 训练数学。
- 不改变真实评估、worker transport、recorded-data 或用户 task rawData 格式。
- 不承诺任何有限 ensemble 的 min/max 是置信区间。
- 不把 posterior prediction 存为可被历史重新解释的真实证据。

## 完成规则

- 轻量公共协议、联合 draw 容器、cost projector 和失败/诊断语义已经实现并有安装包测试；
- 至少一个 fake posterior 通过端到端 cost 投影测试；
- 现有 GPSAF/conditional-INR API 无行为回归；
- architecture、surrogate/optimize/job-template blueprints、terminology、user docs 和
  checkpoint/semantic identity 文档已同步；
- 本文件所列后续工作仍按各自 TODO 独立完成，本契约完成后移入 `dev_doc/obsolete/`。
