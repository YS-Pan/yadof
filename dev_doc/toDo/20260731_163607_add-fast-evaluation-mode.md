# 增加支持并行和外部模拟器的 Fast Evaluation Mode

## 背景

- 当前 `local` 和 `distributed` 后端都会为每个个体准备独立 job 文件夹，将任务内容、
  assigned `parameters_constraints.py`、运行元数据和 rawData 先落到 job 目录，再汇入
  `recorded_data`。对于单机上的快速计算，这些复制、进程启动和文件往返可能占据显著
  比例。
- 希望增加 `fast` evaluation mode：它只在一台计算机上运行，不创建或保留独立的
  yadof job 文件夹，不把 logical job 作为中间产物落盘；计算完成后由提交侧直接把
  rawData 和运行元数据写入 workspace `recorded_data`，再从已记录证据动态计算 cost。
- fast 不能仅限于不会失败的进程内 Python 函数。它必须能够调用电路仿真器等速度较快
  的外部模拟器，并隔离 Python 计算、worker 或外部模拟器的崩溃、卡死和异常退出。
- fast 还必须支持同一台计算机上的多个个体并行计算，同时保持个体失败隔离、输入顺序
  和 recorded-data 原子性。

## 目标

- 将 `fast` 增加为与 `local`、`distributed` 并列的显式 evaluation backend，而不是
  在 `local_runner` 中叠加绕过 job preparation 的隐蔽分支。
- fast 不调用现有的 `prepare_job()`，不复制 job template，不生成 job-local
  `parameters_constraints.py`、`workflow.py`、metadata 或 `rawData/`，也不伪造一个
  不存在的 `job_dir`。
- 使用本机受控 worker 进程执行 fast-compatible task kernel。worker 可以直接运行
  Python 计算，也可以启动外部模拟器；worker、Python 扩展或模拟器崩溃时，父进程仍能
  识别对应个体失败、清理其进程树、补充 worker，并继续处理其余个体。
- 使用可配置且受资源约束的并行 worker 池。完成顺序可以不同于输入顺序，但返回 cost、
  `population_index` 和历史记录必须保持正确对应关系。
- 让成功计算只产生内存中的具名 rawData items；父进程验证并直接归档到
  `recorded_data/rawData.zip`，随后通过当前 workspace `calc_cost.py` 计算 cost。
- 保持 `normalized variables -> rawData evidence -> recorded_data -> current cost` 为
  唯一权威链路。fast task 不得直接返回或持久化 authoritative cost。
- 现有 local/distributed 行为、job 诊断能力和分布式 execute-side 契约保持不变。

## 指导

### 后端和执行隔离

- 在 `evaluate_manager` 中增加独立的 fast dispatch/runner，并继续由
  `evaluate_manager.api` 统一负责后端选择、population 顺序、逐个失败隔离、记录和
  cost 返回。不要让 fast runner 绕过公共 recording boundary 直接操作历史文件。
- 不要把首个可用版本实现成主优化进程内的线程回调。线程不能可靠隔离崩溃、原生扩展
  fault、`os._exit()`、无限循环或外部子进程树，也不能提供可信的硬超时。
- 优先使用可长期复用、可替换的本机 worker 进程池，避免像 local mode 一样为每个个体
  启动一次完整 workflow 子进程。worker 接收显式 workspace identity、task signature、
  assigned parameters、logical evaluation identity 和 timeout，不接收 job 路径。
- 每个 worker 一次只负责一个个体。异常退出、无响应或超时必须只使该个体失败；父进程
  应终止该 worker 及其已启动的外部进程树、记录诊断、创建替代 worker，并继续尚未完成
  的队列。复用或提取现有 local process-tree 观察与终止机制，不要复制一套语义不同的
  清理实现。
- 定义清楚 worker 与外部模拟器的生命周期。支持每个个体启动一次模拟器，也允许安全
  的 worker-local 模拟器复用，但复用必须由 task contract 显式声明，并在一次失败后
  丢弃该 worker，避免污染后续个体。
- fast 是单机后端而不是无资源限制后端。增加独立、明确命名的并行配置，例如
  `FAST_EVALUATION_MAX_WORKERS`，并根据 population size、CPU、可用内存以及 task/
  simulator 声明的每 worker 资源上限确定有效并发数。不要默认复用 HTCondor request
  字段来表达 fast 配置。

### 外部模拟器和临时文件

- fast-compatible task kernel 可以通过 subprocess、COM、本机 API、共享库或其他明确
  的本地 adapter 调用外部模拟器。对 subprocess 模拟器必须捕获退出码、stderr 摘要、
  elapsed time 和进程树信息，并将可序列化诊断交回父进程。
- “job 不落盘”的保证是：yadof 不创建可恢复或长期保留的 per-job 工作目录，不把任务
  快照、参数快照、rawData 和 lifecycle 文件先写入 `jobs/`。能通过 stdin/stdout、
  API 或内存接口工作的模拟器应完全避免候选级文件。
- 某些外部模拟器不可避免地要求输入、输出或 scratch 文件。为支持这类模拟器，可以
  使用显式受控的 worker/candidate 临时 scratch，但它必须：
  - 位于配置明确的临时根目录，而不是 workspace `jobs/` 或 `recorded_data/`；
  - 不承担 yadof job、证据或恢复点语义；
  - 在成功、Python 异常、模拟器异常、超时和 worker 崩溃后的父进程回收路径中清理；
  - 为并行 worker 提供互不冲突的路径和模拟器实例；
  - 对残留清理失败给出可观察诊断，而不是静默积累。
- 文档必须明确上述临时 scratch 例外，不能宣称所有外部软件都能做到物理意义上的零
  磁盘 I/O。

### Task contract 和参数

- 为 fast-compatible workspace 定义一个任务拥有的纯计算入口，优先采用可由
  `workflow.py` 和 fast runner 共同调用的独立 task kernel，例如
  `job_template/evaluation.py` 中的 `evaluate_rawdata(...)`。不要维护普通 workflow
  与 fast workflow 两份容易漂移的仿真算法。
- task kernel 接收不可变、显式传入的 assigned parameter objects 或具名值映射，以及
  不含 job 路径的 evaluation context。它返回具有唯一直接 `.npz` basename 的具名
  rawData items 和可序列化 task diagnostics，不返回 cost。
- 从当前 `materialize_job_parameters()` 中分离纯内存的参数赋值步骤，使 fast、
  local 和 distributed 使用同一套范围、离散值、unit、normalization 和 constraint
  语义；文件 materialization 只保留为 prepared-job adapter。
- 普通 `workflow.py` 可以调用同一 task kernel 后把结果写入 job-local `rawData/`，
  从而验证 fast 与 local 的 rawData/cost 等价性。distributed worker 仍不得要求安装
  或导入 yadof。
- fast mode 对没有声明或不满足 fast contract 的 task 必须在 `yadof check`、
  smoke test 或启动前给出明确错误。不要静默回退到 local，也不要尝试 monkeypatch
  `np.savez`、虚拟 `cwd` 或伪造 job-local imports 来运行旧 workflow。

### 结果、记录和流量控制

- 将公共 execution result 从“必有 `job_dir` 和 `raw_data_paths`”推广为能显式表示
  file-backed 或 memory-backed rawData 的 backend-neutral 结果。若保留 `JobResult`
  名称，则 `job_dir` 必须真正可选；不得用尚未创建的路径充当 fast job 目录。
- 内存 rawData 必须先通过当前 schema、metadata、shape、axis、basename 和重复名称
  校验。recorded_data 层负责把 payload 规范化为不需要 pickle 的 `.npz` bytes，并以
  当前 `<logical_job_name>/<filename>.npz` 结构写入 archive。
- recorded_data 仍是唯一 durable evidence owner。worker 不并发写 archive 或
  manifest；父进程中的单一 recorder 负责锁、归档更新、manifest 更新和故障恢复。
- 避免把整代所有 rawData 无限制地留在内存中。设计有界结果队列和 backpressure；
  recorder 应随着个体完成持续消费结果。若为避免反复复制大型 zip 而使用 generation
  transaction，应把完成项流式写入 recorded_data 所属的临时 archive，并在提交时
  原子替换；该临时文件不具有 job-folder 语义。
- 只有 rawData 和 manifest 成功持久化后，才通过 recorded_data/current
  `calc_cost.py` 得到 cost。记录或 cost 计算失败仍按单个个体隔离，并返回正确宽度的
  failure cost。
- 保留 logical job/evaluation name、run/optimization/generation/population identity、
  normalized/unnormalized variables、task/static signature、host、worker pid、开始结束
  时间、elapsed time、timeout、退出类型和外部模拟器诊断。不要伪造 fast 无法提供的
  job-local stdout/stderr 或 disk-usage 字段。

### CLI、检查、文档和兼容性

- 将 `fast` 加入 config、API、`run`、`smoke-test` 和 workspace check 的显式选择，
  并使 smoke test 使用一个 worker、无隐式无限并发。
- 定义 fast timeout、并发数、资源探测、外部进程环境、scratch root 和清理策略的配置
  precedence 与诊断输出。环境变量和 subprocess 参数不得泄漏 workspace 之外的隐式
  全局状态。
- 保持 `after_jobs_submitted` 等现有优化器回调语义可解释。fast 没有 scheduler submit
  时，不应伪造 submit 事件；若需要共享 lifecycle hook，应先将其推广为后端中立名称
  和契约。
- 更新 user documentation，明确哪些 task 适合 fast、如何编写共享 task kernel、
  外部模拟器/scratch 限制、并行与资源设置，以及何时应改用 local/distributed。
- 更新 architecture、blueprints、terminology 和 change record，使 fast 被描述为
  单机、无 durable job folder、进程隔离、可并行、rawData-first 的第三后端。

### 验证

- 单元和集成测试至少覆盖：
  - fast 成功后没有创建 per-job `jobs/` 子目录，rawData archive/manifest/cost 正确；
  - 同一 task kernel 经 fast 与 local 产生等价 rawData 和 current cost；
  - 一个可控的外部 simulator stub 成功运行并返回 rawData；
  - Python worker、原生/外部进程异常退出以及不可捕获式 worker 终止只影响一个个体；
  - timeout 会终止 worker 和模拟器后代进程，替代 worker 能继续后续个体；
  - 配置的多个 worker 确实重叠执行，完成乱序时最终 cost 顺序仍与 population 一致；
  - 并发外部模拟器拥有隔离实例/scratch，成功、失败和崩溃后没有未报告的残留；
  - 大结果受到有界队列/backpressure 约束，不要求把整代证据同时保留在内存；
  - recorded_data 写入保持单 writer、锁和原子恢复语义；
  - 两个 workspace 的 task module、worker 状态和 recorded data 互不污染；
  - 不支持 fast contract 的 task 得到清楚的 check/startup 错误且不静默回退；
  - 所有现有 local/distributed、history、surrogate 和 CLI 回归测试继续通过。
- 在可用环境中增加一次真实的快速外部模拟器 smoke test，例如电路仿真；自动测试可以
  使用受控 simulator stub 保持可重复性，但必须覆盖真实 subprocess、并行和崩溃清理
  路径，而不能只 mock fast runner 内部函数。

## Completion Rule

- `fast` 已作为正式第三后端通过 config、API、CLI、check 和 smoke-test 暴露；它不
  创建 durable per-job folder，也不伪造 job paths。
- fast-compatible task 使用一份可由普通 workflow 复用的 task kernel，参数赋值和
  rawData/cost 语义与 local/distributed 保持一致。
- 多 worker 单机并行、外部模拟器调用、硬超时、worker/模拟器崩溃隔离、进程树清理和
  worker replacement 均有实现、诊断和自动化测试。
- 成功 rawData 由父进程直接、原子且有界地进入 recorded_data，之后才动态计算 cost；
  失败个体被记录且不阻断其余 population。
- 模拟器不可避免的临时 scratch 已被明确限制、隔离和清理；没有 yadof job 快照或
  rawData 中间证据残留在 `jobs/`。
- local/distributed 的现有行为和测试不退化，相关 user docs、architecture、
  blueprints、terminology 和 change record 已同步更新。
