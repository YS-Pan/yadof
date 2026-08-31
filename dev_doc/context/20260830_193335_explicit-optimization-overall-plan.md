# Explicit Optimization Refactor Overall Plan

## 文档角色、优先级与执行授权

本文保存 yadof 显式 optimization 重构的跨阶段目标、依赖、不变量、执行节奏和最终停止条件。
它是跨 session context，不是当前 architecture，也不会仅因被读取就触发手动 TODO。

执行期间按以下优先级判断：

1. 用户最新明确指示与正在运行的 Goal；
2. 当前阶段经重新核对后写入其 TODO 的精确 delta；
3. 当前代码、architecture、blueprints、terminology 和 user docs；
4. 本文对尚未精化阶段的预测性方向；
5. 历史 change records 和 obsolete 文档。

当前代码与当前合同是每一阶段开始时的 pre-change baseline。只有正在执行且已精化的阶段 TODO
定义该阶段允许改变的部分；该 delta 之外，当前合同继续权威。预测性 TODO 不能反向宣称未来
设计已经实现。

2026-08-30 用户作出两项明确决定：

- 使用一个 Goal 依次精化并执行本文列出的全部八个阶段，取消普通阶段完成后的强制等待；
- 本重构不修改 GPSAF `gamma`，保留它现有的 factory、settings、validation、semantic
  identity 和 diagnostics 语义。

由于 `dev_doc/toDo/` 的手动触发合同要求明确点名文件，真正启动执行的 Goal 必须逐一列出
[阶段 1](../obsolete/todo/20260830_174607_explicit-optimization-stage-1-preserve-evidence-on-cost-failure.md)、
[阶段 2](../obsolete/todo/20260830_174608_explicit-optimization-stage-2-dataset-and-cost-tables.md)、
[阶段 3](../toDo/20260830_174609_explicit-optimization-stage-3-evaluation-handle.md)、
[阶段 4](../obsolete/todo/20260830_174610_explicit-optimization-stage-4-surrogate-fit-predict.md)、
[阶段 5](../toDo/20260830_174611_explicit-optimization-stage-5-search-selection-primitives.md)、
[阶段 6](../toDo/20260830_174612_explicit-optimization-stage-6-workspace-program-pilot.md)、
[阶段 7](../toDo/20260830_220200_explicit-optimization-stage-7-retained-capability-migration.md) 和
[阶段 8](../toDo/20260830_220201_explicit-optimization-stage-8-cutover-and-release.md)。
本文记录用户决定，但它本身不替代该显式 Goal。

## 单一 Goal 的滚动执行合同

一个 Goal 覆盖全部阶段，但同一时刻最多只有一个阶段进入源码实施。阶段 1 已是精确 TODO；
阶段 2--8 是获得执行授权的预测性 handoff，轮到它们时必须先在原文件内精化，再实施，不能
直接把草图当作冻结 API。

每个阶段执行同一闭环：

1. 重新读取当时的 mandatory docs、本文、当前阶段 TODO、当前代码/测试、相关合同、上一阶段
   evidence 和仍适用的 active TODO；记录输入 HEAD、TODO digest、关键 evidence identity。
2. 在当前 TODO 内区分 verified fact、settled requirement、proposal 和 open implementation
   choice；把它改写为可独立执行的精确 delta、测试矩阵和完成规则。普通 API 命名、内部拆分
   和测试设计由执行者在已定边界内决定，不再等待用户确认。
3. 实施源码、测试和同步文档，按开发指南完成 wheel build、force reinstall、import-origin、
   focused/full installed-package tests 以及本阶段 benchmark。
4. 根据测试和 measured evidence 接受、修复、重做或在同一阶段内缩小实现。普通失败先诊断、
   修复并重跑，不把“测试第一次没过”当作阶段间等待理由。
5. 检查 active automatic TODO 的客观触发条件；更新本文 ledger、适用合同、change record 和
   当前阶段 TODO。
6. 形成一个完整、已验证的阶段提交，按仓库规则 fetch 并判断是否 push。不得把未验证中间态
   提交成阶段完成。
7. 将完成的阶段 TODO 原样移入 `dev_doc/obsolete/todo/`，把 ledger 链接改为归档路径，然后
   自动进入下一阶段。

普通阶段结束不要求用户审阅、确认或发送“继续”。用户已经授权在证据支持总体方向时自动
滚动到下一阶段；最后阶段也不以再次取得“最终行为确认”为完成条件。

如果精化后发现一个阶段需要多个内部 implementation slices，可在同一个 TODO 和 Goal 中串行
完成并分别验证；不得为了绕过手动 TODO 点名合同临时创建未获触发的新阶段文件。只有确需
改变八阶段地图或扩大授权时才暂停。

## 必须暂停的边界

仅在继续工作需要新的实质权限或会改变已定方向时暂停并向用户说明证据与所需决定，包括：

- 启动真实 simulator、HTCondor/共享集群、付费服务、稀缺许可证或本 Goal 未明确授权的长/
  高后果执行；
- 超出已授权 fast synthetic benchmark 范围的 measured campaign，或明显高于计划的时间、
  内存、磁盘与并发成本；
- 修改/删除用户运行证据、迁移活动 workspace、执行不可逆或破坏性外部操作；
- 改变参数身份/数量、objective 数量，或需要用户判断旧 evidence 是否仍有科学意义；
- evidence 证明总体目标、阶段顺序或保留能力无法同时成立，需要删能力、改变默认科学行为、
  修改 GPSAF `gamma` 或新增未列出的阶段；
- 需要 merge/rebase/force-push、远端已前进而必须选择历史处理方式，或缺少外部凭据/权限；
- 用户发出停止、改向或更窄限制。

普通实现取舍、文件移动、API 名称、内部同步/异步形式、在授权范围内增加测试、修复回归、
按证据重写尚未实施的当前 TODO，以及仓库既定的 commit/fetch/条件 push 都不构成强制暂停。

## 最终框架方向

目标版本是 yadof 0.5.0。workspace `submit/optimization.py` 最终拥有可读的 optimization
algorithm、generation loop、端到端数据流、控制流和并发顺序。用户可用普通 Python、
NumPy/SciPy 与窄 public primitives 显式表达：

```python
with optimization_scope(...) as run:
    evidence = run.read_evidence()
    costs = calculate_cost(evidence)
    training_data = user_transform(evidence, costs)
    surrogate_state = fit(training_data)
    pool, search_state = search(costs)
    prediction = predict(surrogate_state, pool)
    selected = select(pool, prediction, costs)
    handle = run.start_evaluation(selected)
    results = handle.wait()
```

这只是职责和数据流示意，不冻结名称、同步形式或类型。阶段 2--6 的 evidence 决定真实 API。

“program 拥有 loop”不等于 framework 放弃可靠性。yadof 继续强制拥有 campaign/generation
scope、task/program snapshot、workspace lock、bounded recording、durable commit、handle state
machine、backend cleanup/recovery、optimizer/checkpoint identity 和 generation-boundary resume。
workspace program 通过这些 scope/primitives 选择显式顺序，不能绕过它们。

## 跨阶段不变量

- **INV-EVIDENCE**：真实 rawData 是 evidence。合法 evidence 必须
  `validate -> own -> durable publish -> committed acknowledgement` 后，用户 cost 才能运行。
  recorder failure 是 campaign-fatal；predicted rawData/cost 永不进入 recorder。
- **INV-INTERPRETATION**：cost 是绑定 task interpretation identity 的派生 view。evidence、
  execution 和 interpretation status 分离；invalid interpretation 在 optimizer adapter 边界才
  映射为正确宽度 `inf`。
- **INV-LIFECYCLE**：一个 workspace 同时只有一个 campaign。generation 结束前没有 open
  evaluation/training handle、未发布 evidence 或未收口 state；异常、取消和 resume 都有明确
  cleanup。
- **INV-PROGRAM**：一个 `yadof run` 冻结一份 program snapshot。只在完整 generation
  boundary 停止并 resume 时加载修改后的 program；不恢复任意 Python 中间局部变量。
- **INV-CAPABILITY**：保留全部现有 optimize/surrogate/tools、fast/local/distributed 模式与
  fail-closed/full-real fallback。GPSAF `gamma` 保持现状。只有 Stage 8 证明旧路径无消费者后
  才能删除隐藏编排。
- **INV-BACKEND**：fast/local/distributed 共享 evaluation/evidence/result 语义，各自成熟的
  worker/process/scheduler transport、timeout、resource 与 cleanup 机制继续由 backend 实现。
- **INV-ALGORITHM**：pymoo 继续拥有 GA/NSGA-III operators、ask/tell 与 survival 数值；BoTorch
  继续拥有 qLogNEHVI 数值。yadof 只提供组合、身份、失败和真实评估边界。

各阶段 TODO 必须在局部重新陈述其关键要求，不能只引用这些编号。

## Evidence、interpretation 与 publication 顺序

Stage 1 采用 bounded two-phase coordinator，而不是“每得到一个 row 就立即 offer 并同步等待”
的串行实现：

```text
prepare/own several completed evidence rows
  -> bounded group publication
  -> per-row or per-group committed receipts
  -> deterministic parent-side current-cost interpretation
```

receipt 只能在 immutable segment 原子发布且 recovery discovery 可见后成功。writer death、
oversized envelope、重试耗尽必须唤醒所有 waiter 并中止 campaign。已 commit 但尚未解释的
队列同样受显式内存/数量上限约束。cost callback 可能因 commit 后崩溃而在后续 snapshot 被
再次调用，因此它必须被视为 replayable/at-least-once 派生解释，文档应要求 deterministic、
无不可重放副作用的实现。

Stage 2 在现有 `candidate_id` evidence identity 之上区分 design key、evidence row identity 和
变换后 row identity。CostTable 的 interpretation identity 至少绑定 evidence、task fingerprint
和 objective schema。Dataset/CostTable 是只读/owned/lazy 的内存 view，不是第二套持久真值。

## Program、backend 与检查边界

训练和真实评估是否重叠由 program 的代码顺序决定，backend 不隐式选择 orchestration policy。
唯一 package starter 使用三 backend 都安全的保守顺序；source-checkout examples 可以展示
有资源说明的异步 overlap。

`yadof check` 必须保持 read-only：它可以验证 program source、声明、入口和 capability
compatibility，但不能执行任意 optimization loop、启动 evaluation 或训练。若需要运行级验证，
使用名称和风险明确的 bounded dry-run/smoke 边界，不能把它伪装成 `check`。

program snapshot 在一次 run 内冻结；cost/evaluator/task snapshot 仍按 generation 刷新。
program resume 只从完整 generation state 与 durable evidence 开始，不承诺 mid-generation
Python continuation。

## 保留、迁移与删除政策

- 保留 real search、GPSAF、posterior-assisted/qNEHVI、conditional-INR、PCA/SVD、
  Hierarchical CAE、viewer/tools、benchmark integration 和三 backend 的现有能力。
- GPSAF `alpha`、`beta`、`gamma`、seed、archive、duplicate、validation、identity 和 diagnostics
  在本重构中保持等价。即使当前 `gamma` 不参与选择数学，也不删除、不迁移为无效字段、不写
  删除 parity 或 0.5.0 removal note。未来若要删除，需独立用户授权、TODO 和 evidence。
- prediction 类型不能混同：GPSAF predicted current cost、posterior joint objective samples 和
  real CostTable 使用不同类型/能力边界。
- posterior/qNEHVI 不因显式 program 自动变为 eligible/default；typed readiness、hard stop 和
  full-real fallback 保持 fail closed。
- Stage 6 允许一个有终止条件的 pilot dual path；Stage 7 完成消费者迁移；Stage 8 必须删除
  已无消费者的旧 path。0.5.0 不保留永久 dual orchestration。
- parked trust-region、noise-robust 与 acquisition-protocol TODO 不因本 Goal 自动激活；Stage 7
  只迁移它们当前依赖的公共边界并更新 handoff 术语。

## Starter、examples 与 user docs 最终交付

- `src/yadof/_resources/templates/default/workspace/submit/optimization.py` 是唯一 package starter，
  采用三 backend 都安全的完整通用 program。
- 顶层 source-checkout `examples/` 下建立 optimization-program examples 目录。每个
  `optimization.py` 有同 basename `.md`，解释背景、适用场景、数据流、资源/并发取舍、组件和
  所需 workspace 环境。
- examples 不是完整 workspace，不复制 `config.py`、`calc_cost.py`、`job_template/` 或
  simulator assets；普通 pip 安装不保证包含顶层 examples。
- `user_doc/` 提供轻量索引与每例一句用途说明，不复制 example 旁的详细背景。
- `yadof init` 始终生成唯一 starter；不增加模板 selector、算法 registry、字符串 discovery 或
  新的 init 选项。

最终示例至少覆盖 real-only、顺序 surrogate、显式 evaluation/training overlap 和自定义
cost/surrogate 数据分流。posterior-assisted 只有在 public primitives 能诚实表达当前 blocked/
eligible/fallback 状态时才提供示例。

## 八阶段地图与 ledger

| 阶段 | 当前状态 | TODO | 主要交付 |
|---|---|---|---|
| 1 | 已完成并归档（2026-08-30） | [publication before cost](../obsolete/todo/20260830_174607_explicit-optimization-stage-1-preserve-evidence-on-cost-failure.md) | bounded group commit、receipt、replayable interpretation、性能/批量基线 |
| 2 | 已完成并归档（2026-08-31） | [Dataset/CostTable](../obsolete/todo/20260830_174608_explicit-optimization-stage-2-dataset-and-cost-tables.md) | stable identity、live/durable view、invalid interpretation |
| 3 | 已完成并归档（2026-08-31） | [Evaluation Handle](../obsolete/todo/20260830_174609_explicit-optimization-stage-3-evaluation-handle.md) | start/wait/cancel、scope/cleanup、三 backend 同义 |
| 4 | 已完成并归档（2026-08-31） | [surrogate fit/predict](../obsolete/todo/20260830_174610_explicit-optimization-stage-4-surrogate-fit-predict.md) | PCA/SVD 显式数据、state/checkpoint/provenance |
| 5 | 预测性，已授权届时精化/执行 | [search/select](../toDo/20260830_174611_explicit-optimization-stage-5-search-selection-primitives.md) | opaque pymoo state、GPSAF 原语、gamma 不变 |
| 6 | 预测性，已授权届时精化/执行 | [workspace program pilot](../toDo/20260830_174612_explicit-optimization-stage-6-workspace-program-pilot.md) | real-only 与 PCA/SVD+GPSAF pilot、program freeze |
| 7 | 预测性，已授权届时精化/执行 | [retained capability migration](../toDo/20260830_220200_explicit-optimization-stage-7-retained-capability-migration.md) | advanced paths、callbacks、viewer/tools/benchmark 迁移 |
| 8 | 预测性，已授权届时精化/执行 | [cutover and 0.5.0](../toDo/20260830_220201_explicit-optimization-stage-8-cutover-and-release.md) | 删除旧编排、starter/examples/docs、release |

Goal 启动后，每一行还必须更新以下运行字段；开始时为空不是缺证据：

| 阶段 | 输入 HEAD / TODO digest | accepted tests / benchmark / change record | commit / push | 下一动作 |
|---|---|---|---|---|
| 1 | `17c3e95b3a24184977b300972661a48650632ac7` / `6A01CBD8…CABB`；0.4.2 installed-wheel，同一 recording harness/input `c3f6a5cc…cd34` / `7ba18420…233b` | pre/post 100-row：5/5 durable 100，均为 7 segments，median wall `0.2101266 -> 0.1353709 s`，signed commit-to-cost median `-25.3994 -> +0.33655 ms`；installed-wheel full pytest `388 passed in 81.06s`；fast smoke `40/40/40`、measured `2000/2000/2000` 均 collected/valid；[change record](../change_records/20260830_234247_stage-1-evidence-first-finalization.md) | Stage 1 closure commit（本行所在提交）；fresh `origin/main=9b4ed745…a0ac`，closure 后 behind 0 / ahead 3，未达 ahead >= 5 gate，push skipped | 读取、精化并执行 Stage 2 |
| 2 | `f74b1a46644925064be3d8fa310ff9b5d2ef4def` / pre-refinement `B103F453…FD67`；Stage 1 accepted commit/evidence，installed yadof 0.4.2 | direct `12/12`、recording/session `37/37`、focused `76/76`、installed-wheel full pytest `400 passed in 81.00s`；fast smoke `40/40/40`、measured `2000/2000/2000` 均 collected/valid，20 generations、generation-zero 100/100、runtime `539.1970091 s`；[change record](../change_records/20260831_003835_add-identity-preserving-evidence-cost-views.md) | Stage 2 closure commit（本行所在提交）；fresh `origin/main=9b4ed745…a0ac`，closure 后 behind 0 / ahead 4，未达 ahead >= 5 gate，push skipped | 读取、精化并执行 Stage 3 |
| 3 | `39da8b3a9ea2262b73a6411c40035ec21c558a5f` / pre-refinement `A8A9219D…3E08`、post-refinement `21B934A3…F7FA`；Stage 2 accepted commit/evidence，installed yadof 0.4.2 | direct `10/10`、focused `109/109`、installed-wheel full pytest `410 passed in 86.27s`；fast smoke `40/40/40/40`、measured `2000/2000/2000/2000` 均 collected/valid、zero anomalies；measured elapsed `568.137814 s`；[change record](../change_records/20260831_084158_add-unified-evaluation-handle-lifecycle.md) | Stage 3 closure commit（本行所在提交）；fresh `origin/main=9b4ed745…a0ac`，closure 后 behind 0 / ahead 5，达到 gate 后 normal push | 读取、精化并执行 Stage 4 |
| 4 | `38c091d264cc47d9457878d76d8a784b97e7e45b` / pre-refinement `33E66D8E…7B00`、post-refinement `B7E1CC3C…FC13`；Stage 3 accepted commit/evidence，installed yadof 0.4.2 | direct `20/20`、GPSAF/posterior `25/25`、installed-wheel full pytest `419 passed in 86.88s`；fast smoke `40/40/40/40`、measured `2000/2000/2000/2000` 均 collected/valid、zero issues；20/20 training/manifests，measured result runtime `624.151074 s`；[change record](../change_records/20260831_100109_add-explicit-surrogate-fit-state-prediction.md) | Stage 4 closure commit（本行所在提交）；fresh `origin/main=38c091d…e45b`，closure 后 behind 0 / ahead 1，未达 ahead >= 5 gate，push skipped | 读取、精化并执行 Stage 5 |
| 5--8 | 各阶段开始时冻结 | 待各阶段执行 | 待各阶段执行 | 严格串行 |

完成阶段归档后，ledger 链接必须指向 `obsolete/todo/` 中的同名文件。若阶段 evidence 只要求
在既定阶段内重做或调整，更新当前 TODO 与 ledger 后继续；若要求改变八阶段地图，则命中暂停
边界。

## 验证与 benchmark 政策

每个源码实施阶段都遵循开发指南的 wheel build、host force-reinstall、import-origin、
focused/full installed-package tests。除通用回归外，按阶段增加：

- Stage 1：publication ordering、receipt/writer death/backpressure、segment occupancy、wall time、
  commit-to-cost latency、backlog 与 peak memory；
- Stage 2：identity/filter/reorder、live/durable equivalence、invalid/reinterpretation；
- Stage 3：fast/local/distributed start/wait/cancel/failure/cleanup/resume；
- Stage 4：transformed training data、content digest、checkpoint recovery、prediction non-entry；
- Stage 5：old/new deterministic selection parity、duplicate/refill、single/multi objective、
  GPSAF `gamma` identity/diagnostics unchanged；
- Stage 6--8：program freeze、real-only/GPSAF/posterior fallback、capability matrix、CLI/init/examples、
  stop/resume 和 no-dual-path evidence。

Stage 1 在修改源码前先运行一个 bounded、可重复的 recording microbenchmark，冻结当前
throughput、segment occupancy、latency、backlog 与 peak memory；改后用同一 harness 比较。
它不是优化性能证据。其余阶段以各自 pre-change tests/evidence 为基线。

每个实施阶段还运行一次完整 fast synthetic measured benchmark：

- baseline：`test-com/synthetic-antenna`；
- representative strategy：NSGA-III + GPSAF + PCA/SVD，届时在精确 TODO 冻结完整 settings；
- population `100`、generations `20`、seed `[101]`，即 2,000 次真实 synthetic evaluation；
- measured 前在独立 fresh workspace 运行同源 `20 x 2` smoke，并用 `check` 与
  `plan --json` 证明除预算外的 baseline、source digest、strategy、seed、policy 和 postprocessor
  相同；
- measured cell 必须 `collected=true`、`valid=true`、attempted `2000` 且无缺代/缺个体；
- 这是结构、可靠性和回归 gate，不要求 hypervolume 相对某个 arm 提升，也不能单独证明全部
  retained capability。

该 Goal 明确授权这些 fast、synthetic、workspace-local benchmark 使用 Windows host execution
在 foreground 运行，并由同一 agent turn 跟随同一 terminal/session 到最终退出码；这对该 Goal
覆盖的 runs 明确取代 yadof-benchmark 文档中 full-budget detached-handoff 的默认等待方式。
每个阶段的 long run 只启动一次；使用运行时支持的最长有界 wait 持续等待同一 session，不用
`sleep`、高频轮询或重复 run。若实际成本明显超出计划，则按暂停边界处理。

上述授权不包含真实 simulator、local/distributed full-budget benchmark、共享集群或付费执行。
local/distributed 只做相称的 fake/contract/small synthetic smoke。documentation-only plan 修订
本身不运行 wheel、pytest 或 benchmark。

## 最终完成判据

单一 Goal 只有在以下结果共同成立时完成：

- 八个阶段均有 accepted evidence、change record 和 commit，TODO 已归档且 ledger 完整；
- `optimization.py` 用普通 Python 显式表达 retained algorithms 的完整数据流和并发顺序；
- evidence publication、interpretation identity、Dataset/CostTable、handle lifecycle、
  prediction non-entry 和 backend cleanup 有直接测试/recovery evidence；
- 所有既有 optimize/surrogate/tools 与三 backend 能力仍可用；GPSAF `gamma` 的 API、validation、
  identity 和 diagnostics 与本重构前等价；
- 唯一 starter、多份 paired source examples、user-doc 索引、`init` 无 selector、`check`
  不执行 program 的合同已经交付；
- strategy-owned loop、hidden session training reads、`after_jobs_submitted` 和其他无消费者旧
  编排已删除，没有永久 dual path；
- 0.5.0 wheel 已按 installed-package workflow 验收，full suite 与最终 100 x 20 benchmark
  成功，migration/capability matrix、architecture、blueprints、terminology 和 user docs 一致；
- 已按仓库规则完成最终 fetch/push 判断并向用户报告结果。

完成不要求用户再发送一次“确认”。如果最终证据触发前述实质暂停边界，则 Goal 保持未完成并
报告具体 blocker，而不是把初始草图强行发布。
