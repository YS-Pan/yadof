# 大幅精简 benchmark 与 hierarchical CAE 工程结构

## 本文的角色

- 本文是一次只读结构审查的执行计划，不授权立即修改产品代码、重跑 benchmark/仿真，
  或改变 hierarchical CAE 已记录的科学结论。
- 后续实施必须由用户明确选中本文，并遵守届时 `dev_doc/README.md` 的构建、安装、测试、
  change record、提交和推送流程。
- 本文承接
  [surrogate/qNEHVI 剩余工作](20260828_121904_surrogate-qnehvi-remaining-work.md)
  中“共享 versioned engine + 薄 adapter”的工程建议，但范围只限代码组织、重复消除和
  可维护性；它不能把 Gate 0 v5/v8 的失败改写成接受。
- 背景判断来自 Codex 任务
  `codex://threads/01a045a2-5fe4-7992-9932-4c35cd3382ad`，并定向核对了其中明确关联的
  `01a04046-99c7-7fc0-a2a1-91835bc898a8`、
  `01a04164-d04f-7873-a8e8-6ddab35ad2f5`、
  `01a04242-14f1-7162-8c38-c44a8b02fe12`，以及抗噪声证据任务
  `01a04151-bc16-7ff0-84d5-16eef2e1b5c6`。本文件已经包含继续实施所需的结构结论，
  实施者不应默认重读完整历史任务。

### 用户关于哈希锁的最新决定

- 用户于 2026-08-28 明确要求移除本文范围内的**所有哈希锁**。这里的哈希锁是指：因为
  SHA-256、fingerprint、content digest 或 source digest 不相等，就拒绝源码修改、移动、
  合并、删除、resume、replay、state/evidence 使用或验收。
- hash/fingerprint 字段可以作为非权威 provenance 保留在旧记录中，也可以由新工具输出供
  诊断；它们不得再成为 admission、compatibility、scientific validity 或 completion gate。
- 历史 plan、threshold、receipt 和结果仍然描述当时发生过的实验，不应倒改数值或结论；
  但它们记录的旧源码 hash 不锁定当前工作树，也不要求最新 HEAD 继续通过旧的当前路径
  hash validator。
- 可复现性改由普通 Git 历史、明确 revision、run-local implementation/task snapshot、保存的
  输入与结果承担。旧实验若只能在旧 revision 运行，应在该 revision 的独立 checkout 中重放，
  不能为了让旧 validator 在最新 HEAD 通过而永久保留重复源码。
- 同一 benchmark run 的一致性也不得依赖比较当前工作树 hash。新 run 必须携带并使用自己的
  execution snapshot；旧 run 缺少可执行 snapshot 时应明确要求 restart/migration 决策，而
  不是把当前源码差异解释成证据损坏。

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
| `hierarchical_cae_dataset.py` | 密封/校验三段 dataset，解析 locator，加载 selected records/rawData，建立 rank-3 layout | 证据隔离与 schema 一致性需要 | 把仍需逻辑迁入共享 dataset contract，然后删除旧文件 |
| `hierarchical_cae_validation_v1.py` | 第一次失败 runner 的当时实现 | 当前实现不需要；Git 历史足以定位 | 删除；需要重放时使用原提交的独立 checkout，不在当前树保留副本 |
| `hierarchical_cae_validation.py` | case 装载、quality、资源监控、CAE/conditional/PCA arms、rawData/cost/Pareto 指标与总编排 | 科学语义需要，但不应集中 1,226 行 | 把仍需语义拆进共享 engine + declarative plan，然后删除旧文件 |
| `hierarchical_cae_gate4_assessment.py` | 汇总 representation/quality/resource 指标并执行当时阈值 | reducer 机制仍有用 | 并入统一 assessment reducer；历史阈值只作旧结果上下文 |
| `hierarchical_cae_experimental_offline.py` | v6 固定 offline-test、coordinate 指标、CAE/conditional 比较 | 当前通用 runtime 不需要完整脚本 | 迁移可复用机制后删除；未来只写薄 experiment adapter |
| `hierarchical_cae_experimental_assessment.py` | v7 对 v6 evidence 做后访问汇总 | 当前无需独立脚本 | 并入统一 assessment reducer 后删除 |
| `hierarchical_cae_calibration_checkpoint.py` | 按实验身份训练并发布 development checkpoints | train/publish 机制需要 | 改为调用共享 service 的薄命令，或由 workflow 直接替代后删除 |
| `hierarchical_cae_calibration.py` | calibration case/fold、field distribution、cost/Pareto/HV、qNEHVI proxy、applicability、gate、artifact 输出 | 科学评估机制需要，但 1,828 行混合过多职责 | 拆成 calibration metrics、decision proxy、gate policy 与 orchestration，随后删除旧文件 |

这 8 个文件当前确实被 v4--v8 的 plan/amendment/validator 以当前路径和 SHA-256 绑定，但这是
需要移除的遗留实现，不是继续保留它们的理由。实施时应先把旧 validator 从当前验收入口
退役，或删除其中针对当前源码/artifact digest 的拒绝逻辑；旧 plan/receipt 里的 hash 字段
可以保留为当时的 provenance。之后可正常修改、移动、合并或删除这 8 个文件。历史代码由
Git revision 提供，最新 HEAD 无需伪装成旧实验环境。

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
重组。旧 plans/receipts 是历史记录；旧 validators 若仍把 digest mismatch 当成拒绝条件，
必须退役、删除或改为纯诊断工具，不得继续约束活动源码结构。

## 目标架构

目标不是把一个巨型文件切成大量随意小文件，而是让依赖方向与生命周期可见。建议结构如下；
文件名可在实施前微调，但边界和依赖方向不可反转：

```text
benchmark_automation/
  benchmark.py                     # 仅 CLI 参数与呈现
  benchmark_core.py                # <=250 行临时 facade；只服务当前 CLI/调用者
  benchmark_runtime/
    contracts.py                   # BenchmarkError、Paths、内部 dataclasses/JSON codecs
    storage.py                     # path confinement、canonical JSON、atomic/new writes、manifests
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
  preregistrations/
    <future-version>/
      plan.json
      run.py                        # <=120 行薄 adapter，调用普通 versioned engine API

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

- CLI/薄 adapter 可以依赖 runtime；runtime 不得 import CLI、preregistration 或 legacy runner。
- scientific metrics 必须是显式输入/输出的纯函数，不读取全局 plan，也不从另一个 runner 的
  `_private_helper` 借实现。
- plan/threshold/policy 负责“本次实验测什么、门槛是什么”；engine 只负责可版本化算法。
- package 的 `runtime -> training/inference/schema/checkpoints` 单向依赖；network/objective 不得
  import workspace、recorder、task 或 benchmark。
- shared primitive 只抽取两个现有组件都通过行为等价测试的稳定机制。禁止为了复用而建立
  callback soup、全局 registry、万能 base class 或新的组件 selector。
- 新 run 必须复制并使用完整的 `benchmark_runtime`/`experiment_runtime` execution snapshot；
  run spec 可以记录 revision 和来源作为 provenance，但不得比较当前工作树 digest 来拒绝
  resume 或验收。

## 可量化目标

全部当前源码都进入可维护和可删除范围：

- 八个 legacy runner 的可复用行为迁移后，从当前树删除 274,942 bytes / 7,254 行；不在
  `archive/`、改后缀文件或重复目录中保留源码副本。
- `benchmark_core.py`：4,887 行降到不超过 250 行；只保留稳定 facade/re-export 与过渡说明。
- generic benchmark runner（facade + `benchmark_runtime`）：物理行数不超过 3,450，较当前
  4,887 至少减少 29%；任何模块不超过 700 行。
- hierarchical CAE package：5,042 行降到不超过 4,200 行；任何模块不超过 700 行；
  `modeling.py` 和独立 `metadata.py` 不再存在。
- generic runner 与 hierarchical CAE package 合计从 9,929 行降到不超过 7,650 行；如需建立
  新 experiment engine，其第一版上限 2,400 行。包含该 engine 时，上述 repository subtotal
  从 17,183 行降到不超过 10,050 行，至少减少 41.5%；暂不需要 engine 时应降到不超过
  7,650 行，至少减少 55.5%。
- 新 version adapter/CLI 文件不超过 120 行；普通函数不超过 100 行。确属单一数学 kernel
  可放宽到 150 行，但必须在 blueprint 解释；不得再出现 300+ 行 orchestration function。
- 活动 benchmark 模块间不允许 import 对方下划线符号；AST duplication check 不允许新增
  20 行以上的完全相同 top-level function body。
- 只减少文件数不是验收指标；模块职责、依赖方向、总活动 LOC、重复率和行为等价必须同时
  达标。

## 分阶段 TODO 与验收

### Phase 0：建立不运行 simulator 的行为保护网

- [ ] 记录基线规模、AST symbols、import graph，以及八个 legacy runner 对应的 Git revisions；
  这些信息只作迁移 provenance，不形成当前源码锁。
- [ ] 盘点 benchmark/preregistration 中所有 `SHA-256`、fingerprint、digest comparison 及
  `source drift` 分支；标出哪些只是显示字段，哪些会拒绝执行。所有拒绝型 hash lock 必须
  在后续 phase 删除，旧 validator 不再是最新 HEAD 的 completion gate。
- [ ] 为 `benchmark.py` 实际使用的 facade surface 建清单；至少覆盖 plan、preflight、
  run/resume、collect、report、inspect、ETA 和 JSON/storage helpers。现有 fingerprint helper
  只有在仍有非阻塞 provenance 调用者时才保留。
- [ ] 从现有 unit fixtures 生成稳定 golden expectations：plan/spec/state/collection/report 的
  schema、排序、错误类型和摘要字段。fixture 不得包含真实 simulator 输出的新
  访问。
- [ ] 为新 run-local execution snapshot 写隔离测试：创建 run 后修改当前源码，run/resume 仍
  使用自己的 snapshot，不混入新旧模块。
- [ ] 记录旧 run 的兼容矩阵：已完成 run 可 inspect/collect/report；带完整 execution snapshot
  的未完成 run 从 snapshot resume；缺少 snapshot 的旧 run 需要显式 restart/migration，不能
  单凭当前源码 digest 不同而宣称历史证据损坏。

验收：现有 benchmark automation unit tests 全通过；新增 characterization tests 全通过；
hash-lock inventory 完整且每项都有删除/退役去向；未执行 benchmark、仿真或受保护 dataset
访问。

### Phase 1：直接切分 `benchmark_core.py`

- [ ] 先抽 `storage.py` 与 `contracts.py`，统一 canonical JSON、atomic/new write、路径
  containment 和 manifest；保留错误文字与 JSON bytes 语义。
- [ ] 抽 `progress.py`、`execution.py`、`state.py`，把 stream/process 与状态转移分开；将
  `_run_one_cell` 拆成 prepare、execute、verify、seal 四个显式步骤。
- [ ] 抽 `results.py`，把 `_collect_cell` 拆成证据装载、有效性、rawData/cost、audit、cell
  record 五段，并保持结构/性能报告输入 schema 不变。
- [ ] 抽 `timing.py`，把 exact/compatible signature、history selection、active progress 和 ETA
  composition 分开；不得改变 matched-history fallback 顺序。
- [ ] 最后抽 `planning.py`，让 `benchmark_core.py` 只做当前调用者所需的受控 re-export。
  不得为了让已退役的历史 validator 继续 import `task_fingerprint` 而永久保留 facade；当前
  CLI/tests 切换完成后可直接删除它。
- [ ] 同步 nested benchmark architecture、runner blueprint、tests blueprint 和文件 blueprints；
  明确废止“所有 orchestration 保持一个 module”的旧结论。

验收：不跑 simulator；现有 benchmark unit suite、golden schema/error tests、CLI
`--help` 与 structural no-write plan/preflight tests 全通过；旧完成 run 可 inspect/collect/report；
新 run 可从 run-local execution snapshot resume；旧 run 缺 snapshot 时给出明确迁移/重启
说明；LOC/模块/函数上限达标。

### Phase 2：迁移并删除 legacy 实验 runner

- [ ] 退役把当前路径/source digest 当成执行前提的 v4--v8 validator；保留的旧 plan/receipt
  只作历史记录，其 hash 字段不再参与当前验收。
- [ ] 从八个 `hierarchical_cae_*.py` 只迁移仍需的 dataset、metric、assessment、calibration、
  arm 和 orchestration 行为；建立等价测试后删除全部八个旧文件，不在当前树保留 archival
  source copy。
- [ ] 只在 successor/PCA 等下一项真实实验需要时建立 `experiment_runtime`；先从 plan 声明、
  case/dataset contract、arm protocol、pure metrics、artifact writer 六个最小边界开始。
- [ ] 将 shared quality/field/cost/Pareto/resource metrics 各保留一个实现；calibration 和
  assessment 组合这些 primitives，不复制 case loading、cost projection 或 JSON utilities。
- [ ] 每个新 experiment 只携带 declarative plan 和不超过 120 行 adapter。plan 可记录 Git
  revision、package version、环境和来源字段，但它们都是 provenance，不锁定当前源文件。
- [ ] 新 experiment 使用 run-local implementation/package snapshot；validator 只校验声明的
  schema、输入授权、结果完整性和科学规则，不比较当前源码、wheel 或 adapter digest。

验收：用 synthetic fixtures 跑同一 plan 的 arm ordering、metric values、gate reduction、
failure semantics 与 artifact schema；不同 chunk/order 不改变结果；当前工作树源码变化不影响
已创建 run 的 snapshot 执行，且不会触发 hash-based refusal；不得访问 offline/calibration
locator 或启动 simulator。

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

- [ ] `rg` 确认八个 legacy `hierarchical_cae_*.py` 已删除，活动代码不依赖另一个模块的私有
  函数。
- [ ] 生成 before/after 机器可读规模报告，分别列 active source、tests、historical
  plans/receipts 与 validators；不得用移动到另一个目录、压缩或改后缀伪造
  LOC 降幅。
- [ ] 更新 root/nested architecture、project/module/file blueprints、术语、适用 user docs 和
  change record；明确 source hash 只作 provenance、旧 hash validator 已退役，以及 run-local
  execution snapshot 的定位方式。
- [ ] 只有用户明确授权且存在科学实验需求时，才运行 benchmark/仿真；结构重构本身只做
  unit/installed-wheel/structural no-write acceptance。

验收：目标目录、LOC、最大文件/函数、duplicate/private-import gates 全通过；活动代码、
validator、resume 和 completion rules 中不存在 hash-based lock；构建 wheel、force reinstall、
import-origin、focused/full tests 按届时开发指南完成；最终 diff 不含实验结果、生成物、
受保护数据或阈值变化。

## 兼容性与风险

- **历史实验与当前源码必须解耦。** 删除 legacy runner 不改变旧数值、阈值或结论；旧代码
  通过 Git revision 查阅/重放。最新 HEAD 不再承担让旧 current-path validator 通过的责任。
- **resume snapshot 迁移。** 新 run 使用完整 execution snapshot。旧 run 若没有该 snapshot，
  不能安全自动补造当时实现；应保留其完成证据，并要求显式 restart/migration 决定。不得用
  当前源码 hash mismatch 代替这个能力判断。
- **历史 validator import 不构成 API。** `benchmark_core.task_fingerprint` 被旧 validator import
  过，不足以要求永久 facade。退役旧 validator 后按当前 CLI/tests 的真实调用面直接切换。
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
- 不倒改旧实验的数值、阈值、数据访问时间线或失败结论；可以退役/删除旧 validator，也可以
  让旧 hash 字段作为非权威历史数据留存。
- 不为减少文件数把 package 的 schema/checkpoint/scheduler/posterior 边界重新塞回一个文件。
- 不新增 Pydantic、service container、plugin registry、全局 algorithm selector 或自动 discovery。

## 完成规则

只有同时满足以下条件，本文才可移入 `dev_doc/obsolete/`：

- `benchmark_core.py`、generic runner、hierarchical CAE package 和活动总 LOC 均达到量化目标；
- 八个 legacy runner 已从当前树删除，所需行为只在新的共享实现中保留；
- 所有 source/artifact/wheel/runner hash lock 已从活动 validator、resume、compatibility 和
  completion rules 移除；任何保留 digest 都仅用于显示 provenance；
- 新 run-local execution snapshot 隔离当前源码修改，旧 run 的只读与迁移边界有测试；
- 活动代码不存在跨模块私有 helper 耦合或大段完全重复实现；
- 最大模块/函数上限、依赖方向、lazy import、checkpoint/recovery、posterior coherence、
  current-cost 与 schema invariants 全部通过；
- architecture、blueprints、术语、tests 和 change record 与实现同步；
- 按届时开发指南完成 wheel build、force reinstall、import-origin、focused/full tests 和最终
  Git 工作流，并如实报告 legacy source 的实际删除量与新 runtime 的实际新增量。
