# 直接迁移到声明式核心配置与组件自有 Settings

## 状态与背景

- 本文是待执行的架构重构 handoff，不代表当前运行时、配置格式或 public API 已经改变。
- yadof 已完成优化算法模块化：workspace 通过
  `submit/optimization.py:build_optimization()` 显式组合完整策略，package 不再用中央字符串
  selector 选择算法。hierarchical CAE、posterior calibration、qNEHVI、PCA/SVD baseline 等
  新模块也已经或计划沿用该组合边界，未来还会继续增加组件。
- 当前 `yadof.config` 仍集中拥有 package defaults、全部合法 uppercase 字段名、类型/范围
  分类和专用校验。pymoo、GPSAF、conditional-INR 等组件同时在自己的 runtime、factory 或
  dataclass 中保留默认值与 fallback，形成多点修改和默认值漂移风险。
- 计划阶段核查到 `src/yadof/config.py` 约 495 行。当前需要从中央配置拆分或重新归类的设置
  至少包括：
  - 9 个 optimize/search-related 设置：reference-direction、refill、archive precision、
    crossover 和 mutation；其中 archive precision 同时被 posterior-assisted 路径消费，不能
    未经 Gate 0 就断言为 pymoo-only；
  - 4 个 GPSAF 设置：alpha、beta、gamma 和 exploration fraction；
  - 17 个 `SURROGATE_INR_*` 设置。
  这些数量只是 2026-08-28 的 inventory 证据；实施时必须从当前代码重新生成完整 owner/
  consumer 表，不能把数量视为永久契约。
- 当前 drift 不是纯理论问题。例如中央默认的 crossover probability/eta 为 `0.85/10.0`，
  pymoo backend 的局部 fallback 仍出现 `0.8/20.0`；conditional-INR 也同时存在中央配置与
  `INRTrainConfig` 默认值。正常路径未必触发所有 fallback，但新增模块会继续放大漂移风险。

## 用户已确定的产品决定

以下决定来自用户，不留给实施者重新选择：

1. **不兼容仓库外 workspace。** 本次迁移允许删除旧的 algorithm-specific uppercase keys；
   无需 deprecation window、legacy adapter、alias 或自动 workspace 改写。
2. **算法参数只有 factory 入口。** 不保留通过 CLI/API temporary config override 覆盖算法
   参数的能力；用户要改变算法参数时，直接编辑 `submit/optimization.py`。
3. **factory 保持 generation 热重载。** `optimization.py` 在 generation snapshot 中重新加载，
   factory 为该 generation 构造一次 immutable component/strategy；generation 内不得再次读取
   mutable source。
4. **`OPTIMIZE_SURROGATE_MAX_TRAINING_LAG` 是 campaign policy。** 它继续由核心配置拥有，
   而不是复制到每个 surrogate factory。除非实施时发现当前合同另有冻结要求，它继续遵循
   generation-scoped core config reload，而不是因“campaign policy”一词自动变成 session-frozen。
5. **Settings implementation 保持内部。** 面向 workspace author 的稳定 surface 是带明确
   关键字参数的 factory，不公开内部 settings dataclass 作为承诺兼容的高级 API。
6. **输入转换保持窄且显式。** 不提供任意字符串到数字、bool/int 混用或 backend object
   coercion；每个 factory 只做其字段文档明确允许的 normalization。
7. **NumPy scalar 不是正式公共输入。** 调用者应先转换为普通 Python scalar；实现可以偶然
   接受，但不得形成测试保证或兼容承诺。
8. **当前不引入 Pydantic。** 现阶段没有真实 JSON Schema/editor/plugin 消费者，未来 GUI
   主要是 CLI 外壳；Pydantic 对本重构的额外收益不足以抵消 core dependency、安装 artifact、
   import、升级和行为耦合成本。
9. **暂不面向第三方组件作者，也没有近期第二种 acquisition/search backend。** 不为假想插件
   建 registry、entry points、通用 settings 基类或提前冻结公共扩展协议。

## 目标

1. 一个核心配置项的默认值、类型、基础约束、路径/reload/provenance metadata 尽量只有一个
   权威声明位置。
2. 核心配置只拥有跨任务、跨算法成立的 framework/campaign policy；算法数学、backend
   tuning 和 surrogate 训练参数由对应 component/factory 拥有。
3. 新增一个算法或 surrogate 时，只需新增该模块的内部 immutable settings、显式 factory
   参数、实现、测试和文档，不再编辑中央 `config.py` 登记专用 uppercase keys。
4. 组件 runtime 获得自己的窄 immutable settings snapshot，不读取完整 `LoadedConfig` 来
   搜索算法参数。
5. 保留现有核心 config 的成熟能力：显式 workspace、默认值/工作区/API-CLI override
   precedence、逐来源 eager validation、provenance、路径隔离、generation reload，以及明确
   session-frozen 的 recorder policy。
6. 保持 ordinary import 轻量；settings 声明不得导入 Torch、BoTorch、pymoo 算法对象或
   其他 optional numerical backend。

## 目标所有权

### 核心 `yadof.config`

核心配置继续拥有真正跨 component 的 framework/campaign policy，包括：

- workspace/framework paths；
- history、reliable recorder 和 session publication policy；
- fast/local/distributed evaluation 与公共 resource policy；
- HTCondor transport、timeout、retry 和 request policy；
- campaign 通用控制，例如 population size、random seed、smoke-test policy；
- surrogate 训练协调中的公共 maximum training lag；
- logging/progress 以及经 inventory 证明跨全部实现共享的调度边界。

核心 uppercase surface 可以继续支持
`package defaults < workspace config.py < API/CLI temporary override`。这套 precedence 和
`source_for()`/`describe()` provenance 只适用于核心设置，不再被用作算法参数的第二入口。

### Component/factory settings

以下设置由对应 module package 的内部 frozen settings 和 factory 拥有：

- `pymoo_ga()`/`pymoo_nsga3()`：crossover/mutation probability、eta、每个 individual 的
  mutation dimension 数、refill attempts，以及 NSGA-III reference direction
  method/partitions；
- `gpsaf()`：alpha、beta、gamma、exploration fraction；
- `conditional_inr()`：网络结构、epochs、ensemble、batch、optimizer/loss、query chunk/
  sample budget、bootstrap 等当前 `SURROGATE_INR_*` 参数；
- hierarchical CAE、posterior calibration、qNEHVI、PCA/SVD 及未来组件的专用数学/backend
  参数。

`SURROGATE_CONSTANT_ATOL`、`SURROGATE_TARGET_SCALE_FLOOR`、
`SURROGATE_RELATIVE_ERROR_EPS`、`SURROGATE_MAX_NONFINITE_FRACTION`、
`SURROGATE_TORCH_DEVICE` 和 `OPTIMIZE_ARCHIVE_KEY_DECIMALS` 等跨 consumer 或不带具体实现名
的现有字段，必须在 Gate 0 按真实 consumer 分类：

- 若它控制的是一个 component 的数学、训练或 backend 行为，移入该 component；
- 若它真的是所有 surrogate 共享且由 framework 统一执行的资源/调度 policy，保留为核心；
- 不能仅因名字较通用就留在中央，也不能为了减少中央字段而复制进每个 component。

## 不使用 Pydantic 的实现方向

### 核心声明式 schema

- 使用标准库构建一个小型 immutable `SettingSpec`（或同等窄结构），集中声明 core setting
  的 name、default、normalizer/validator、reload policy、path policy、provenance/describe
  metadata。
- `DEFAULT_CONFIG`、合法字段集合、类型分类和通用 validator 应从同一组 specs 派生，逐步
  删除当前互相独立的 `_DEFAULT_ITEMS`、`_*_NAMES` 和专用分支重复。
- 复杂 cross-field rule 使用明确命名的普通函数，靠近最小 owner；不要把所有规则重新聚成
  一个巨型 `validate_everything()`。
- 继续由 yadof loader 执行 workspace `config.py`、逐层验证、merge、provenance、path
  resolution 和 `LoadedConfig` publication。`SettingSpec` 不是 environment loader、DI
  container 或持久化协议。
- 保留稳定的 `ConfigError` 边界；内部 helper/dataclass 的异常布局不成为公共合同。

### 内部 component settings

- 每个 component 使用 module-local `@dataclass(frozen=True, slots=True)` 或同等标准库
  immutable value object。嵌套序列/映射在构造时复制成 tuple、frozenset 或只读映射，不能
  把调用方的可变引用放进 semantic identity。
- workspace author 只调用带明确 keyword-only 参数的 factory。不要暴露 `settings=` 双入口，
  不接受 unrestricted `**kwargs`，也不要求用户 import 内部 settings type。
- Factory 在构造时完成 normalization、default validation 和同一 component 内的 cross-field
  validation；错误必须指出 factory、字段、收到的值和约束。
- Component 的 runtime、trainer、scheduler 和 backend 接收其 settings 或明确拆出的窄值；
  不在运行中通过 `getattr(config, "ALGORITHM_KEY", fallback)` 重新建立隐式配置源。

目标 workspace 形状类似：

```python
def build_optimization():
    search = by_objective_count(
        single=pymoo_ga(
            crossover_probability=0.85,
            mutation_probability=0.35,
        ),
        multi=pymoo_nsga3(
            crossover_probability=0.85,
            mutation_probability=0.35,
            reference_direction_method="das-dennis",
            reference_direction_partitions=None,
        ),
    )
    surrogate = conditional_inr(
        epochs=32,
        ensemble_size=3,
        batch_size=16,
    )
    return gpsaf(
        search=search,
        surrogate=surrogate,
        alpha=3,
        beta=3,
        gamma=0.5,
        exploration_fraction=0.10,
    )
```

示例值表达当前默认迁移方向，不是批准更改算法默认值。最终签名和默认值必须以 Gate 0 的
source/consumer inventory 与 parity tests 为准。

## 输入、校验与不可变性规则

- bool 字段只接受普通 Python `bool`；`0/1` 整数不能冒充 bool。
- integer 字段接受普通 Python `int` 但拒绝 bool，并执行正数/非负数/范围约束。
- real 字段可以接受普通 Python `int`/`float` 并规范化为 float，但拒绝 bool、NaN 和 infinity。
- enum/mode 字段只接受文档列出的普通 Python 字符串或明确公开的 enum，不做模糊大小写/
  别名猜测，除非该字段已有必须保留的当前合同。
- sequence/mapping 只在字段明确允许时复制并冻结；不提供全局“任何 iterable 都可用”的
  coercion。
- `Path`/`os.PathLike` normalization 只属于声明为 path 的核心字段；component 不借此读取
  workspace 隐式路径。
- 不正式支持 NumPy scalar、Torch scalar、字符串数字或其他第三方 scalar。调用者负责显式
  转换。
- default 自身必须经过与显式输入相同的 validation；不能因为默认由 package 提供就绕过
  cross-field invariant。

## Generation reload 与状态 identity

- 每个 generation 继续同时冻结 core config 和完整 task source snapshot，并从当前 snapshot
  fresh-load `submit/optimization.py:build_optimization()`。
- Factory 参数修改只影响下一 generation；已经构造的 generation component/settings 不可变。
- 不增加算法参数的 CLI/API override channel，也不把 factory kwargs 镜像回 core config。
- 核心 temporary overrides 继续只处理核心设置。调用者传入已删除的 algorithm key 时应按
  unknown core setting 失败，而不是静默忽略或动态编辑 `optimization.py`。
- 每个 component 定义显式、版本化、JSON-safe 的 semantic payload；只包含真正改变算法
  数学、训练/推理、schema 或 state 兼容性的 resolved settings。
- population size、random seed、maximum training lag 等仍可能影响 strategy/state identity，
  但由组合层以明确 campaign-policy block 加入；不要求 component 为获得这些值读取完整
  `LoadedConfig`。
- 不直接 hash `dataclasses.asdict()` 的全部结果。runtime budget、日志、path、provenance 和
  诊断字段按真实语义处理；source fingerprint 与 deterministic semantic signature 继续分离。
- 纯所有权迁移且行为/默认值未变时，现有策略 signature、checkpoint namespace 和恢复结果
  应保持一致。若更正已证实的默认值 drift 会改变行为，必须作为明确 behavior change 单独
  记录和验收，不能伪装成机械重构。

## 直接迁移政策

本任务采用一次性 cutover，而不是兼容迁移：

1. 先在同一工作分支建立 factory settings、窄 runtime 传递和 parity tests。
2. 同步迁移 package default workspace template、仓库内 examples、benchmark baselines/
   preregistrations、测试 fixtures 和文档中的所有 algorithm-specific uppercase keys。
3. 在同一完整验收单元中从 `config.py` defaults、合法字段集合、validator 和 consumer 中删除
   对应 keys；旧 key 随后成为 unknown config setting。
4. 不实现 legacy-key-to-factory mapping、warning、alias、`UNSET`、legacy/new conflict
   precedence 或自动 source rewrite。
5. 不保证仓库外 workspace 无修改继续运行。发布/变更记录必须给出 old-key 到新 factory
   kwarg 的完整人工迁移表，让用户可以明确编辑 `optimization.py`。
6. 核心 config 的现有 uppercase keys、precedence、provenance 与 temporary overrides 不因
   algorithm cutover 被删除。

## 实施阶段与 Gates

### Gate 0：完整 inventory 与 owner 表

- 重新清点当前 `config.py` 的全部字段、default、validator、consumer、source/reload policy、
  CLI/API override use、semantic identity 和 checkpoint/scheduler 影响。
- 为每个字段标记 `core-campaign`、具体 component、共享 service 或待证据决定，并为每个分类
  指出直接 consumer；不按名称猜 owner。
- 固定迁移前 behavior fixtures，覆盖默认值、explicit factory 等价值、invalid input、core
  precedence/provenance/path、generation reload、session-frozen recorder policy 和 state
  identity。
- 明确所有仓库内 workspace/config 位置以及 benchmark preregistration 的 immutable/hash
  约束。任何冻结 benchmark 输入需要新 preregistration 或批准时，不得原地改写以伪造旧
  evidence。

### Gate 1：内部 settings 与 factory contract

- 建立共享的最小标准库 validation helpers，但不建立所有 component 必须继承的 settings
  base class。
- 先将 conditional-INR 当前双重 default/config mapping 收敛到 module-local frozen settings，
  为 `conditional_inr()` 添加显式 keyword-only 参数并窄传给 runtime/scheduler。
- 同样为 `pymoo_ga()`、`pymoo_nsga3()` 和 `gpsaf()` 增加 component-owned settings；
  `by_objective_count()` 只组合已绑定的 search components，不重新合并配置。
- 审计当前公开的 `hierarchical_cae(train_config=CAETrainConfig(...))` surface。既定目标是
  workspace author 通过明确 factory kwargs 配置，而不是把内部 settings type 作为第二入口；
  因此在不改变 CAE 数学的前提下直接迁移该 surface，并同步其 user docs/tests。task-owned
  schema、quality policy 等有独立领域含义的 value object 不因名称相似而自动视为 settings。
- hierarchical CAE、qNEHVI 及后续模块继续直接采用 factory-owned 模式，不新增中央算法键。

### Gate 2：identity、scheduler 与 runtime 去环境化

- 移除 component 对 algorithm-specific `LoadedConfig` 属性的读取，包括 semantic identity、
  backend fallback、GPSAF phases、conditional-INR training/runtime 和 posterior adapter。
- `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG` 继续从 core campaign policy 通过窄 scheduler 参数
  传入各 surrogate；不得复制到 component settings。
- 将 population/random seed 等 generation context 值与 component settings 在组合层明确
  汇入 identity，证明所有权移动不改变真正的数学/state 边界。
- 未选择的 component 不得因其 optional dependency、validator 或 runtime requirement 失败；
  ordinary import 继续保持 backend-lazy。

### Gate 3：仓库内迁移与旧 key 删除

- 迁移 template、examples、benchmark inputs、tests 和 user-facing examples，使算法参数只在
  `submit/optimization.py` 出现。
- 从 `config.py` 删除已迁移 algorithm keys 及相关 type/name/validator branches；删除 runtime
  中已无意义的 fallback constants。
- 保留 core keys，包括 `OPTIMIZE_POPULATION_SIZE`、`OPTIMIZE_RANDOM_SEED`、
  `OPTIMIZE_SMOKE_TEST_ENABLED` 和 `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG`。
- `OPTIMIZE_ARCHIVE_KEY_DECIMALS` 按 Gate 0 证据只保留一个 owner：若它是跨 strategy 的
  candidate-identity campaign policy 就留在 core；若它属于组合/search 行为就迁入对应
  factory。不得在 core 与多个 factories 中复制同一默认值。
- 增加 focused tests，证明旧 algorithm uppercase keys 被明确拒绝、core override 仍有效、
  编辑 `optimization.py` 在下一 generation 生效且 generation 内一致。

### Gate 4：核心声明式 schema 收敛

- 用 `SettingSpec` 或等价标准库声明生成 core defaults、合法字段集合、基础 validation 和
  describe metadata。
- 保留逐 source layer validation，避免低优先级非法值被高优先级 override 掩盖。
- 保留 `LoadedConfig` 的 immutable lookup/attribute、`source_for()`、`describe()` 和
  `WorkspaceContext` 行为，除非另有显式 API 变更批准。
- 删除已经由单一声明派生的中央平行 lists/branches；用 cross-field tests 锁定 path overlap、
  recorder budget 和 backend policy。

### Gate 5：文档与 installed-package 验收

- 更新 architecture、config/optimize/surrogate module 与 file blueprints、terminology、
  user docs、workspace template 和 API examples。
- 在 user docs/change record 提供完整 old-key 到 factory kwarg 的一次性迁移表，但不实现
  runtime compatibility。
- 按届时 `dev_doc/README.md` 完成 wheel build、force reinstall、import-origin、artifact
  membership、focused tests 和 full suite；不得用 editable install/PYTHONPATH 验收。

## 验证矩阵

### Core config

- package/workspace/temporary override precedence、每个有效值的 provenance 和 invalid lower
  layer rejection；
- unknown uppercase、bool/int、finite real、fraction/bounds、mode、sequence 和 PathLike；
- relative/absolute path、path overlap、双 workspace 隔离和 config exception/SystemExit；
- generation-hot core policy 与 session-frozen recorder path/capacity 的构造时机不变；
- core `DEFAULT_CONFIG`、`LoadedConfig` lookup、`source_for()` 和 `describe()` 保持一致。

### Components

- 每个 factory 默认值与迁移前有效默认行为一致；显式传入旧值产生等价 identity/runtime；
- invalid factory input 在构造阶段失败，错误包含组件、字段和值/约束；
- component 只收到自己的 immutable settings，不读取 ambient algorithm config；
- factory 修改只在下一 generation 生效，同一 generation 的 validate/identity/run 使用同一
  resolved settings；
- Pymoo GA/NSGA-III、GPSAF、conditional-INR、posterior adapter 和 scheduler 的 existing
  focused regressions 全部通过；
- semantic identity 对字段顺序和等价 immutable input 稳定，对真实数学变化敏感，对
  path/log/provenance 等非语义变化不误失效；
- strategy switch、retained inactive artifacts、checkpoint recovery 和每 workspace 最多一个
  trainer 的约束不变；
- ordinary `import yadof.config/optimize/surrogate` 不加载 Torch、BoTorch 或 pymoo algorithm。

### Direct cutover

- 所有仓库内 workspace/template/example/benchmark/test 已迁移，仓库搜索不再发现已删除 key
  的活动使用；历史 change records/obsolete 文档可以保留原文。
- 旧 algorithm key 在 workspace config 或 temporary override 中给出 actionable unknown-setting
  错误；不存在 warning-only、silent ignore 或双入口 precedence。
- 核心 temporary override 继续工作；没有通过该入口改变 component settings 的旁路。
- `optimization.py` factory kwargs 是算法参数的唯一 workspace source，完整 strategy source
  snapshot/provenance 继续记录。

## GUI 与机器可读接口边界

- 当前不增加 JSON Schema、form schema 或新的 CLI config-edit API。未来 GUI 作为 CLI 外壳，
  若要改变算法参数，应明确编辑/生成 workspace `submit/optimization.py`，而不是恢复一套
  algorithm override 配置。
- 核心 `SettingSpec` 可以为现有 `describe()` 或未来版本化 CLI JSON 提供 metadata，但只有
  真实 GUI/editor 消费者获批后才设计该输出协议。
- 如果未来出现自动表单、外部 plugin settings、深层嵌套外部 config 或大量结构化错误消费，
  可以在独立决策中重新评估 Pydantic。届时它只能是内部实现选择，不能改变本 TODO 的
  ownership、factory-only 和 generation-binding 边界。

## 成本与风险

- 这是中等规模的多模块 breaking refactor，不是删除 `config.py` 若干行即可完成；runtime、
  scheduler、identity、template、benchmark 和 tests 必须同步迁移。
- 仓库外 workspace 会在旧 key 上失败，这是用户明确接受的 tradeoff；清晰迁移表仍是必要
  文档，而不是兼容承诺。
- factory source 成为算法参数唯一入口后，失去临时 per-run override 是有意设计；不得在
  CLI 或 hidden kwargs 中悄悄重建第二入口。
- dataclass `frozen=True` 只提供浅层不可变，嵌套 mutable input 必须复制冻结。
- 过度通用的 validation helper 会重建中央巨型 schema；共享 helper 只处理稳定、无 owner
  争议的 primitive checks。
- 所有权移动容易意外改变 semantic identity。迁移必须比较 resolved payload，而不是只比较
  class/field 名称或序列化格式。
- benchmark 的 tracked preregistration、hash 或已产生 evidence 可能禁止原地修改；Gate 0
  必须区分可迁移模板与不可改历史输入。

## 非目标

- 不引入 Pydantic、pydantic-settings、Hydra、OmegaConf、YAML/TOML config groups、环境变量
  settings 或 multirun。
- 不保留 algorithm legacy uppercase aliases、compatibility window、deprecation warnings、
  `UNSET` conflict resolution 或自动 workspace migration。
- 不公开内部 Settings model，不保证第三方 subclass/plugin compatibility。
- 不建立算法 registry、entry-point discovery、service locator 或第二个 complete-method
  selector。
- 不改变 conditional-INR/GPSAF 数学、新 CAE/qNEHVI/PCA benchmark 结论、recording durability、
  checkpoint artifact schema 或默认 optimization composition。
- 不把 task-owned parameter、rawData schema、simulator/project、objective/cost policy 或
  physics-specific settings 移入 package config。
- 不把 settings dump、source map、predicted rawData 或 GUI form state 变成 durable truth。

## 与现有 TODO 的关系

- [hierarchical CAE](20260827_082608_hierarchical-cae-rawdata-surrogate.md)、
  [posterior calibration](20260827_082609_coherent-posterior-sampling-calibration.md)、
  [qNEHVI strategy](20260827_082611_qnehvi-acquisition-strategy.md) 和
  [PCA/SVD baseline](20260828_081523_pca-svd-baseline-surrogate-module.md) 继续按各自 gate 与
  benchmark 权限推进；本文不授权 simulator 或 formal benchmark。
- 新模块从现在起应优先使用 internal frozen settings + explicit factory kwargs，不新增中央
  专用 uppercase key；这只是避免扩大待迁移面，不自动触发本文完整重构。
- [Acquisition capability protocol](20260828_091749_acquisition-capability-protocol.md) 仍等待
  第二个真实 acquisition/consumer，不因 settings 重构而提前实施。
- [持续 reliable recording 检查](auto/20260815_170021_check-reliable-recording-consistency.md)
  只有在实施真正触及 recorder/session 配置时才可能由其 bounded trigger 条件命中；本计划
  不改变 recording contract。
- 本文是未来计划，不覆盖当前
  [config blueprint](../blueprints/10_modules/config.md) 或 architecture。实际实施改变代码合同后，
  必须同步维护 current-view 文档。

## 完成规则

只有同时满足以下条件，本 TODO 才可移入 `dev_doc/obsolete/`：

- 核心配置 default/type/basic constraint 不再由互相独立的中央 lists/branches 重复声明；
- algorithm/surrogate settings 由其 module/factory 所有，runtime 接收窄 immutable snapshot；
- 新增一个模块不需要编辑中央 `config.py` 登记专用参数；
- 旧 algorithm uppercase keys 已从活动代码、模板、仓库内 workspace 和 tests 删除，并被
  unknown-setting tests 明确拒绝；
- component 参数只有 `optimization.py` factory 入口，核心 temporary override 无旁路；
- `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG` 仍作为 core campaign policy 工作；
- core precedence、provenance、path、安全、generation reload 与 session-frozen contracts
  全部通过 parity tests；
- semantic identity/checkpoint namespace 只对真实语义变化敏感，并保持 source fingerprint
  分离；
- ordinary import、optional backend lazy loading 和完整 installed-wheel suite 通过；
- architecture、blueprints、terminology、user docs、workspace template、tests、迁移表和
  change records 已同步；
- 若只完成部分 gates，剩余工作必须留在本文或拆成新的 standalone TODO，不能把未完成范围
  一同归档。
