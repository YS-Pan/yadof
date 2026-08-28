# 将 benchmark 收敛为通用模块化算法比较器

## 文档角色

这是一个根级手动待办。只有用户明确要求执行本文件时，才允许据此修改、删除或移动 benchmark 文件；创建本文件本身不授权启动仿真、运行 benchmark campaign 或读取受保护数据。

本任务的目标不是给现有结构增加一层包装，而是让活动工具只呈现一套职责清楚、可以直接解释的设计。Git 与已经生成的 run 保存历史；活动源码、路径、接口、字段、命令帮助和当前视图文档不承担历史讲解，也不保留代际编号、替代入口、别名、双读逻辑或历史回放分支。

## 已确认问题

当前 `src/yadof/benchmark_automation/` 将多种不同性质的内容放在同一产品目录中：

- 根目录同时存在命令入口、中心配置、专项运行器、数据集配置、使用说明和局部代理说明。
- `benchmark.toml` 重复描述 baseline 自己已经拥有的信息，新增 baseline 或算法时容易形成第二个注册点。
- `strategy_templates/` 把算法知识复制进 benchmark，使 benchmark 开始组装、命名和分类 yadof 算法。
- `benchmark_runtime/results.py` 假设比较对象具有固定角色，并把特定算法的诊断写进通用报告路径。
- `benchmark_runtime/execution.py` 和专项运行器根据算法类别分支，导致每加入一种算法都可能改动调度器。
- 计划阶段检查的 workspace 与实际单元运行时覆盖策略后的 workspace 不是同一个物化对象。
- resume 同时依赖 run 内快照和当前 checkout 中的配置，恢复语义不是单一来源。
- 仓库内保存了属于具体研究计划、回执、历史快照和专项验证的材料，使工具目录兼任研究档案库。
- `benchmark_core.py` 通过私有符号和动态导出拼接内部实现，没有形成可审查的公共边界。
- 当前根入口与运行时代码约 3,135 个物理行，tests 约 2,678 个物理行；复杂度主要来自重复配置、专项分支、额外生命周期和历史读取路径。

这些问题共同造成一个错误扩展方向：算法能力越丰富，benchmark 越需要知道算法内部细节。目标架构必须反转这个依赖，只认识 yadof 的稳定运行契约和通用观测结果。

## 最终目录边界

`src/yadof/benchmark_automation/` 的顶层结构必须精确收敛为：

```text
benchmark_automation/
├── benchmark.py
├── benchmark_core.py
├── baselines/
├── benchmark_runtime/
├── dev_doc/
└── tests/
```

约束如下：

- 顶层代码文件只有 `benchmark.py` 和 `benchmark_core.py`。
- 顶层不保留 README、局部 AGENTS、中心 TOML、专项运行器或专项数据配置。
- 使用说明、架构说明和 run 格式说明统一归入 `dev_doc/`。
- baseline 的事实只由各 baseline 自己持有；顶层不再存在 baseline 注册表。
- 研究计划、研究回执、跨 run 历史快照和专项算法验证不属于 benchmark 工具产品树。
- tests 只验证通用契约，不把某一种算法的名称或内部指标固定为 benchmark 行为。

建议的 `benchmark_runtime/` 内部职责如下；实施者可在不破坏边界的前提下调整文件名，但不得重新合并成大模块：

```text
benchmark_runtime/
├── __init__.py
├── contracts.py      # 不可变输入、计划、状态和结果模型
├── baselines.py      # baseline 发现、解析和 workspace 快照
├── planning.py       # 展开运行矩阵与可比性检查
├── storage.py        # run 布局、原子写入和摘要
├── execution.py      # 单元物化、yadof check 与执行
├── progress.py       # 进度、耗时和停滞观测
└── results.py        # 通用采集、比较和报告
```

## 核心对象

### BaselineManifest

每个 `baselines/**/baseline.json` 是该 baseline 的唯一声明，至少描述：

- 稳定 `id` 和显示名称；
- workspace 根目录；
- yadof 的执行方式；
- 目标、原始数据形状和可比较字段；
- 建议预算、资源等级和预期产物；
- 允许从干净 workspace 排除的标准运行时目录。

baseline 快照复制完整干净 workspace，而不是维护一张不断增长的 `include_paths` 清单。排除项只允许是缓存、临时目录和已经生成的运行产物；任何影响 yadof 行为的输入都必须进入快照。

manifest 使用稳定的格式标识表达数据类型，不把代际数字写进文件名、类型名、字段名或命令名。

### StrategySpec

算法是 benchmark 的不透明输入。一个 strategy 至少包含：

- 本次 study 内唯一的 `id`；
- 完整 `submit/optimization.py` 的来源路径；
- 可选显示名称；
- 必要时按 baseline 指定的完整策略来源。

benchmark 不维护算法注册表，不拼装 surrogate、acquisition、optimizer 等组件，不解析算法类别，不根据类名推断能力，也不接受需要 benchmark 补全的策略片段。`optimization.py` 通过 yadof 公共工厂和模块化组件自行定义完整算法。

### StudyRequest

一次研究请求由 benchmark 目录之外的 TOML 文件或 Python API 提交，并映射到同一个不可变 `StudyRequest`：

- baseline 选择；
- 任意数量的 strategy；
- seed 集合；
- 统一预算和公开的资源限制；
- 可选 reference arm；
- fail-fast 策略；
- run 输出根目录。

外部 TOML 是一次研究的输入，不是工具的中心配置。计划创建后，规范化请求和完全展开的运行矩阵写入 run，自此不再读取原请求文件。

### RunSpec 与 RunState

- `RunSpec` 是冻结事实：规范化请求、baseline 摘要、strategy 摘要、单元矩阵、预算、seed 和 driver 摘要。
- `RunState` 只记录可变化状态：单元状态、尝试次数、时间、退出信息和采集状态。
- 两者分开写入并使用原子替换；状态更新不得改写计划事实。
- 摘要用于来源追踪和差异说明，不作为阻止运行或恢复的哈希锁。

## 唯一执行主链

所有命令和 Python API 都必须复用下面这一条主链：

```text
发现 baseline
  → 解析 StudyRequest
  → 展开确定性 RunSpec
  → 快照完整 driver 与输入
  → 物化每个最终运行单元
  → 对该单元执行 yadof check
  → 执行 yadof
  → 采集公共结果
  → 自动生成结果文件和报告
```

具体要求：

1. preflight 必须检查已经放入目标 strategy、预算和覆盖项的最终单元，不能检查另一个 workspace。
2. plan 和 run 使用同一个 planner；run 不得再次解释输入并生成另一份计划。
3. run 创建时复制完整 driver 到 run 内，driver 包含入口、core 和 runtime。
4. resume 只读取 run 内的 `RunSpec`、`RunState`、driver 和输入快照；当前 checkout 只负责定位 run 并启动快照入口。
5. 单元状态至少区分 planned、checked、running、succeeded、failed、collected；中断后的 running 单元按明确规则恢复为可重试状态。
6. 采集与报告是成功执行后的同一生命周期步骤，不再维护独立 collect 命令和第二套状态机。
7. 进度只报告已完成数量、当前耗时和停滞信息。删除依赖跨 run 匹配的预计完成时间与 timing history。
8. 所有 subprocess 参数使用序列传递，不通过 shell 拼接；路径比较使用解析后的规范路径。

## 公共接口

`benchmark.py` 只承担 CLI 解析和用户可读错误；`benchmark_core.py` 只显式导出少量稳定 API，例如：

```python
discover_baselines(...)
load_study(...)
plan_study(...)
run_study(...)
resume_run(...)
inspect_run(...)
```

不得使用星号导入、动态导出映射或跨模块私有符号转发。runtime 模块之间通过 `contracts.py` 的公开对象协作。

CLI 保留以下职责：

```text
benchmark.py baselines
benchmark.py plan --study <path>
benchmark.py run --study <path>
benchmark.py resume --run <path>
benchmark.py inspect --run <path>
```

`plan` 是无仿真的确定性检查；`run` 创建新 run；`resume` 延续既有 run；`inspect` 只读显示状态、结果和报告位置。帮助文本只解释当前职责，不讲述被移除的命令或目录。

## 任意数量算法的结果模型

结果层按长表保存观测，每行至少包含：

- run、baseline、strategy、seed 和 budget 身份；
- 状态、耗时、评估数量和公开目标值；
- yadof 公共统计与来源摘要；
- 排除原因或失败原因。

比较分组由 baseline、seed、budget 和问题指纹确定，同一组允许任意数量 strategy。reference arm 是可选展示基准，不是固定角色；没有 reference 时仍生成完整报告。

通用报告可以计算：

- 成功率、运行时间和评估数量；
- 公开目标的绝对值；
- 相对可选 reference 的配对差值；
- seed 级配对覆盖率；
- 明确标记的不完整、失败和不可比较单元。

benchmark 不解释某个算法独有的训练损失、降维秩、代理模型误差或 acquisition 诊断。算法若通过 yadof 的命名空间元数据公开额外证据，benchmark 可以原样保留和链接，但不据此分支、排名或改变执行流程。算法内部正确性由相应模块测试或独立研究验证负责。

## Run 自包含布局

新 run 至少具有以下结构：

```text
<run>/
├── spec.json
├── state.json
├── driver/
├── inputs/
│   ├── baselines/
│   └── strategies/
├── cells/
├── results.json
├── results.csv
├── report.md
└── visualizations/
```

- `driver/` 是可直接启动的完整 benchmark driver 快照。
- `inputs/` 保存规范化后的 baseline 与 strategy 输入。
- `cells/` 保存每个运行单元的 workspace、日志和 yadof 产物。
- `results.*` 和 `report.md` 可由 run 内证据重新生成，不读取当前 checkout 的配置。
- run 内路径尽量使用相对路径，复制整个 run 后仍可 inspect 和 resume。

## 删除与归位清单

实施时删除 benchmark 顶层中不属于最终目录的所有条目，重点包括：

- 中心 benchmark TOML；
- bundled strategy templates；
- benchmark 内的 history snapshots；
- experiment runtime；
- preregistrations 与 verification；
- 根目录专项算法运行器；
- 根目录专项 representation dataset 配置；
- 根目录 README 与局部 AGENTS。

归位规则：

- 仍然有效的当前使用说明合并到 benchmark 的 `dev_doc/`。
- 当前架构事实同步到根 `dev_doc/architecture/` 和 `dev_doc/blueprints/`。
- 已完成工作的解释留在 Git 与根 change records，不复制到活动产品目录。
- 仍需执行的研究工作留在根 `dev_doc/toDo/`，其 study 文件和运行证据由研究 workspace 或用户指定的 run 根目录持有。
- 与 surrogate、降维、噪声场景相关的活动待办必须同步引用新的通用 StudyRequest 和 strategy 输入方式，不得要求把专项入口重新放回 benchmark。

## 实施顺序

### 一、锁定行为边界

- 为 baseline 发现、计划展开、最终单元检查、执行状态、恢复和 N-arm 报告写 characterization tests。
- 使用微型 fake yadof subprocess 或现有无写入测试夹具，不运行真实仿真。
- 记录当前可信 run 中需要继续可读的最小证据；活动工具不承担历史 driver 的重新执行。

### 二、建立输入与契约

- 在 `contracts.py` 定义不可变模型和边界校验。
- 将 baseline 事实移入各自 manifest，消除中心重复配置。
- 实现完整 workspace 快照和标准排除规则。
- 让 StudyRequest 同时服务 TOML 与 Python API。

### 三、建立单一 planner 与执行器

- 以确定性顺序展开任意 strategy × baseline × seed 矩阵。
- 物化最终单元后调用 yadof check。
- 写入完整 run-local driver 和输入快照。
- 实现基于 RunSpec 与 RunState 的创建、恢复和原子状态更新。

### 四、建立通用结果与 CLI

- 采集 yadof 公共输出并生成长表。
- 实现任意数量 strategy 与可选 reference 的配对报告。
- 将命令表面收敛为 baselines、plan、run、resume、inspect。
- 保证 CLI 与 Python API 调用完全相同的 core 函数。

### 五、清理目录与文档

- 删除清单中的目录和文件，不保留空壳、重定向脚本或别名。
- 重写 benchmark `dev_doc/` 为当前使用方式、架构和 run 格式。
- 同步根 architecture、blueprints、terminology 和受到影响的活动待办。
- 从 wheel 资源映射和安装包测试中移除已删除路径。

### 六、验证和交付

- 完成源 checkout 测试、构建、wheel 强制安装、import-origin 检查和已安装包完整测试。
- 用外部临时目录执行无写入的 `plan`，证明 baseline 和多个未知 strategy 可被发现并展开。
- 检查安装 wheel 中的 benchmark 顶层结构与最终目录完全一致。
- 更新 change record，审查 diff，创建一个完整提交；按仓库规则判断是否推送。

## 测试矩阵

至少覆盖：

- 递归发现多个自描述 baseline，且不存在中心注册表；
- baseline manifest 缺字段、路径越界、id 重复和 workspace 污染时给出有上下文的错误；
- 两个名称和实现均未在 benchmark 源码出现过的 optimization strategy 可以直接参与计划和执行；
- 同一请求包含三个或更多 strategy，结果层不要求固定角色；
- 可选 reference 的配对差值正确，没有 reference 时报告仍完整；
- plan 与 run 产生相同 RunSpec；
- yadof check 看到的是最终 selected strategy，而不是 baseline 原始 strategy；
- run 创建后修改 checkout、外部 study 或源 strategy，不改变该 run 的 resume 行为；
- driver 文件缺失、状态截断、单元失败和进程中断均有确定恢复结果；
- inspect 不写入 run；
- 报告保留未知命名空间元数据但不解释它；
- CLI 和 benchmark_core 不导出 runtime 私有符号；
- wheel 只包含规定的顶层条目和必要内部文件；
- 帮助、当前视图文档、文件名、类型名和字段名均不出现代际编号、替代入口或历史讲解。

## 量化工程门槛

以下门槛用于阻止复杂度重新增长：

- `benchmark.py`、`benchmark_core.py` 与 `benchmark_runtime/` 合计目标不超过 2,000 个物理行；超出时必须在 change record 中逐项说明不可合并的职责。
- 单个 runtime 模块不超过 450 个物理行，普通函数不超过 80 行；数据表或平台边界代码需要例外时单独解释。
- runtime 中不存在算法名称分支、strategy registry、角色布尔值或算法特有结果字段。
- 不存在跨模块私有导入、动态导出映射或二十行以上的同构顶层函数体。
- 加入一个全新 yadof 模块化算法时，benchmark 源码、文档和测试的预期修改数为零；study 输入和算法自身文件不计入。
- 最终顶层目录和文件与本文件给出的树完全一致。

## 不在范围内

- 不修改 yadof 算法组件的数学实现、默认参数或公共策略契约。
- 不创建新的科学结论、阈值、排行或推荐。
- 不执行真实 benchmark campaign、仿真器或受保护数据访问，除非用户另行明确授权具体运行。
- 不建立全局算法注册表、插件 DSL、字符串自动发现机制或组件装配器。
- 不把研究计划、研究回执或算法专项 validator 放进通用 benchmark 产品树。
- 不改写已经生成的 run；它们继续作为原地证据存在。

## 完成判据

只有同时满足以下条件，本待办才可标记完成：

1. benchmark 顶层精确符合最终目录边界，根代码文件只有两个。
2. baseline 自描述且没有中心重复表；StudyRequest 位于工具目录之外并被快照进 run。
3. benchmark 把完整 optimization strategy 当作不透明输入，运行未知算法不需要修改 benchmark。
4. plan、run 和 resume 共享单一契约；preflight 检查最终物化单元。
5. run 拥有完整 driver 与输入快照，resume 不读取当前 checkout 配置。
6. 结果与报告支持任意数量 strategy 和可选 reference，不包含算法特有分支。
7. 删除清单全部完成，相关架构、蓝图、术语、活动待办、wheel 映射和测试同步。
8. 当前命名与帮助只表达职责，不出现代际编号、替代入口、别名、双读逻辑或历史讲解。
9. 量化工程门槛通过，源 checkout 与安装 wheel 验证通过。
10. 没有在缺少明确授权时启动仿真、campaign 或受保护数据读取。

## 无效化规则

本待办不会因时间自动失效。只有用户明确取消、用另一份根级待办完整取代，或全部完成判据已经由代码、测试、文档、change record 和提交共同证明时，才可移出活动待办目录。
