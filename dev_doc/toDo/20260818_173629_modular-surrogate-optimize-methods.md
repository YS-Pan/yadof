# Surrogate 与 Optimize 可组合组件重构

## Execution Dependency

- 这是手工触发、一次性的组件重构工作流；不能因读取本文而自动执行。
- 必须先完整执行并归档
  `20260819_144148_simplify-surrogate-real-only-training.md`，以最终 real-only、
  field/slot-balanced、ensemble-with-bootstrap 训练和 fresh-only atomic checkpoint 为唯一
  基线。
- 随后必须把本 toDo 作为
  `20260820_125457_workspace-submit-optimization-composition.md` 的协调工作流执行。后者
  负责新 `submit/` workspace 标准、`optimization.py` 加载、snapshot、provenance、
  init/check 与迁移；本文负责把 package 实现拆成可由 workspace 组合的组件。
- 两份协调 toDo 不得独立落地临时中间态，也不得保留 package-owned 完整算法再由
  workspace 做一层表面包装。共享安装态验收全部通过后，两份文件一起归档。

## Revised Context

- 当前 `yadof.optimize.api` 直接调用完整的 `gpsaf.run_one_generation()`；GPSAF 又直接
  绑定 pymoo GA/NSGA-III、surrogate phases、real evaluation 和 history helpers。
- 当前 `yadof.surrogate` 直接公开 conditional-INR runtime；scheduler、checkpoint、
  metadata、viewer 与模型具体 state 互相耦合。
- 旧版本文计划在 package 内建立 complete optimizer method、surrogate method 和 GPSAF
  search backend 三层 static registry，再通过三个 config selector 选择完整组合。新的
  workspace 标准已经改变这一所有权：完整算法只在
  `submit/optimization.py:build_optimization()` 中组合，不能再由 package config/registry
  选择第二次。
- Optimize 仍有多个真实组件角色：global search、GPSAF assistance、surrogate model、
  可追加 refinement，以及 package-owned campaign/evaluation engine。它们需要清楚
  contract，但不再被压成一个 complete method ID。
- 稳定数据链仍是
  `normalized variables -> predicted/real rawData -> current submit calc_cost -> cost`。
  任一 surrogate 组件都必须预测 rawData；workspace composition 不能建立平行的权威
  `variables -> cost` 或 predicted-history 路径。
- 本次重构只建立当前真实调用面需要的组件边界，不建立第三方插件系统，也不实现第二套
  生产 search/surrogate/refinement 数值方法。

## Goal

- 把 conditional INR、GPSAF pressure 和 pymoo GA/NSGA-III mechanics 从 package 根层的
  完整算法耦合中拆出，成为可直接导入、具有稳定 role/identity 的组件。
- package 父层只保留跨组合稳定的 campaign、plan validation、history/evaluation、
  rawData-first training data、scheduler lifecycle、checkpoint publication、metadata 和
  公共 result contracts。
- 新 workspace starter 用这些组件定义当前默认：GPSAF +（单目标 GA / 多目标
  NSGA-III）+ simplified conditional INR。
- 同一个 engine 能运行 multi-objective NSGA-III-only plan，并用 test components 证明
  search/surrogate 可替换、refinement 可追加，而不复制 session、snapshot、real evaluator、
  history、recorder 或 metadata。
- 保持 workspace isolation、generation snapshot、current-cost reinterpretation、staggered
  training、recording-loss isolation、real validation、fresh-only checkpoint 和 lazy
  optional dependencies。

## Non-Goals

- 不实现 production particle swarm、第二 surrogate 或 trust-region refinement；test double
  只验证 contract 和依赖方向，不证明数值有效性。
- 不通过任意 Python import path 加载第三方插件。workspace 只组合安装版 yadof 暴露的公共
  组件和自己的轻量 plan；新增真实组件仍先进入 yadof 并接受 package 测试。
- 不在重构中重新调参、改变 GPSAF 数值策略、恢复 ensemble/error trust、改变 simplified
  conditional-INR 网络或读取 legacy checkpoint/history。
- 不支持一个 workspace 同时维护或切换多套 plan state。改变完整 plan 必须新 workspace
  或显式 clear，并遵守新 toDo 的 plan fingerprint/provenance 规则。
- 不为了目录对称创建空壳 contract、通用 `utils.py` 或多层原样转发；只有至少两个真实
  组件共享且语义稳定的机制才进入父包。

## Component Roles

### Campaign engine and plan contract

- `yadof.optimize.api` 继续拥有 `CampaignSession`、每 generation config reload、双
  source-root snapshot、run/optimization/generation identity、metadata、progress、
  all-infinite policy 和 recorder lifecycle。
- 公共 `OptimizationResult`、normalized population/cost/history types 不能从 GPSAF
  组件反向导入。
- plan contract 只暴露 engine 真正需要的 generation lifecycle 和 component graph；
  `build_optimization()` 返回的完整 graph 位于 workspace snapshot，不在 package registry。
- plan validation 收集 component role、ID/version、state/checkpoint needs 和 capability
  compatibility；不得执行训练、预测或真实 evaluation。
- common real-evaluation handoff 由 engine 提供。组件只能提出 normalized candidates、
  接收 real result 和返回 diagnostics，不能直接写 recorder/history 或把 surrogate 预测
  当作 accepted result。

### Global-search components

- 当前 single-objective GA 与 multi-objective NSGA-III 的 pymoo state、ask/tell、clone、
  seed、reference directions、survival 和 diagnostics 从 GPSAF orchestration 中抽离。
- workspace 默认通过 objective-count dispatch 选择 GA/NSGA-III；NSGA-III-only plan 在
  objective count 小于 2 时必须清楚失败，不能静默回退 GA。
- search contract 使用 normalized arrays、objective rows、backend-neutral problem info 和
  opaque state。不得把 pymoo `Algorithm`、`Population`、`Individual` 或 reference-
  direction 类型提升到 plan/GPSAF/public engine contract。
- future particle swarm 实现同一个 search role；GPSAF 不复制 particle-swarm-specific
  参数或假设。

### GPSAF assistance component

- GPSAF 组件拥有 alpha/beta/exploration、surrogate pressure、warmup/fallback、candidate
  source 和 real-validation policy，但不拥有 campaign/session/recorder。
- 它显式接收 global-search 和可选 surrogate-model 组件，不从 config selector 或 global
  registry 查询默认实现。
- after-submit staggered training、fast-mode fallback 和 lag gate 顺序保持当前行为；
  scheduler-specific callback 仍不能由 fast 伪造。
- post-simplification member spread 和 training-fit diagnostics 保持可观察但不影响
  candidate decision，直到真实 benchmark 后另行设计 trust policy。

### Surrogate-model component

- 公共 training bundle 只含 parameter names、normalized real rows 和 owned/rawData
  samples。query table、field embedding、target scaler、Torch model/device 是
  conditional-INR 私有实现。
- component contract 提供 train/recover/predict rawData、state/checkpoint identity、必要
  lifecycle reset 和 compact summary。optimizer-facing current costs 只能由预测完整 rawData
  经当前 `submit/calc_cost.py` 计算得到。
- scheduler 依赖选中 component 的 contract/state key，不导入 conditional-INR backend。
  一个 workspace 至多一个当前 plan 的 background training task。
- checkpoint 公共层拥有 component namespace、manifest-last atomic publication、discovery
  和通用 provenance；conditional-INR 子包拥有模型 payload、query/scaler/schema
  serialization 和 inspection adapter。
- viewer 通过 artifact component ID 和 inspection adapter 工作；未知或无 inspection
  capability 的组件明确报错，不能默认按 INR 解释。

### Refinement components

- 定义最小可追加 stage role，使 workspace plan 能在 global/GPSAF proposal 后追加 bounded
  proposal + common real-validation 步骤。
- 本任务只用无数值意义的 test component 证明 stage sequencing、budget、diagnostics 和
  evaluator ownership；真正 trust-region surrogate refinement 由其现有 toDo 实现。
- refinement 不是 GPSAF search backend，也不能绕过 rawData-first/current-cost/real-
  validation/session contracts。

## Proposed Source Responsibility Layout

最终文件名可从实际调用面小幅调整；职责和依赖方向必须保持：

```text
src/yadof/surrogate/
  __init__.py                  lightweight public component exports
  contracts.py                shared surrogate component/result protocols
  training_data.py            campaign/public rawData-first bundle adaptation
  scheduler.py                selected component's staggered lifecycle
  metadata.py                 component-neutral compact metadata
  checkpoints.py              namespace/manifest/atomic discovery rules
  conditional_inr/
    __init__.py                public component constructor/identity
    backend.py                 train/recover/predict implementation
    data.py                    query table, reconstruct, scaler, off-grid
    modeling.py                Torch conditional INR deep ensemble
    checkpoints.py            component-specific artifacts
    types.py                   INR-only config/schema/state
    inspection.py              viewer/audit adapter

src/yadof/optimize/
  __init__.py                  stable campaign and component exports
  api.py                       campaign engine + workspace plan invocation
  plan.py                      minimal immutable plan graph/validation
  types.py                     common Population/Costs/History/Result
  history.py                   session/current-history adapter if substantive
  evaluation.py                common real-evaluation handoff if substantive
  problem_info.py              parameter/objective shape
  runner.py                    run identity/metadata/strict helpers
  components/
    dispatch.py                objective-count dispatch if substantive
    gpsaf/
      backend.py               GPSAF assistance role
      phases.py                alpha/beta/exploration
      types.py                 GPSAF-only records/context
    search/
      contracts.py             minimal search role
      pymoo/
        ga.py                  single-objective mechanics
        nsga3.py               multi-objective/reference directions
        common.py              only genuinely shared pymoo helpers
    refinement/
      contracts.py             appendable stage role if separately useful
```

若某个 `history.py`、`evaluation.py`、`common.py` 或 contract 只有一个薄调用方，应
合并回最近的领域文件。不得为了符合图形机械创建文件；Torch/pymoo/private artifact state
也不能为了少文件而泄漏到父层。

## Current Coupling To Resolve

- `optimize/api.py`、`runner.py` 从 `gpsaf.py` 导入 `OptimizationResult`，公共
  engine 反向依赖具体算法。
- `gpsaf_misc.py` 混合 common population/cost/history/evaluation 与 GPSAF candidate
  helpers，需要按实际职责拆分，不能整文件移动。
- `gpsaf.py`、`gpsaf_phases.py`、`gpsaf_pymoo.py` 共享具体 pymoo object，阻止
  search role 被替换或独立用 NSGA-III。
- `gpsaf_phases.py` 动态导入 `surrogate.runtime` 获取 session training data，绕过
  公共边界。
- `surrogate/scheduler.py` 直接依赖 `runtime.StateKey` 和 concrete runtime；
  `surrogate/types.py` 混合 common bundle 与 Torch/INR state。
- `tools/history.py` 直接 reset current runtime/scheduler；新实现应走 workspace
  component lifecycle manager，处理该 workspace 已实例化的状态，而不是加载全部组件。
- surrogate viewer 和测试散布 modeling/runtime/types 私有导入，需要集中到
  `conditional_inr/inspection.py`。
- package/source artifact 测试只扫描父目录 `*.py` 的位置必须递归覆盖子包。

## Selection, Identity, And Lifecycle Decisions

- 删除旧计划准备新增的 `SURROGATE_METHOD`、`OPTIMIZE_METHOD` 和
  `OPTIMIZE_GPSAF_SEARCH_BACKEND`。当前代码尚未拥有这些设置，实现时不得新增。
- 完整 plan 的唯一来源是 snapshotted `submit/optimization.py`。component constructors
  可以拥有 stable ID/version，但这些字段用于 validation/provenance/checkpoint，不是另一个
  complete-plan selector。
- generation/campaign metadata 记录 plan fingerprint、component roles/IDs 和适用
  backend/model identity。checkpoint 使用 component namespace 和 final real-only policy；
  目录重构不再做第二次格式迁移。
- workspace 第一次 generation 后 plan fingerprint/graph 固定。reload 发现变化必须在
  evaluation 前失败，要求新 workspace 或显式 clear；不支持 retained history 上 method
  switch。
- `history clear` 在 campaign lock 空闲时 reset 该 workspace 已存在的 scheduler/component
  state，再删除 checkpoint/history/jobs。它不实例化全部可用组件，也不能因用户已编辑
  plan 而遗留旧 workspace-keyed in-memory state。
- parent package/lightweight CLI/config/help import 不加载 Torch、具体 pymoo algorithms、
  Matplotlib、Tkinter 或 viewer UI。选择相应 component 时才 lazy import。

## Migration Map

| Current responsibility | Target responsibility |
|---|---|
| `optimize/api.py` hard-coded GPSAF | common engine loads/invokes workspace plan |
| `OptimizationResult` in `gpsaf.py` | public optimize common type |
| `gpsaf.py` complete generation | common engine + GPSAF assistance component |
| `gpsaf_phases.py` | GPSAF phases using search/surrogate contracts |
| `gpsaf_pymoo.py` | private GA/NSGA-III pymoo components/shared mechanics |
| `gpsaf_misc.py` history/evaluate/types | common optimize boundaries where truly shared |
| `gpsaf_misc.py` candidate helpers | GPSAF or search component owning semantics |
| `surrogate/runtime.py` history/session bundle | common training-data boundary |
| `surrogate/runtime.py` query/scaler/off-grid | conditional-INR data |
| `surrogate/runtime.py` train/state/recover/predict | conditional-INR backend |
| `surrogate/modeling.py` | conditional-INR modeling |
| `surrogate/types.py` | common contracts plus INR-private types |
| `surrogate/checkpoints.py` | common atomic manifest plus INR payload |
| viewer private imports | conditional-INR inspection adapter |

删除旧模块前必须搜索直接/动态 import、public exports、CLI、tests、wheel members 和 docs。
稳定 `yadof.optimize.run_*` 入口保留；旧 internal 路径不保留原样转发 compatibility
module。

## Implementation Plan

### Phase 0 - Freeze The Simplified Behavior

- [ ] 确认 real-only toDo 已归档，active code 不含 mixup/importance/relative/rank
  heuristic、GPSAF spread/error noise 或 legacy checkpoint reader。
- [ ] 固定 seeded GA/NSGA-III、warm start、fallback、alpha/beta/exploration、staggered
  scheduling、field-balanced conditional INR、ensemble/bootstrap/spread、current-cost、
  checkpoint recovery 和 workspace isolation 行为测试。
- [ ] 记录 import-time dependency，证明普通 CLI/config/optimize import 仍轻量。

### Phase 1 - Add Common Types And Component Contracts

- [ ] 先移动 `OptimizationResult` 和真正公共的 problem/population/history/evaluation
  types，消除 engine 对 GPSAF 反向依赖。
- [ ] 从当前调用点提取最小 plan、search、surrogate 和 refinement role；不预建第三方
  plugin lifecycle 或 capability matrix。
- [ ] 用 test components 验证 role validation、diagnostics、failure 和 dependency
  direction，不声称新算法质量。

### Phase 2 - Extract Conditional INR

- [ ] 拆分 common training bundle 与 INR query/schema/model/state，再逐步移动并运行
  focused tests。
- [ ] scheduler 接收当前 plan 选择的 component，不再 import concrete runtime；保持 one-
  workspace/one-pending-training 和 lag policy。
- [ ] 保持 final namespace、format/method/policy、manifest-last atomic publication、
  full-grid optimizer/audit 和 off-grid viewer 数值语义，不加 legacy reader。
- [ ] viewer 私有依赖集中到 inspection adapter；unknown/unsupported component 明确失败。

### Phase 3 - Extract Search And GPSAF Components

- [ ] 将 pymoo GA、NSGA-III 和真实共享 mechanics 从 GPSAF 分离，保持 seed、ask/tell、
  clone/continue、reference directions、survival 和 diagnostics。
- [ ] 让 GPSAF 只通过 search/surrogate roles 工作，保留 alpha/beta/exploration、fallback、
  real validation 和 after-submit scheduling 顺序。
- [ ] 对相同 post-simplification history/config/seed 比较默认 workspace plan 与迁移前的
  candidate population/source/core diagnostics；real evaluator 顺序和 objective width 不变。
- [ ] 证明 NSGA-III-only plan 不复制 GPSAF/campaign/evaluation/history，并在单目标清楚
  拒绝。

### Phase 4 - Integrate Workspace Composition Consumers

- [ ] 与新 workspace toDo 一起把 engine 接到 snapshot plan loader，移除完整算法 package
  registry/config selector。
- [ ] 更新 history clear、metadata、scheduler state、checkpoint discovery 和 viewer
  inspection 使用 plan/component identity。
- [ ] 公共 contract tests 走 workspace `build_optimization()`；只有 component 单元测试
  直接导入子包。
- [ ] 递归更新 source/wheel scanning，删除旧 imports、空转发模块和重复 helpers。

### Phase 5 - Documentation And Installed Acceptance

- [ ] 更新 root architecture、module/file blueprints、terminology、user workflow/config、
  template、examples 和 surrogate-viewer nested dev_doc；历史 change records 不改。
- [ ] 构建 wheel、force-reinstall 到 sibling `.venv`，确认 site-packages import，无
  `PYTHONPATH`，运行 focused tests 与完整 pytest。
- [ ] 添加完成 change record；只有与 workspace composition toDo 全部 criteria 同时满足
  后，才一起归档两份 toDo。

## Verification Plan

- Static/import:
  - 两个子树递归无旧 internal import 或完整算法副本；
  - parent API/help/config import 不提前加载数值/GUI backend；
  - 没有 complete-method selector/registry 与 workspace plan 并存；
  - 没有 legacy checkpoint/workspace fallback 或无意义 compatibility facade。
- Focused behavior:
  - 默认 objective-count GA/NSGA-III + GPSAF + simplified conditional INR；
  - NSGA-III-only multi-objective plan 和 invalid objective compatibility；
  - fake search replacement、fake rawData-first surrogate、fake appended refinement，且不
    复制或直接调用 recorder/evaluator internals；
  - scheduler/state/checkpoint/history clear/workspace isolation；
  - ensemble/bootstrap/spread 保留但不影响 GPSAF selection；
  - viewer conditional-INR inspection 与 unknown-component error；
  - one-generation snapshot 与 plan provenance/freeze。
- Installed acceptance:
  - compileall 两个子树；
  - build + force-reinstall wheel，验证 import origin；
  - CLI/help、fresh synthetic workspace、default plan、NSGA-III-only plan、checkpoint
    recovery 和完整 pytest；
  - 不启动真实 simulator 或 HTCondor，除非用户另行授权。
- Diff/artifact:
  - `git diff --check`；
  - wheel 包含组件子包、新 template/docs，不含 workspace runtime/checkpoint/history；
  - 不通过制造空壳文件满足目录图。

## Completion Rule

- 前置 real-only/field-balanced toDo 已完成并归档。
- package 不再拥有或选择一套完整 GPSAF + GA/NSGA-III + conditional-INR algorithm；完整
  graph 只由 workspace `submit/optimization.py` 组合。
- `yadof.optimize` 保留 campaign engine/common contracts，并暴露可组合 GPSAF、GA、
  NSGA-III/refinement roles；`yadof.surrogate` 暴露 simplified conditional-INR component
  和 method-neutral lifecycle/data/checkpoint mechanisms。
- 默认 workspace 行为与 post-simplification baseline 等价；NSGA-III-only 与 fake
  append/swap tests 证明边界，但不冒充未实现算法的有效性证明。
- 一个 workspace 只有一套 frozen plan/component provenance/state；改变 plan 需要新
  workspace 或显式 clear，不存在 package selector、all-method coexistence 或 legacy
  compatibility。
- rawData-first、current submit cost、real validation、generation snapshot、staggered
  training、recording-loss isolation、checkpoint atomicity 和 viewer isolation 全部保持。
- 所有相关 docs/blueprints/tests/wheel 内容已更新，安装态完整 pytest 通过；本文与
  workspace composition toDo 同时归档。
