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
- 用户确认重复评估的随机性通常很小，首版按近似确定性任务处理。当前 benchmark
  baselines 是首版数据形态的事实来源：它们包含实数标量、固定轴 1-D 曲线，以及带
  `Freq/Phi/Theta` 轴的固定形状天线张量；首版不应先假设任意缺失字段、可变 shape 或
  随设计变化的坐标网格。

## 目标

定义一个与具体不确定性实现无关的、rawData-first 的联合 posterior 能力，让新拟合器、
conditional-INR 兼容适配器以及未来 posterior 方法可以被 qNEHVI 等采集组件统一消费。
样本是基础能力；均值、分位数和区间都是派生的诊断视图。

本文件是以下工作包的首要依赖：

1. [分层 CAE rawData 拟合器](../toDo/20260827_082608_hierarchical-cae-rawdata-surrogate.md)
2. [自洽后验抽样与校准](../toDo/20260827_082609_coherent-posterior-sampling-calibration.md)
3. [conditional-INR 后验兼容适配器](../toDo/20260827_082610_conditional-inr-posterior-adapter.md)
4. [qNEHVI 采集与独立策略](../toDo/20260827_082611_qnehvi-acquisition-strategy.md)
5. [基准、验收与渐进发布](../toDo/20260827_082612_validate-new-surrogate-and-qnehvi.md)

## 已确定的契约

### 1. 以持久 function sampler 为抽样单位，并允许候选分块

核心接口不能是每次调用都重新抽样的逐点 `sample_rawdata(x, n)`，也不应把整个候选池
永久绑定进一个 posterior 对象。一次 Monte Carlo draw 必须先固定一个可能的函数；之后
同一 sampler 可以用相同 draw identities 预测任意候选分块：

```python
sampler = surrogate.make_rawdata_sampler(
    context,
    draw_count=sample_count,
    seed=random_seed,
)

for population_chunk in candidate_chunks:
    samples = sampler.predict(population_chunk)
    # 概念形状：[draw, candidate, structured RawSample]
    # 每个 draw_id 在所有 chunk、候选和字段中始终表示同一个函数。
    ...
```

该边界同时满足联合采样和内存约束：

- 同一 `draw_id` 必须贯穿该次采集的所有候选、所有 rawData 字段，以及由它们导出的所有
  目标；以后若 yadof 引入 pending points，同一 sampler 也必须覆盖它们。
- 改变 chunk size、chunk 顺序或候选排列只能相应重排结果，不能改变某个候选在同一
  `draw_id` 下的预测；接口必须通过 permutation-equivariance 和 chunk-invariance 测试。
- 重复候选在同一 draw 中必须得到同一函数值。sampler 不得在 `predict()` 时为每行重新
  选择 ensemble member、dropout mask 或 latent noise。
- 对不需要分块的小 population，可以提供一次性便利包装；它只是持久 sampler 的薄包装，
  不是另一套抽样语义。

`sample_rawdata(x, n)` 仍可作为单候选便利函数，但不得成为采集组件依赖的基础协议。

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

### 3. field identity 不依赖可选 metadata

- 已确定的稳定 field selector 是二元组
  `(NPZ basename including .npz, resolved main array key)`；main key 由现有 rawData
  contract 解析为 `values` 或 `data`。
- selector 使用 schema 中的精确 canonical basename/key，并在 schema signature 中固定；
  不能依赖可选的 `metadata.rawdata_name`，也不能依赖字段在某个 sample 中的遍历顺序。
- axis arrays、unit scalars 和 metadata 仍属于该 NPZ template，但不是独立待预测 field。
  首版从冻结 schema template 还原它们，只预测 selector 指向的 main array。
- 首版 concrete surrogate 只接收训练集中 field selector 集合、main shape/dtype 表示、axis
  keys/values 和必要 metadata template 均固定的 compatible rows。缺失 field、可变 shape、
  随设计变化的 axis 或 schema drift 必须给出明确 incompatibility diagnostic；协议本身可在
  后续扩展，但首版不得用 padding 或猜测掩盖这些变化。

### 4. 抽样协议必须暴露真实性而不是伪造支持度

posterior 诊断至少应包含：

- `posterior_kind`，例如 `empirical_ensemble`、`weight_posterior` 或明确标记的组合；
- `requested_draw_count`；
- `support_kind`，至少区分 `finite` 与 `continuous_or_unknown`；
- `unique_support`：仅对有限 ensemble/离散支持为必填整数，连续或未知支持使用 `None`，
  不得为满足统一字段而伪造一个有限数；
- 稳定的调用内 `draw_id` 和可复现 seed；
- schema/state/strategy signature；
- 是否为近似后验及适用限制；
- 支持的字段集合、候选数和失败统计。

相同 seed、状态和配置应产生相同 draw 顺序。候选排序和分块不属于 posterior identity；
它们只能重排/分块同一组函数值，不能改变抽到的函数。

### 5. 按 draw 和 candidate chunk 流式缩减

rawData 可能远大于 cost。默认实现应按 posterior draw 流式执行：

```text
one coherent rawData draw for one candidate chunk
  -> current RawDataCostProjector
  -> one [chunk_candidate, objective] cost draw
  -> discard predicted rawData draw
```

最终只需要保留小得多的 `[draw, candidate, objective]` 张量。首版必须支持 candidate
chunking；不必同时定义任意字段/坐标分块协议。若一个候选的一份完整 rawData draw 仍
无法容纳内存，再增加保持 `draw_id` 的 field/coordinate chunk 扩展，不能用逐候选重新
抽样规避内存问题。

### 6. cost 投影是现有 CostInterpreter 的薄流式适配层

增加 task-neutral 的 `RawDataCostProjector` 或等价窄接口，但它必须复用现有
`yadof.job_template.api.CostInterpreter` 冻结参数和 `calc_cost.py` 的能力，而不是增加第二套
task loader、callback 调度、宽度校验或失败回退：

- 输入一个联合 rawData draw、对应 normalized population 和已冻结的 task snapshot；
- 对每个候选调用与真实/现有代理路径相同的当前 cost 解释；
- 输出联合 objective samples、有效掩码和有界诊断；首版 outcome-constraint sample 协议
  延后到有具体任务需求时定义；
- 保持目标顺序、宽度和 normalized population 顺序；
- 明确处理某个 draw/candidate 的 schema 或 cost 失败，不能悄悄把失败转换成“高不确定
  性”或有利采集值。
- 首版 `valid` 只表示 rawData schema/callback 调用、objective width 和 finite-result 检查
  成功。当前 task helper 内部可能把计算异常回退成有限的 `error_cost=1.0`；由于现有
  `CostInterpreter` 不携带该回退来源，这个 `1.0` 按用户决定视为有效的最差 task cost，
  不得靠数值反推成 invalid。框架执行失败的 `inf` 仍是另一条不可用路径。

qNEHVI 只消费投影后的联合 cost samples，不了解 CAE、INR、NPZ template 或
`calc_cost.py` 内部细节；这不构成直接 cost 拟合，因为每个 cost draw 都来自一份完整
rawData draw。

### 7. 采用增量能力协议

- 保留现有 `predict_population()` 返回值和 GPSAF 调用链，避免为新消费者改变旧 tuple
  的含义。
- 新增 `RawDataPosteriorSurrogate`/`RawDataPosterior` 协议或语义等价的窄类型；不要用
  `hasattr` 散布隐式能力判断。
- 新拟合器直接实现 posterior 协议；conditional-INR 通过独立适配器提供有限经验后验。
- posterior/acquisition 能力、后端版本和所有有效参数必须进入 strategy/component semantic
  identity。不得因只增加适配器而让现有 conditional-INR GPSAF checkpoint 冷失效。
- parent `yadof.surrogate` 和 `yadof.optimize` 导入仍必须保持 Torch、BoTorch/pymoo 等
  可选依赖的 lazy-loading 边界。

最小协议完成后应立即实现 conditional-INR adapter 和一个 fake/sample-backed backend
spike，先验证模块边界，再开始完整 CAE。benchmark schema inventory、split、指标和停止
条件应先于模型超参数实现，不把验收留到所有模块串行完成之后。

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
- 验证不同 chunk size、chunk 顺序和候选排列只重排相同预测；按 draw/chunk 流式投影与
  完整物化所得 cost samples 完全一致。
- 验证 selector 使用 NPZ basename + main array key；缺失/可变 schema 被明确拒绝。
- 验证有限 `error_cost=1.0` 保持 valid，而 schema、宽度和非有限结果失败进入 invalid。
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
