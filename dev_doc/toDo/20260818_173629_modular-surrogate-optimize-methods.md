# Surrogate 与 Optimize 可组合组件重构

## Execution Dependency

- 这是手工触发、一次性的组件重构工作流；不能因读取本文而自动执行。
- 必须先完整执行并归档
  `20260819_144148_simplify-surrogate-real-only-training.md`，以最终 real-only、
  rawData-field-balanced、ensemble-with-bootstrap 训练、保留但隔离旧状态的 atomic
  checkpoint，以及用户确认的真实 benchmark gate 为唯一基线。
- 随后必须把本 toDo 作为
  `20260820_125457_workspace-submit-optimization-composition.md` 的协调工作流执行。后者
  负责新 `submit/` workspace 标准、`optimization.py` 加载、snapshot、provenance、
  init/check 与迁移；本文负责把 package 实现拆成可由 workspace 组合的组件。
- 两份协调 toDo 可以按清楚的兼容阶段落地，但不得保留 package-owned 完整算法再由
  workspace 做一层表面包装。共享安装态验收全部通过后，两份文件一起归档。
- 执行时必须先做成熟依赖复用审计，再决定保留、删除或新增 yadof 代码；“组件化”不等于
  把第三方算法重新实现成更多 yadof 模块。

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
- engine 只接收一个 workspace-owned optimization strategy/callable。当前 GPSAF 内部仅为
  实际替换需求保留 global-search 与 rawData-surrogate 两条窄缝；不要把它扩成通用组件图、
  capability registry 或 lifecycle framework。
- 稳定数据链仍是
  `normalized variables -> predicted/real rawData -> current submit calc_cost -> cost`。
  任一 surrogate 组件都必须预测 rawData；workspace composition 不能建立平行的权威
  `variables -> cost` 或 predicted-history 路径。
- 本次重构只建立当前真实调用面需要的边界；不建立第三方插件系统，也不实现第二套
  production surrogate、PSO 或 refinement。真实的 multi-objective NSGA-III-only strategy
  是本次唯一新增生产组合。
- 当前 pymoo 已提供 GA、NSGA-III 和单目标 PSO，但没有 GPSAF；PyTorch 提供 conditional-
  INR 所需 primitives。实现前只对本次会调用的 backend 做版本、license、seed/state 与
  数值语义审计。trust-region/local refinement 已暂缓，当前任务不得为它引入 SciPy。

## Goal

- 把完整算法耦合拆开：GA/NSGA-III 直接委托 pymoo，conditional INR 尽量委托 PyTorch
  primitives，yadof 只保留无法由成熟 package 表达的 GPSAF assistance、rawData/task
  adaptation 和薄 backend adapter。
- `surrogate`、`optimize` 父层和子模块总量都应最小化，只保留跨组合确实稳定且由 yadof
  拥有的 campaign、strategy invocation、history/evaluation、rawData-first adaptation、必要
  scheduler/checkpoint/provenance 和公共 result contracts。不要为了理论上的扩展性搭建
  自有优化或 surrogate framework。
- 新 workspace starter 用这些组件定义当前默认：GPSAF +（单目标 GA / 多目标
  NSGA-III）+ simplified conditional INR。
- 同一个 engine 能运行真实的 multi-objective NSGA-III-only strategy；当前 GPSAF 的窄
  search/surrogate seam 可用小型 engine/seam test doubles 验证，而不复制 session、snapshot、
  real evaluator、history、recorder 或 metadata。
- 保持 workspace isolation、generation snapshot、current-cost reinterpretation、staggered
  training、recording-loss isolation、real validation、旧状态保留与隔离、atomic checkpoint
  和 lazy optional dependencies。

## Non-Goals

- 不实现 production particle swarm、第二 surrogate 或 trust-region/local refinement；也不
  预建 refinement role、API、capability、state、SciPy dependency 或 fake refinement。
- 不通过任意 Python import path 加载第三方插件。workspace 只组合安装版 yadof 暴露的公共
  组件和自己的 strategy；真实组件可以由 yadof 的薄 adapter 调用受支持的成熟依赖，但
  adapter 与依赖版本仍需 package 测试和 provenance。
- 不在重构中重新调参、改变 GPSAF 数值策略、恢复 ensemble/error trust、改变 simplified
  conditional-INR 网络或读取 legacy checkpoint/history。
- 不并行运行多套 strategy。切换时一个 workspace 仍只有一个 active strategy，但旧的
  recorded evidence 与 run/component-namespaced persistent state 保留为 inactive；切换不得
  要求新 workspace、`history clear` 或自动删除旧权重。
- 不为了目录对称创建空壳 contract、通用 `utils.py` 或多层原样转发；只有至少两个真实
  组件共享且语义稳定的机制才进入父包。
- 不复制 pymoo/PyTorch 已有的数值循环、population operator、loss、layer、
  optimizer 或 serializer。除非复用审计给出具体 incompatibility 证据，否则“不方便适配”
  不能成为自实现算法的理由。

## Component Roles

### Campaign engine and strategy boundary

- `yadof.optimize.api` 继续拥有 `CampaignSession`、每 generation config reload、双
  source-root snapshot、run/optimization/generation identity、metadata、progress、
  all-infinite policy 和 recorder lifecycle。
- 公共 `OptimizationResult`、normalized population/cost/history types 不能从 GPSAF
  组件反向导入。
- strategy boundary 只暴露 engine 真正需要的一次 generation invocation；
  `build_optimization()` 返回一个完整 immutable strategy/callable，位于 workspace snapshot，
  不在 package registry。
- validation 只检查当前 strategy、objective width、backend availability 和 state signature
  compatibility；不得执行训练、预测或真实 evaluation，也不得构建通用 component graph。
- common real-evaluation handoff 由 engine 提供。组件只能提出 normalized candidates、
  接收 real result 和返回 diagnostics，不能直接写 recorder/history 或把 surrogate 预测
  当作 accepted result。

### Global-search components

- 当前 single-objective GA 与 multi-objective NSGA-III 通过薄、lazy 的 pymoo adapter 从
  GPSAF orchestration 中抽离。pymoo 继续拥有 algorithm、population、ask/tell、reference
  directions、survival 和数值 operator；yadof 只转换 normalized problem/result、管理需要的
  opaque state，并补充 yadof diagnostics/provenance。
- workspace 默认通过 objective-count dispatch 选择 GA/NSGA-III；NSGA-III-only strategy 在
  objective count 小于 2 时必须清楚失败，不能静默回退 GA。
- search contract 使用 normalized arrays、objective rows、backend-neutral problem info 和
  opaque state。不得把 pymoo `Algorithm`、`Population`、`Individual` 或 reference-
  direction 类型提升到 strategy/GPSAF/public engine contract。
- 每个 backend factory 只显式暴露 yadof 当前控制且经过测试的少量参数；其余默认交给固定
  支持版本的成熟 backend，并把 backend/version 与受控参数记录到 provenance。不要复制
  整个 backend signature 或维护第二份默认参数表。
- future particle swarm 必须留给届时的真实需求和成熟实现审计；当前不为它扩展 public
  contract。已知 pymoo PSO 是单目标算法，不能冒充 NSGA-III 的多目标直接替代。

### GPSAF assistance component

- GPSAF 组件拥有 alpha/beta/exploration、surrogate pressure、warmup/fallback、candidate
  source 和 real-validation policy，但不拥有 campaign/session/recorder。
- 它显式接收 global-search 和可选 surrogate-model 组件，不从 config selector 或 global
  registry 查询默认实现。
- after-submit staggered training、fast-mode fallback 和 lag gate 顺序保持当前行为；
  scheduler-specific callback 仍不能由 fast 伪造。
- post-simplification member spread 和 training-fit diagnostics 保持可观察但不影响
  candidate decision，直到真实 benchmark 后另行设计 trust policy。
- 当前安装的 pymoo 不提供 GPSAF，因此这一层暂时可能保留 yadof-specific orchestration；
  实现前必须再次搜索受支持成熟依赖。任何保留代码都要逐项证明属于 yadof 的 rawData、
  generation、real-validation 或 component coordination 契约，而不是可委托的通用算法。

### Surrogate-model component

- 当前只提取 GPSAF 真正需要的窄 rawData-surrogate seam：从 normalized real rows 训练、恢复、
  预测完整 rawData，并返回 current scheduler 所需的最小状态/diagnostics。optimizer-facing
  current costs 只能由预测完整 rawData 经当前 `submit/calc_cost.py` 计算得到。
- training target 必须逐项来自真实 evaluation。所有 numeric rawData field 等权参与训练；
  field 内先对全部 scalar/slot 求平均，再对 field loss 做 macro average，不能让大 field 因
  slot 数量获得更大总权重。
- scheduler、checkpoint 与 viewer 可以继续明确依赖 conditional-INR artifact；在第二个真实
  surrogate consumer 出现前，不为形式统一抽象通用 scheduler、artifact 或 inspection
  capability。一个 workspace 至多一个 active strategy 的 background training task。
- checkpoint discovery 按 run/component namespace 与 deterministic semantic state signature
  隔离。切换会释放 active in-memory state，但保留旧模型权重和其它 persistent artifacts；
  不兼容状态不得被新 strategy 误加载。
- conditional-INR 数学与训练实现优先直接组合 PyTorch 的 layer、loss、optimizer、data 和
  serialization primitives。yadof 只拥有 field-balanced query schema、完整 rawData 重建、真实
  campaign row adaptation、可复现 seed 派生和自身 checkpoint/provenance 接口；不得为了
  “统一接口”再实现一个通用 tensor/trainer/model framework。

### Parked local refinement

- `20260520_180701_trust-region-surrogate-gradient-optimization.md` 只是暂停的研究记录。当前
  重构不得以它为 consumer，不定义 refinement role/API/sequencing/state/capability，不引入
  SciPy，也不写 fake refinement test。所有其它 active toDo 完成后再按当时架构重新审计。

## Backend Adapter And Default Contract

- 数值 factory 是短小接口而不是 yadof 算法实现。它只暴露 yadof 明确控制且经过测试的
  少量参数，并可用几行代码让这些参数在 starter 中可读；未支持的 backend 选项不通过
  任意 `**kwargs` 泄漏到稳定 workspace contract，也不复制 backend 的完整默认表。
- component identity 至少记录 yadof adapter ID/version、backend distribution/version、
  backend algorithm 名称和影响数值语义的显式参数。对象地址、repr 默认值和 import path
  不能作为稳定 identity。
- adapter 只能做 lazy import、当前组合所需参数/兼容性验证、yadof/backend 数据转换、seed/state
  handoff、异常归一化和 compact diagnostics。若出现 selection、mutation、line search、
  population update、gradient step 或 surrogate training loop，应先证明成熟 backend 无法
  满足契约并在 change record 中记录原因。
- yadof 直接 import 的 backend 必须在 `pyproject.toml` 声明为 direct core/optional
  dependency 并限定受支持版本，不能依赖传递安装。本任务不增加 SciPy dependency。
- backend 默认值随依赖升级可能改变。starter 只固定 yadof 有意控制的参数；其余行为由
  supported backend version 界定。依赖升级时运行 seeded behavior、restart 和 provenance
  tests，再有意识地接受变化或新增受控参数。

## Proposed Source Responsibility Layout

先以最少文件表达真实边界，再仅因清楚的 cohesion、lazy dependency 或多个真实调用方拆分。
下面是目标预算而不是要求机械匹配的目录图：

```text
src/yadof/surrogate/
  __init__.py                  lightweight public component exports
  api.py                       only if the narrow rawData seam is substantive
  conditional_inr.py           thin public factory + yadof-specific Torch adaptation
  artifacts.py                 only if current persistence code has real cohesion

src/yadof/optimize/
  __init__.py                  stable campaign and strategy exports
  api.py                       campaign engine, common types, strategy invocation
  strategy.py                  one engine boundary/signature, only if substantive
  gpsaf.py                     irreducible yadof assistance/orchestration
  pymoo_backend.py             thin lazy GA/NSGA-III factories/adapters
```

若 `api.py` 或 `conditional_inr.py` 已因实际职责过大，可以按调用面拆出 scheduler、training
data、checkpoint、inspection 或 INR-private 子包；change record 必须解释每个新增文件为何
不能合并。反过来，只有一个薄调用方的 history/evaluation/common/contracts 应合并回最近的
领域文件。不得为了符合图形机械创建文件，也不得为了“组件化”把一个第三方 backend 分成
每种算法一个 yadof 模块。Torch/pymoo private object 仍不能泄漏到公共 strategy/engine contract。

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
- `tools/history.py` 直接 reset current runtime/scheduler；新实现应让 active strategy/run
  coordinator 停止 pending work 并释放内存引用，而不是加载全部组件或删除 inactive state。
- surrogate viewer 和测试散布 modeling/runtime/types 私有导入，需要集中到
  conditional-INR component 的 inspection boundary；只有职责足够大时才为它单设文件。
- package/source artifact 测试必须覆盖最终真实文件树；若没有子包，不为“递归扫描”制造
  子包。

## Selection, Identity, And Lifecycle Decisions

- 删除旧计划准备新增的 `SURROGATE_METHOD`、`OPTIMIZE_METHOD` 和
  `OPTIMIZE_GPSAF_SEARCH_BACKEND`。当前代码尚未拥有这些设置，实现时不得新增。
- 完整 strategy 的唯一来源是 snapshotted `submit/optimization.py`。source hash 只用于
  provenance/cache invalidation，不能决定 recorded variables/rawData 是否有效。
- generation/campaign metadata 记录 source hash、deterministic semantic state signature、
  backend distribution/version、algorithm/model identity 和 yadof-controlled parameters。
  state signature 只包含实际影响 persistent state compatibility 的语义。
- reload 发现 strategy 改变时，在 generation/evaluation boundary 停止或等待 pending work，
  释放 active in-memory pointers，并在新的 run/component namespace 激活新 strategy。旧的
  weights、checkpoint、diagnostics 与 recorded real evidence 都保留；active discovery 不得跨
  namespace 误加载。
- 若 semantic signature 兼容，可以恢复旧 state；不兼容则从保留的真实 evidence cold
  retrain，旧 artifact 仍留在磁盘。一个 workspace 只运行一个 active strategy，但可保留
  多个 inactive run/component state。不得自动 prune；`history clear` 是独立、显式、破坏性
  用户决定，绝不是切换算法的前置条件。
- parent package/lightweight CLI/config/help import 不加载 Torch、具体 pymoo algorithms、
  Matplotlib、Tkinter 或 viewer UI。选择相应 component 时才 lazy import。

## Migration Map

| Current responsibility | Target responsibility |
|---|---|
| `optimize/api.py` hard-coded GPSAF | common engine loads/invokes workspace strategy |
| `OptimizationResult` in `gpsaf.py` | public optimize common type |
| `gpsaf.py` complete generation | common engine + irreducible GPSAF assistance |
| `gpsaf_phases.py` | GPSAF-specific coordination only; delegate generic mechanics |
| `gpsaf_pymoo.py` | one thin lazy pymoo backend adapter; delete copied mechanics |
| `gpsaf_misc.py` history/evaluate/types | common optimize boundaries where truly shared |
| `gpsaf_misc.py` candidate helpers | GPSAF or search component owning semantics |
| `surrogate/runtime.py` history/session bundle | common training-data boundary |
| `surrogate/runtime.py` query/scaler/off-grid | yadof-specific conditional-INR adaptation |
| `surrogate/runtime.py` train/state/recover/predict | minimal lifecycle around PyTorch backend |
| `surrogate/modeling.py` | PyTorch composition only; no generic trainer/layer reimplementation |
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
  retained-state recovery/isolation 和 workspace isolation 行为测试。
- [ ] 记录 import-time dependency，证明普通 CLI/config/optimize import 仍轻量。
- [ ] 对本次真实调用的 GA、NSGA-III、GPSAF 和 conditional INR 做 focused reuse audit：确认
  成熟 package ownership、受支持版本/license、seed/state/restart 与最小 adapter 工作；只对
  确认无法委托的 yadof 代码记录具体证据。

### Phase 1 - Add Common Types And Component Contracts

- [ ] 先移动 `OptimizationResult` 和真正公共的 problem/population/history/evaluation
  types，消除 engine 对 GPSAF 反向依赖。
- [ ] 从当前调用点提取一个最小 strategy/result/context boundary，以及 GPSAF 当前真正需要的
  search/rawData-surrogate seam；不预建第三方 plugin、通用 capability 或 lifecycle framework。
- [ ] 用小型 engine/current-seam test doubles 验证 invocation、diagnostics、failure 和
  dependency direction，不伪造未来 numerical method。

### Phase 2 - Extract Conditional INR

- [ ] 先删除或委托 PyTorch 已有的通用 modeling/training/serialization mechanics，再把
  yadof-owned training bundle 与 INR query/schema/rawData reconstruction/state 按实际调用面
  合并或拆分，并逐步运行 focused tests。
- [ ] scheduler 围绕 active strategy/state key 工作；若抽象不能减少当前耦合，可继续使用
  conditional-INR-specific runtime。保持 one-workspace/one-pending-training 和 lag policy。
- [ ] 保持 run/component namespace、format/method/policy、经过 Windows failure injection
  验证的 atomic publication、full-grid optimizer/audit 和 off-grid viewer 数值语义；旧
  artifact 可保留但不加 legacy reader。
- [ ] viewer 可继续使用 conditional-INR-specific inspection；未知或 inactive state 明确失败。

### Phase 3 - Extract Search And GPSAF Components

- [ ] 用一个薄 pymoo backend adapter 从 GPSAF 分离 GA/NSGA-III；显式传递受支持默认参数，
  由 pymoo 保持 ask/tell、reference directions、survival 和 operators，yadof 只保持 seed/
  state handoff、normalized translation 与 diagnostics/provenance。
- [ ] 让 GPSAF 只通过窄 search/surrogate seams 工作，保留 alpha/beta/exploration、fallback、
  real validation 和 after-submit scheduling 顺序。
- [ ] 对仍由 yadof 实现的每段 GPSAF 数值/coordination 代码逐项复核：若成熟依赖可满足
  contract 则委托；若当前无兼容实现，则在 change record 记录证据并保持最小实现。
- [ ] 对相同 post-simplification history/config/seed 比较默认 workspace strategy 与迁移前的
  candidate population/source/core diagnostics；real evaluator 顺序和 objective width 不变。
- [ ] 证明 NSGA-III-only strategy 不复制 GPSAF/campaign/evaluation/history，并在单目标清楚
  拒绝。

### Phase 4 - Integrate Workspace Composition Consumers

- [ ] 与新 workspace toDo 一起把 engine 接到 snapshot strategy loader，移除完整算法 package
  registry/config selector。
- [ ] 更新 metadata、scheduler state、checkpoint discovery 和 viewer inspection 使用
  source hash + semantic state signature + run/component namespace；证明切换保留旧 state、
  compatible return 可恢复、incompatible return cold retrain 且不 cross-load。
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
  - 两个子树无旧 internal import、完整算法副本或第三方 numerical loop 副本；
  - parent API/help/config import 不提前加载数值/GUI backend；
  - 没有 complete-method selector/registry 与 workspace strategy 并存；
  - 没有 legacy checkpoint/workspace fallback、无意义 compatibility facade 或无真实共享
    职责的模块。
- Focused behavior:
  - 默认 objective-count GA/NSGA-III + GPSAF + simplified conditional INR；
  - NSGA-III-only multi-objective strategy 和 invalid objective compatibility；
  - engine 与 GPSAF 当前 search/rawData-surrogate seam test doubles，且不复制或直接调用
    recorder/evaluator internals；不包含 fake refinement；
  - scheduler/state/checkpoint/workspace isolation；切换保留 inactive weights/artifacts，
    compatible return 恢复，incompatible return 从 retained real evidence cold retrain，且
    active discovery 不 cross-load；
  - ensemble/bootstrap/spread 保留但不影响 GPSAF selection；
  - viewer conditional-INR inspection 与 unknown-component error；
  - one-generation snapshot、source provenance 与 semantic state signature；
  - pymoo adapter 的 yadof-controlled parameters、objective compatibility、seed/state/result
    translation，backend version 纳入 provenance；
  - monkeypatch/spy 或等价测试证明 numerical update 由 backend 执行，而非 yadof 副本。
- Installed acceptance:
  - compileall 两个子树；
  - build + force-reinstall wheel，验证 import origin；
  - CLI/help、fresh synthetic workspace、default strategy、NSGA-III-only strategy、checkpoint
    recovery 和完整 pytest；
  - 不启动真实 simulator 或 HTCondor，除非用户另行授权。
- Diff/artifact:
  - `git diff --check`；
  - wheel 只包含实际需要的 adapter/component 文件和新 template/docs，不含 workspace
    runtime/checkpoint/history；
  - 不通过制造空壳文件满足目录图，focused audit 中每项自实现例外都有证据。

## Completion Rule

- 前置 real-only/rawData-field-balanced toDo 已通过用户确认的真实 benchmark gate 并归档。
- package 不再拥有或选择一套完整 GPSAF + GA/NSGA-III + conditional-INR algorithm；完整
  strategy 只由 workspace `submit/optimization.py` 组合，engine 只看一个 strategy/callable。
- `yadof.optimize` 保留最小 campaign/common contract 和不可委托的 GPSAF coordination，
  通过薄 adapter 暴露成熟 package 的 GA/NSGA-III；
  `yadof.surrogate` 只保留 simplified conditional-INR 所需的 rawData/task adaptation 与
  必要 scheduler/checkpoint 边界，并直接复用 PyTorch primitives；不得先造通用 surrogate
  framework。
- 没有复制成熟 backend 的数值算法。adapter 只暴露 yadof-controlled parameters，记录
  backend identity/version，并 lazy import；所有 yadof-owned numerical code 都在 focused
  audit/change record 中说明为何不能由受支持成熟 package 替代。
- 默认 workspace 行为与 post-simplification baseline 精确等价；真实 multi-objective
  NSGA-III-only strategy 与当前 seam tests 证明边界，不冒充未实现算法的有效性证明。
- 一个 workspace 同时只有一个 active strategy；允许多个 inactive run/component states
  共存。切换不要求新 workspace 或 clear，不自动删除 conditional-INR weights，也不允许
  active discovery cross-load 不兼容 state。
- 当前没有 refinement role/API/capability/state、SciPy dependency 或 fake refinement；暂停的
  trust-region 研究不约束本重构。
- rawData-first、current submit cost、real validation、generation snapshot、staggered
  training、recording-loss isolation、checkpoint atomicity 和 viewer isolation 全部保持。
- 所有相关 docs/blueprints/tests/wheel 内容已更新，安装态完整 pytest 通过；本文与
  workspace composition toDo 同时归档。
