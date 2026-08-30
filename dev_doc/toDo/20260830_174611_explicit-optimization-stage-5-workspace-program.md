# 预测性阶段 5：由 optimization.py 拥有完整优化程序

## 状态与依赖

这是未获准执行的预测性手动 TODO。只有 Dataset/cost、surrogate fit/predict 与 search/selection
原语已经用 benchmark 验证后，才能精确设计 workspace program；不得从本草图直接实施不兼容
入口。

## 预期目标

把 generation loop 和显式数据流放入 `submit/optimization.py`。目标程序大致可逐行看到读取
evidence、计算真实 cost、构造 surrogate data、fit/predict、计算 predicted cost、选择 population、
开始/完成真实 evaluation；这些对象可由普通 Python/NumPy/SciPy 操作。yadof 只保留 session、
snapshot、记录、评估、搜索和 surrogate 等跨任务机制。

## 已确定的 program、模板与示例交付

以下内容是用户已确定的产品决策，不因本文仍是预测性 TODO 而重新开放；阶段 5 精化时只决定
API 名称、示例目录最终 basename 和与当时实现相符的具体代码：

- package starter
  `src/yadof/_resources/templates/default/workspace/submit/optimization.py` 只提供一份通用、
  保守、对 fast/local/distributed 三种 backend 都安全的完整 optimization program。默认程序
  不依靠 backend-specific 隐式 hook，也不为追求 distributed throughput 自动给 fast/local
  引入资源竞争。
- 顶层 source-checkout `examples/` 下新增一个专门存放 optimization programs 的目录。它包含
  多份不同编排方式的 `optimization.py` 示例；每个 `.py` 都有一个同 basename 的 `.md`，说明
  该程序的背景、适用场景、数据流/并发取舍、所需组件和它应被放入怎样的 workspace 环境。
- 这些示例不是完整 workspace：目录中不复制 `config.py`、`submit/calc_cost.py`、
  `job_template/` 或 simulator assets，单个 `optimization.py` 也不能直接运行。配套 `.md` 必须
  明确缺少的环境、预期文件/API 和采用方式，不能让读者猜测隐藏上下文。
- 示例集合按编排模式提供参考，而不是建立算法注册表或穷举所有组件组合。执行时至少重新
  评估 real-only、顺序 surrogate、显式异步重叠和自定义 cost/surrogate 数据分流；
  posterior-assisted 示例只有在届时 public primitives 足够稳定时才纳入。最终清单由阶段 4
  evidence 决定，但必须保留多种有实质差异的 program。
- `user_doc/` 新增一个轻量索引文档，指向 source-checkout examples 目录中的每份
  `optimization.py` 及其配套 `.md`。索引对每个示例只写一句用途概述，不复制详细背景；详细
  说明只由示例旁的 `.md` 拥有。因为顶层 `examples/` 仍不是 wheel resource，索引必须明确
  这些文件只在 source checkout 中存在，不能暗示普通 pip 安装一定携带它们。
- `yadof init` 不提供多模板 selector、命令行选项、字符串 registry 或自动 discovery。init
  始终生成上述唯一通用 starter；需要其他编排的用户在 AI agent/文档指导下显式参考、复制
  并编辑 source-checkout example。

## 已确定的运行边界

- 一个 `yadof run` 冻结它加载的 `optimization.py` program。用户修改该文件时，在完整
  generation 边界安全停止当前命令，再通过 resume 加载新 program；不支持同一命令内热重载
  optimization loop 本身。
- 框架不根据 fast/local/distributed 自动选择训练与 evaluation 是否重叠。顺序或异步顺序由
  starter/example/user program 的普通代码显式表达；backend 只提供能力和资源/失败边界。

## 待精化决策

- `yadof check` 如何只验证入口和声明式组件而不执行任意优化程序；
- `run_one_generation`、resume、CLI progress、metadata 和 strategy namespace 的替代接口；
- 旧 `build_optimization()` 是直接删除还是仅在开发迁移期间短暂共存。最终目标为 0.5.0
  不兼容收口，不保留永久 dual path。

## 预测性验证与完成

starter、source-checkout example programs/配套文档、user-doc 轻量索引和 benchmark complete
strategy modules 必须一起迁移。测试至少验证默认 starter 在三 backend 的安全合同、示例
`.py`/`.md` 一一对应且文档声明完整环境依赖、init 始终只生成通用 starter且没有 selector、
普通 Python 数据变换、显式顺序/异步编排、program freeze/stop/resume、失败传播和 installed
docs routing。完整验收继续使用同一 seed 101、100 × 20 synthetic-antenna NSGA-III + 简单
surrogate benchmark。执行前根据阶段 4 evidence 与用户反馈把本文重写为精确 TODO。
