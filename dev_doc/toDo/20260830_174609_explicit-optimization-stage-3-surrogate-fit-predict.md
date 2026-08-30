# 预测性阶段 3：surrogate 显式 fit/predict 数据边界

## 状态

这是预测性手动 TODO，未获准执行。它依赖阶段 2 最终确定的 Dataset/CostTable 合同；阶段 2
完成和用户反馈后必须重新核对 current code、checkpoint identity、scheduler 与 benchmark，再
把下一步改成精确范围。

## 预期目标

让至少一个简单、代表性的 rawData-first surrogate 不再在组件内部调用
`training_data_from_session()`，而由 optimization program 显式传入普通 Python 可变换后的
training dataset，并显式返回 state/prediction。预计先迁移 `pca_svd()`，因为它没有 posterior
和复杂概率语义，可用于证明数据分流：真实 rawData/cost dataset 与 surrogate training dataset
可以不同，但稳定 sample identity、schema、checkpoint semantic identity 和 recorder 边界不变。

## 预测性约束

- fit 只接受真实 recorded evidence 或它的 owned、可追溯变换；预测数据不得成为真值；
- checkpoint identity 必须包含实际训练数据摘要和组件设置，但不把路径/日志误作数学身份；
- 明确同步/异步 fit 生命周期与 generation snapshot ownership；
- conditional-INR、hierarchical CAE、posterior adapter 和 viewer 的迁移顺序由简单组件结果决定，
  不在本预测文档中一次承诺全部切换。

## 预测性验证与完成

预计增加 raw/filtered training-data 分流、checkpoint recovery、prediction/cost projection、
lazy import 和 recorder non-entry 测试；每次精确实施仍使用 synthetic-antenna、NSGA-III、简单
surrogate、seed 101、100 × 20 完整 benchmark。完成后反馈，再精化阶段 4。
