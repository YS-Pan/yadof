# yadot v3 后续实施计划 v4

## 本轮已完成

### Step 5: 通用 rawData contract

- `project/job_template/rawdata_contract.py` 已改为通用 N 维数组 contract，不绑定 HFSS、频率、极化或其它仿真语义。
- rawData item 主数组使用 `values`，兼容 `data`；`metadata.shape` 为必需项，并与主数组 shape 严格一致。
- `metadata.axes` 改为按轴序号排列的 descriptor list，只校验 `index`、`size` 和可选 `values_key`。`name`、`unit`、`description` 只作为说明，不参与框架逻辑。
- 默认 `test_com.py` 输出的 `curve`、`surface` 等 rawData 已改为 `axis_0`、`axis_1` 这类通用轴数组，并保持每个 rawData item 的轴顺序稳定。
- `recorded_data` 写入时拒绝 nested rawData 目录；读取历史 cost 时会跳过不兼容旧 rawData，而不是让整个历史读取崩溃。
- `get_surrogate_training_data()` 也会跳过不兼容旧 rawData，避免旧样本破坏 surrogate 训练入口。

### Step 7: 优化恢复与多代入口

- 新增 `project/optimize/api.run_generations()`，可循环运行多代，并在每代后重新依赖 `recorded_data` 读取历史结果。
- 新增 `project/optimize/runner.py`，写入轻量 optimize metadata 到 `project/optimize/checkpoints/<run_id>/`。
- optimize metadata 只记录 run/generation/source/population/job names/timestamps/diagnostics，不保存 cost 派生文件。
- `.gitignore` 已加入 `/project/optimize/checkpoints/`，运行 metadata 默认不进入 Git。

### Step 9: 默认无 surrogate 的 NSGA-III 模式

- `project/config.py` 中 `OPTIMIZE_SURROGATE_ENABLED` 默认改为 `False`。
- 新增 `project/optimize/nsga3.py`，默认优化路径使用不依赖 surrogate 的轻量 NSGA-III 思路。
- 保留 `run_one_generation()` 兼容入口：默认走 NSGA-III；显式 `use_surrogate=True` 或 mode 选择 surrogate 时仍走现有 GPSAF 路径。
- NSGA-III 模式支持历史 warm start、历史不足随机补齐、历史足够时生成 offspring，并只通过 `evaluate_manager.api` 做真实评估。

### viewCost 工具迁移

- 新增 `project/tools/viewCost.py`，迁移旧工具的成本趋势/Pareto 摘要能力。
- 新工具只读取 `recorded_data.api.get_historical_results()` 和 `list_records()`，不再读取旧的 `para_cost.jsonl`、`optMeta.jsonl`、`indMeta.jsonl`。
- cost 仍由 `recorded_data -> job_template/calc_cost.py` 动态计算，不生成或保存 cost 文件。
- 工具使用 matplotlib `Agg` backend，支持 headless 保存 PNG，也支持 `--summary-only` 只打印摘要。

### HFSS 默认流程边界

- `hfss_com.py` 仍保留在 `project/job_template/` 作为 optional adapter。
- 默认 `workflow.py` 没有调用 `hfss_com.py`。
- 默认 `copy_job_files()` 已排除 `hfss_com.py`，新生成 job 不再复制 HFSS 适配文件。
- 默认测试和本轮优化验证都没有启动 HFSS。

## 本轮验证

- `pytest -q`：42 passed。
- `python -m compileall -q project\optimize project\job_template project\recorded_data project\tools`：通过。
- 执行一次默认优化：
  - `run_generations(1, population_size=4, random_seed=20260510, run_id="manual_verify")`
  - 结果：默认 NSGA-III、无 surrogate、local evaluate，生成 4 个有效样本。
- 修改 job copy 后再次执行小优化：
  - `run_generations(1, population_size=1, random_seed=20260511, run_id="manual_verify_after_copy")`
  - 新 job：`job_20260510_200841_285567`
  - 验证：该 job 中没有 `hfss_com.py`。
- `python -m project.tools.viewCost --summary-only`：成功读取 5 条有效历史结果并输出 Pareto 摘要。
- 当前真实 `recorded_data` 中旧 axes mapping 样本会被跳过，新样本可进入 optimization history 和 surrogate training data。

## 尚未完成内容

### Step 5 后续深化

- 为 rawData metadata 增加显式 schema version 和迁移策略。
- 为 skipped/incompatible rawData 增加更完整的诊断查询接口，例如返回 job name、文件名、错误原因。
- 对真实仿真输出的大型数组、稀疏数组、复数数组、分块数组等场景继续扩展 contract。

### Step 6: HTCondor distributed 最小版

- 尚未实现 Condor submit/runner 内部模块。
- 仍需复用 `prepare_job()`、shared finalization 和 `recorded_data` 写入。
- timeout、`condor_rm`、cluster id、stdout/stderr/log tail 等分布式诊断仍未接入。
- 默认 pytest 仍应只 mock HTCondor，不依赖真实 Condor 环境。

### Step 8: surrogate baseline 稳固

- surrogate checkpoint restore 仍不完整。
- 需要从最新 checkpoint/model 恢复当前 surrogate 状态。
- rawData schema 不兼容时已能在 training data 层跳过一部分样本，但 surrogate 内部仍需要更系统的降级策略和诊断。
- historical error 已按相对误差思路存在，但还需要结合 checkpoint restore 做持续验证。

### Step 9 后续 GPSAF/NSGA-III 完整策略

- 本轮只新增默认无 surrogate 的 NSGA-III 路径，未修改 GPSAF 内部细节。
- 仍需继续吸收 `20260418 shorten` 中 alpha/beta/gamma、候选去重、uncertainty/residual 选择策略。
- NSGA-III 当前是轻量实现；后续可继续向 reference 中更成熟的 DEAP 流程靠拢，包括 population size/reference points 的完整配置体验。

### Step 10: 真实 backend 后续接入

- 真实 HFSS backend 仍未接入默认 pipeline。
- 后续接入时仍需遵守边界：默认 workflow 不直接改成调用 `hfss_com`，默认 `pytest -q` 不启动 HFSS。
- 真实 HFSS 测试需要单独标记并在无 HFSS/PyAEDT 环境时 skip。
- workflow 继续只负责导出 rawData；`calc_cost.py` 才负责目标计算。
