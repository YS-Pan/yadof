# 显式 optimization 重构阶段 1：先可靠发布 evidence，再解释 cost

## 状态与来源

- 用户在 2026-08-30 明确要求把大范围 optimization 架构改造拆成多个阶段，只让当前阶段
  精确。本文是当前唯一精确 TODO；本次授权只要求修订 goal/TODO，因此在用户再次明确
  指示执行前，不得修改源码、测试、architecture/blueprints/terminology/user docs，不得启动
  benchmark，也不得精化阶段 2。
- 最终目标是让 workspace `submit/optimization.py` 显式拥有读取数据、计算 cost、训练
  surrogate、产生候选和真实评估的数据流。该目标要求 rawData 真值不能因为派生 cost 的
  当前解释失败而丢失。
- 已验证的当前缺口是 `evaluate_manager/finalizer.py` 在把 owned evidence 交给 recorder 前
  调用 `calc_cost.py`。即使把普通 Python exception 拆成两个异常边界，cost 卡死、native
  crash、`os._exit()`、OOM 或 orchestration process 终止仍会丢失尚未发布的有效 rawData。
  recorder queue/admission 也只表示 writer 已接收请求，不是 recovery 可见的 durable commit。
  另一个已验证缺口是非有限 objective 目前没有统一被拒绝，可能进入即时或历史 cost view。

## 本阶段精确可靠性合同

每个获得合法 rawData 的真实 evaluation 必须遵守以下因果顺序：

```text
backend result
  -> validate rawData
  -> transfer/copy into yadof-owned evidence
  -> publish immutable evidence through recorder
  -> wait for committed acknowledgement
  -> calculate current cost through user code
  -> return cost success/failure as a derived interpretation
```

- **validate** 证明 rawData 符合 schema；**own** 证明 job、worker 或 candidate scratch 此刻
  消失也不会使 yadof 失去 payload；**durable publish** 证明当前 orchestration process 随后
  终止时，重新打开 workspace 的 session/query 仍能发现完整 evidence。
- committed acknowledgement 只能在承载该 evidence 的 immutable segment 已完成现有
  same-directory atomic publication、且 recovery discovery 能识别它之后返回。允许 recorder
  batching/group commit，但一个 candidate 的用户 cost 代码必须等待包含该 candidate 的 commit
  acknowledgement。本文不额外承诺超出现有 segment-store 合同的掉电级 `fsync` 保证。
- queue put、admission、accepted-current-row 或仅在内存中取得 ownership 都不是 durable
  acknowledgement。recorder commit failure 继续是 campaign-fatal；不得把它降级成个体 cost
  failure，或为了提前计算 cost 而绕过 backpressure。
- evidence publication 与 cost interpretation 是两个生命周期。evidence segment 不因 cost
  成功、失败或以后更换 `calc_cost.py` 而重写。阶段 1 的 live result/generation diagnostics
  表达 current-cost outcome；稳定 sample-aligned `CostTable` 和更完整 interpretation view 由
  阶段 2 设计，不能为等待它而削弱本阶段 publication-first 保证。

## 本阶段精确范围

- 将 rawData validation、ownership、durable publication acknowledgement 与 current-cost
  interpretation 分成有顺序的阶段；任何用户 cost 代码只在对应 evidence commit 后运行。
- current-cost 的统一解释合同同时约束即时 `calculate_cost()` 与冻结
  `CostInterpreter.calculate_costs()`：callback 抛错、objective width 错误或任一非有限 objective
  都是 current-cost failure。有限性检查不能只放在 finalizer，否则历史重解释仍可能把 `NaN`
  接纳为可用 cost。
- rawData 无效时继续形成没有正常 evidence 的候选失败记录。
- rawData 有效但 current cost 失败时：
  - 当前 evaluation 仍返回缺失 cost，population API 继续产生正确宽度的 `inf`；
  - durable record 的 evidence status 为 completed，并包含 owned rawData；
  - durable evidence metadata 只记录 evidence/commit 状态与 provenance；current-cost 状态、
    失败阶段和耗时作为 publish 后的 live/generation interpretation diagnostics，不能反向重写
    evidence segment；
  - 同一 generation 的冻结错误解释不能产生 history cost；修正 `calc_cost.py` 后，下一个
    generation snapshot 可以从保留 evidence 重新计算有限 cost。
- 不改变 campaign loop、strategy API、surrogate 隐式训练数据读取、三种 backend 的成熟执行
  引擎或包版本；除可靠 acknowledgement 所必需的 receipt/metadata 调整外，不在本阶段进行
  Dataset/CostTable、evaluation handle 或 recorded-data 物理格式的全面重设计。

## 预期修改点

- `src/yadof/evaluate_manager/finalizer.py` 及其直接 coordinator/caller：把 evidence
  validation/ownership、durable publication 和 current-cost interpretation 拆成明确阶段；只要
  evidence 有效就先交给 recorder，并等待 commit acknowledgement 后才运行用户 cost。
- `src/yadof/recorded_data/session.py`、writer/segment-store 的直接边界：提供可等待且只在
  真正 publication 后完成的 per-envelope 或 per-batch receipt；writer death、重试耗尽和
  oversized envelope 必须唤醒等待者并传播 `RecordingError`。
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
- 增加 ordering/termination 回归：正常 cost 必须在 commit acknowledgement 后才执行；在
  evidence commit 后、cost completion 前注入 orchestration termination，新 session 仍能发现
  完整 evidence；仅 enqueue 后终止不得被误报为 committed。
- 增加 writer failure/oversized envelope/backpressure 回归，证明 cost 不会提前执行且 campaign
  在没有后续 evaluation/history gap 的情况下明确停止。
- fast、local、distributed 用小规模 contract/smoke tests 覆盖同一 publication-before-cost
  顺序和失败分类；local/distributed 不运行全量 benchmark。
- 完成 wheel build、force reinstall、import-origin、focused tests 和全量 pytest。
- 使用 `test-com/synthetic-antenna` benchmark baseline 做真实完整工作流验证。strategy 是
  单一结构验收 arm：`gpsaf(search=pymoo_nsga3(...), surrogate=pca_svd(...), ...)`，不虚构第二个
  reference arm。NSGA-III 与 GPSAF 的现有默认参数都在 strategy 文件中显式写出；PCA/SVD 固定
  为 `decomposition="pca"`、`rank=4`、`predictor="ridge"`、`ridge_alpha=1e-6`、
  `field_mode="per-field"`、`rank_policy="clamp"`、`solver="torch-lowrank"`、`dtype="float32"`、
  `device="auto"`、`power_iterations=1`、`seed=101`、`fit_intercept=True`、
  `constant_atol=1e-12`。measured run 只使用 fast backend，严格使用 population `100`、
  generations `20`、seed `[101]`，执行 2,000 次真实 baseline evaluation；这是结构/回归验收，
  不宣称 optimizer 性能结论。
- measured run 前用相同 baseline、strategy、seed、policy 和 postprocessor 做独立小预算
  benchmark smoke（population `20`、generations `2`）；smoke 只证明执行链，不进入性能解释。
- measured 前分别运行 benchmark `check` 与 `plan --json`，确认 smoke/measured 除预算外的
  baseline、strategy source digest、seed、policy、postprocessor 全部一致。验收要求 measured cell
  `collected=true`、`valid=true`、attempted evaluations 为 `2000`，且没有缺代/缺个体；不设置
  hypervolume improvement gate。
- 长 benchmark 只启动一次并跟随同一个 foreground terminal/session 到最终退出码，以最长约
  60 秒一轮的低频等待观察；不得重复启动、用高频轮询或把 partial progress 当成验收结果。
- 本阶段不改变 optimization/strategy API，预计无需修改 source baseline。若 installed yadof 的
  实际接口迫使 benchmark baseline 或 postprocessor 调整，只做该接口所需的最小修改，先增加
  benchmark focused test，再运行上述同源 smoke/measured；不得借机改变 synthetic objective。

## 完成规则

- 上述代码、测试和文档一致，publication-before-cost、ownership、commit acknowledgement、
  异常/进程终止恢复和 cost 修复重解释均有直接证据，正常 cost 成功路径无回归；
- installed-wheel 验收和 100 × 20 benchmark 均达到正常 collected/valid 状态；
- 形成变更记录、提交，并按仓库规则判断 push；随后把本文移入 `dev_doc/obsolete/todo/`，
  向用户反馈结果并等待下一阶段精化。

## 暂停期间获得但未保留的证据

一次随后完全撤回的临时实现运行了 focused tests，结果为 `27 passed, 2 failed`。两项失败都
用于收紧本文而不是作为已完成实现保留：其一证明 finalizer-only 非有限检查不足，历史路径会
重新接纳 `NaN`；其二证明 fast backend 的实际 job name 不应由测试硬编码。临时源码、测试、
合同文档和安装包均已恢复到本 TODO 创建前的 `HEAD` 状态。
