# 修复参数范围热更新与 job 参数传递

## Context

### 任务背景

项目规格要求用户能够在优化进程运行期间修改
`project/job_template/parameters_constraints.py` 中的变量范围，后续新建的 job
必须立即使用新范围，不应要求重启优化进程。历史样本仍只保存未归一化原始值；
`recorded_data` 在被请求时，也应使用当前参数范围动态计算历史样本的归一化值。

当前实现不满足这个要求。job 目录虽然会复制磁盘上最新的
`parameters_constraints.py`，但个体实际使用的变量值来自 `job_input.json`。
这形成了两个互相可能不一致的参数来源。

本任务只修复参数定义、个体参数传递及其直接合同。应保留当前的其他核心设计：

- workflow 只生成 rawData 和运行 metadata，不生成 `cost.json`。
- `calc_cost.py` 不复制到 job。
- `recorded_data` 只持久化原始变量、rawData 和 metadata，cost 与历史归一化值动态计算。
- local 与 distributed 模式共用相同的 job 内容和记录合同。
- 当前任务的参数名、范围、约束、workflow、仿真文件和 cost 定义仍由
  `project/job_template/` 所有。

### 已复现的现象

当前工作区中的下面这组文件直接展示了问题，不需要运行 HFSS 即可验证：

- 当前模板：`project/job_template/parameters_constraints.py`
- 修改范围后生成的 job：`temp/job_20260715_050131_507077/`
- 该 job 中复制的新参数定义：`parameters_constraints.py`
- 该 job 中实际传值文件：`job_input.json`

模板文件的修改时间是 `2026-07-14 16:10:32`。上述 job 的名字时间晚于该修改，
而且 job 内复制的 `parameters_constraints.py` 已经包含新范围。但是
`job_input.json` 中的未归一化值仍由旧范围计算：

| 参数 | normalized value | job 内复制的新范围 | `job_input.json` 实际值 | 按新范围应得值 | 实际值对应的旧范围 |
|---|---:|---|---:|---:|---|
| `dipole_gap` | `0.04799231326259079` | `(1.6, 4)` | `2.0959846265251816` | `1.715181551830218` | `(2, 4)` |
| `dipole_post_xposi` | `0.10025942169201896` | `(1, 3)` | `1.6503891325380284` | `1.200518843384038` | `(1.5, 3)` |
| `dipole_w` | `0.9991982890121859` | `(4, 9)` | `6.9975948670365575` | `8.99599144506093` | `(4, 7)` |

例如第一行的实际值严格等于：

```text
2 + (4 - 2) * 0.04799231326259079
= 2.0959846265251816
```

而不是用当前范围计算的：

```text
1.6 + (4 - 1.6) * 0.04799231326259079
= 1.715181551830218
```

该 job 的 `run_id` 是 `opt_20260714_120138_a001ead8`，说明优化进程在参数文件
修改前已经启动。这个证据与 Python 模块缓存造成的旧定义驻留完全一致。

### 当前错误调用链

当前核心调用链是：

```text
optimizer normalized row
  -> evaluate_manager/job_files.py: prepare_job()
  -> 从磁盘复制当前 job_template 文件
  -> import project.job_template.api
  -> 使用已导入模块中的旧 PARAMETERS 反归一化
  -> 写 job_input.json
  -> job/workflow.py: worker_misc.load_variables()
  -> 从 job_input.json 读 unnormalized_variables
  -> 把这些值设置到 HFSS
```

根因不在文件复制。`project/job_template/api.py` 在模块导入时执行：

```python
from .parameters_constraints import get_parameters
```

`project/evaluate_manager/job_files.py::_denormalize_variables()` 后续即使反复调用
`importlib.import_module("project.job_template.api")`，得到的仍是同一个已缓存模块，
不会重新执行磁盘上已修改的 `parameters_constraints.py`。与此同时，
`copy_job_files()` 每次都从磁盘复制文件，所以一个 job 会同时出现：

- 新的参数范围文件；
- 按旧参数范围生成的 `job_input.json` 数值。

workflow 把后者当成权威值，因此复制进去的新范围没有控制实际仿真。

### 当前工作区中的未完成绕行方案

当前未提交的 `project/job_template/workflow.py` 又增加了：

- `PARAMETER_VALUES_FILE = BASE_DIR / "parameters_values.py"`；
- `_write_parameter_values_file()`；
- 先用 `load_variables()` 从 `job_input.json` 取值，再临时生成
  `parameters_values.py`，最后调用 `set_para()`。

这个方案只改变了 HFSS adapter 接收值的形式，没有改变值的来源。它仍然把
`job_input.json` 中基于旧缓存范围计算的值传给 HFSS，因此不是本任务的正确实现。
实现本待办时应删除这条临时支线，不应保留为 fallback。

## Reference Behavior

未来执行本任务的环境可能没有 `temp/20260403 fanyufei`。下面完整记录与本任务
有关的参考行为；不需要再依赖参考目录。

### 参考参数对象

参考版本的参数对象是一个可保存当前个体值的可变 dataclass，主要字段为：

```python
name: str
ranges: tuple[float | tuple[float, float], ...]
value: float = float("nan")
normValue: float = float("nan")
unit: str = ""
```

它的 `denorm(normValue=None, clip=True, update=True)` 行为是：

1. 未显式传值时使用对象自己的 `normValue`。
2. 默认把 normalized value 限制到 `[0, 1]`。
3. 把 `[0, 1]` 均分成 `len(ranges)` 个片段。
4. 选中的 range 元素如果是 `(lo, hi)`，就在该片段内线性插值。
5. 选中的 range 元素如果是单个数，就直接使用该离散值。
6. `update=True` 时同时写回对象的 normalized value 与 `value`。

参考版本没有提供反向 `norm()`，理由是 ranges 允许重叠时反向映射可能不唯一。
当前 `recorded_data` 明确要求根据当前范围动态归一化历史原始值，因此目标
实现不能机械删除现有 normalize 能力。应在保留当前历史归一化合同的同时，
把参考版本的“参数对象携带本 job 的 normalized value 和 raw value”语义移植回来。

不要求为了模仿旧代码而把当前 `Parameter` 改名为 `para`。应只保留一套清晰接口，
不要增加 `Parameter`/`para` 双接口或旧字段别名作为兼容层。

### 参考 job 参数文件生成

参考版本的 `prepare_job.write_parameters_file()` 每次建 job 时都重新执行磁盘上的
权威参数文件，不复用一个长期驻留的模块对象。核心逻辑等价于：

```python
source = fresh_load(canonical_parameters_constraints_path)
base_parameters = source["PARAMETERS"]
constraints = tuple(source["CONSTRAINTS"])

if len(normalized_values) != len(base_parameters):
    raise ValueError

job_parameters = []
for base_parameter, normalized_value in zip(base_parameters, normalized_values):
    parameter = Parameter(
        name=base_parameter.name,
        ranges=base_parameter.ranges,
        value=float("nan"),
        normalized_value=normalized_value,
        unit=base_parameter.unit,
    )
    parameter.denormalize(update=True)
    job_parameters.append(parameter)

write_python_file(
    job_dir / "parameters_constraints.py",
    PARAMETERS=job_parameters,
    CONSTRAINTS=constraints,
)
```

参考文件实际使用的 normalized 字段名是 `normValue`，方法名是 `denorm()`。
目标实现可以按当前项目命名习惯确定最终名称，但必须只有一种格式，并满足上述
状态与行为。

生成后的 job-local `parameters_constraints.py` 同时包含：

- 参数名；
- ranges；
- 当前个体的 normalized value；
- 按这些 ranges 计算出的 raw `value`；
- unit；
- constraints。

因此它既是该 job 的参数定义快照，也是 workflow 的唯一参数值输入。

### 参考 workflow 读取

参考 HFSS workflow 不读取 JSON 参数文件。它直接调用：

```python
set_para(hfss_app)
```

`hfss_com.set_para()` 默认读取 job 当前目录的 `parameters_constraints.py`。
其内部遍历 `PARAMETERS`，读取 `p.name`、`p.value` 和 `p.unit`，拒绝 NaN value，
然后把类似 `{"dipole_gap": "2.5mm"}` 的映射写入 HFSS。

当前 `project/job_template/hfss_com.py` 已经保留了相同的
`_load_parameters_py_value_only()` 和 `set_para()` 能力，目标实现应直接使用它，
无需再生成 `parameters_values.py`。

纯 Python workflow 也应从同一个 job-local `parameters_constraints.py` 读取
`parameter.value`，而不是使用另一种 JSON 输入格式。

### 参考静态哈希

job-local 参数文件加入个体 value 后，每个 job 的文件字节都会不同。参考版本没有
因此让 `job_static_hash` 变成“每个个体都不同”，而是为
`parameters_constraints.py` 构造语义签名，只纳入：

```text
parameter name + ranges + unit + CONSTRAINTS
```

不纳入：

```text
value + normalized value
```

所以不同个体、相同任务定义的 static hash 相同；参数名、范围、单位或约束变化后，
static hash 才变化。目标实现必须保留这个性质。

### 不应从参考版本带回的内容

参考版本比当前实现更旧，其中还有 `cost.json`、旧 metadata、旧 recorded-data
布局和旧 optimizer/surrogate 流程。这些都不属于本任务，不得恢复。这里只参考：

- 参数对象携带 per-job assigned value 的做法；
- 每次建 job 从权威参数文件重新物化 job-local 参数文件的做法；
- workflow 直接读取 job-local 参数文件的做法；
- static hash 忽略 per-individual assigned value 的做法。

## Goal

完成后必须形成以下单一数据流：

```text
project/job_template/parameters_constraints.py on disk
  -> 每次 prepare_job 时 fresh load 当前定义
  -> 用本 individual 的 normalized row 计算 raw values
  -> 生成 job/parameters_constraints.py，包含定义和 assigned values
  -> workflow 只读取 job/parameters_constraints.py
  -> rawData
  -> evaluate_manager 从同一批 assigned raw values 构造 JobSpec/JobResult
  -> recorded_data 持久化 raw variables
```

不得再存在下面的数据流：

```text
normalized row -> cached PARAMETERS -> job_input.json -> workflow
```

也不得存在：

```text
job_input.json -> parameters_values.py -> set_para()
```

## Guidance

### 1. 建立唯一的参数文件合同

`project/job_template/parameters_constraints.py` 是当前任务的权威参数定义。
每个 job 中同名文件是该定义在 job 创建时的快照，并额外携带该个体的 assigned
normalized/raw values。

canonical 文件中的 assigned value 可以使用 NaN/default 表示“尚未分配”；
job-local 文件中的 assigned raw value 必须是有限数值。参数数量不匹配、定义缺失、
文件无法加载或反归一化失败时，应让 job preparation 明确失败，并进入现有
prepare-failure 隔离路径。不得悄悄把 normalized values 当作 raw values。

保留 `parameters_constraints.py` 中为 package import 与复制后同目录执行服务的
relative/import fallback 是可以的；这是两种执行位置，不是旧数据格式兼容。

### 2. 通过 `job_template.api` 保持模块边界

`evaluate_manager` 与 `job_template` 都是核心模块。根据项目规格，跨模块调用应通过
`job_template/api.py`，不要让 `evaluate_manager` 直接依赖
`parameters_constraints_class.py` 的内部实现。

建议让 `job_template.api` 提供一个清晰的“复制并物化本 job 参数”入口，或者扩展
现有 `copy_job_files()`，使其接收 normalized row 并返回同一批计算出的 raw values。
`evaluate_manager` 用返回值构造 `JobSpec.unnormalized_variables`，从而保证执行值与
记录值来自同一次物化。

实现仍需尊重 `prepare_job(..., job_template_dir=...)` 的实际模板目录。不要无条件
从已导入的默认 `project.job_template.api.TEMPLATE_DIR` 获取参数定义，导致自定义
模板目录的文件被忽略。

fresh load 可以使用类似参考版本的 `runpy.run_path()`，也可以使用其他不会复用旧
模块状态的结构化 Python 加载方式。需要注意 local 并行评估会并发 prepare job；
如果实现会临时修改 `sys.path` 或 reload 共享模块，必须加锁或改用线程安全的加载
方式。不要用没有并发保护的 `importlib.reload()` 形成新的竞态。

### 3. 修复当前参数 API 的陈旧缓存

只修 job writer 还不够。规格还要求：

```text
recorded_data/raw_variables
  -> 当前 job_template/parameters_constraints.py
  -> normalized_variables
```

因此 `job_template.api` 的以下参数相关查询不能永久绑定到首次 import 时的
`get_parameters`/`PARAMETERS`：

- `get_parameter_definitions()`；
- `get_parameter_metadata()`；
- `get_parameter_names()`；
- `get_variable_count()`；
- `normalize_variables()`；
- `denormalize_variables()`，如果该入口仍保留用于非 job 场景。

这些入口应看到当前磁盘定义，至少在文件发生变化后的下一次调用中刷新。测试必须
在同一个 Python 进程中先导入 API、再修改 fixture 参数范围、再调用 API，证明不需要
清理 `sys.modules` 或重启进程。

范围变化后历史 raw variables 可能落到新范围外。继续沿用当前明确的 normalize
策略并通过测试固定行为，不要借本任务改变历史继承政策。

### 4. 让 workflow 直接消费 job-local 参数文件

当前 HFSS workflow 应恢复为单一入口：

```python
hfss_app, *_ = solver_init(...)
set_hfss_temp_directory(hfss_app, TEMP_DIR)
set_para(hfss_app)  # 默认读取同目录 parameters_constraints.py
```

删除为 JSON 输入服务的参数拼装代码。纯 Python workflow 示例应通过
`get_parameters()` 读取 `parameter.value`，需要 mapping 时现场构造：

```python
variables = {parameter.name: parameter.value for parameter in get_parameters()}
```

不添加任何 `job_input.json`、`variables.json` 或 `parameters_values.py` fallback。

### 5. 保持 static hash 的任务定义语义

更新 `prepared_job_static_hash()`，使 job-local 参数文件中的 per-individual value
与 normalized value 不参与 hash，但参数名、ranges、unit 和 constraints 参与 hash。

不要简单把整个 `parameters_constraints.py` 排除在 hash 外，否则范围修改无法反映
在 static hash 中。也不要继续按文件原始字节 hash，否则每个 individual 都会得到
不同 hash。

语义签名的解析最好复用 `job_template` 的参数加载逻辑或 public metadata，避免再写
一套脆弱的 Python 文本处理器。

### 6. 删除错误实现，不写兼容层

核心运行路径中应删除以下内容：

- `project/evaluate_manager/job_files.py` 写 `job_input.json` 的代码；
- `HASH_EXCLUDED_NAMES` 中只为 `job_input.json` 存在的规则；
- 基于缓存 `job_template.api.denormalize_variables()` 生成 job JSON 的
  `_denormalize_variables()` 路径；
- 模块不可用时把 normalized values 原样当作 raw values 的静默 fallback；
- `project/job_template/worker_misc.py::load_variables()`；
- `load_variables()` 对 `variables.json`、`unnormalized_variables` 和 `raw_variables`
  的兼容读取；
- workflow 中 `_hfss_variables()`、`_write_parameter_values_file()`、
  `PARAMETER_VALUES_FILE` 及其清理代码；
- 核心 tests 与 docs 中把 `job_input.json` 描述为 job 输入合同的内容。

完成后，核心代码、核心测试和当前文档中不应再出现用于优化变量传递的
`job_input.json`。不要同时写新旧两套输入，也不要以“方便手工运行”为理由保留
`variables.json` 分支。

`project/tools/submit_*probe.py` 中也有名为 `job_input.json` 的探针私有 payload，
其中部分传递的是脚本名或探针 metadata，而不是 optimizer 参数。这些 tools 不属于
核心运行合同。不要只按文件名盲删；先判断其用途。本任务的验收搜索范围至少包括
`project/evaluate_manager/`、`project/job_template/`、`project/test/`、`user_doc/`
和当前 `dev_doc/`。

临时目录和已生成的历史 job 是证据/运行产物，不需要迁移，也不要为它们添加兼容。

### 7. 保留用户当前任务定义

当前 `project/job_template/parameters_constraints.py` 有未提交的范围修改，而且当前
参数集合与测试中硬编码的旧任务参数集合不一致。实现时必须在其当前内容上增加所需
字段/合同，不得恢复旧范围、旧参数列表或覆盖用户修改。

`project/test/test_optimize_parameter_count.py` 目前硬编码了旧任务的 19 个参数，
而当前模板是另一组参数。实现时应让该测试与当前任务定义一致，或改为验证 API 与
源文件一致，不能为了让旧断言通过而回滚模板。

## Expected File Impact

实现者至少应检查并按实际设计更新以下文件：

- `project/job_template/parameters_constraints_class.py`
- `project/job_template/parameters_constraints.py`
- `project/job_template/api.py`
- `project/job_template/workflow.py`
- `project/job_template/worker_misc.py`
- `project/evaluate_manager/job_files.py`
- `project/test/test_job_static_hash.py`
- `project/test/test_htcondor_distributed_mode.py`
- `project/test/test_real_local_pipeline.py`
- `project/test/test_recorded_data_contract.py`
- `project/test/test_optimize_parameter_count.py`
- `project/tools/hfss_get_para_and_range.py`
- `project/tools/hfss_get_para_and_range_direct.py`

参数生成工具只有在新 `Parameter` 构造格式需要 assigned-value 字段时才必须改生成
文本，但无论是否依赖默认值，都要增加/更新测试，确保生成的 canonical 文件能被新
loader 和 job materializer 使用。

实现后还应更新当前合同文档，至少包括：

- `dev_doc/architecture/4plus1_process_view.md`
- `dev_doc/architecture/c4_component.md`
- `dev_doc/architecture/4plus1_scenarios.md`
- `dev_doc/blueprints/00_project.md`
- `dev_doc/blueprints/10_modules/job_template.md`
- `dev_doc/blueprints/10_modules/evaluate_manager.md`
- `dev_doc/blueprints/10_modules/jobs_runtime.md`
- `dev_doc/terminology.md`
- `user_doc/optimization_workflow.md`
- `user_doc/workflow_typical_patterns.md`
- `user_doc/com_lib/test_com.md`

尤其要删除这些当前错误描述：job 包含 `job_input.json`、workflow 从
`job_input.json`/`variables.json` 读取变量、`job_input.json` 是 static-hash 运行时
排除项。

完成代码与当前文档更新后，按 `dev_doc/README.md`：

1. 添加一份 `dev_doc/change_records/` 变更记录。
2. 将本待办移动到 `dev_doc/obsolete/`，不要让已完成任务继续留在 `toDo/`。

## Verification

默认验证不得启动真实 HFSS。至少增加以下自动化覆盖。

### 参数对象测试

- 连续 range 的端点、中点和 clip 行为正确。
- 离散 range 和混合 ranges 的分段行为正确。
- job assigned normalized value 能生成并保存对应 raw `value`。
- 参数数量不匹配、空 ranges 和非有限 assigned value 明确失败。
- 当前 raw-to-normalized 行为仍满足 recorded-data 合同。

### 同进程热更新回归测试

在一个测试进程内执行完整顺序：

1. 导入 `project.job_template.api` 或等价长期存活入口。
2. 用 fixture canonical 参数范围创建第一个 job。
3. 不清理 `sys.modules`，修改同一 canonical 文件中的范围。
4. 创建第二个 job。
5. 读取第二个 job 的 `parameters_constraints.py`。
6. 断言 ranges 和 assigned raw value 都来自修改后的定义。
7. 断言第二个 job 中不存在 `job_input.json` 和 `parameters_values.py`。

这个测试必须能复现并阻止本文件“已复现的现象”中的 split-brain 问题。

### job 文件与 static hash 测试

- 两个 normalized rows 不同但 task definition 相同的 job，static hash 相同。
- 参数 ranges、name、unit 或 constraints 任一变化，static hash 改变。
- job-local 参数文件中的 assigned value 与 `JobSpec.unnormalized_variables` 一致。
- prepared job 不包含 `job_input.json`、`variables.json`、`parameters_values.py`、
  `calc_cost.py` 或 `cost.json`。

### workflow 与 adapter 测试

- 不启动 AEDT，直接用 `hfss_com._load_parameters_py_value_only()` 或 monkeypatch
  `set_para()`，验证 job-local 参数文件能生成正确的 name/value/unit 映射。
- workflow 的参数路径不调用 `worker_misc.load_variables()`，也不生成临时参数文件。
- synthetic workflow/示例只读取 job-local `parameter.value`。

### local、distributed 与记录合同测试

- local prepare/run/finalize 使用 job-local assigned values，并把同一 raw values
  记录到 `recorded_data`。
- HTCondor `transfer_input_files` 包含 `parameters_constraints.py` 和
  `parameters_constraints_class.py`，不包含 `job_input.json`。
- `job.sub` 仍直接执行 `workflow.py`，不恢复 interpreter-as-executable 或 cost 文件。
- 同一进程修改 canonical ranges 后，`recorded_data.get_normalized_variables()` 的下一次
  调用使用新范围重新解释历史 raw variables。
- prepare failure、local failure 和 distributed failure 仍隔离为单个 individual 的
  metadata/`inf` 结果，不让整代崩溃。

建议验证命令：

```powershell
pytest -q
```

如果完整套件受当前任务的真实 HFSS 资源或其他无关工作区修改影响，至少运行本任务
直接相关的测试文件，并在变更记录中说明未运行或失败的无关项。不要在默认测试中
启动 HFSS。

## Completion Rule

同时满足以下条件才算完成：

- 长期运行的 Python 进程无需重启；编辑 canonical 参数范围后，下一个新 job 的
  job-local ranges 与 assigned raw values 都使用新定义。
- `parameters_constraints.py` 是每个 job 的唯一变量定义和值输入。
- 核心运行路径不创建、读取或传输 `job_input.json`、`variables.json` 或
  `parameters_values.py`。
- workflow 直接消费 job-local 参数对象的 assigned values。
- `JobSpec`、执行值与 recorded raw variables 来自同一次参数物化，不会分叉。
- static hash 忽略 per-individual assigned values，但能检测参数定义和约束变化。
- `recorded_data` 在同一进程中按当前范围动态归一化历史 raw variables。
- local 与 distributed 合同均有不依赖真实 HFSS 的自动化测试。
- 当前 architecture、blueprints、terminology 和 user docs 已删除旧 JSON 参数传递描述。
- 已添加 change record，本文件已移入 `dev_doc/obsolete/`。
