# yadot v3 后续实施计划 v5

## 本轮已完成

### 1. NSGA-III 简单迁移与瘦身

- `project/optimize/nsga3.py` 已改回入口脚本形态，当前约 2401 bytes / 69 行，接近 `reference/20260403 fanyufei/code/optimize.py` 的规模。
- 大部分辅助逻辑拆到 `project/optimize/nsga3_misc.py`，避免把旧项目的 misc/helper 内容全部塞进入口文件。
- 默认优化仍是不使用 surrogate 的 NSGA-III 路径。
- `OPTIMIZE_NSGA3_P_CAP` 已从 `config.py` 删除，reference point order 不再设置人为上限。

### 2. optimize 从 job_template 查询问题规模

- `config.py` 中已删除 `OPTIMIZE_VARIABLE_COUNT`、`OPTIMIZE_OBJECTIVE_COUNT`。
- 新增 `project/optimize/problem_info.py`，优化开始前通过 `project.job_template.api` 查询问题信息。
- `project/job_template/api.py` 新增：
  - `get_variable_count()`
  - `get_objective_count()`
  - `get_objective_names()`
- 当前默认 `parameters_constraints.py` 提供 10 个优化变量，`calc_cost.py` 提供 1 个目标：`default_cost`。

### 3. Step 9: GPSAF 最小可运行迁移

- `project/optimize/gpsaf.py` 已瘦身到约 3005 bytes / 103 行。
- GPSAF 辅助逻辑拆到：
  - `project/optimize/gpsaf_misc.py`
  - `project/optimize/gpsaf_phases.py`
- 已迁移一个轻量 GPSAF 流程：
  - surrogate train / predict / historical error 入口
  - alpha 多批候选比较
  - beta cluster 扩展
  - gamma 概率替换
  - probabilistic knockout
  - candidate 去重
- 修复了一个集成问题：`config.OPTIMIZE_SURROGATE_ENABLED=False` 只控制默认模式；显式 `use_surrogate=True` 或 `mode="gpsaf"` 时，GPSAF 不会再被默认配置禁用。

### 4. Step 5 后续深化

- rawData metadata 增加 `schema_version`，当前版本为 `1`。
- `workflow.py` 生成的 rawData 会自动写入 schema version。
- `recorded_data.api.get_rawdata_diagnostics()` 已加入，可返回 job name、文件名、路径、状态和错误原因。
- 历史 cost 读取和 surrogate training data 读取会跳过 legacy / unsupported / bad rawData，而不是让整个流程失败。
- 按本轮新要求，未扩展大型数组、稀疏数组、复数数组、分块数组等场景。

### 5. generated data / gitignore

- `project/recorded_data/` 中的数据文件仍被忽略，代码文件仍可被 Git 跟踪。
- `project/tools/cost_*.png` 已加入 `.gitignore`，viewCost 生成的图片不会再作为普通 untracked 文件出现。
- `project/optimize/checkpoints/`、`project/jobs/` 等运行产物仍被忽略。

## 本轮验证

- `pytest -q`：51 passed。
- `python -m compileall -q project\optimize project\job_template project\recorded_data project\tools`：通过。
- `project.job_template.api` 当前返回：
  - variable count: 10
  - objective count: 1
  - objective names: `("default_cost",)`
- 文件尺寸检查：
  - `project/optimize/nsga3.py`: 2401 bytes
  - `project/optimize/gpsaf.py`: 3005 bytes
- 默认 NSGA-III 本地优化验证：
  - 命令：`run_generations(1, run_id="verify_v5_nsga3")`
  - 结果：`nsga3_random 100 100 10 1 False`
  - 含义：100 个体、100 条 cost、10 变量、1 目标、未使用 surrogate。
- GPSAF surrogate smoke 验证：
  - 命令：`run_generations(1, start_generation=2, population_size=8, use_surrogate=True, run_id="verify_v5_gpsaf_smoke2")`
  - 结果：`gpsaf_surrogate 8 8 True`
  - diagnostics 包含 alpha/beta/gamma 相关统计。
- `python -m project.tools.viewCost --summary-only`：成功读取 132 条历史结果并输出 Pareto 摘要。

## 现在手动运行完整优化

默认无 surrogate，使用当前 `config.py` 的 100 个体：

```powershell
python -c "from project.optimize.api import run_generations; run_generations(1, run_id='manual_nsga3')"
```

运行多代：

```powershell
python -c "from project.optimize.api import run_generations; run_generations(10, run_id='manual_nsga3_10gen')"
```

显式运行 GPSAF / surrogate 模式：

```powershell
python -c "from project.optimize.api import run_generations; run_generations(1, start_generation=1, use_surrogate=True, run_id='manual_gpsaf')"
```

查看结果摘要：

```powershell
python -m project.tools.viewCost --summary-only
```

保存可视化 PNG：

```powershell
python -m project.tools.viewCost -o project/tools/cost_manual.png
```

本轮验证已经生成了一批 ignored runtime data。若需要从完全空历史重新评估，需要清理 `project/jobs/`、`project/recorded_data/manifest.json`、`project/recorded_data/rawData/` 和相关 `project/optimize/checkpoints/verify_v5_*` 目录。

## 尚未完成内容

### Step 6: HTCondor distributed 最小版

- 尚未实现 Condor submit / runner 内部模块。
- 仍需复用 `prepare_job()`、shared finalization 和 `recorded_data` 写入。
- timeout、`condor_rm`、cluster id、stdout/stderr/log tail 等分布式诊断仍未接入。
- 默认 pytest 仍应只 mock HTCondor，不依赖真实 Condor 环境。

### Step 8: surrogate baseline 稳固

- surrogate checkpoint restore 仍不完整。
- 需要从最新 checkpoint/model 恢复当前 surrogate 状态。
- rawData schema 不兼容时 training data 层已经能跳过坏样本，但 surrogate 内部还需要更系统的降级策略和诊断。
- historical error 已能进入 GPSAF，但仍需结合 checkpoint restore 和真实多代优化做持续验证。

### Step 9: GPSAF/NSGA-III 后续完善

- 当前 GPSAF 是最小可运行迁移，还需要和 `reference/20260418 shorten/code` 的完整行为继续对齐。
- GPSAF 仍缺少正式 constraint/feasibility API；如果要贴近 “constrained single- and multi-objective optimization”，job_template 需要继续暴露 constraint count、constraint names、constraint violation 或 feasibility 信息。
- 当前真实验证仍是 1 目标；需要增加 2+ 目标的 job_template/calc_cost 测试，确认 NSGA-III reference points、GPSAF selection、viewCost 都能稳定处理多目标。
- NSGA-III 目前是轻量实现；后续可继续靠近 reference 的成熟 DEAP 流程，但入口文件应继续保持瘦身，复杂逻辑放在 misc/helper 模块。

### Step 10: 真实 backend 后续接入

- 真实 HFSS backend 仍未接入默认 pipeline。
- 后续只应迁移真实 backend 所需文件并做必要适配，默认 workflow 不应直接改成调用 `hfss_com`。
- 默认 `pytest -q` 不应启动 HFSS。
- 真实 HFSS 测试需要单独标记，并在无 HFSS/PyAEDT 环境时 skip。
- workflow 继续只负责导出 rawData；`calc_cost.py` 才负责目标计算。

### spec v4.md 状态

- 本轮任务提到 `spec v4.md`，但当前根目录没有这个文件，目录中只有 `spec v3.md`。
- 因此本轮没有应用任何来自 `spec v4.md` 的新增细节；后续若加入该文件，需要重新阅读并把差异合并到计划中。
