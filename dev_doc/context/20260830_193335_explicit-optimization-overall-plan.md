# Explicit Optimization Refactor Overall Plan

## 文档角色与优先级

本文保存显式 optimization 重构的跨阶段意图、依赖关系、共同不变量和验收节奏，供后续
session 在压缩上下文后定向恢复背景。它不是当前 architecture、执行授权或第二套任务队列。

- 用户的最新明确指示、当前代码与当前合同文档优先于本文；
- `dev_doc/toDo/` 中各阶段文档拥有该阶段的具体范围、测试和完成规则；
- 手动 TODO 只有在用户明确要求执行对应文件时才触发；
- 当前只有阶段 1 是精确实施 TODO，阶段 2--6 必须根据前一阶段 evidence 继续改写，本文
  不把预测性 API 草图提升为兼容承诺。

简短 Goal 应只说明最终框架结果、关键保留边界和滚动实施方式，并引用本文。需要执行某一
阶段时，必须重新读取本文和即将执行的那个 TODO，而不是把 Goal 本身当作实施规格。

## 最终方向

目标是面向 yadof 0.5.0，把 yadof 重构成以 workspace
`submit/optimization.py` 为显式程序入口的可组合优化框架。

`optimization.py` 最终应拥有 generation loop 和端到端数据流。用户可以在普通 Python 代码中
看到并组合以下动作：

- 从 live campaign 或 durable history 读取真实 evidence；
- 使用当前 task snapshot 解释真实 cost；
- 通过普通 Python、NumPy 或 SciPy 过滤、复制、重排和构造数据；
- 显式准备 surrogate training data，调用 fit/predict 并取得 state/prediction；
- 产生搜索候选、计算 predicted current cost、选择需要真实评估的 population；
- 启动、等待、完成或取消真实 evaluation；
- 在 generation boundary 形成一致的 optimizer、checkpoint、diagnostics 和 progress 状态。

yadof 负责提供可组合、可测试的 session、snapshot、recording、dataset、cost interpretation、
evaluation、search、selection 和 surrogate primitives，以及成熟的 fast、local、distributed
执行引擎。strategy、surrogate component 或 backend 不再暗中拥有完整 generation workflow，
也不根据 backend 名称替用户选择训练与评估的先后关系。

下面的形状只说明期望的可见数据流，不冻结函数名、同步形式或返回类型：

```python
evidence = read_evidence(session, snapshot)
costs = calculate_cost(evidence, snapshot)
training_data = prepare_training_data(evidence, costs)
surrogate_state = fit(training_data)
candidate_pool = search(real_history=costs)
prediction = predict(surrogate_state, candidate_pool)
selected = select(candidate_pool, prediction)
handle = start_real_evaluation(selected, snapshot)
results = wait_real_evaluation(handle)
```

阶段 1--4 的 evidence 将决定这些 public primitives 的真实名称和边界。阶段 5 之前不得从
此示意代码直接建立永久 API。

## 可靠性与数据真值边界

真实 rawData 是 evidence，cost 是在某一 task snapshot 下得到的派生 interpretation。二者必须
具有不同生命周期。任何用户 cost 代码运行前，对应 rawData 都必须完成：

```text
validate -> own -> durable publish -> committed acknowledgement -> calculate cost
```

- `validate` 证明 rawData 符合 schema；
- `own` 证明 job、worker 或 scratch 立即消失也不会丢失 payload；
- `durable publish` 与 acknowledgement 证明当前 orchestration process 随后终止时，新的
  session 仍可通过 recovery discovery 找到完整 immutable evidence；
- queue admission、仅内存 ownership 或 accepted row 不是 commit；
- 本计划沿用现有 same-directory atomic segment publication 的持久性承诺，不额外声称已经
  提供掉电级 `fsync` 保证。

cost callback 抛错、objective width 错误、非有限 objective、进程终止或以后修改
`calc_cost.py` 都不能删除或重写已发布 evidence。修正解释逻辑后，后续 generation 可以从同一
evidence 派生新的 cost view。recorder 无法可靠发布仍是 campaign-fatal；individual execution、
rawData 或 current-cost failure 则保持独立、有序并产生正确宽度的失败结果。

后续 Dataset/CostTable 应以稳定 sample identity 对齐 evidence 与 interpretation，使普通 Python
过滤和重排不依赖数组位置。它们是现有 recorder 的内存/view 层，不建立第二套 authoritative
history。surrogate prediction、predicted rawData 和 predicted cost 永远不能成为真实 recorder
中的 evidence。

## 程序顺序、backend 与修改边界

训练和真实评估是否重叠，由 `optimization.py` 的可见代码顺序决定：

- fast、local、distributed 都只提供能力、资源和失败边界，不自动切换 orchestration policy；
- package 默认 starter 使用对三种 backend 都安全的保守通用顺序；
- 需要 distributed throughput 的程序可以在提交 evaluation 后显式启动异步 fit，再等待
  evaluation handle；对应示例必须说明资源竞争、生命周期和适用环境；
- fast/local 不因为 backend-specific 隐式 hook 被迫与 surrogate training 竞争资源。

一次 `yadof run` 冻结它加载的 `optimization.py`。用户修改 program 时，在完整 generation
边界安全停止当前命令，再通过 resume 加载新版本。同一命令内不热重载 optimization loop
本身。cost、参数、workflow/evaluator 等 task 内容仍按各自 generation snapshot 合同处理。

## 保留、删除与迁移政策

- 保留当前全部 optimize 算法、surrogate 算法及实现入口、tools，以及 fast、local、
  distributed 三种模式；内部可以重构，公共能力不能借删除隐藏编排而消失。
- GPSAF `gamma` 是唯一已明确删除的表面：它当前只参与 validation、identity 和 diagnostics，
  不参与候选选择数学。删除时必须提供 0.5.0 migration 说明，并用 deterministic parity 证明
  selection 不变；GPSAF alpha/beta 不随之调整。
- pymoo 继续拥有 NSGA-III、operators、ask/tell 和 survival 数值；yadof 不复制成熟算法。
- posterior/qNEHVI 不因本重构自动启用或成为默认。typed readiness、真实评估和 fail-closed/
  full-real fallback 边界继续成立。
- 0.5.0 可以是不兼容收口，但不得长期保留隐藏旧 orchestration 与显式 program 的双路径。

## Starter、示例与用户文档

该产品交付的权威细节保存在
[阶段 5 TODO](../toDo/20260830_174611_explicit-optimization-stage-5-workspace-program.md)。跨阶段
计划只保留下面的关系：

- `src/yadof/_resources/templates/default/workspace/submit/optimization.py` 是唯一 package
  starter，采用对三种 backend 都安全的通用方案；
- 顶层 source-checkout `examples/` 新增专门目录，保存多种有实质编排差异的
  `optimization.py`；每份程序有同 basename 的 `.md` 解释背景、适用场景、数据流、并发取舍、
  所需组件和预期 workspace 环境；
- 这些示例不是完整 workspace，不复制 `config.py`、`calc_cost.py`、`job_template/` 或 simulator
  assets，单个程序不能直接运行；
- `user_doc/` 只提供轻量索引和每例一句用途概述，详细说明由示例旁的 `.md` 拥有，并明确
  source checkout 与普通 pip installation 的可见性差异；
- `yadof init` 始终生成唯一通用 starter，不提供多模板 selector、字符串 registry、自动
  discovery 或新增 CLI 选择器。

示例集合预计覆盖 real-only、顺序 surrogate、显式异步重叠和自定义 cost/surrogate 数据分流。
posterior-assisted 示例只有在届时 public primitives 与 readiness 足够稳定时才纳入；最终集合
由阶段 4 evidence 决定。

## 阶段地图

| 阶段 | 当前状态 | 主要结果 | 对下一阶段提供的 evidence |
|---|---|---|---|
| [1](../toDo/20260830_174607_explicit-optimization-stage-1-preserve-evidence-on-cost-failure.md) | 唯一精确、未获执行授权 | publication-before-cost、commit receipt、failure/recovery 合同 | durable evidence 与重解释行为 |
| [2](../toDo/20260830_174608_explicit-optimization-stage-2-dataset-and-cost-tables.md) | 预测性 | 稳定 sample identity 的 Dataset/CostTable view | 普通 Python filter/reorder 与 cost alignment |
| [3](../toDo/20260830_174609_explicit-optimization-stage-3-surrogate-fit-predict.md) | 预测性 | 显式 surrogate fit/predict 输入输出 | training-data 分流、state/checkpoint 生命周期 |
| [4](../toDo/20260830_174610_explicit-optimization-stage-4-search-selection-primitives.md) | 预测性 | 拆分 search/predict/select primitives；删除 GPSAF gamma | 等价 selection 与 workspace 可组合边界 |
| [5](../toDo/20260830_174611_explicit-optimization-stage-5-workspace-program.md) | 预测性 | `optimization.py` 拥有完整 program；starter/examples/docs | 三 backend 下显式程序的真实运行证据 |
| [6](../toDo/20260830_174612_explicit-optimization-stage-6-evaluation-and-release.md) | 预测性 | evaluation handle、删除旧编排、0.5.0 收口 | installed-wheel、迁移与最终验收证据 |

阶段数量不是永久承诺。结果可以要求重做当前阶段、改变方向、取消某项预测工作、拆分/合并
后续阶段或新增 TODO。不得为了保持这张表不变而忽略测试暴露出的更合理边界。

## 滚动执行与决策循环

每轮只精化并执行一个 TODO：

1. 重新核对当前代码、相关合同、前一阶段 evidence 和用户最新决定；
2. 把即将执行的 TODO 改写为可独立执行的精确范围，其他 TODO 保持预测性；
3. 获得用户对该 TODO 的明确执行指示后实施；
4. 完成相称的源码、文档、installed-wheel 和 contract tests；
5. 运行 benchmark，分析可靠性、结构、行为、资源和回归结果；
6. 根据 evidence 决定接受、重做、缩小、改向或取消，而不是默认前进；
7. 只有当前阶段成立，才精化下一 TODO，并更新其余预测性 TODO 使其反映新证据；
8. 形成 change record、commit，并按仓库规则判断 push，然后等待用户继续指示。

不得并行实施后续预测阶段，也不得因 Goal 或本文存在就取得源码修改、真实 simulator 或长
benchmark 的执行授权。

## 共同验证与 benchmark 政策

每个实际实施阶段至少运行一次完整 fast benchmark：

- baseline：`test-com/synthetic-antenna`；
- optimizer/surrogate：NSGA-III + 一个简单代表性 surrogate；当前结构验收使用 GPSAF +
  PCA/SVD，具体 source 与参数由即将执行的精确 TODO 冻结；
- measured budget：population `100`、generations `20`、单一 seed `[101]`，即 2,000 次真实
  baseline evaluation；
- 目的：结构、可靠性和回归验收，不以单个 run 宣称 optimizer 性能优越，也不设置必须提升
  hypervolume 的 gate；
- measured 前运行同源小预算 smoke，并通过 benchmark `check` 与 `plan --json` 核对除预算外
  的 baseline、strategy digest、seed、policy 和 postprocessor；
- fast 是唯一全量 backend。local 与 distributed 只运行足以覆盖接口、failure、cleanup、
  resume 和 ordering 的小规模 contract/smoke tests。

每个实施阶段里，长 benchmark 只启动一次，并跟随同一个 foreground terminal/session 到最终
退出码。等待使用当前 Codex/runtime 支持的最长有界 wait 或等价事件驱动方式；无异常时可把
约 20 分钟作为目标观察/汇报间隔，而不是要求一次 terminal poll 必须阻塞 20 分钟。若单次
wait 的工具上限更短，或因新输出提前返回，继续等待同一个 session；不得用阻塞 `sleep`、
高频轮询或重复 run 模拟较长间隔。partial progress 既不是成功也不是失败。

代码阶段还必须遵循仓库的 wheel build、force reinstall、import-origin、focused/full tests 和
文档同步合同。只修改计划文本时使用 documentation-only validation exception，不运行与文字
变更无关的软件测试或 benchmark。

## 最终完成判据

整个重构只有在下列结果共同成立后才完成：

- workspace program 能用普通 Python 显式表达 retained algorithms 的完整优化数据流；
- evidence publication、cost interpretation、sample identity、prediction non-entry 和
  recorder failure 边界都有直接测试与 recovery evidence；
- fast/local/distributed 共用明确的 evaluation primitives，同时保留各自成熟执行实现；
- 全部既有 optimize/surrogate/tools 能力仍可用，GPSAF gamma 按 parity 证据删除；
- 唯一通用 starter、多种非独立 program examples、配套 `.md`、user-doc 索引和 init 无
  selector 合同已经交付并验证；
- strategy-owned loop、隐藏 training-data session 读取、backend-owned overlap policy 和其他
  已无消费者的旧编排已经删除，没有永久 dual path；
- 每个已执行阶段都有测试、fast 100 x 20 benchmark 分析、change record 和用户审阅；
- 0.5.0 installed wheel、迁移说明、文档和最终完整 benchmark 一致，并获得用户对最终行为的
  确认。

本文允许结论是取消某一预测性路线或重新划分阶段；它不要求为了完成最初草图而保留被
evidence 否定的设计。
