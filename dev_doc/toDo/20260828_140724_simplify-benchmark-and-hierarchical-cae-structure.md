# 大幅精简 benchmark 与 hierarchical CAE 工程结构

## 本文的角色

- 本文是一次只读结构审查的执行计划，不授权立即修改产品代码、重跑 benchmark/仿真、
  改写冻结 preregistration/receipt，或改变 hierarchical CAE 的科学结论。
- 后续实施必须由用户明确选中本文，并遵守届时 `dev_doc/README.md` 的构建、安装、测试、
  change record、提交和推送流程。
- 本文承接
  [surrogate/qNEHVI 剩余工作](20260828_121904_surrogate-qnehvi-remaining-work.md)
  中“共享不可变 engine + 薄 version adapter”的工程建议，但范围只限代码组织、重复消除和
  可维护性；它不能把 Gate 0 v5/v8 的失败改写成接受。
- 背景判断来自 Codex 任务
  `codex://threads/01a045a2-5fe4-7992-9932-4c35cd3382ad`，并定向核对了其中明确关联的
  `01a04046-99c7-7fc0-a2a1-91835bc898a8`、
  `01a04164-d04f-7873-a8e8-6ddab35ad2f5`、
  `01a04242-14f1-7162-8c38-c44a8b02fe12`，以及抗噪声证据任务
  `01a04151-bc16-7ff0-84d5-16eef2e1b5c6`。本文件已经包含继续实施所需的结构结论，
  实施者不应默认重读完整历史任务。

## 审查基线与事实纠正

本次以 `main` 分支提交 `323f8e1a69ba9e9860b45369d0dc055cdb7c5819` 为基线；审查开始及
写本文前工作树均无已有改动，分支相对 `origin/main` ahead 3。

### 代码规模

| 范围 | 文件数 | 字节数 | 物理行数 | 非空非整行注释行 |
| --- | ---: | ---: | ---: | ---: |
| `benchmark_automation/benchmark_core.py` | 1 | 188,688 | 4,887 | 4,610 |
| 顶层 `benchmark_automation/hierarchical_cae_*.py` | 8 | 274,942 | 7,254 | 6,795 |
| `src/yadof/surrogate/hierarchical_cae/*.py` | 10 | 178,194 | 5,042 | 4,659 |
| 上述三部分合计 | 19 | 641,824 | 17,183 | 16,064 |

`benchmark_core.py` 在导入 benchmark 工具的提交 `aba3be8` 中已经有 123,791 bytes；当前比
该版本净增加 1,771 行（1,897 additions / 126 deletions），字节数增加约 52.4%。昨天实际
触及该文件的主要提交是：

- `a81981f`（ETA 与 matched timing history）：`+633/-51`，净增 582 行；
- `3189633`（hierarchical CAE baseline）：`+7/-1`，净增 6 行；
- 今天的 `6ad22a5`（component-owned settings）：`+104/-19`，净增 85 行。

因此“CAE 使 `benchmark_core.py` 膨胀到 185 kB”不是准确因果。真正问题是从一开始就把
配置、路径安全、计划、preflight、run state、子进程、进度、采集、报告、摘要、跨 run ETA
和 inspect 放在一个模块里；CAE 的主要新增量在独立实验 runner 与 surrogate package。

### 已量化的结构问题

- `benchmark_core.py` 的最长单体分别是 `_collect_cell` 375 行、`_run_one_cell` 305 行、
  `CellProgress` 289 行、`estimate_run_timing` 241 行、`_execute_logged` 170 行。这些已经是
  独立生命周期，不再符合 nested blueprint 中“尚无稳定独立边界，所以保持单文件”的原始
  判断。
- `hierarchical_cae_validation_v1.py` 为 1,223 行，当前
  `hierarchical_cae_validation.py` 为 1,226 行；逐行 `SequenceMatcher` 相似度为 0.986525，
  1,208 行直接匹配。实际差异只有 plan 路径、一个不再使用的 import，以及
  `_conditional_named_samples()` 的 schema 重建修复。
- 8 个 CAE benchmark 脚本重复实现 `_json`、`_json_bytes`、`_write_json_atomic`、`_sha256`、
  CLI parser/output preparation 等基础设施；AST 检查确认多组函数体逐字等价。
- 更严重的不是同名小 helper，而是横向私有耦合：calibration、offline 和 checkpoint 脚本
  直接调用 `hierarchical_cae_validation.py` 的 `_rank3_layouts`、`_chrono_policy`、
  `_ResourceMonitor`、`_evaluate`、`_costs`、`_cae_config` 等大量下划线函数。validation
  实际上已经成为没有公开契约、却被多条实验链依赖的隐式 framework。
- package 内的多数文件边界合理，但 `modeling.py` 单文件 66,396 bytes / 1,824 行，同时拥有
  codecs、网络、teacher latent、loss、split、四段训练、全网格推理、坐标推理和序列化。
  `runtime.py` 也有 877 行，并同时承担数据适配、状态恢复、预测和 current-cost 投影。
- conditional-INR 与 hierarchical CAE 的 checkpoint、metadata、scheduler、finite-member
  posterior 机制存在真实重复；逐行相似度分别约为 0.64、0.81、0.74、0.64。但 runtime 和
  types 的相似度只有约 0.27、0.17，说明不能把两个组件粗暴塞进一个万能基类。

## 文件职责与去留判断

### CAE benchmark 文件

| 当前文件 | 实际职责 | 功能是否需要 | 处理决定 |
| --- | --- | --- | --- |
| `hierarchical_cae_dataset.py` | 密封/校验三段 dataset，解析 locator，加载 selected records/rawData，建立 rank-3 layout | 证据隔离与 schema 一致性需要 | 旧文件冻结；新实验只使用共享 dataset contract，不复制 I/O/helper |
| `hierarchical_cae_validation_v1.py` | 第一次失败 runner 的完整源快照 | 仅历史复现需要，不是活动实现 | 必须原字节、原路径保留；标为 frozen evidence，不允许新代码 import |
| `hierarchical_cae_validation.py` | case 装载、quality、资源监控、CAE/conditional/PCA arms、rawData/cost/Pareto 指标与总编排 | 科学语义需要，但不应集中 1,226 行 | 旧文件冻结；未来语义拆进共享 engine + declarative plan + 薄 adapter |
| `hierarchical_cae_gate4_assessment.py` | 汇总 representation/quality/resource 指标并执行冻结阈值 | 旧决定复现需要 | 冻结；未来复用统一 assessment reducer，阈值留在 plan/policy |
| `hierarchical_cae_experimental_offline.py` | v6 固定 offline-test、coordinate 指标、CAE/conditional 比较 | 旧机制证据需要，不是通用 runtime | 冻结；未来只写薄 experiment adapter |
| `hierarchical_cae_experimental_assessment.py` | v7 对 v6 evidence 做后访问汇总 | 旧 receipt 复现需要 | 冻结；未来并入统一 assessment reducer |
| `hierarchical_cae_calibration_checkpoint.py` | 按精确身份训练并发布 development checkpoints | checkpoint 机制需要 | 冻结；未来成为调用共享 train/publish service 的薄命令 |
| `hierarchical_cae_calibration.py` | calibration case/fold、field distribution、cost/Pareto/HV、qNEHVI proxy、applicability、gate、artifact 输出 | 科学评估需要，但 1,828 行混合过多职责 | 冻结；未来拆成 calibration metrics、decision proxy、gate policy 与 orchestration |

这 8 个文件当前全部被 v4--v8 的 plan/amendment/validator 以原相对路径和 SHA-256 绑定。
例如 v4 同时固定 v1/current runner hashes，v5 固定 gate assessment，v6/v7 固定 offline 与
assessment，v8 固定 calibration、checkpoint、dataset 和 validation。直接修改、删除或搬动会
让已有 validator 报 source drift，破坏冻结证据。它们的 7,254 行必须计为“历史证据负担”，
不能通过改写 validator 或 receipt 冒充代码精简。

### hierarchical CAE package 文件

| 当前文件 | 实际职责 | 判断与目标 |
| --- | --- | --- |
| `__init__.py` | 私有包标记与 lazy-import 边界 | 保留；已经足够小 |
| `types.py` | training row、axis/layout/scaler/schema/config/state/result value objects | 保留；配置与状态身份确有必要 |
| `schema.py` | selector/group/layout/axis 规范化、schema 建立、矩阵/缩放、重建 | 保留；这是 rawData 完整性边界 |
| `coordinates.py` | 坐标校验、编码、网格、插值 | 保留；补齐缺失的 file blueprint |
| `modeling.py` | codecs、模型、loss/split、训练、推理、save/load | 功能需要，单文件不需要；拆为 network/objective/training/inference，不复制代码 |
| `runtime.py` | training data、schema/state、recover、rawData/cost/applicability/coordinate prediction | 保留 facade；数据适配、state repository 与 projection 分开 |
| `checkpoints.py` | semantic signature、namespace、atomic publication/recovery | 组件策略保留；通用原子 artifact primitive 与 conditional-INR 共享 |
| `metadata.py` | bounded training success/failure event | 独立 CAE 文件无必要；共享通用 training-event writer 后删除 |
| `scheduler.py` | workspace keyed background training/freshness/deactivation | 生命周期需要；只抽取两组件确实相同的 slot/status/join primitive，保留薄组件 policy |
| `posterior_adapter.py` | persistent finite-member sampler 与支持度诊断 | 组件 adapter 需要；member index/失败容器等通用 primitive 移入已有 posterior 层 |

关联的 `src/yadof/surrogate/quality.py`、`calibration.py`、`posterior.py` 是后端中立契约，不应
为了减少文件数并入 CAE。`api.py` 仍只拥有 lazy public factory。相关 tests 需要按新模块边界
重组，但 preregistration 目录、receipts、plans 和 validators 是不可变证据，不属于待清理的
活动源码。

## 目标架构

目标不是把一个巨型文件切成大量随意小文件，而是让依赖方向与生命周期可见。建议结构如下；
文件名可在实施前微调，但边界和依赖方向不可反转：

```text
benchmark_automation/
  benchmark.py                     # 仅 CLI 参数与呈现
  benchmark_core.py                # <=250 行兼容 facade；旧 validator 仍可导入 task_fingerprint
  benchmark_runtime/
    contracts.py                   # BenchmarkError、Paths、内部 dataclasses/JSON codecs
    storage.py                     # path confinement、canonical JSON、hash、atomic/new writes、manifests
    planning.py                    # config、selection、plan、preflight、run spec
    state.py                       # run/attempt state 与 input materialization/sealing
    execution.py                   # subprocess、cell execution、resume/fail-fast
    progress.py                    # stream parser、CellProgress、progress event log
    results.py                     # collection、structural/performance report、summary/markdown
    timing.py                      # timing signatures/history/ETA/inspect timing view
  experiment_runtime/
    rawdata_dataset.py             # 新实验的 sealed dataset/case contract
    rawdata_metrics.py             # field/cost/Pareto/quality/calibration pure metrics
    surrogate_arms.py              # CAE/conditional/PCA 等明确 adapter protocol
    workflow.py                    # cell matrix、resource measurement、bounded artifact output
    calibration.py                 # folds/spread/applicability/decision proxy；不拥有 CLI
    assessment.py                  # plan-driven reducer；阈值不硬编码在 engine
  hierarchical_cae_*.py            # 八个原路径冻结文件；只作历史证据，不再增长/被新代码导入
  preregistrations/
    <future-version>/
      plan.json
      run.py                        # <=120 行薄 adapter，绑定内容寻址 engine artifact/hash

src/yadof/surrogate/
  _shared/
    artifacts.py                    # 两个真实组件共同需要的原子发布 primitive
    training_events.py              # bounded success/failure event primitive
    finite_members.py               # seeded finite-member selection/支持度 primitive
    background_training.py          # 仅在行为等价测试通过后抽取 slot/status/join primitive
  hierarchical_cae/
    __init__.py
    types.py
    schema.py
    coordinates.py
    networks.py                     # codecs、predictor、HierarchicalCAEModel
    objectives.py                   # design×field loss、quality batch、design split
    training.py                     # staged training 与 early-stop/fine-tune acceptance
    inference.py                    # full-grid/coordinate member inference 与 bundle serialization
    runtime.py                      # 对 api/scheduler 的窄 facade
    checkpoints.py                  # CAE identity/policy；调用 shared artifact primitive
    scheduler.py                    # CAE freshness policy；调用 shared background primitive
    posterior_adapter.py            # CAE draw reconstruction；调用 shared finite-member primitive
```

### 依赖规则

- CLI/薄 adapter 可以依赖 runtime；runtime 不得 import CLI、preregistration 或 frozen runner。
- scientific metrics 必须是显式输入/输出的纯函数，不读取全局 plan，也不从另一个 runner 的
  `_private_helper` 借实现。
- plan/threshold/policy 负责“本次实验测什么、门槛是什么”；engine 只负责可版本化算法。
- package 的 `runtime -> training/inference/schema/checkpoints` 单向依赖；network/objective 不得
  import workspace、recorder、task 或 benchmark。
- shared primitive 只抽取两个现有组件都通过行为等价测试的稳定机制。禁止为了复用而建立
  callback soup、全局 registry、万能 base class 或新的组件 selector。
- 新 run spec 必须记录整个 `benchmark_runtime`/`experiment_runtime` 的规范化文件 manifest
  与组合 hash，不能继续只 hash `benchmark_core.py` facade，否则拆包后实现漂移不可见。

## 可量化目标

历史冻结源与活动可维护源必须分账：

- 八个 frozen runner：保持 274,942 bytes / 7,254 行逐字不变；这部分不计入活动维护 LOC，
  但继续计入 repository evidence footprint。
- `benchmark_core.py`：4,887 行降到不超过 250 行；只保留稳定 facade/re-export 与过渡说明。
- generic benchmark runner（facade + `benchmark_runtime`）：物理行数不超过 3,450，较当前
  4,887 至少减少 29%；任何模块不超过 700 行。
- hierarchical CAE package：5,042 行降到不超过 4,200 行；任何模块不超过 700 行；
  `modeling.py` 和独立 `metadata.py` 不再存在。
- 当前两块活动实现合计从 9,929 行降到不超过 7,650 行，至少减少 22.9%；包含 frozen
  evidence 后的上述 repository subtotal 从 17,183 行降到不超过 14,904 行。未来实验 engine
  是新能力，必须单列预算，第一版上限 2,400 行，不能把它伪装成本次删减成果。
- 新 version adapter/CLI 文件不超过 120 行；普通函数不超过 100 行。确属单一数学 kernel
  可放宽到 150 行，但必须在 blueprint 解释；不得再出现 300+ 行 orchestration function。
- 活动 benchmark 模块间不允许 import 对方下划线符号；AST duplication check 不允许新增
  20 行以上的完全相同 top-level function body。
- 只减少文件数不是验收指标；模块职责、依赖方向、总活动 LOC、重复率和行为等价必须同时
  达标。

## 分阶段 TODO 与验收

### Phase 0：建立不运行 simulator 的行为保护网

- [ ] 冻结基线规模、AST symbols、import graph、八个历史 runner 的路径/SHA-256，并新增
  明确的 frozen-source index；index 可以新增，旧 plan/validator/receipt 不得修改。
- [ ] 为 `benchmark.py` 实际使用的 facade surface 建清单；至少覆盖 plan、preflight、
  run/resume、collect、report、inspect、ETA、`task_fingerprint` 和 JSON/hash helpers。
- [ ] 从现有 unit fixtures 生成稳定 golden expectations：plan/spec/state/collection/report 的
  schema、排序、hash 输入、错误类型和摘要字段。fixture 不得包含真实 simulator 输出的新
  访问。
- [ ] 给 current core 的整模块 automation identity 写失败测试：拆包后若任一 runtime 文件
  漂移，resume verification 必须 fail closed。
- [ ] 记录旧 run 的兼容矩阵：允许 inspect/collect/report 已完成 run；任何实现 hash 变化后
  继续拒绝 resume。不得为了“兼容”绕过 fingerprint。

验收：现有 benchmark automation unit tests 全通过；新增 characterization tests 全通过；
八个 frozen hashes 与当前值一致；未执行 benchmark、仿真或受保护 dataset 访问。

### Phase 1：直接切分 `benchmark_core.py`

- [ ] 先抽 `storage.py` 与 `contracts.py`，统一 canonical JSON、atomic/new write、hash、路径
  containment 和 manifest；保留错误文字与 JSON bytes 语义。
- [ ] 抽 `progress.py`、`execution.py`、`state.py`，把 stream/process 与状态转移分开；将
  `_run_one_cell` 拆成 prepare、execute、verify、seal 四个显式步骤。
- [ ] 抽 `results.py`，把 `_collect_cell` 拆成证据装载、有效性、rawData/cost、audit、cell
  record 五段，并保持结构/性能报告输入 schema 不变。
- [ ] 抽 `timing.py`，把 exact/compatible signature、history selection、active progress 和 ETA
  composition 分开；不得改变 matched-history fallback 顺序。
- [ ] 最后抽 `planning.py`，让 `benchmark_core.py` 只做受控 re-export。因为旧
  preregistration validator 会 `from benchmark_core import task_fingerprint`，在确认所有冻结
  validator 仍可导入前不能删除 facade。
- [ ] 同步 nested benchmark architecture、runner blueprint、tests blueprint 和文件 blueprints；
  明确废止“所有 orchestration 保持一个 module”的旧结论。

验收：不跑 simulator；现有 benchmark unit suite、golden schema/hash/error tests、CLI
`--help` 与 structural no-write plan/preflight tests 全通过；旧完成 run 可 inspect/collect/report；
旧未完成 run 因 automation fingerprint 变化明确拒绝 resume；LOC/模块/函数上限达标。

### Phase 2：停止复制实验 runner

- [ ] 八个现存 `hierarchical_cae_*.py` 全部保持原字节，不在其中“抽 helper”，也不让新代码
  继续 import 它们。
- [ ] 只在 successor/PCA 等下一项真实实验需要时建立 `experiment_runtime`；先从 plan 声明、
  case/dataset contract、arm protocol、pure metrics、artifact writer 六个最小边界开始。
- [ ] 将 shared quality/field/cost/Pareto/resource metrics 各保留一个实现；calibration 和
  assessment 组合这些 primitives，不复制 case loading、cost projection 或 JSON utilities。
- [ ] 每个新 preregistration 只携带 declarative plan 和不超过 120 行 adapter。engine 必须以
  内容寻址 wheel/zip/tree artifact 固定；plan 同时记录 adapter hash、engine manifest hash、
  package wheel hash和 policy/threshold hashes。
- [ ] 新 validator 从显式 artifact 参数或不可变内容寻址位置验证，不依赖会被同版本 build
  覆盖的 `dist/yadof-<version>.whl`。

验收：用 synthetic fixtures 跑同一 plan 的 arm ordering、metric values、gate reduction、
failure semantics 与 artifact hashes；不同 chunk/order 不改变结果；篡改任一 engine/plan/
adapter 文件必须 fail closed；不得访问 offline/calibration locator 或启动 simulator。

### Phase 3：整理 hierarchical CAE package，而不是合并回巨型文件

- [ ] 按 `networks/objectives/training/inference` 拆除 `modeling.py`；先机械移动并保持 public
  internal call signatures，再做去重，避免结构重写与算法调参混在同一提交。
- [ ] 把 runtime 的 data adaptation、state recovery 和 cost projection 分成私有 service，
  `runtime.py` 只暴露 component lifecycle facade。
- [ ] 在 conditional-INR/CAE 两套测试证明等价后，抽取 atomic artifact、training event、
  seeded finite-member selection 等小型 shared primitives；checkpoint namespace、schema、
  quality policy和 component semantic identity仍由组件自己拥有。
- [ ] scheduler 只在 join/cancel/status/state-machine 行为逐项等价后抽公共 primitive；若需要
  大量组件 callback 才能共享，则放弃该项，接受两个清晰的小 scheduler。
- [ ] 删除 CAE `metadata.py` 前，确认 wheel member、lazy import、metadata event schema、失败
  记录和 recovery 路径都由共享模块覆盖。
- [ ] 为现有 `coordinates.py` 补 file blueprint；为所有新/移动文件同步 blueprint，删除已经
  不存在文件的 blueprint。

验收：不得改变 architecture version、state signature payload、checkpoint namespace、quality
policy identity、rawData reconstruction、current-cost interpreter、posterior member identity、
zero-observation-noise 或 Gate 0 failed status；hierarchical/conditional focused tests、checkpoint
round-trip、lazy-import test、完整 installed-wheel suite 全通过；LOC 和依赖规则达标。

### Phase 4：清理活动入口并量化收尾

- [ ] `rg` 确认除 frozen sources/receipts/docs 外，没有活动代码 import 旧
  `hierarchical_cae_*.py` 或依赖另一个模块的私有函数。
- [ ] 生成 before/after 机器可读规模报告，分别列 active source、frozen evidence、tests、
  preregistration validators；不得用移动到另一个目录、压缩或改后缀伪造 LOC 降幅。
- [ ] 更新 root/nested architecture、project/module/file blueprints、术语、适用 user docs 和
  change record；记录旧 validator 仍可复验，及新 engine artifact 的定位方式。
- [ ] 只有用户明确授权且存在科学实验需求时，才运行 benchmark/仿真；结构重构本身只做
  unit/installed-wheel/structural no-write acceptance。

验收：目标目录、LOC、最大文件/函数、duplicate/private-import gates 全通过；所有 frozen
hashes 不变；构建 wheel、force reinstall、import-origin、focused/full tests 按届时开发指南
完成；最终 diff 不含实验结果、生成物、受保护数据或阈值变化。

## 兼容性与风险

- **冻结证据风险最高。** 八个 runner 不能直接删除/搬动/格式化；“把 v1 合并进 current”会
  立即破坏 v4 hash。推荐做法是把它们从活动维护面隔离，而不是篡改历史。
- **resume 不能透明跨实现。** 当前 run spec 直接 hash `benchmark_core.py`；拆包后必须 hash
  全 runtime manifest。旧完成 run 继续支持只读 inspect/collect/report，旧未完成 run 按现有
  fail-closed 规则拒绝 resume，不提供绕过开关。
- **内部 import 也可能被历史 validator 使用。** `benchmark_core.task_fingerprint` 已被旧
  validator 直接 import，因此需要小 facade；其他 re-export 只按调用清单保留，不建立无限期
  wildcard compatibility layer。
- **拆文件不会自动减代码。** Phase 1/3 必须在行为等价后删除重复 dict choreography、I/O、
  event、member selection 与状态样板；达不到总 LOC 目标就不能把“模块化完成”当成精简完成。
- **过度抽象风险。** conditional-INR 和 CAE 的 runtime/types 差异很大。共享层只接受稳定
  primitive，不统一模型训练、schema 或 component policy。
- **科学语义漂移风险。** 结构重构不得改变数据 split、seed、field macro、quality masks、
  current cost、Pareto/HV、calibration 或 gate；数值改变必须另立 successor preregistration，
  不能混入本 TODO。
- **并发共享工作树风险。** 每阶段开始和 staging 前重新检查 HEAD、status、unstaged/staged
  diff，分析并保留其他任务的连贯改动。

## 明确不做

- 不把失败的 hierarchical CAE 设为默认、不放宽 threshold、不重解释 v5/v8 结果。
- 不借结构清理实现 successor/MoE、PCA/SVD、真实 qNEHVI exploitation 或七臂 formal run。
- 不修改 old plans、validators、receipts、hashes，亦不删除 ignored runtime evidence。
- 不为减少文件数把 package 的 schema/checkpoint/scheduler/posterior 边界重新塞回一个文件。
- 不新增 Pydantic、service container、plugin registry、全局 algorithm selector 或自动 discovery。

## 完成规则

只有同时满足以下条件，本文才可移入 `dev_doc/obsolete/`：

- `benchmark_core.py`、generic runner、hierarchical CAE package 和活动总 LOC 均达到量化目标；
- 八个 frozen runner 原路径、原内容、原 SHA-256 与全部既有 validator/receipt 仍有效；
- 新 runtime manifest 能检测任一拆分模块漂移，旧 run 的只读/拒绝-resume 边界有测试；
- 活动代码不存在跨模块私有 helper 耦合或大段完全重复实现；
- 最大模块/函数上限、依赖方向、lazy import、checkpoint/recovery、posterior coherence、
  current-cost 与 schema invariants 全部通过；
- architecture、blueprints、术语、tests 和 change record 与实现同步；
- 按届时开发指南完成 wheel build、force reinstall、import-origin、focused/full tests 和最终
  Git 工作流，并如实报告 frozen evidence footprint 没有被当作可删除的活动代码。
