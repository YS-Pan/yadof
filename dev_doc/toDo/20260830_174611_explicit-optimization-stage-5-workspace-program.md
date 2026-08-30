# 预测性阶段 5：由 optimization.py 拥有完整优化程序

## 状态与依赖

这是未获准执行的预测性手动 TODO。只有 Dataset/cost、surrogate fit/predict 与 search/selection
原语已经用 benchmark 验证后，才能精确设计 workspace program；不得从本草图直接实施不兼容
入口。

## 预期目标

把 generation loop 和显式数据流放入 `submit/optimization.py`。目标程序大致可逐行看到读取
evidence、计算真实 cost、构造 surrogate data、fit/predict、计算 predicted cost、选择 population、
开始/完成真实 evaluation；这些对象可由普通 Python/NumPy/SciPy 操作。yadof 只保留 session、
snapshot、记录、评估、搜索和 surrogate 等跨任务机制。

## 待精化决策

- command 内 `optimization.py` 是冻结一次还是 generation 重载；当前讨论倾向一个 run 冻结
  program，用户需修改时在 generation 边界结束命令再继续；
- `yadof check` 如何只验证入口和声明式组件而不执行任意优化程序；
- `run_one_generation`、resume、CLI progress、metadata 和 strategy namespace 的替代接口；
- 旧 `build_optimization()` 是直接删除还是仅在开发迁移期间短暂共存。最终目标为 0.5.0
  不兼容收口，不保留永久 dual path。

## 预测性验证与完成

模板、examples 和 benchmark complete strategy modules 必须一起迁移；普通 Python 数据变换、
program freeze/resume、失败传播和 installed docs 需要测试。完整验收继续使用同一 seed 101、
100 × 20 synthetic-antenna NSGA-III + 简单 surrogate benchmark。执行前根据阶段 4 evidence 与
用户反馈把本文重写为精确 TODO。
