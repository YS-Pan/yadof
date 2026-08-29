# 恢复 yadof-benchmark 用户体验与测试方法契约

## 本文的角色

- 本文是手工 TODO，汇总旧版 benchmark 工具开发期间用户明确提出、但在 2026-08-28
  code-first 重写后没有完整保留下来的用户体验和测试方法要求。
- 证据范围是本机当前可访问的全部 Codex task 历史：先检索所有真实 user message 中的
  `benchmark`/“基准”，再完整读取 2026-08-22 至 2026-08-28 的 benchmark 工具设计、实现、
  实测和重写链，并定向读取更早的三基线选择、迁移和 preflight task。文末列出直接形成
  本文要求的 task ID；只讨论某个算法结果而没有形成工具契约的 task 不重复列入需求正文。
- 本文区分“已验证的当前事实”“用户要求”“被后续决定取代的旧要求”和“尚待实现者决定的
  设计问题”。历史 task 中的早期方案不能覆盖同一事项上更晚、更明确的用户决定。
- 本文不授权启动长时间 simulator 或正式性能 campaign。实施、短测、安装和正式实测仍须
  分别遵守当时任务的执行权限与当前 yadof 文档。

## 已验证的当前缺口

2026-08-29 对用户指出的
`codex://threads/01a048c2-e6b9-70f1-9b05-90bf62484ecf` 所启动工作区进行了只读核对：

- `temp/full-benchmark-20260828` 的 18 个 cell 全部进入 collected 状态；配置为 3 个 baseline
  × 2 个 strategy × 3 个 seed，然而每个 cell 只有 `population=12`、`generations=20`。
- 工作区顶层 `visualizations/` 和 `reports/` 均存在但为空。run-local 目录虽然非空，
  `visualizations/` 只有 `reference_deltas.csv`，`reports/` 只有含最终 HV 表的
  `summary.md`；旧版要求的逐优化 cost 图和三个 baseline 的领域可视化没有产生。
- 人类可见的工作区名 `full-benchmark-20260828` 和 run 名
  `full-benchmark-runtime-compatible-20260828` 均未以精确到秒的日期时间开头。
- 当前 user docs 的 API 示例仍使用 `population=12`、`generations=20`，没有把这种规模限定为
  structural smoke，因此容易继续生成不合格的 performance campaign。
- 当前文档已经写有“可测量的 run/resume 默认可见”，但这次实际启动没有向用户展示可观察的
  CLI/进度界面。仅有文字约定不足以构成验收。

## 必须恢复的有效要求

实施进度：2026-08-29 已完成第 1--8 小节。初始化 scaffold 现在从唯一入口展示 policy、算法语义
strategy、baseline、seed/budget 和 postprocess；baseline discovery 强制 editable source 的
相对目录等于 `provider/task` semantic ID，run 仍负责 digest 与不可变 snapshot。人类可见
workspace/run/output-index 现由 benchmark 统一添加秒级时间前缀；每个 cell 强制生成 cost 图与
baseline 领域后处理产物，并发布 cell 有效性、final-HV 和机器可读报告，workspace 顶层索引指向
唯一 run root。CLI 现由前台 owner 统一管理 Rich cell/global 两行与 lifecycle 输出，消费
yadof child 的真实中间评估进度；Windows `--detach` 默认打开独立可见 console 并立即返回
PID/run/log/inspect 回执，`--hidden` 只能显式与 detach 同用，同步 API 不启动窗口或等待输入。
独立 package、Python-only workflow、无算法 registry、无阶段式命名和 compact internal workspace 的
现行边界已由安装态测试和实际 Windows/Codex visible-console structural run 验证。
`check`/`plan` 默认只给有界摘要，完整 plan JSON 必须显式请求；child stdout/stderr 默认只进入
分离日志，显式选项才由前台 owner 流式显示。只读 `inspect` 现提供有界 status、validity、
comparison、异常、下一步路径以及 elapsed/active/recent/remaining/completion/confidence/evidence；
每个新 run 冻结 bounded timing history，ETA 先用同 baseline/strategy/budget/task/resource/host/
config 的 exact 或 compatible prior，禁止跨 strategy 点估计，并用带时间戳的 generation trend
识别后期训练变慢。每个 workflow 现在必须显式冻结 `structural` 或 `performance` 证据分类，并把
分类与固定用途提示贯穿 plan/cell/report/index/inspect/CSV/JSON；包/CLI 测试统一标记 structural，
故障注入与 resume 测试另标 recovery，二者均不能替代真实 adapter smoke 或算法性能证据。用户与
开发文档规定 full 前依次完成有界 plan/check、同 adapter smoke 和使用相同 baseline/strategy/
配置路径的 structural canary；benchmark 不兼容时先修工具并重跑结构验证，yadof 根缺陷则建立
独立根 TODO 并阻止受影响 full。performance workflow 现拒绝低于每代 100 个体或 20 代的配置，
把 2000 planned real evaluations 明确为有效性硬下限而非难度目标；单 seed performance 结果贯穿
plan/cell/report/index/inspect/CSV/JSON 标为 exploratory，多 seed 数量继续显式可配且不自动宣称
稳健性。用户与开发文档要求先用完整纯 NSGA-III 参考把任务难度校准到接近约 10000 evaluations
才收敛。同 baseline/seed 的 arms 现在校验冻结 baseline snapshot、planned/attempted budget 和完整
generation-0 normalized-population fingerprint；cell 明确发布 planned/attempted/completed/finite
计数，final HV 与 HV trajectory/AUC 以 attempted real evaluations 对齐。无效或不完整 evidence
保留在 run 中但显式从跨 seed 描述性 aggregate 排除，失败不再包装为 performance score，主比较
表不以 optimizer wall time 排名。surrogate training duration 单独发布，并只在 workflow 显式给出
代表性昂贵 generation 时生成描述性比值。structural workflow 现默认 fail-fast，performance 默认
继续独立 cell 以保全昂贵 evidence，但任一 invalid/incomplete cell 仍使最终状态和 CLI 退出非零；
cell aggregate publication 是下一 cell 前的 campaign-fatal barrier，失败会保留 state diagnostics。
执行中断/失败 attempt 现以独立 `attempt.json` 封存为 incomplete，stdout/stderr 分离保留，resume 新建
编号 attempt 与 compact workspace；collection-only failure 则复用成功但尚未封存的执行 evidence。
每次执行还会重新校验 run-owned driver、workflow/resources、baseline、strategy digest，外部可编辑源只
影响后续新 run。第 9 小节仍保持 active；本进度不代表并行要求已经完成。

### 1. 工具边界和工作区体验

- `yadof-benchmark` 保持独立包和 code-first 设计；`benchmark init` 创建可直接编辑、可版本管理
  的 benchmark 工作区，唯一主要入口是 `benchmark.py`。
- 工作区至少清楚提供 `runs/`、`visualizations/`、`reports/`、`temp/` 和入口文件。workflow、
  baseline、algorithm module、seed/budget 和 postprocess 都能从入口代码发现。
- 不恢复 TOML，不创建隐藏的算法注册表，不把某次重写命名为 `v2` 等临时发布阶段；公开 API
  应小而稳定，user docs 必须列出入口、参数、产物和典型命令。
- strategy/arm 名使用真实算法语义，例如 `nsga3`，不使用 `real-search` 这类看不出算法的名字。
- baseline 源目录按 provider/adapter 和任务语义命名，例如 `ngspice/saw-ladder`、
  `chrono/trebuchet`，不在可编辑源目录名中附加 opaque fingerprint。baseline 可以随时编辑；
  每次 run 再冻结自己的不可变 snapshot。

### 2. 命名和结果可发现性

- `benchmark init` 自动创建的人类可见工作区、自动创建的 run 和默认输出目录都必须以
  `YYYYMMDD_HHMMSS` 开头，随后才是可读语义名。该规则由 benchmark 实现，不委托给 yadof。
- 为避免 Windows 路径过长而创建的 run-internal compact execution workspace 可以使用短 digest；
  它不是人类可见的 workspace/run 名，不受上条限制。
- 一次 benchmark 的所有结果必须能从一个 run root 找到。正式完成后，工作区顶层
  `reports/`、`visualizations/` 不得仍是无意义的空目录：可以存放 run-index/latest 指针或
  物化的 workspace 汇总，但必须把用户可靠地引到相应 run 的真实产物。
- run-local `reports/` 至少提供总体摘要、cell 完成/有效性摘要、最终 HV 表和可机读的描述性
  结果；不得只有内部状态文件。
- 每次 optimization 完成后自动执行等价于 `yadof view cost` 的 cost 可视化。所有 cost 图归入
  一个清楚命名的分类，不能散落在执行 cell 内。
- 领域 postprocess 使用各 baseline 中统一名称/接口的脚本，并在每个 optimization 后自动运行：
  - trebuchet 选择该 optimization 中平均 cost 最小的个体，生成约定的图片/动画；
  - SAW 使用其已有领域可视化；
  - testcom 提供简单但可用的领域可视化。
- 领域可视化按 baseline 汇总为 3 个语义目录，而不是按 18 个 optimization 建 18 个顶层目录；
  `view cost` 结果另归一类。旧要求“一次 benchmark 的可视化放在同一文件夹”应理解为同一
  `visualizations/` root 下的逻辑分类，而不是把所有文件压平。

### 3. CLI、进程窗口和进度

- 人类或 AI 启动可测量的 `run`/`resume` 时，默认都显示 benchmark 进程窗口。长任务可以分离，
  但要打开普通、可检查的独立 console，并立即返回 PID、run path、log path 和 inspect 命令。
  只有用户明确要求隐藏时才允许 hidden launch。
- 启动者不通过频繁轮询维持长任务；用户或定时 task 稍后用只读 inspect/ETA 查看状态。
- 使用 Rich 等成熟终端组件，不维护自制 cursor 控制。底部固定显示两行：当前 active cell 在前、
  global benchmark 在后；正常 lifecycle/log 文本只出现在其上方。
- 进度组件不得产生 ghost bar、截断 global trailing fields，或让 cell 长时间停在 0% 后瞬间跳到
  100%。执行中的 cell 必须收到真实中间进度；窄终端可压缩字段但不能丢失关键状态。
- 进度实现必须在 Windows、Codex terminal、`TERM=dumb`/`NO_COLOR` 等实际启动环境工作；Rich
  console 的创建、更新、stop 和普通输出由前台 terminal owner 统一管理。
- 任务完成/失败后的最终摘要和错误必须仍可检查。历史上的“CLI 窗口不要立刻消失”表达的是
  这一可观察性目标；具体采用保留 console、launcher acknowledgement 还是等价机制仍需设计，
  但不能以破坏无人值守自动化或让 API 永久阻塞的方式实现。

### 4. 面向人和 AI 的 inspect、日志与 ETA

- 默认输出有界摘要，不把大 JSON、raw child stdout/stderr 或所有 cell 明细灌入上下文。
  `plan`/`preflight` 默认给摘要，完整 JSON 显式请求；`run`/`resume` 将 child output 写入分离日志，
  只有显式选项才流式输出。
- 推荐的渐进披露顺序是：`inspect` → `report.md` → 定向读取 `report.json` → 单个 cell log →
  `metrics.json` 的指定字段。inspect 至少回答 status、validity、comparison、异常和下一步命令。
- inspect/ETA 必须是只读的，并同时显示 elapsed、active-cell runtime、最近活动、预计剩余时间、
  预计完成时间、置信度/证据来源。适合定时 task 查看后按 ETA 安排下一次检查，不要求轮询。
- ETA 优先复用同一 case、arm、budget、task/resource/host/config 的已完成 matched cell；必须区分
  exact 与 compatible prior。同 case 不同 arm 不能作为点估计，尤其 surrogate 和 non-surrogate
  运行时不可互代。
- 每个 command/progress/generation phase 写时间戳；ETA 应识别后期 surrogate training 变长等
  非线性趋势，而不是只按当前 generation 做简单线性外推。

### 5. structural test 与 performance campaign 必须分层

- benchmark 包代码测试、恢复/故障注入测试和 optimization performance campaign 是不同证据。
  recovery test 证明恢复语义，不是算法性能 benchmark。
- 小规模 fake/cheap runner、CLI smoke 和一代 canary 只用于结构验证；它们必须明确标成
  `structural`/`smoke`，不得生成或暗示 performance 结论。structural canary 仍要使用真实配置
  路径，adapter 先做 smoke 再做 full。
- 所有长任务先通过 `plan`/`preflight` 和有界 smoke。benchmark 自身不兼容时先修 benchmark、
  重跑 smoke 再申请 full；发现 yadof 根层 bug 时不得在 benchmark 塞进别扭 workaround，应在
  yadof `dev_doc/toDo/` 建立独立 TODO，并且不启动受影响的 full campaign。

### 6. 正式性能测试规模、难度和 seed

- 正式 performance cell 的硬下限是每代至少 100 个体、至少 20 代，即每个 cell 至少 2000 个
  planned real evaluations。文档、示例和 guard 都必须阻止“几代、十几个个体”被当成性能测试。
- 2000 evaluations 只是最低有效规模，不是任务难度目标。baseline 要足够难：参考纯 NSGA-III
  应接近约 10000 evaluations 才收敛（历史示例为 200 × 50）；若约 2000 evaluations 已轻易
  解决，surrogate 的比较意义不足，应先用完整 non-surrogate run 调整任务难度。
- 为算法调试而进行的快速迭代允许每个 state/arm 只用 1 个 seed，以缩短“分析—修改—安装—
  启动—定时查看—再分析”循环；这种结果必须标为 exploratory，不能冒充正式、稳健结论。
- 需要更强结论的 campaign 使用多个显式、可配置 seed。历史三基线 campaign 使用过 3 seed，
  但工具不得把 3 写成无法调整的科学常数。

### 7. 配对公平性、计数和指标

- 同一 case/seed 的各 arm 必须共享相同的 task/baseline snapshot、generation-0 初始 population
  fingerprint 和 planned/attempted real-evaluation budget；任何不匹配都使配对比较无效。
- 每个 cell 明确记录 planned、attempted、completed、finite 数量；HV trajectory 和 HV-AUC 按
  attempted real-evaluation count 对齐，不能用 generation label 掩盖重试、失败或不同批次大小。
- 至少输出 final HV、HV trajectory/HV-AUC 和相关描述性计数。benchmark 可以生成原始/描述性
  结果，但不自动宣布 winner、显著性、acceptance 或算法优劣；最终解释由人或 AI 结合任务做出。
- simulator failure、非有限 cost 和不完整 cell 属于 validity/completeness，而不是把错误率包装成
  performance score。不完整 cell 保留全部 raw evidence，但从跨 seed aggregate 排除并显式标记。
- optimizer wall time 不是主要性能指标。surrogate training time 要单独记录，并与代表性昂贵
  generation 的真实评估时间比较；不能因为 cheap benchmark 的单代很快就错误判定 surrogate
  训练不可接受。peak resources 和 checkpoint size 不是旧 campaign 的验收重点。

### 8. 记录持久性、失败和恢复

- 不为追求吞吐量丢弃结果。recorder/存储较慢时，在结果可靠发布后才继续下一次 simulation；
  存储失败是 campaign-fatal，并保留可诊断证据。
- structural run 默认 fail-fast。performance run 可让相互独立的 cell 继续，以保全昂贵证据，
  但任一无效/不完整 cell 使总体退出非零；all-infinite cell 必须失败。
- 半代或不完整 attempt 保留原始证据并标为 sealed/incomplete；重试创建新 attempt/workspace，
  不覆盖旧证据。attempt metadata、stdout 和 stderr 分开保存。
- 已启动 run 冻结 workflow、资源、baseline、strategy、driver/code 和配置；外部编辑不改变旧 run，
  resume 只使用 run-owned snapshot。可编辑 baseline 源与不可变 run snapshot 两者必须同时成立。
- Windows 执行路径使用 compact internal workspace，从工具层根治路径长度问题；不得靠修改某个
  Chrono scenario 名称来掩盖通用 adapter/path bug。

### 9. 并行度和资源使用

- cell/simulation 并行度必须显式可配置，并尽量提高 CPU 利用率。历史用户允许并发数超过物理
  core（例：8 core 配 32 个并发 simulation），但实际默认值仍须受 simulator、内存、license、
  recorder 和当前 yadof 并发契约约束，不能把示例数字硬编码成普遍安全值。
- 提升并发不得改变配对预算、跳过持久化、吞掉失败或使进度/ETA 失真。

## 已被后续决定取代或澄清的旧要求

- “baseline source 冻结并用 fingerprint 命名”已被“可编辑的语义 baseline source + 每个 run
  不可变 snapshot”取代；只保留后者。
- 早期 full campaign 的 3 seed 不能否定后来为算法迭代明确允许的 1 seed；两者分别对应正式
  证据和 exploratory 调试，不应混用。
- 初始 delegated launch 中的 hidden/detached 启动方式已被用户在
  `01a048c2-e6b9-70f1-9b05-90bf62484ecf` 的后续明确要求取代：人和 AI 默认都显示进程窗口。
- “所有 visualization 放在同一文件夹”后来被细化为一个 `visualizations/` root，下面按
  `view cost` 和 3 个 baseline 分类；不得回退为 18 个 cell 顶层目录或无分类平铺。
- “CLI 不要立即消失”按“最终状态可观察”验收，不解释为破坏 script/API 的永久阻塞。

## 实施与验收清单

1. 更新 benchmark user/dev docs 和所有公开示例：performance 示例满足 `population >= 100`、
   `generations >= 20`；任何更小配置都显式标注 structural-only。CLI/preflight 对误标的小配置
   给出拒绝或不可忽略的明确分类，不静默产出 performance report。
2. 为 `init`、自动 run/output naming 增加测试，验证人类可见名称以
   `YYYYMMDD_HHMMSS` 开头，同时 compact internal path 仍满足 Windows 长路径约束。
3. 用 fake/cheap runner 验证完整产物流水线：顶层 reports/visualizations 可发现且非空，run-local
   report、HV 表/机器可读结果、逐 cell cost 图、按 3 baseline 分类的领域 postprocess 均存在；
   缺失/失败的 postprocessor 必须进入有效性和退出状态，不能留下“成功但空目录”。
4. 在实际 Windows/Codex terminal 做 CLI 验收：默认 visible launch、独立 console 分离、PID/path
   回执、两行 Rich progress、真实中间 cell update、窄终端字段、`TERM=dumb`/`NO_COLOR`、正常完成
   和失败后的最终信息都可观察；同时验证非交互 API 不被永久等待输入。
5. 用确定性 event replay 验证 inspect/ETA、matched-history 选择、跨 arm prior 排除、非线性阶段
   估计以及默认输出上限；无需为这些测试启动 simulator。
6. 覆盖 paired generation-0 fingerprint、attempted-count 对齐、partial/incomplete aggregate exclusion、
   storage-fatal、structural fail-fast、performance independent-cell continuation、new-attempt resume 和
   immutable run snapshot。
7. 按 `yadof-benchmark` 自己的开发文档构建并 force-reinstall wheel，验证 import origin 和全套包测试；
   如行为改变了 repository-wide architecture/terminology/blueprint，再同步根文档。
8. 完成上述结构验收后，必须另获 simulator 权限才可启动正式三 baseline campaign。正式每个 cell
   不低于 100 × 20；若任务难度仍过低，先按约 10000 evaluations 的参考目标校准 baseline，
   再开始有科学解释意义的多 seed 比较。
9. 正式 campaign 完成后检查所有 cell、report、visualization、CLI/log receipt 和描述性指标，
   记录 exact commands/paths/config/commit。只有本文全部条目已实施并有相应证据时才可归档 TODO。

## 明确非目标

- 本 TODO 不恢复 TOML、旧 algorithm registry、release-transition `v2` 命名或自动 winner 判定。
- 本 TODO 不要求 benchmark 接管单个 yadof workspace 已有的领域观察能力；benchmark 负责跨
  case/arm/seed orchestration、统一调用、汇总和可发现性。
- 本次仅恢复需求文档，不修改 benchmark 实现，不把当前 12 × 20 run 追认为有效 performance
  evidence，也不自动启动新的长任务。

## Codex task 证据索引

以下是直接形成本 TODO 的 benchmark 工具 task；ID 用于追溯原始用户措辞，不作为运行时依赖：

- 基线选择、迁移和 preflight：
  `01a022ed-c1ee-7ce1-96a7-b2dd85c7ec5a`、
  `01a023a5-9bc2-77f2-8aa1-3008e861930a`、
  `01a02764-dcd2-7202-b01a-f6913d126820`、
  `01a02904-b24c-73b3-9751-c562f3f95424`。
- 自动化、失败语义和性能 campaign：
  `01a02989-7c07-7530-b4d0-daacf7aee6fb`、
  `01a02c11-8f68-74c0-917b-6f7664752696`、
  `01a02e58-05ae-7f41-ad29-cd6a72f1d33d`、
  `01a03118-6afb-7ba2-8afc-d1d7abe1cf79`、
  `01a03189-981a-79a2-9ff7-33bac57d94e4`、
  `01a031b0-398c-73e0-84e0-9bfdcf7c29fd`。
- agent UX、输出和可视化：
  `01a02d48-f52d-7692-bd0d-139485170e9d`、
  `01a02d99-f006-7da1-9a50-f8458083b7b4`、
  `01a02de0-faa0-70b3-a7bf-9592bed7b7cf`、
  `01a02de2-938f-75a2-9018-0e493be08a28`、
  `01a03262-a192-7dc2-9e8e-e190f400849e`、
  `01a03291-f408-7f03-962b-e55e563509f9`、
  `01a033c9-5a2d-7721-9dff-f6d9d9019557`、
  `01a0365b-beab-7281-b6b5-c7fbbba824eb`。
- progress、ETA、Windows 和迭代调试：
  `01a03630-2bfb-7453-b282-47fba9537564`、
  `01a03c47-f309-7103-b7fb-d4eeb857918b`、
  `01a03cd4-ee08-75d2-9235-73598ad3e9a5`、
  `01a03cdb-9085-75c2-9303-b5274a5a27b0`、
  `01a03cff-6bc8-7853-a38b-ab89862394c6`、
  `01a04030-cfa6-7760-8879-ea0237475a9b`。
- code-first 重写和本次缺口：
  `01a0481d-33a8-7442-a82b-b1f549b6aac1`、
  `01a0487b-5441-7133-a887-3a822d0ce950`、
  `01a048c2-e6b9-70f1-9b05-90bf62484ecf`。
