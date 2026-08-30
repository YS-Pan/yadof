# 在第二个真实实现出现时提炼 Acquisition Capability Protocol

## 状态与触发条件

- 本文是手动待执行的架构 handoff，不代表已经批准修改当前代码或引入第二种 acquisition。
- 当前用户没有近期增加第二种 acquisition/search backend 的计划，也暂不面向第三方组件作者。
  因此本 TODO **现在只记录技术债，不实施 Protocol**。
- 2026-08-29 用户暂停抗噪声 Hierarchical CAE 扩展，并明确它不是基础 Hierarchical CAE 的
  验收指标或 blocker；当前 Hierarchical CAE 将
  `frequency` 数据筛选设为显式 opt-in、默认 `none`，都属于 surrogate 侧的优先级或组件
  边界变化；它们既不是第二个 acquisition，也没有证明真实调用方被 qNEHVI 具体类型阻塞，
  因而不触发本文。
- 只有满足以下任一条件后才开始实施：
  1. 一个有明确用途、算法语义和验收标准的第二种 acquisition 已获批准；
  2. 一个真实调用方已经被当前 qNEHVI 具体类型依赖阻塞，并能提供与 qNEHVI 共同需要的
     最小能力证据。
- 不得仅因本文存在、代码看起来可以抽象，或为了未来可能的 GUI/插件而提前启动。
- [EHVI/qNEHVI TODO](20260828_121904_surrogate-qnehvi-remaining-work.md)
  可以在只有 qNEHVI 一个真实 acquisition 的情况下继续保持 fail-closed/full-real fallback；
  基础 Hierarchical CAE 的独立科学验收、抗噪声扩展状态与本文的架构触发条件三者相互独立。

## 当前证据与问题

- `PosteriorAssistedStrategy` 当前把 `acquisition` 标注为
  `DiscreteQNEHVIAcquisition`，并在构造阶段用具体 `isinstance` 检查拒绝其他实现。
- 该策略实际需要的是“根据一个 generation 的真实 baseline 和联合 posterior objective
  samples，从有限候选池中选择 batch”的能力；但当前唯一实现恰好是离散 qNEHVI。
- `DiscreteQNEHVIAcquisition` 的 reference point、finite-support policy、draw support、
  qLogNEHVI backend diagnostics 和 multi-start greedy selection 都可能是 qNEHVI 专用语义，
  不能在没有第二个实现证据时宣称为通用 acquisition 契约。
- 当前具体依赖是真实的模块边界技术债，但只有一个实现时不是功能阻塞。现在抽象会增加一个
  需要维护的接口，并可能把错误边界和数据形状冻结在错误层级。

## 目标

当第二个真实实现到来时：

1. 让 `PosteriorAssistedStrategy` 依赖最小 acquisition capability，而不是依赖
   `DiscreteQNEHVIAcquisition` 具体类。
2. 让 qNEHVI 和第二个实现各自拥有专用 settings、校验、backend 和 semantic identity；
   通用协议只表达调用方实际共享的能力。
3. 保留 workspace 在 `submit/optimization.py:build_optimization()` 中的显式组合、generation
   snapshot、真实 evaluator、完整 real-search fallback 和 recorder 边界。
4. 保持 protocol 与配置实现无关：不得要求 Pydantic model、dataclass、全局配置对象或
   backend 类型穿过能力边界。

## 提炼原则

### 从两个实现反推最小接口

- 先实现或完整设计第二个 acquisition 的真实调用路径，再列出两个实现共同消费的输入、
  共同返回的结果、共同失败语义和共同 identity 需求。
- 只有两个实现都必需的概念才进入 protocol。qNEHVI 独有的 reference point、BoTorch
  device、finite empirical support 和 restart 参数继续留在 qNEHVI settings/identity 中。
- 不为 EI、UCB、Thompson sampling 等尚未批准的算法写 placeholder 实现或假想方法。

### 候选接口形状仅作为待验证草图

执行时可以从以下形状开始比较，但不得把名称或字段直接视为已批准 API：

```python
class Acquisition(Protocol):
    def select_batch(self, context: AcquisitionContext) -> AcquisitionResult:
        ...
```

- `AcquisitionContext` 只应携带完成一次选择所需的 immutable、backend-neutral 数据；其字段
  必须从两个真实实现的共同需求得出。不要把完整 `LoadedConfig`、workspace、recorder、
  evaluator 或 surrogate trainer 放入 context。
- `AcquisitionResult` 至少要让调用方取得选择结果，并允许有限、JSON-safe 的诊断；是否返回
  candidate indices、rows 或稳定 candidate IDs 由第二个实现和现有池语义共同决定。
- `validate(...)`、`semantic_identity(...)` 或 generation binding 只有在两个实现确实共享相同
  生命周期后才加入 protocol。否则由组合层分别调用具体组件的现有窄接口。
- 可以使用 structural `typing.Protocol`；若确有运行时检查需求，可以使用
  `@runtime_checkable`。不得再用对 qNEHVI 具体类的 `isinstance` 作为能力判断。

### 输入、结果与错误边界

- 输入必须保留联合 posterior draw 的 candidate/objective 对齐，不能降级为均值、逐候选
  独立噪声或逐目标重排。
- 输出必须验证 batch 大小、candidate 范围、唯一性和确定性 seed 语义。诊断保持有界且
  JSON-safe；predicted rawData 不得出现在返回结果、history、recorder 或持久 metadata 中。
- 只有两个实现都共享的错误类别才进入 acquisition-neutral boundary。qNEHVI 的 support
  fallback/reject 或 backend 专用错误可以先由其 adapter 映射为 strategy 已有的 soft
  fallback / hard stop 语义，不能为了统一名字而改变行为。
- real evaluation、finalization 和 recording 仍在 acquisition 调用之外；acquisition 永远不能
  直接接受预测结果为 durable evidence。

## 兼容与迁移约束

- 保持现有 workspace 写法 `posterior_assisted(..., acquisition=qnehvi(...))` 可用；
  `qnehvi()` 仍是公开 factory，`DiscreteQNEHVIAcquisition` 仍可作为其具体实现。
- 先添加针对 capability 的契约测试，再替换 `PosteriorAssistedStrategy` 的具体类型标注和
  `isinstance` 检查。
- 纯接口重构且算法行为未变时，现有 qNEHVI semantic identity、strategy signature、
  checkpoint namespace、真实 history 和 fallback 结果不得改变。
- 初期 protocol 可以是 package-internal contract。用户暂不面向第三方组件作者，因此不要
  提前承诺长期公共扩展 API、版本兼容窗口或自动 discovery。
- 不建立全局 acquisition registry、字符串 selector、entry-point plugin graph 或 service
  locator。workspace factory 继续显式实例化和组合组件。
- Protocol 不依赖 Pydantic。若组件 settings 未来选择 dataclass、Pydantic 或其他内部实现，
  都不得泄漏到 capability contract。

## 非目标

- 现在实现 Protocol 或虚构第二种 acquisition。
- 把 qNEHVI 专用字段重命名后当成通用 acquisition 参数。
- 同时抽象 search、candidate pool、posterior、pending points、outcome constraints 或连续
  acquisition optimization。
- 修改 GPSAF、real-search、surrogate calibration、真实 evaluator 或 recorder 语义。
- 为未来 GUI 暴露 Python implementation type；GUI 仍应通过稳定的 CLI/JSON 边界消费能力。
- 借本 TODO 推进配置重构、引入 Pydantic 或删除 legacy config keys。

## 实施步骤（触发后）

### Gate 0：第二实现与共同需求 inventory

- 写清第二个 acquisition 的真实用途、objective/candidate/posterior 要求、fallback、seed、
  optional dependency 和验收场景。
- 对 qNEHVI 和第二实现逐项比较输入、输出、校验、identity、错误、诊断和生命周期。
- 标出 shared、qNEHVI-only、second-only、strategy-owned 四类职责；存在争议的字段不进入
  protocol。

### Gate 1：最小 contract 与适配

- 定义最小 context/result DTO 和 structural protocol，保持 import 轻量且 backend-neutral。
- 让 qNEHVI 通过薄 adapter 或自然 structural conformance 满足协议，不移动其数值循环、
  support policy 或 backend ownership。
- 实现第二个真实 acquisition；禁止只用 mock 证明所谓通用性。

### Gate 2：组合层迁移

- 把 `PosteriorAssistedStrategy` 的 concrete annotation/check 替换为 capability validation。
- 保持显式 workspace factory 注入、generation snapshot、semantic identity 和完整 real-search
  fallback。
- 若第二 acquisition 不适合现有 `PosteriorAssistedStrategy` 的算法语义，应建立另一个组合
  strategy，而不是不断扩大一个假通用 context。

### Gate 3：文档与发布边界

- 更新 architecture、optimize/file blueprints、terminology、user docs 和示例，使当前实现与
  文档一致。
- 只有确认第三方扩展场景、稳定性承诺和兼容策略后，才把 protocol 提升为明确 public API。
- 按届时开发指南完成 wheel、force reinstall、import-origin、focused tests 和 full suite。

## 验证矩阵

- qNEHVI 默认值、显式参数、selection、diagnostics、support fallback/reject、seed 和 semantic
  identity 与迁移前一致。
- 第二个真实实现通过其算法数值与端到端验收，不以 mock-only conformance 代替。
- spy/fake strategy test 证明组合层只依赖 protocol 能力，并且没有 qNEHVI concrete
  `isinstance`、字段探测或 backend import。
- 两个实现均拒绝 invalid batch size、越界/重复选择、非有限输入和不满足自身 capability 的
  problem shape，错误能映射到既定 soft fallback 或 hard stop。
- selected candidates 全部进入 common real evaluator；predicted rawData/cost samples 不进入
  recorder、history 或 checkpoint。
- ordinary `import yadof.optimize` 不加载 Torch、BoTorch 或其他第二 backend 的可选依赖。
- 接口字段审计能为每个字段指出两个真实消费者；无法证明者从 protocol 移回具体实现或
  strategy。

## 完成规则

- 至少两个获批准、经过真实验收的 acquisition 实现共同支持一个最小 capability contract。
- `PosteriorAssistedStrategy` 不再依赖 qNEHVI 具体类型，同时没有扩大其算法职责。
- qNEHVI 行为、identity、fallback、checkpoint/history 和 optional-import 回归全部通过。
- architecture、blueprints、terminology、用户文档与 installed-wheel tests 已同步，随后将本文
  移入 `dev_doc/obsolete/todo/`。
- 如果第二个真实实现尚未出现，本文继续保持 active；不得仅因时间经过或完成接口草图而
  宣称完成。
