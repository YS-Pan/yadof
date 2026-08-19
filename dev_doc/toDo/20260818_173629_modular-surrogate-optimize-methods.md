# Surrogate 方法与 Optimize 两级方法目录重构

## Execution Dependency

- 这是手工触发、一次性的第二阶段任务。
- 必须先完整执行
  `dev_doc/toDo/20260819_144148_simplify-surrogate-real-only-training.md`，确认其代码、测试、
  文档、安装态验收和归档条件全部满足，并把该文件移入 `dev_doc/obsolete/`，才能开始本
  toDo。
- 本任务以简化后的 real-only、field/slot-balanced、ensemble-with-bootstrap 训练实现和最终
  checkpoint schema 为唯一基线。不得重新引入 mixup、relative loss、task importance、
  rank-based forced queries、GPSAF ensemble/error noise 或 legacy compatibility。

## Context

- 当前 `src/yadof/surrogate/` 只有 conditional INR deep ensemble 一套方法，
  `src/yadof/optimize/` 只有 GPSAF + pymoo GA/NSGA-III 一套完整方法组合。两套实现都把
  公共编排、workspace 状态和具体算法放在同一层，新增方法时容易复制 campaign、
  history、scheduler、checkpoint、evaluation 和 metadata 逻辑。
- Optimize 有两个不同的扩展轴：一是完整替代 GPSAF 的 optimizer method；二是保留
  GPSAF 流程，只替换其内部 evolutionary/search backend，例如将当前 GA/NSGA-III
  backend 替换为 future particle-swarm backend。两级扩展不得挤进同一个 method ID。
- 现有公开入口是 `yadof.surrogate` 与 `yadof.optimize`。优化、历史清理、
  surrogate viewer 和测试还直接依赖部分具体实现文件；仅移动文件会破坏这些调用，
  不能把目录整理当成机械重命名。
- yadof 的稳定数据链仍然是
  `normalized variables -> rawData -> current cost`。新 surrogate 方法必须预测
  rawData，再用当前 workspace cost 解释结果；optimizer 和 surrogate 都不能建立
  平行的权威 `variables -> cost` 路径。
- 这次重构的目标是让内置方法具有清楚、可扩展的边界，不是建立第三方插件系统，
  也不是同时实现第二套真实算法。

## Goal

- 在 `surrogate/` 与 `optimize/` 下为每套具体方法建立独立子包。
- 把真正跨方法稳定的机制留在父包，由所有方法复用；方法特有模型、候选生成、
  checkpoint artifact 和算法状态只留在对应子包。
- 增加两级、最小、可验证的静态注册边界：顶层选择完整 surrogate/optimizer method；
  GPSAF method 内部独立选择 search backend。以后既可以新增完整 optimizer 子包，也可以
  只在 `gpsaf/search/` 增加 backend，而不复制 campaign 或 GPSAF surrogate phases。
- 保持当前默认行为：未指定方法时仍使用 conditional INR、GPSAF 和 pymoo
  GA/NSGA-III backend；
  `yadof.optimize.run_*`、`yadof.surrogate` 的现有稳定公开调用继续可用。
- 保持 workspace 隔离、generation task snapshot、rawData-first、current-cost、
  staggered training、recording-loss isolation 和安装态 wheel 测试契约。
- 一个 workspace 从首次 campaign 起固定一个 surrogate method、一个完整 optimizer method
  以及该 optimizer 的内部 backend；切换任一项必须使用新 workspace 或先显式 clear。

## Non-Goals

- 本任务不实现新的真实 surrogate 或 optimizer 算法。
- 本任务不实现 particle swarm，只建立 current pymoo backend 能够被未来 backend 替换的
  边界；test double 只能验证 dispatch/依赖方向，不能被描述成第二算法的有效性证明。
- 本任务不允许 workspace 通过任意 Python import path 加载不受信任实现；第一版使用
  package 内静态 registry。
- 本任务不借结构调整重新调参、改变 GPSAF 数值策略、修改 conditional INR 网络，
  重新连接 ensemble trust，或改变默认 candidate/checkpoint 数值结果。
- 本任务不支持同一 workspace 保存并切换多种方法状态，也不读取、转换或展示本系列任务
  之前的旧 history/checkpoint。
- 本任务不顺带创建泛化的 `utils.py`。只有具有稳定跨方法语义的代码才能留在父包；
  只有一个调用方的便利函数继续属于具体方法。

## Current Coupling To Resolve

- `optimize/api.py` 和 `optimize/runner.py` 从 `gpsaf.py` 取得
  `OptimizationResult`，导致公共 campaign 层反向依赖具体算法。
- `gpsaf_misc.py` 同时含有公共 population/cost/history/evaluation 逻辑和 GPSAF
  candidate 逻辑，需要按职责拆分，不能整文件搬迁。
- `gpsaf.py`、`gpsaf_phases.py` 和 `gpsaf_pymoo.py` 通过 pymoo `Algorithm`、
  `Population`、`Individual`、ask/tell/clone 细节耦合；若只替换为 particle swarm，当前
  边界会迫使新 backend 复制或改写 GPSAF phase orchestration。
- `surrogate/scheduler.py` 直接使用 `runtime.StateKey` 和 conditional-INR runtime；
  scheduler 目前不是方法无关的。
- `surrogate/types.py` 同时含有通用 training bundle 和带 Torch/
  `INRTrainConfig` 的具体 state，公共类型会加载具体模型依赖。
- 简化 toDo 已建立 method-aware checkpoint manifest/path；目录重构必须保留其
  format/method/policy 与 atomic publication，不得再做第二次格式迁移。
- `optimize/gpsaf_phases.py` 动态导入 `yadof.surrogate.runtime` 来构造 session
  training data，绕过了 surrogate 的父包 API。
- `tools/history.py` 直接 reset 当前 surrogate runtime/scheduler；重构后应走父包 lifecycle
  API，但一个 workspace 只会有当前选定方法的 pending task、state 和 checkpoint。
- surrogate viewer backend 与相应测试直接导入
  `surrogate.modeling/runtime/types` 的 conditional-INR 私有函数和类型。重构后需要一个
  有能力声明的 package-internal inspection 边界，不能把这些私有依赖散布到 UI。
- `tests/test_packaged_optimize_surrogate.py` 的 source-import 检查只扫描父目录
  `*.py`；新增子包后必须改成递归检查。

## Proposed Source Layout

最终文件名可在实现时小幅调整，但职责和依赖方向应保持如下：

```text
src/yadof/surrogate/
  __init__.py                 稳定、轻量的公开 re-export
  api.py                      workspace-explicit 公共调用与 method dispatch
  contracts.py                最小 method protocol 与公共结果类型
  registry.py                 内置 method ID -> lazy backend factory
  training_data.py            公共 rawData-first training bundle/session 适配
  scheduler.py                当前 workspace method 的 staggered training
  metadata.py                 方法无关的 compact training metadata
  checkpoints.py              已定稿 manifest/path/atomic discovery 公共规则
  conditional_inr/
    __init__.py               method registration surface
    backend.py                method contract 实现、state/recovery/prediction
    data.py                   INR query table、flatten/reconstruct/scaler/off-grid
    modeling.py               Torch conditional INR 与 deep ensemble
    checkpoints.py            INR artifact 序列化/恢复
    types.py                  INR schema、scaler、train config 和 state
    inspection.py             conditional-INR viewer/audit 适配

src/yadof/optimize/
  __init__.py                 稳定公开 re-export
  api.py                      campaign/session/config/snapshot 编排与 dispatch
  contracts.py               完整 optimizer method 的最小 protocol
  registry.py                内置完整 optimizer method 的 static lazy registry
  types.py                    Population、Costs、HistoryRecord、OptimizationResult
  history.py                  当前 session/history 的公共只读适配
  evaluation.py               backend-neutral real-evaluation handoff
  problem_info.py             参数/目标 shape 公共解析
  runner.py                   run ID、generation metadata、strict failure 辅助
  gpsaf/
    __init__.py               完整 GPSAF method registration surface
    backend.py                一代 GPSAF 主流程与 search-backend dispatch
    phases.py                 alpha/beta/exploration 与 surrogate pressure
    types.py                  CandidateRecord、SearchContext 等 GPSAF 内部类型
    search/
      contracts.py            GPSAF 内部 search backend 的最小 contract
      registry.py             内置 search backend 的 static lazy registry
      pymoo_ga_nsga3/
        __init__.py           backend registration surface
        backend.py            当前 GA/NSGA-III、reference directions、ask/tell
```

父包文件不应导入 Torch、具体 pymoo algorithm 或 viewer UI。registry 只在选中方法时
lazy import 对应子包，保证普通 CLI/config/help 路径仍然轻量。

这是职责布局而不是必须机械创建的文件清单。实现时若 `history.py`、`evaluation.py` 或某个
contract 只有一个薄调用方，应合并回最近的领域模块；不得为了图形对称制造二三十行的
空壳文件、通用 `utils.py` 或多层原样转发。相反，`gpsaf/phases.py` 与 search backend
拥有独立状态和依赖时可以继续分文件，不以最少文件数为目标。

## Common Contracts

### Surrogate parent package

- 为内置方法定义稳定 `method_id`；当前方法使用 `conditional_inr`。
- 公共 training bundle 只包含 parameter names、normalized rows 和 owned/rawData
  samples。rawData query table、field embedding、target scaler 和 Torch device 都是
  conditional-INR 私有实现。
- optimizer-facing prediction 继续返回每个 candidate 的 current-cost row 与每目标
  interval。方法必须先生成完整兼容 rawData，再调用当前 task cost。
- scheduler 只依赖 method contract：train、has/latest/reset 和 state key；不得导入
  `conditional_inr.backend`。
- metadata 接受小型公共 training summary，并记录 `surrogate_method`；不得要求具体
  `SurrogateState`。
- 当前 viewer adapter 归入 `conditional_inr/inspection.py`，不得继续从 viewer 散布对
  modeling/runtime/types 私有函数的导入。等第二个真实 method 出现后，再根据实际能力差异
  决定是否需要公共 capability facade；本任务不预建 capability matrix。

### Complete optimizer method

- 为完整 optimizer 定义稳定 `method_id`；当前 method 使用 `gpsaf`。GA/NSGA-III 属于其
  内部 search backend，不进入完整 method ID。
- `api.py` 继续唯一拥有 CampaignSession、每 generation config reload、task snapshot、
  metadata 记录和 all-infinite policy。具体方法只实现一代 candidate mechanics。
- `OptimizationResult` 移到公共 `types.py`，至少保留现有字段并增加稳定
  `optimizer_method` / `surrogate_method` provenance；公共层不能从具体方法导入类型。
- history loading、problem shape 和 real-evaluation dispatch 由父包提供。方法子包只
  选择 normalized candidates，不直接操作 recorder 或 simulator。
- GPSAF 只通过 `yadof.surrogate.api`/contract 使用当前 surrogate，不直接导入某个
  surrogate runtime。real evaluation 仍验证每个 surrogate 选中的 candidate。

### GPSAF internal search backend

- 当前 backend ID 使用 `pymoo_ga_nsga3`：单目标由 GA 处理，多目标由 NSGA-III 处理。
- `gpsaf.backend/phases` 继续拥有 surrogate-assisted alpha/beta/exploration、fallback、
  candidate source 和 real-validation policy；search backend 只拥有 population state、
  evolutionary proposal/advance、clone/seed 与其算法内部 diagnostics。
- backend contract 只能使用 normalized candidate arrays、backend-neutral problem/objective
  信息和最小 opaque state；不得把 pymoo `Individual`、`Population`、`Algorithm` 或
  reference-direction 类型提升到 GPSAF/父包公共 contract。
- contract 需要支持从当前真实 history 初始化、按 seed 提议候选、接收真实 objective、
  clone/continue state，并对 objective count/bounds 不支持给出明确错误。具体函数划分应从
  现有 GPSAF 调用点提取，不预先设计第三方插件 API。
- future `particle_swarm` 可以作为同级 backend 注册。它替换 proposal/evolution mechanics，
  不复制 GPSAF phases、campaign、real evaluation、history、surrogate 或 metadata。

## Configuration And Lifecycle Decisions

- 新增三个结构型配置：
  - `SURROGATE_METHOD = "conditional_inr"`；
  - `OPTIMIZE_METHOD = "gpsaf"`；
  - `OPTIMIZE_GPSAF_SEARCH_BACKEND = "pymoo_ga_nsga3"`。
- search-backend 配置只由选中的完整 optimizer method 解释；未来非 GPSAF method 不得被迫
  实现或接受 GPSAF-specific backend。未知/不适用 ID 在任何 evaluation 开始前明确失败并
  给出允许值。
- 第一轮重构保留现有 `OPTIMIZE_*`、`OPTIMIZE_SURROGATE_*` 和
  `SURROGATE_INR_*` 配置名，避免把目录迁移与 workspace 配置重命名混在一起。新增
  方法的配置必须使用清晰 method-specific 前缀；如需重命名旧配置，单独制定迁移。
- 三个 selector 都在 workspace 首次 campaign 启动时冻结并记录。generation reload 发现
  任一 selector 与 workspace provenance 不同，必须在 evaluation 前失败，要求使用新
  workspace 或显式 `history clear`；不支持同 workspace 多方法 state/checkpoint 共存。
- surrogate checkpoint 继续使用前置简化任务已经定稿的
  `SURROGATE_CHECKPOINT_DIR/<method_id>/generation_*.json`、`format_version`、
  `surrogate_method`、`training_policy` 和 atomic publication。目录重构只移动 writer/
  loader 代码，不改变格式，也不增加 legacy reader。
- `history clear` 等 workspace 操作等待并 reset 当前 workspace 唯一选定的 method/backend
  state，然后删除 checkpoint/history root；无需实例化或 reset 所有 registry entries。
- optimization/surrogate metadata 同时记录 `optimizer_method`、适用时的
  `optimizer_search_backend` 和 `surrogate_method`。本任务只支持新优化，不处理缺失字段的
  旧 metadata。

## Migration Map

| Current file/responsibility | Target |
|---|---|
| `optimize/gpsaf.py` generation flow | `optimize/gpsaf/backend.py` |
| `optimize/gpsaf_phases.py` | `optimize/gpsaf/phases.py`；session bundle 调用改走父包 surrogate API |
| `optimize/gpsaf_pymoo.py` | pymoo-independent GPSAF orchestration 留 `gpsaf/`；GA/NSGA-III state/ask/tell 移入 `gpsaf/search/pymoo_ga_nsga3/backend.py` |
| `gpsaf_misc.py` population/cost/history/evaluate | 分到父包 `types.py`、`history.py`、`evaluation.py` |
| `gpsaf_misc.py` GPSAF comparison/key/candidate helpers | 留在 `gpsaf/` 的明确领域文件中 |
| `OptimizationResult` | `optimize/types.py` |
| `surrogate/modeling.py` | `surrogate/conditional_inr/modeling.py` |
| `surrogate/runtime.py` history/session loading | `surrogate/training_data.py` |
| `surrogate/runtime.py` flatten/query/scaler/off-grid | `surrogate/conditional_inr/data.py` |
| `surrogate/runtime.py` training/state/recovery/predict | `surrogate/conditional_inr/backend.py` |
| `surrogate/checkpoints.py` | 已定稿 manifest/path/atomic 规则留父包，INR payload 移入 method 子包；持久化格式不变 |
| `surrogate/types.py` | common bundle/result 留父包 contract；INR/Torch state 移入 method 子包 |
| `surrogate/scheduler.py` | 留父包，改为当前 workspace method 的 registry/contract 驱动 |
| viewer 的 private INR imports | 集中改走 `surrogate/conditional_inr/inspection.py`；出现第二真实 method 后再评估公共 facade |

删除旧模块前必须用 import/caller/test 搜索证明没有剩余生产调用。不要永久保留只做原样
转发的兼容模块；迁移同一次变更中的内部调用后直接删除旧路径。稳定公开入口
`yadof.optimize` 和 `yadof.surrogate` 继续保留。

## Implementation Plan

### Phase 0 - Freeze Existing Behavior

- [ ] 确认前置简化 toDo 已归档，active code 没有 mixup/importance/relative/rank heuristic、
  GPSAF spread/error noise 或 legacy checkpoint reader。
- [ ] 为当前公开 API、seeded candidate generation、single/multi-objective GA/NSGA-III、
  warm start、GPSAF fallback/alpha/beta/exploration 增加结构重构行为测试。
- [ ] 固定简化后的 conditional-INR field-balanced training、ensemble/bootstrap/spread、
  current-cost re-evaluation、当前 checkpoint recovery、workspace isolation 和 staggered
  scheduling 测试；不冻结已删除的旧行为。
- [ ] 记录当前 import-time dependency；证明普通 `yadof --help`、config 和 optimize
  import 不会因为 registry 提前加载 Torch/viewer UI。

### Phase 1 - Add Minimal Common Types, Dispatch, And Selectors

- [ ] 只建立当前调用面实际需要的父包 types、最小 contracts 和 static lazy registry；
  不增加 capability matrix、第三方 plugin hooks 或 speculative lifecycle methods。
- [ ] 将 `OptimizationResult` 和真正公共的 normalized population/history/evaluation
  类型移到父包，消除公共 API 对 `gpsaf.py` 的反向依赖。
- [ ] 添加 surrogate、完整 optimizer、GPSAF search backend 三个 selector 的验证、默认值、
  `check` 输出、workspace freeze 和 metadata provenance。
- [ ] 内部 test double 只验证 dispatch、错误处理和 common layer 不导入具体数值 backend；
  不把它写成“第二真实算法已经证明可接入”的完成结论。

### Phase 2 - Move Conditional INR Into Its Method Package

- [ ] 先拆分 common training bundle 与 conditional-INR schema/model/state，再移动实现；
  每一步运行 focused tests，避免一次搬动 2,000 多行后定位失败。
- [ ] scheduler/runtime 通过当前 workspace 固定 method dispatch；不实现同 workspace 多
  method state key 或共存 discovery。
- [ ] 移动 checkpoint writer/loader 时保持前置任务的 method namespace、format/method/
  policy 和 atomic publication 逐字段不变；不新增 legacy reader。
- [ ] 保留 full-grid optimizer/audit 路径和 off-grid viewer 路径的现有数值语义。
- [ ] 将 `surrogate/api.py` 改为 registry dispatch；移除 optimizer 对具体 runtime 的
  session training-data 导入。

### Phase 3 - Move GPSAF And Extract Its Search Backend

- [ ] 将完整 GPSAF method flow 与 phases 移入 `optimize/gpsaf/`，公共 campaign API 不变；
  将 pymoo GA/NSGA-III mechanics 移入 `gpsaf/search/pymoo_ga_nsga3/` 子包。
- [ ] 拆开 `gpsaf_misc.py`，只把至少两个方法会共享且语义稳定的 history/evaluation/
  result 机制留在父包；不要仅为了计划布局拆出薄文件。
- [ ] 从当前 GPSAF 实际调用点提取 backend-neutral search contract，使 phases 不导入 pymoo
  类型。contract 覆盖 init/propose/tell/clone/continue 与 objective compatibility，但不预建
  particle-swarm-specific 参数或状态。
- [ ] 保证 surrogate disabled、first-generation warmup、stale-model fallback、
  after-submit training hook 和 fast-mode fallback 的调用顺序不变。
- [ ] 对相同 history/config/seed 比较迁移前后的 candidate population、source 和核心
  diagnostics；real evaluator 返回顺序与 objective width 必须不变。
- [ ] 证明替换一个最小 search-backend test double 不需要复制 GPSAF alpha/beta/exploration、
  campaign、evaluation 或 history；该测试只证明边界，不宣称算法质量。

### Phase 4 - Update Cross-Module Consumers

- [ ] `tools/history.py` 通过父包 lifecycle API 等待/reset 当前 workspace 唯一方法/backend。
- [ ] surrogate viewer 通过 conditional-INR inspection adapter 读取当前 method checkpoint；
  summary 显示 method，未知 method 明确报错，不预建通用 capability matrix。
- [ ] conditional-INR viewer 的 checkpoint、stored-grid、off-grid、member interval 和
  audit 结果保持不变；未知/不支持方法给出明确错误，不静默按 INR 读取。
- [ ] 更新 tests 中对具体 internals 的 import；公共契约测试优先走公开入口，只有 method
  单元测试直接导入子包。
- [ ] 将 package/source 扫描改为递归，覆盖新子包和 wheel members。

### Phase 5 - Documentation And Cleanup

- [ ] 更新 root architecture、module/file blueprints、terminology、user
  `config_and_run.md`、模板配置和 surrogate-viewer nested dev_doc。
- [ ] 增加完成变更记录，说明两级 selector、目录职责、一个 workspace 一种方法、fresh-
  only checkpoint 边界，以及 ensemble trust 仍未重新连接。
- [ ] 搜索并删除旧内部 import、旧空转发模块、失效 blueprint 与仅因搬迁留下的重复
  helper；不要保留双实现。
- [ ] 只有所有 completion criteria 满足后，才把本 toDo 移到 `dev_doc/obsolete/`。

## Verification Plan

- Focused static/import checks:
  - `python -m compileall -q src/yadof/optimize src/yadof/surrogate`
  - 递归检查两个子树没有旧 project namespace、父包没有具体数值 backend 的反向导入。
- Focused tests:
  - surrogate/full-optimizer/GPSAF-search-backend 三个 selector、invalid/not-applicable ID、
    defaults 和 workspace freeze；
  - 完整 optimizer contract、GPSAF search contract、seeded behavior、history/failure/
    workspace isolation；
  - surrogate registry、field-balanced training、ensemble/bootstrap/spread、当前 checkpoint
    recovery、scheduler/state isolation；
  - history clear 只处理当前 workspace 唯一 method/backend state；
  - surrogate viewer conditional-INR adapter 与 unknown-method error；
  - 改变 ensemble spread 或 training-fit audit 不改变 GPSAF candidate selection；
  - package artifact 成员和 lazy imports。
- Installed acceptance:
  - 按 `dev_doc/README.md` 构建 wheel、force-reinstall 到 sibling `.venv`；
  - 确认 `yadof.__file__` 来自 `.venv/Lib/site-packages` 且没有 `PYTHONPATH` 注入；
  - 运行完整 pytest；
  - 运行 CLI/help、viewer help 和一个 synthetic workspace 的 optimize/surrogate recovery
    测试，不启动真实 simulator 或 HTCondor。
- Diff checks:
  - `git diff --check`；
  - 检查 wheel 包含 conditional-INR method、GPSAF method 和 pymoo search-backend 子包、
    更新后的 docs/blueprints，以及不包含 runtime checkpoint/history。

## Completion Rule

- 前置 real-only/field-balanced surrogate toDo 已完整完成并归档。
- `surrogate/conditional_inr/`、`optimize/gpsaf/` 和
  `optimize/gpsaf/search/pymoo_ga_nsga3/` 分别成为当前 surrogate method、完整 optimizer
  method 和 GPSAF 内部 search backend 的唯一生产实现；父包只保留稳定公共编排。
- 默认 workspace 在未设置 method selector 时与重构前行为等价，现有公开
  `yadof.optimize` / `yadof.surrogate` 调用继续工作。
- 三个 selector 的职责互不混淆：可完整替代 GPSAF，也可只替换 GPSAF search backend；
  test double 证明 dispatch/依赖边界，但不作为未来算法适配性的永久证明。
- 一个 workspace 只持有一组 surrogate/optimizer/search-backend provenance 和 state；改变
  组合必须新建 workspace 或显式 clear，不存在 all-method coexist/reset 机制。
- conditional-INR 当前 checkpoint 格式、atomic publication 和 fresh-only policy 在搬迁前后
  不变；没有 legacy compatibility，viewer 不再直接依赖旧顶层私有模块路径。
- ensemble/bootstrap/spread 输出保持，spread 与 training-fit error 仍不参与 GPSAF 决策。
- 所有相关文档、blueprints、测试和 wheel 内容已更新，安装态完整 pytest 通过；没有
  旧实现、无意义转发层或未说明的 compatibility path 留在生产代码中。
