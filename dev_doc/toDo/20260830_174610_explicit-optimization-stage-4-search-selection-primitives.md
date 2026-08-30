# 预测性阶段 4：拆分搜索、预测与选择原语

## 状态与依赖

这是未获准执行的预测性手动 TODO。它依赖阶段 3 的显式 surrogate 输入/输出形状；在前一
阶段完成和用户反馈前，不冻结这里的函数名、数据类型、GPSAF 分解边界或 pymoo state 形状。

## 预期目标

把当前 `RealSearchStrategy.run_generation()` 和 GPSAF `run_generation()` 中隐藏的 generation
编排拆成 workspace program 可逐行调用的窄原语：从 history 构造 pymoo state、生成候选池、
调用 surrogate prediction、按 predicted current cost 做 survival/选择、补充真实 exploration，
最后得到一个仍需公共 real evaluation 的 population。

## 预测性约束

- pymoo 继续拥有 NSGA-III 算法、operators、ask/tell 和 survival 数值，不在 yadof 重写；
- GPSAF alpha/beta/gamma 行为、seed、archive/duplicate 语义和 strategy identity 在纯拆分阶段
  应保持等价；若测试暴露必须改变的行为，先反馈而不是静默调整；
- qNEHVI/posterior-assisted 不因本阶段自动迁移或激活，现有 typed readiness 和 full-real
  fallback 保持 fail closed；
- 所有 selected candidates 仍通过公共 real evaluator 和可靠 recorder。

## 预测性验证与完成

预计用旧/新路径确定性 parity、duplicate/refill、single/multi-objective、fallback 和 recorder
传播测试，随后运行同一 seed 101、100 × 20 synthetic-antenna NSGA-III + 简单 surrogate
benchmark。
阶段 3 结果可能要求拆分或合并本 TODO，执行前必须精化并获得用户继续指示。
