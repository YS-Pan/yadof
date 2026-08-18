# Surrogate 与 Optimize 多方法目录重构

## Context

- 当前 `src/yadof/surrogate/` 只有 conditional INR deep ensemble 一套方法，
  `src/yadof/optimize/` 只有 GPSAF + pymoo GA/NSGA-III 一套方法。两套实现都把
  公共编排、workspace 状态和具体算法放在同一层，新增方法时容易复制 campaign、
  history、scheduler、checkpoint、evaluation 和 metadata 逻辑。
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
- 增加显式、可验证的方法选择和静态注册边界，使以后新增方法主要表现为：新增一个
  子包、注册 method ID、增加该方法配置与契约测试，而不是修改所有调用方。
- 保持当前默认行为：未指定方法时仍使用 conditional INR 和 GPSAF + GA/NSGA-III；
  `yadof.optimize.run_*`、`yadof.surrogate` 的现有稳定公开调用继续可用。
- 保持 workspace 隔离、generation task snapshot、rawData-first、current-cost、
  staggered training、recording-loss isolation 和安装态 wheel 测试契约。

## Non-Goals

- 本任务不实现新的真实 surrogate 或 optimizer 算法。
- 本任务不允许 workspace 通过任意 Python import path 加载不受信任实现；第一版使用
  package 内静态 registry。
- 本任务不借结构调整重新调参、改变 GPSAF 数值策略、修改 conditional INR 网络，
  或改变默认 candidate/checkpoint 结果。
- 本任务不顺带创建泛化的 `utils.py`。只有具有稳定跨方法语义的代码才能留在父包；
  只有一个调用方的便利函数继续属于具体方法。

## Current Coupling To Resolve

- `optimize/api.py` 和 `optimize/runner.py` 从 `gpsaf.py` 取得
  `OptimizationResult`，导致公共 campaign 层反向依赖具体算法。
- `gpsaf_misc.py` 同时含有公共 population/cost/history/evaluation 逻辑和 GPSAF
  candidate 逻辑，需要按职责拆分，不能整文件搬迁。
- `surrogate/scheduler.py` 直接使用 `runtime.StateKey` 和 conditional-INR runtime；
  scheduler 目前不是方法无关的。
- `surrogate/types.py` 同时含有通用 training bundle 和带 Torch/
  `INRTrainConfig` 的具体 state，公共类型会加载具体模型依赖。
- checkpoint JSON、artifact 目录、内存 state 和 schedule key 没有独立 method ID；
  不同 surrogate 方法不能安全共存在同一 workspace。
- `optimize/gpsaf_phases.py` 动态导入 `yadof.surrogate.runtime` 来构造 session
  training data，绕过了 surrogate 的父包 API。
- `tools/history.py` 直接 reset 当前 surrogate runtime/scheduler，未来必须清理一个
  workspace 中所有方法的 pending task、state 和 checkpoint。
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
  contracts.py                method protocol、公共结果/能力类型
  registry.py                 内置 method ID 的静态、lazy registry
  training_data.py            公共 rawData-first training bundle/session 适配
  scheduler.py                workspace + method keyed staggered training
  metadata.py                 方法无关的 compact training metadata
  checkpoints.py              method-aware manifest/path/discovery 公共规则
  inspection.py               viewer 使用的 package-internal capability facade
  conditional_inr/
    __init__.py               method registration surface
    backend.py                method contract 实现、state/recovery/prediction
    data.py                   INR query table、flatten/reconstruct/scaler/off-grid
    modeling.py               Torch conditional INR 与 deep ensemble
    checkpoints.py            INR artifact 序列化/恢复
    types.py                  INR schema、scaler、train config 和 state

src/yadof/optimize/
  __init__.py                 稳定公开 re-export
  api.py                      campaign/session/config/snapshot 编排与 dispatch
  contracts.py               optimizer method protocol 与 generation context
  registry.py                内置 method ID 的静态、lazy registry
  types.py                    Population、Costs、HistoryRecord、OptimizationResult
  history.py                  当前 session/history 的公共只读适配
  evaluation.py               backend-neutral real-evaluation handoff
  problem_info.py             参数/目标 shape 公共解析
  runner.py                   run ID、generation metadata、strict failure 辅助
  gpsaf_nsga3/
    __init__.py               method registration surface
    backend.py                一代 GPSAF 的主流程
    phases.py                 alpha/beta/exploration 与 surrogate pressure
    pymoo_backend.py          GA/NSGA-III、reference directions、ask/tell
    types.py                  CandidateRecord、PymooContext 等方法内部类型
```

父包文件不应导入 Torch、具体 pymoo algorithm 或 viewer UI。registry 只在选中方法时
lazy import 对应子包，保证普通 CLI/config/help 路径仍然轻量。

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
- inspection capability 独立于 optimizer-facing prediction。每个方法声明是否支持
  checkpoint summary、member inference、rawData audit 和 off-grid query；viewer 对不支持
  的能力给出明确状态，不能假装所有方法都是 INR。

### Optimize parent package

- 为内置方法定义稳定 `method_id`；当前方法使用 `gpsaf_nsga3`，显示名称可说明单目标
  使用 GA、多目标使用 NSGA-III。
- `api.py` 继续唯一拥有 CampaignSession、每 generation config reload、task snapshot、
  metadata 记录和 all-infinite policy。具体方法只实现一代 candidate mechanics。
- `OptimizationResult` 移到公共 `types.py`，至少保留现有字段并增加稳定
  `optimizer_method` / `surrogate_method` provenance；公共层不能从具体方法导入类型。
- history loading、problem shape 和 real-evaluation dispatch 由父包提供。方法子包只
  选择 normalized candidates，不直接操作 recorder 或 simulator。
- GPSAF 只通过 `yadof.surrogate.api`/contract 使用当前 surrogate，不直接导入某个
  surrogate runtime。real evaluation 仍验证每个 surrogate 选中的 candidate。

## Configuration And Lifecycle Decisions

- 新增 `OPTIMIZE_METHOD = "gpsaf_nsga3"` 与
  `SURROGATE_METHOD = "conditional_inr"` 默认值。未知 ID 在任何 evaluation 开始前
  给出允许值列表。
- 第一轮重构保留现有 `OPTIMIZE_*`、`OPTIMIZE_SURROGATE_*` 和
  `SURROGATE_INR_*` 配置名，避免把目录迁移与 workspace 配置重命名混在一起。新增
  方法的配置必须使用清晰 method-specific 前缀；如需重命名旧配置，单独制定迁移。
- 第一版把 method selector 视为 campaign-structural 配置：一个
  `run_generations()` campaign 启动时冻结 optimizer/surrogate method。其他受支持配置
  仍按 generation reload；如果 campaign 运行期间 selector 改变，在下一代 evaluation
  前报错并要求启动新 campaign。这样不会在一个活动 scheduler/optimizer state 中混合
  两套状态语义。
- 新 campaign 可在同一 workspace 选择另一方法。所有 in-memory state、pending
  schedule 和 checkpoint 都按 `(workspace, method_id)` 隔离。
- 不同方法的 checkpoint 写到
  `SURROGATE_CHECKPOINT_DIR/<method_id>/generation_*.json`，manifest 明确包含
  `surrogate_method`、artifact format 和 capability/version 信息。artifact 文件由具体
  方法拥有。
- conditional-INR loader/viewer 在迁移期只读兼容现有平铺
  `generation_*.json` + `generation_*_conditional_inr/`，把缺失 method ID 明确解释为
  legacy conditional INR；新代码只写 method 子目录，不复制、不删除旧 checkpoint。
- `history clear` 等 workspace 级操作等待并 reset 该 workspace 的所有已注册方法，
  然后删除整个 checkpoint root。它不能只处理当前 selector。
- optimization 与 surrogate metadata 都记录 method ID；旧 metadata 缺失该字段只用于
  历史显示，不参与新 registry dispatch。

## Migration Map

| Current file/responsibility | Target |
|---|---|
| `optimize/gpsaf.py` generation flow | `optimize/gpsaf_nsga3/backend.py` |
| `optimize/gpsaf_phases.py` | `optimize/gpsaf_nsga3/phases.py`；session bundle 调用改走父包 surrogate API |
| `optimize/gpsaf_pymoo.py` | `optimize/gpsaf_nsga3/pymoo_backend.py` |
| `gpsaf_misc.py` population/cost/history/evaluate | 分到父包 `types.py`、`history.py`、`evaluation.py` |
| `gpsaf_misc.py` GPSAF comparison/key/candidate helpers | 留在 `gpsaf_nsga3/` 的明确领域文件中 |
| `OptimizationResult` | `optimize/types.py` |
| `surrogate/modeling.py` | `surrogate/conditional_inr/modeling.py` |
| `surrogate/runtime.py` history/session loading | `surrogate/training_data.py` |
| `surrogate/runtime.py` flatten/query/scaler/off-grid | `surrogate/conditional_inr/data.py` |
| `surrogate/runtime.py` training/state/recovery/predict | `surrogate/conditional_inr/backend.py` |
| `surrogate/checkpoints.py` | common manifest/path 规则留父包，INR payload 移入 method 子包 |
| `surrogate/types.py` | common bundle/result 留父包 contract；INR/Torch state 移入 method 子包 |
| `surrogate/scheduler.py` | 留父包，改为 registry/contract 驱动并按 method key 隔离 |
| viewer 的 private INR imports | 改走 `surrogate.inspection`，具体适配仍限制在 viewer backend |

删除旧模块前必须用 import/caller/test 搜索证明没有剩余生产调用。不要永久保留只做原样
转发的兼容模块；迁移同一次变更中的内部调用后直接删除旧路径。稳定公开入口
`yadof.optimize` 和 `yadof.surrogate` 继续保留。

## Implementation Plan

### Phase 0 - Freeze Existing Behavior

- [ ] 为当前默认 method ID、公开 API、seeded candidate generation、single/multi-
  objective GA/NSGA-III、warm start、GPSAF fallback/alpha/beta/exploration 增加行为测试。
- [ ] 固定 conditional-INR training/prediction、interval、current-cost re-evaluation、
  checkpoint recovery、workspace isolation 和 staggered scheduling 测试。
- [ ] 保存一个最小 legacy conditional-INR checkpoint fixture，作为迁移读取契约。
- [ ] 记录当前 import-time dependency；证明普通 `yadof --help`、config 和 optimize
  import 不会因为 registry 提前加载 Torch/viewer UI。

### Phase 1 - Add Common Types, Contracts, Registries, And Selectors

- [ ] 先建立父包 `types/contracts/registry`，让 registry 静态列出 built-in method，
  但 lazy import 实现。
- [ ] 将 `OptimizationResult` 和真正公共的 normalized population/history/evaluation
  类型移到父包，消除公共 API 对 `gpsaf.py` 的反向依赖。
- [ ] 添加两个 method selector、验证、默认值、`check` 输出和 metadata provenance。
- [ ] 用内部 test double 验证新增方法只需实现 contract + registry entry；不要为了测试
  发布第二套假方法。

### Phase 2 - Move Conditional INR Into Its Method Package

- [ ] 先拆分 common training bundle 与 conditional-INR schema/model/state，再移动实现；
  每一步运行 focused tests，避免一次搬动 2,000 多行后定位失败。
- [ ] 将 state key、scheduler key 和 checkpoint manifest 增加 method ID。
- [ ] 实现新 method-namespaced checkpoint writer 和 legacy flat checkpoint reader；验证
  新旧格式产生相同 current-cost prediction。
- [ ] 保留 full-grid optimizer/audit 路径和 off-grid viewer 路径的现有数值语义。
- [ ] 将 `surrogate/api.py` 改为 registry dispatch；移除 optimizer 对具体 runtime 的
  session training-data 导入。

### Phase 3 - Move GPSAF + GA/NSGA-III Into Its Method Package

- [ ] 将一代 method flow、GPSAF phases 和 pymoo mechanics 移入
  `gpsaf_nsga3/`，公共 campaign API 不变。
- [ ] 拆开 `gpsaf_misc.py`，只把至少两个方法会共享且语义稳定的 history/evaluation/
  result 机制留在父包。
- [ ] 保证 surrogate disabled、first-generation warmup、stale-model fallback、
  after-submit training hook 和 fast-mode fallback 的调用顺序不变。
- [ ] 对相同 history/config/seed 比较迁移前后的 candidate population、source 和核心
  diagnostics；real evaluator 返回顺序与 objective width 必须不变。

### Phase 4 - Update Cross-Module Consumers

- [ ] `tools/history.py` 通过父包 lifecycle API 等待/reset 一个 workspace 的所有方法。
- [ ] surrogate viewer 通过 inspection facade 发现 method-aware checkpoints；summary
  显示 method，GUI/audit 只启用 method 声明支持的能力。
- [ ] conditional-INR viewer 的 checkpoint、stored-grid、off-grid、member interval 和
  audit 结果保持不变；未知/不支持方法给出明确错误，不静默按 INR 读取。
- [ ] 更新 tests 中对具体 internals 的 import；公共契约测试优先走公开入口，只有 method
  单元测试直接导入子包。
- [ ] 将 package/source 扫描改为递归，覆盖新子包和 wheel members。

### Phase 5 - Documentation And Cleanup

- [ ] 更新 root architecture、module/file blueprints、terminology、user
  `config_and_run.md`、模板配置和 surrogate-viewer nested dev_doc。
- [ ] 增加完成变更记录，说明 selector、目录职责、checkpoint compatibility 和方法切换
  边界。
- [ ] 搜索并删除旧内部 import、旧空转发模块、失效 blueprint 与仅因搬迁留下的重复
  helper；不要保留双实现。
- [ ] 只有所有 completion criteria 满足后，才把本 toDo 移到 `dev_doc/obsolete/`。

## Verification Plan

- Focused static/import checks:
  - `python -m compileall -q src/yadof/optimize src/yadof/surrogate`
  - 递归检查两个子树没有旧 project namespace、父包没有具体数值 backend 的反向导入。
- Focused tests:
  - config method selection/invalid ID/default compatibility；
  - optimizer contract、GPSAF seeded behavior、history/failure/workspace isolation；
  - surrogate registry、training、checkpoint new/legacy recovery、scheduler/state isolation；
  - history clear 覆盖所有 method state；
  - surrogate viewer conditional-INR 与 unsupported-capability paths；
  - package artifact 成员和 lazy imports。
- Installed acceptance:
  - 按 `dev_doc/README.md` 构建 wheel、force-reinstall 到 sibling `.venv`；
  - 确认 `yadof.__file__` 来自 `.venv/Lib/site-packages` 且没有 `PYTHONPATH` 注入；
  - 运行完整 pytest；
  - 运行 CLI/help、viewer help 和一个 synthetic workspace 的 optimize/surrogate recovery
    测试，不启动真实 simulator 或 HTCondor。
- Diff checks:
  - `git diff --check`；
  - 检查 wheel 同时包含两个 method 子包、更新后的 docs/blueprints，以及不包含 runtime
    checkpoint/history。

## Completion Rule

- `surrogate/conditional_inr/` 和 `optimize/gpsaf_nsga3/` 成为当前两套方法的唯一生产
  实现；父包只保留稳定跨方法机制。
- 默认 workspace 在未设置 method selector 时与重构前行为等价，现有公开
  `yadof.optimize` / `yadof.surrogate` 调用继续工作。
- 至少一个内部 test double 证明 registry/contract 能接入第二种方法而不复制 campaign、
  evaluation、history、scheduler 或 metadata 机制。
- conditional-INR 的 legacy/new checkpoint 都可恢复，method state/schedule/checkpoint
  不跨 workspace 或 method 污染，viewer 不再直接依赖旧顶层私有模块路径。
- 所有相关文档、blueprints、测试和 wheel 内容已更新，安装态完整 pytest 通过；没有
  旧实现、无意义转发层或未说明的 compatibility path 留在生产代码中。
