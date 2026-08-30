# 预测性阶段 6：evaluation handle、旧编排删除与 0.5.0 收口

## 状态与依赖

这是系列中的预测性最终阶段，尚未获准执行。它依赖 workspace optimization program 的真实
运行结果；fast/local/distributed 的最终接口、模块移动范围和版本发布内容必须在前一阶段后
重新审计，不能以本文草图替代精确设计。

## 预期目标

- 三种 backend 保留各自成熟 transport/process/scheduler 实现，但统一为可开始、等待/完成、
  取消的 evaluation handle 与公共 coordinator；
- 真实 result 在用户代码可见前完成 rawData validation 与可靠记录，随后由 program 显式
  calculate cost；框架不按 backend 隐式决定训练重叠。阶段 5 的唯一通用 starter 使用对三种
  backend 都安全的顺序，而 source-checkout example program 可以用普通代码显式展示
  distributed-oriented overlap 或其他经资源说明约束的顺序；
- 删除隐藏 `after_jobs_submitted` callback、strategy-owned generation loop、组件内部 session
  training-data 读取和完成迁移后已无消费者的旧编排；
- 按阶段 5 已确定的交付合同完成唯一 starter、source-checkout 多 program examples、每例配套
  `.md`、user-doc 一句话索引和 init 无 selector 边界；同步 architecture、blueprints、
  terminology 与迁移说明，最终把包版本从 0.4.2 提升为 0.5.0。

## 预测性约束与验证

除用户明确决定删除且不参与选择数学的 GPSAF `gamma` 外，当前所有 optimize 算法、surrogate
算法/实现入口、tools 以及 fast/local/distributed 三种模式都必须保留可用；允许重写内部结构，
不得以删除隐藏编排为由删掉通用机制或公共能力。

可靠记录 failure 始终 campaign-fatal，individual execution/rawData/current-cost failure 保持有序
正确宽度；predicted data 永不进入 recorder。需要 fast/local/distributed contract tests、resume、
recording backpressure、worker/scheduler cleanup、示例程序的 resource competition 说明、
starter/example/user-doc 引用完整性和全量 installed-wheel 验收。每个精确实施单元仍要运行
用户指定的 fast NSGA-III + 简单 surrogate、seed 101、100 × 20 baseline benchmark；local 与
distributed 只做相称的小规模 contract/smoke 验证。若本阶段过宽，应根据前述 evidence 再
拆分，而不是一次强行完成。

## 完成规则

只有旧隐藏编排已删除、三 backend 与 docs/templates/benchmark 同步、0.5.0 wheel 全量验收及
完整 benchmark 成功，并获得用户对最终行为的确认后，系列重构才算完成。
