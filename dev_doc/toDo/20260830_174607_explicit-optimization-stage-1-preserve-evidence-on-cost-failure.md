# 显式 optimization 重构阶段 1：cost 失败时保留有效 evidence

## 状态与来源

- 用户在 2026-08-30 明确要求把大范围 optimization 架构改造拆成多个阶段，只让当前阶段
  精确。本文是当前唯一精确 TODO；用户随后明确要求本轮只生成 TODO，因此在用户再次明确
  指示执行前，不得修改源码、测试、architecture/blueprints/terminology/user docs，不得启动
  benchmark，也不得精化阶段 2。
- 最终目标是让 workspace `submit/optimization.py` 显式拥有读取数据、计算 cost、训练
  surrogate、产生候选和真实评估的数据流。该目标要求 rawData 真值不能因为派生 cost 的
  当前解释失败而丢失。
- 已验证的当前缺口是 `evaluate_manager/finalizer.py` 把 rawData ownership/validation 与
  `calc_cost.py` 放在同一个异常边界；cost callback 或 objective width 失败时，已经有效的真实
  rawData 会被清空并只记录 error row，之后无法修正 cost 再解释。另一个已验证缺口是非有限
  objective 目前没有统一被拒绝，可能进入即时或历史 cost view。

## 本阶段精确范围

- 将 rawData ownership/validation 与 current-cost 计算分成两个异常边界。
- current-cost 的统一解释合同同时约束即时 `calculate_cost()` 与冻结
  `CostInterpreter.calculate_costs()`：callback 抛错、objective width 错误或任一非有限 objective
  都是 current-cost failure。有限性检查不能只放在 finalizer，否则历史重解释仍可能把 `NaN`
  接纳为可用 cost。
- rawData 无效时继续形成没有正常 evidence 的候选失败记录。
- rawData 有效但 current cost 失败时：
  - 当前 evaluation 仍返回缺失 cost，population API 继续产生正确宽度的 `inf`；
  - durable record 的 evidence status 为 completed，并包含 owned rawData；
  - metadata 分别记录 evidence/current-cost 状态、失败阶段和分段耗时；
  - 同一 generation 的冻结错误解释不能产生 history cost；修正 `calc_cost.py` 后，下一个
    generation snapshot 可以从保留 evidence 重新计算有限 cost。
- 不改变 campaign loop、strategy API、surrogate 隐式训练数据读取、fast/local/distributed
  backend、recorded-data 物理格式或包版本；这些属于后续阶段。

## 预期修改点

- `src/yadof/evaluate_manager/finalizer.py`：拆分 evidence/current-cost 状态与异常边界；只要
  evidence 有效就向 recorder 交付 owned rawData，current-cost-only failure 保持 `costs=None`。
- `src/yadof/job_template/api.py`：让 point-in-time 与 frozen interpreter 使用同一有限 objective
  合同；避免只修写入路径、遗漏历史/工具/预测投影使用的解释入口。
- `tests/test_loss_tolerant_recording.py`：参数化覆盖 callback 抛错、width 错误、非有限 objective，
  验证 live/durable evidence、当前 snapshot 跳过、修正后的下一 snapshot 重解释。
- fast 公共评估测试：验证正确宽度 `inf` 与 completed rawData；以实际 durable record 的
  `job_name` 对齐查询，不假定 backend 生成 `candidate_0_0`。
- 实施完成时才同步 architecture、blueprints、terminology、user docs 和 change record；本轮
  TODO-only 交付不预先修改这些合同文档。

## 验证

- 增加 installed-package 回归测试，覆盖 live/durable rawData 保留、当前代无 cost、三类
  current-cost failure、修正后跨 generation 重解释，以及 record metadata/status。
- 完成 wheel build、force reinstall、import-origin、focused tests 和全量 pytest。
- 使用 `test-com/synthetic-antenna` benchmark baseline 做真实完整工作流验证。strategy 是
  单一结构验收 arm：`gpsaf(search=pymoo_nsga3(...), surrogate=pca_svd(...), ...)`，不虚构第二个
  reference arm。NSGA-III 与 GPSAF 的现有默认参数都在 strategy 文件中显式写出；PCA/SVD 固定
  为 `decomposition="pca"`、`rank=4`、`predictor="ridge"`、`ridge_alpha=1e-6`、
  `field_mode="per-field"`、`rank_policy="clamp"`、`solver="torch-lowrank"`、`dtype="float32"`、
  `device="auto"`、`power_iterations=1`、`seed=101`、`fit_intercept=True`、
  `constant_atol=1e-12`。measured run 严格使用 population `100`、generations `20`、seed `[101]`，
  执行 2,000 次真实 baseline evaluation；这是结构/回归验收，不宣称 optimizer 性能结论。
- measured run 前用相同 baseline、strategy、seed、policy 和 postprocessor 做独立小预算
  benchmark smoke（population `20`、generations `2`）；smoke 只证明执行链，不进入性能解释。
- measured 前分别运行 benchmark `check` 与 `plan --json`，确认 smoke/measured 除预算外的
  baseline、strategy source digest、seed、policy、postprocessor 全部一致。验收要求 measured cell
  `collected=true`、`valid=true`、attempted evaluations 为 `2000`，且没有缺代/缺个体；不设置
  hypervolume improvement gate。
- 本阶段不改变 optimization/strategy API，预计无需修改 source baseline。若 installed yadof 的
  实际接口迫使 benchmark baseline 或 postprocessor 调整，只做该接口所需的最小修改，先增加
  benchmark focused test，再运行上述同源 smoke/measured；不得借机改变 synthetic objective。

## 完成规则

- 上述代码、测试和文档一致，正常 cost 成功路径无回归，cost 失败证据可在修正后重解释；
- installed-wheel 验收和 100 × 20 benchmark 均达到正常 collected/valid 状态；
- 形成变更记录、提交，并按仓库规则判断 push；随后把本文移入 `dev_doc/obsolete/todo/`，
  向用户反馈结果并等待下一阶段精化。

## 暂停期间获得但未保留的证据

一次随后完全撤回的临时实现运行了 focused tests，结果为 `27 passed, 2 failed`。两项失败都
用于收紧本文而不是作为已完成实现保留：其一证明 finalizer-only 非有限检查不足，历史路径会
重新接纳 `NaN`；其二证明 fast backend 的实际 job name 不应由测试硬编码。临时源码、测试、
合同文档和安装包均已恢复到本 TODO 创建前的 `HEAD` 状态。
