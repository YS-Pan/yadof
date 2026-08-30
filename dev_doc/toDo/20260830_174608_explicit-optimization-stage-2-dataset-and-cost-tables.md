# 预测性阶段 2：稳定 sample identity 的 Dataset 与 CostTable

## 状态

这是显式 optimization 重构的预测性手动 TODO，尚未获准执行。阶段 1 完成后必须根据其
记录/重解释测试、100 × 20 benchmark 结果和用户反馈重写为精确计划；当前名称、类型和 API
草图都不是兼容承诺。

## 预期问题与目标

当前优化器把 history 压缩为按位置配对的 `HistoryRecord(job_name, x, costs)`，surrogate 又从
`CampaignSession` 单独读取 rawData。普通 Python 一旦过滤、复制或重排数据，缺少一个统一、
稳定的样本身份和显式派生关系。预计在 `yadof.dataset` 中建立只驻留内存的 evidence view 与
cost table：每行保留稳定 sample ID，rawData/evaluation 状态与 cost interpretation 状态分离，
过滤和重排不依赖数组位置，也不建立第二套持久化历史。

## 预测性范围

- 从 live campaign 与 durable `yadof.recorded_data` 产生同一种只读/owned dataset 视图；
- 显式 `calculate_cost(dataset)` 产生按 sample ID 对齐的 derived table，并表示 invalid/`inf`；
- 普通 Python 可复制、选择和重排数据，不能把预测或变换后的数据写回真实 recorder；
- 保持 recorded-data ZIP 格式、candidate identity 和当前 query 工具可读。

具体 rawData ownership、懒加载/内存预算、失败行是否进入同一 Dataset、metadata 暴露范围和
公开命名均待阶段 1 evidence 后决定。

## 预测性验证

预计覆盖 ID 对齐、filter/reorder、cost 修复重算、live/durable 等价、坏 segment 隔离和 recorder
non-entry；并用相同 synthetic-antenna、NSGA-III + 简单 surrogate、seed 101、100 × 20 的完整
benchmark 验收。执行前必须把测试矩阵和实际命令精化。

## 完成规则

只有在本文先被精化并获得用户继续指示后才可执行。完成后反馈结果，再精化阶段 3；不得
因为本文存在就并行实施 surrogate API 或 campaign loop。
