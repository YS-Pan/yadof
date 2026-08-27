# 使用 Pydantic 重构配置声明与组件配置所有权

## 状态与背景

- 本文是待执行的架构重构 handoff，不代表已经批准修改当前运行时行为、配置格式或依赖。
- yadof 已完成优化算法模块化：workspace 通过
  `submit/optimization.py:build_optimization()` 组合完整策略，package 不再用全局 selector
  选择完整算法。当前正在增加 hierarchical CAE、posterior calibration、qNEHVI 等模块，
  以后还会继续增加组件。
- 当前 `yadof.config` 仍集中拥有 package defaults、全部合法字段名、字段分类、类型与范围
  校验、路径处理、workspace 覆盖和临时 override。计划阶段清点到约 495 行、85 个 setting，
  其中约 40 个属于 optimize/surrogate；执行本 TODO 时必须重新生成准确 inventory，不能把
  这些数量当成永久契约。
- 模块化之后，conditional-INR、pymoo、GPSAF 等实现仍需要同时维护配置默认值、中央合法
  字段集合、中央校验分支，以及组件运行时自己的 fallback/默认值。新增模块会继续扩大这个
  多点修改和默认值漂移风险。
- 当前配置实现也有必须保留的成熟能力：
  - `package defaults < workspace config.py < API/CLI temporary override` 的优先级；
  - 每个 effective value 的来源追踪与 `describe()`；
  - immutable `LoadedConfig`、显式 workspace、未知字段拒绝和 eager validation；
  - 相对路径以 workspace root 解析，并满足 workspace 路径隔离规则；
  - 每 generation 重新加载配置，但 campaign recorder 的路径和容量策略在 session 创建时
    冻结。
- 本重构将此前讨论中的两项方案组合实施：
  - **A：核心配置采用单一声明式 schema**，消除默认值、类型、范围和字段清单的重复；
  - **C：算法/代理模块拥有自己的 typed settings**，由 workspace composition factory
    构造并窄传递给组件，不再让所有组件读取一个环境式全局配置对象。
- Pydantic 只作为 A+C 的声明、解析和校验引擎。它不负责组件选择、依赖注入、workspace
  路径发现、配置来源合并、热重载、状态 namespace 或插件注册。

## 目标

1. 让一个配置项的默认值、运行时类型、基础约束和文档信息尽量只有一个权威声明位置。
2. 让核心运行时只拥有跨任务、跨算法都成立的 framework policy；让算法和 surrogate
   参数跟随其组件及 factory 演进。
3. 新增一个算法或 surrogate 时，理想情况下只需新增该模块的 settings model、factory
   参数、实现、测试和文档，不再编辑中央 `config.py` 的算法字段集合与专用 validator。
4. 保留当前 workspace `config.py`、优先级、provenance、路径、安全边界和 generation reload
   语义，先完成兼容迁移，再考虑是否收缩旧的 flat uppercase surface。
5. 使用 Pydantic v2 的严格类型、默认值校验、field/model validators、frozen model、
   `extra="forbid"`、结构化错误和 JSON Schema 能力，减少手写校验样板；同时将 yadof
   特有语义保留在薄的 framework metadata/loader 层。
6. 保持普通 import 轻量。核心 schema 或 public settings 类型不能为声明字段而导入 Torch、
   BoTorch、pymoo 算法对象或其他可选数值 backend。

## 已确定的设计决定

### 1. 两层配置所有权

#### 核心配置

核心 Pydantic models 只覆盖 framework 通用、由 package 统一执行的策略，例如：

- workspace/framework paths；
- history、reliable recorder 和 campaign session policy；
- fast/local/distributed evaluation 与共同 resource policy；
- HTCondor transport、timeout、retry 和 request policy；
- campaign 通用控制、logging/progress，以及确实跨全部策略成立的调度边界。

核心字段可以按职责拆成小型 nested models，但初期仍应提供当前 flat uppercase workspace
surface 的兼容映射。不要建立一个包含所有已知算法 settings 的巨型 `YadofConfig`。

#### 组件配置

以下配置由对应 module package 的 typed settings model 所有，并通过公开 factory 或明确的
component construction seam 进入运行时：

- pymoo GA/NSGA-III 的 crossover、mutation、reference-direction 和 refill 参数；
- GPSAF assistance/phases/exploration 参数；
- conditional-INR 的网络、训练、bootstrap、non-finite 和 scheduling 参数；
- hierarchical CAE、posterior calibration、qNEHVI 以及未来算法模块的专用参数。

组件实现接收窄 settings object，不接收完整 `LoadedConfig` 来隐式读取任意全局字段。
共享 framework service 可以继续接收核心配置或更窄的 core policy value。

### 2. Pydantic 的职责边界

Pydantic 负责：

- 字段声明、default/default factory、严格类型和基础数值/长度/枚举约束；
- defaults 自身的 validation；
- 同一 model 内的 cross-field invariant；
- immutable value model 和结构化 validation errors；
- 可选的 JSON Schema/机器可读字段说明生成。

Pydantic 不负责：

- 执行 workspace `config.py` 或决定 package/workspace/override 的优先级；
- 保留每个字段来自哪个 source layer；
- 确保较低优先级中的非法值不会被较高优先级遮蔽；
- 解析相对 workspace path、检查路径重叠或构造 `WorkspaceContext`；
- 选择当前 complete optimization strategy 或发现插件；
- generation boundary reload、campaign-frozen policy 或异步 component snapshot；
- 决定 checkpoint/strategy semantic identity；
- 直接承担跨版本持久化协议。

这些职责由薄的 yadof loader、source map、workspace resolver、snapshot 和 identity 层继续
拥有。首轮不引入 `pydantic-settings`；当前来源优先级和 provenance 不是其默认环境变量
模型能够自然替代的契约。

### 3. yadof 字段 metadata

Pydantic field declaration 之外仍需保留少量 yadof-specific metadata，至少能够表达：

- legacy/external uppercase name；
- owner（core 或具体 component）；
- reload policy（generation-hot 或 campaign-frozen）；
- 是否进入 semantic identity，以及使用哪一个 identity block/version；
- workspace-relative path 的解析/隔离规则；
- deprecation/alias 和移除版本；
- 面向用户文档的简短说明。

优先通过 `Annotated`/`Field(json_schema_extra=...)` 或一个很薄的 typed metadata helper 表达，
不要重新创造一个与 Pydantic 平行、再次声明 type/default/constraint 的完整 `SettingSpec`。

### 4. 加载与校验流水线

目标流水线固定为：

```text
package declared defaults
  -> execute selected workspace config.py and collect uppercase values
  -> normalize legacy names / reject unknown names
  -> validate every source layer sufficiently early
  -> merge package < workspace < temporary override while recording source
  -> construct Pydantic core/component models and run cross-field validation
  -> resolve and validate workspace-relative paths
  -> publish immutable LoadedConfig / WorkspaceContext / component settings snapshot
```

关键约束：一个低优先级 layer 中的非法值不能仅因后续 override 覆盖它而变成合法。若当前
行为已经逐层拒绝，迁移测试必须锁定；若现状有例外，应先记录实际行为并作明确兼容决定。

`LoadedConfig` 可以内部组合 core model、source map 和 `WorkspaceContext`，但兼容期需保持
当前属性/索引读取和 `source_for()`/`describe()` 的可观察语义。不要让调用方直接依赖
Pydantic 的内部 validator、core schema 或错误对象布局。

### 5. Factory 与 component settings API

公开 factory 仍保持 workspace author 易读，例如：

```python
conditional_inr(epochs=300, ensemble_size=5)
hierarchical_cae(groups=..., field_layouts=...)
qnehvi(candidate_pool_size=..., posterior_draws=...)
```

可同时允许高级调用方显式传入对应 `Settings` model，但必须选择一个无歧义规则：

- 推荐 `factory(...explicit keyword settings...)` 和 `factory(settings=Model(...))` 互斥；或
- 显式关键词只允许覆盖 settings model，并把每个覆盖记录进 component identity。

不得静默合并 workspace legacy global key、settings object 和显式 factory keyword 后让用户
无法判断有效值来源。若同一语义项在两个新旧入口同时提供，默认应给出 actionable conflict
错误；只有经过批准的兼容规则才可定义确定优先级。

Factory 在构造阶段完成 settings validation。长生命周期 trainer/strategy 必须接收一次
immutable snapshot，不能在运行中反复读取 mutable workspace config。

### 6. 严格性与不可变性

- 默认使用 Pydantic v2 strict validation、`extra="forbid"`、`validate_default=True` 和
  frozen models。
- 在迁移前建立兼容矩阵，逐项测试：`bool` 与 `int`、整数传给 float、list/tuple、
  `os.PathLike`/`Path`、enum/string、NaN/Infinity，以及 Python-input 与 JSON-input 的 strict
  差异。
- 不以“Pydantic 接受了”作为兼容证明；所有 public workspace 形式都需要明确测试。
- frozen model 只是浅层不可变。字段优先使用 tuple、frozenset、immutable mapping 或在
  validator 中复制冻结，不能把可变 list/dict 引用封进 checkpoint identity。
- 不为迁就历史偶然 coercion 而全局关闭 strict mode。确需兼容的转换必须字段级、带测试、
  有 deprecation 路径。

### 7. Semantic identity 与持久化

- 不得直接对 `model_dump()` 的全部结果做 hash。新增运行时字段、文档 metadata 或输出
  格式变化不应意外使所有 checkpoint 失效。
- 每个 strategy/component 定义显式、版本化、JSON-safe 的 `semantic_payload()`；只包含
  会改变算法数学、训练/推理含义、参数归一化、schema/group/layout 或 state 兼容性的字段。
- runtime-only budget、日志、路径、source provenance 和诊断字段按其真实含义单独处理。
- Pydantic model serialization 不是持久化协议。若 settings 写入 checkpoint/metadata，外层
  artifact schema 必须继续有独立版本、兼容检查和迁移规则。
- source fingerprint 与 deterministic semantic signature 继续分离；源码变化不自动等价于
  scientific identity，也不自动删除真实历史。

## 兼容与迁移政策

1. 首轮保持 workspace 根 `config.py` 和现有 uppercase keys 可用，不同时引入 YAML/TOML、
   环境变量配置或 Hydra config groups。
2. 建立显式 legacy-key-to-component-field table。映射必须保留来源、给出 deprecation warning，
   并在 `yadof check`/配置描述中指出新的 `submit/optimization.py` factory 写法。
3. 兼容窗口和实际移除版本在实施前由用户批准。未经批准，不删除现有 keys、不改变默认值、
   不重写用户 workspace。
4. package workspace template 在对应新路径通过 installed-wheel 验收后再迁移；已有 workspace
   不由 `init` 或 `check` 自动改写。
5. 新模块一旦采用 component-owned settings，不再反向增加新的中央 algorithm uppercase
   keys。若确有全局 campaign policy，先证明它跨全部 component 共享。
6. 当前正在实施的 hierarchical CAE/qNEHVI 工作不因本文被自动改写或阻塞。执行本 TODO
   时应基于届时已提交架构，逐个迁移；不能覆盖其进行中的工作或改变已预登记 benchmark。

## 实施阶段与 gates

### Gate 0：依赖与行为 inventory

- 重新清点 `config.py` 的全部字段、default、validator、controlled-name set、path rule、
  consumer、source/reload policy 和 semantic-identity 参与方式。
- 为每个字段标记 `core`、具体 component、legacy-only 或待决定；未经证据不归类。
- 审计实施时受支持的 Pydantic v2 版本、Python 版本、许可证、wheel 平台、`pydantic-core`
  artifact、安装体积、冷 import 成本和 API 稳定性；版本范围必须声明为 direct core
  dependency，不能依赖 transitive install，也不能在本 TODO 中预先硬编码未来版本。
- 建立当前行为 parity fixtures，覆盖 package/workspace/override、invalid lower layer、
  source provenance、path resolution、hot reload、campaign-frozen values 和错误文本中的关键
  actionable 信息。
- 输出 inventory/reuse decision change record；Gate 0 不改变 public behavior。

### Gate 1：conditional-INR 垂直 spike

- 选择 conditional-INR 是因为它已经模块化、设置数量足以暴露问题，又能和现有 GPSAF
  组合做精确回归。
- 在 `surrogate.conditional_inr` 内建立 frozen Pydantic settings model；把当前约 23 个
  legacy keys 映射进它，执行时再次核实准确数量。
- 先消除该模块内部 default/fallback/validation 的重复，但保持 legacy workspace keys、
  `conditional_inr()` factory、模型数学、训练调度、checkpoint signature 和 GPSAF 行为。
- 量化比较迁移前后：默认值权威位置数、手写 validator/分支行数、structured error 质量、
  普通 import 时间、wheel 大小和测试复杂度。
- 若 Pydantic 造成不可接受的 core import/安装负担、无法保持严格兼容，或仅把重复从一处
  移到另一处，停止后续迁移并记录证据；不要为了完成计划强行推广。

### Gate 2：组件 settings 公共边界

- 基于 spike 固定公共 settings/factory policy、冲突规则、metadata helper 和 semantic payload
  生成方式。
- 将 pymoo 和 GPSAF 专用字段移到其 module-owned models/factories；优先处理 future module
  新增频率最高、跨中央列表最明显的配置。
- 为 hierarchical CAE、posterior calibration、qNEHVI 及后续模块直接使用新模式，不再新增
  中央专用字段。
- 组件 settings 的导入保持轻量；optional backend 仍只在组件实际运行时 lazy import。

### Gate 3：核心 declarative schema

- 将 paths、history/recorder、evaluation/resource、HTCondor、campaign common controls 按职责
  迁移为小型 Pydantic models。
- 构建 source-aware loader bridge，保留现有 precedence、逐层 validation、`source_for()`、
  `describe()` 和 `WorkspaceContext` 解析。
- 移除已被 schema 单一声明替代的中央 default/type/name lists 与重复 special branches；
  只有在直接调用、测试和动态入口审计后才能删除。
- 核心 model 变为 internal contract 还是 public advanced API，在 Gate 0/1 证据后明确；默认
  推荐只公开稳定的 component settings/factory surface，不承诺 Pydantic internals。

### Gate 4：兼容迁移与文档工具

- `yadof check` 同时报告 legacy key、目标 factory 参数、冲突和计划移除版本，但保持只读。
- 更新 package workspace template、user docs、architecture、config/optimize/surrogate/module
  blueprints、terminology 和 API examples。
- 若 JSON Schema 对 editor、UI 或外部 tooling 有真实消费者，再增加版本化 schema export；
  没有消费者时只保留 Pydantic 自带生成能力，不新增 CLI。
- 完成 legacy window 后的实际字段删除必须作为单独的 incompatible-change 决定，不能在本
  TODO 中顺手完成。

## 验证矩阵

### 配置行为 parity

- package defaults、workspace uppercase values 和 temporary/API overrides 的逐项优先级；
- 每个 effective value 的 `source_for()`、`describe()` 与错误 source label；
- unknown uppercase、extra nested field、invalid default、invalid lower layer、重复 alias 和
  legacy/new conflict；
- strict bool/int/float、finite real、fraction/bounds、enum/mode、tuple/list/mapping 和 PathLike；
- relative path、absolute path、path overlap、missing required task paths 和双 workspace 隔离；
- config.py exception/SystemExit 到 actionable `ConfigError` 的边界；
- generation boundary reload 与 campaign-frozen recorder path/capacity 不被 Pydantic model
  构造时机改变。

### 组件与状态

- 每个 factory 的默认值和显式覆盖与迁移前完全一致，除非有单独批准的 behavior change；
- 组件只收到自己的 settings，不读取未声明的 ambient algorithm fields；
- 未选择组件不会为其 optional dependency 或 runtime-only requirement 失败；
- 普通 `import yadof.config/optimize/surrogate` 不加载 Torch、BoTorch 或 pymoo 算法模块；
- semantic payload 对字段顺序稳定，对等价 immutable input 稳定，对真正数学变化敏感，
  对日志/path/provenance 等非语义变化不误失效；
- conditional-INR、GPSAF 和现有 checkpoint recovery 在 legacy/new configuration 下保持兼容；
- strategy switch、retained inactive artifacts 和每 workspace 一个 trainer 的约束不变。

### 安装包与开发验收

- 按当时 `dev_doc/README.md` 完成 wheel build、force reinstall、import-origin、artifact
  membership、focused tests 和 full suite；不得用 editable install/PYTHONPATH 验收。
- 在项目支持的每个 Python/platform 组合上验证 `pydantic-core` wheel 可安装；缺失兼容 wheel
  时不得把源码编译负担静默交给普通用户。
- 记录引入 Pydantic 后 wheel/install size、cold import 和 config load time 的变化。
- 文档-only gate 可使用开发指南定义的例外；任何 package config/settings 代码变更都必须
  经过 installed-package acceptance。

## 预期收益级别与决策门槛

- 以当前规模看，Pydantic 对 A+C 的额外收益预计是**中等（约 6/10）**：明显减少手写
  校验、统一错误和 schema，但架构价值主要仍来自配置所有权拆分。
- 以 hierarchical CAE、posterior、qNEHVI 和未来更多模块的扩展趋势看，收益预计是
  **中高（约 7.5/10）**：新模块 settings、cross-field validation、文档/schema 和测试会
  更一致，中央文件增长显著放缓。
- 只有当 JSON Schema 被 editor/UI/外部插件等真实消费者使用时，收益才接近高等级。
- Gate 1 的第一次实现可能比纯 dataclass/手写 schema 稍多；是否推广看未来模块新增成本、
  重复声明减少和错误质量，不以单次 diff 行数作为唯一判断。

## 成本与风险

- Pydantic 与 `pydantic-core` 成为核心 direct dependency，增加 wheel、平台、安装、导入和
  升级审计成本。
- Pydantic v2 API/错误格式会形成一定耦合；公共 API 不应承诺其内部 schema/error 结构。
- strict mode 与当前 Python coercion 可能不完全一致，尤其 bool/int、int/float、PathLike 和
  sequence；兼容矩阵缺失会造成隐蔽 breaking change。
- `frozen=True` 不会递归冻结任意子对象；错误的可变字段会破坏 identity 和 snapshot。
- model validators 很容易重新聚成大型全局条件树；cross-field rule 必须留在最小 owner
  model，跨组件 rule 应尽量通过组合层显式检查。
- nested model 与 legacy flat uppercase 两套 surface 在兼容期增加暂时复杂度；必须有明确
  的冲突规则和退场计划，不能永久双轨。
- 自动 `model_dump()`/JSON Schema 容易诱导调用方把内部 model 当稳定协议；必须通过公开
  边界和版本化 artifact schema 限制。

## 非目标

- 不引入 Hydra、OmegaConf、config groups、multirun 或 YAML composition。
- 首轮不引入 `pydantic-settings`、环境变量/secrets 读取或新的配置文件格式。
- 不建立完整算法 registry、插件系统、service locator 或第二个 complete-method selector。
- 不把 task-owned parameter、rawData schema、simulator/project、objective/cost policy 或
  physics-specific settings 移入 package global config。
- 不要求所有 component 继承一个庞大的统一 settings 基类；共享层只保留确有共同语义的
  frozen base policy。
- 不通过本 TODO 修改 conditional-INR/GPSAF 数学、新 CAE/qNEHVI benchmark、recording
  durability、checkpoint 数据格式或默认优化组合。
- 不把 predicted rawData、Pydantic dump 或 config source map 写成新的 durable truth。
- 不在没有独立用户决定和迁移期的情况下删除现有 workspace keys。

## 待 Gate 证据决定的问题

以下问题尚未批准，实施者不能自行扩展范围：

- Pydantic 的准确最低/最高版本和 yadof 支持的 Python/platform matrix；
- 核心 schema 使用 `BaseModel` 还是 Pydantic dataclass；首选 `BaseModel`，但以 spike 的
  schema/error/import 证据确认；
- 哪些 component settings types 属于稳定 public API，哪些保持 internal；
- legacy uppercase keys 的兼容时长和最终移除版本；
- `LoadedConfig` 最终公开 flat compatibility view、nested core view，还是两者中的一个；
- 是否有真实消费者足以批准 versioned JSON Schema export 或 editor integration。

## 与现有 TODO 的关系

- [hierarchical CAE](20260827_082608_hierarchical-cae-rawdata-surrogate.md)、
  [posterior calibration](20260827_082609_coherent-posterior-sampling-calibration.md) 和
  [qNEHVI strategy](20260827_082611_qnehvi-acquisition-strategy.md) 继续按各自 gate 和 benchmark
  权限推进；本文不授权运行 simulator 或 formal benchmark。
- 若这些模块在本文 Gate 2 前完成，先保留其当时 factory/config 合同，待本 TODO 实施时做
  source-compatible 迁移。若 Gate 2 已完成，则新模块直接采用 component-owned settings。
- [持续 reliable recording 检查](auto/20260815_170021_check-reliable-recording-consistency.md)
  只有在实施进入 recorder/session 配置时才自然触发；配置重构不得改变 backpressure、
  boundary durability 或 fatal writer failure。
- 本文是纯未来计划，不改变当前
  [config blueprint](../blueprints/10_modules/config.md) 或当前 architecture。实际 gate 改变
  代码/合同后，必须同步维护对应当前文档，不能让本文覆盖 current truth。

## 完成规则

只有同时满足以下条件，本 TODO 才可移入 `dev_doc/obsolete/`：

- 核心配置的 default/type/basic constraint 不再由互相独立的中央 lists/branches 重复声明；
- 算法和 surrogate 专用 settings 由其 module/factory 所有，运行时获得窄 immutable snapshot；
- 新增一个新算法模块不需要编辑中央 `config.py` 来登记其专用参数；
- 当前 package/workspace/override precedence、provenance、path、安全、generation reload 和
  campaign-frozen contracts 全部通过 parity tests；
- legacy 配置要么仍在有时限的兼容窗口内且有完整 warning/docs，要么已经经过单独批准的
  迁移移除；
- semantic identity/checkpoint namespace 只对真实语义变化敏感，并保留 source fingerprint
  分离；
- Pydantic direct dependency 的平台、artifact、import、安装和完整 installed-wheel suite
  已验收；
- architecture、blueprints、terminology、user docs、workspace template、tests 和 change
  records 与最终实现同步；
- 若仅完成部分 gates，把剩余工作拆成新的 standalone TODO 并记录依赖，不得把未完成范围
  随本文一同归档。
