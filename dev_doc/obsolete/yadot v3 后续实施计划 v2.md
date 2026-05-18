# yadot v3 后续实施计划 v2

## 本轮已完成

### 集成收尾

- 修复裸 `pytest -q` 误收集 `project/test/_pytest_tmp_*` 的问题：在 `pyproject.toml` 增加 `norecursedirs`，覆盖 `_pytest_tmp*`、`_tmp_runtime`、`_contract_tmp` 等测试运行产物目录，并补充 `pythonpath = ["."]`。
- 修复根 `.gitignore` 对 `/project/recorded_data/` 的过度忽略：现在只忽略 generated `manifest.json`、`manifest.json.lock`、`rawData/**`、`__pycache__` 和 `.pyc`，允许 `project/recorded_data/api.py`、`__init__.py`、`rawData/.gitkeep` 等 source/control files 被 `git status` 看见。

### Step 1: recorded_data 存储契约

- 已加入 recorded_data manifest schema、状态字段、时间戳、completed/error/timeout 状态区分。
- 已覆盖 completed 进入 optimization history，error/timeout 默认不进入 history/training。
- 已覆盖重复 job、旧 manifest 升级、并发写 manifest 等测试。
- 已保持 v3 原则：recorded_data 不长期保存 cost，不保存 normalized variables。

### Step 2: evaluate_manager 失败隔离

- `evaluate_population()` 已对 prepare/run/record 阶段做 per-individual 隔离。
- 单个 individual 失败时返回 `inf` cost，并尽力写入 error record metadata。
- record 阶段失败不会中断整代评估。

### Step 3: 配置统一与变量维度来源

- `evaluate_manager` 默认 jobs dir 改为调用时读取 `project.config.JOBS_DIR`。
- timeout/mode 提供统一默认读取入口。
- optimizer 随机首代变量维度优先来自 `project.job_template.api.get_parameter_names()`，显式 `variable_count` 仍可覆盖。

### Step 4: job_static_hash 与 run metadata

- `prepare_job()` 已写入 `metadata.json` 和兼容名 `metaData.json`。
- `job_static_hash` 已基于 prepared job 的静态文件生成。
- hash 已排除 `job_input.json`、metadata、rawData、cache、临时目录、cost artifact 等运行产物。
- 已覆盖 individual 值变化不影响 hash、workflow/参数定义变化会改变 hash、hash 进入 metadata 的测试。

## 验证结果

- 裸命令验证：`pytest -q`
- 结果：`20 passed in 1.63s`
- 额外确认：`git status --ignored --short project/recorded_data` 中，`project/recorded_data/` 重新作为未跟踪源码目录出现；generated manifest/rawData/cache 仍被忽略。

## 已知风险

- `project/recorded_data` 现在需要纳入版本追踪，否则 `api.py`、`__init__.py` 等核心模块仍可能在协作时缺失。
- `local_runner` 后续如果在 workflow 结束时重写 metadata，可能覆盖 prepare 阶段写入的 `job_static_hash`；需要加一条回归测试或在 finalization 时合并已有 metadata。
- 当前 `job_static_hash` 来自 prepared job 快照，已能覆盖本地最小闭环，但真实 HFSS/backend 引入后，模型文件、COM 适配脚本、参数约束和关键配置的边界还要重新审计。
- 当前 distributed/HTCondor 仍是 stub，没有真实 submit、poll、timeout、log tail、condor_rm 逻辑。
- surrogate checkpoint restore 未完成；当前 surrogate baseline 还不能保证新进程从最新 checkpoint 恢复。
- 测试运行会继续产生 `_pytest_tmp*` 目录；现在 pytest 不再误收集它们，但是否清理仍属于 housekeeping，不应作为测试通过前提。

## 尚未完成内容

### Step 5: 建立 rawData contract helper

- 提供轻量 rawData metadata/axis/shape 读取与校验 helper。
- 保持 `rawData/` flat root 约束。
- 对 `.npz` 缺 metadata、shape 不一致、rawData 子目录等情况给出明确失败。
- 先服务当前 `test_com.py` 与未来 `calc_cost.py`，暂不接真实 HFSS。

### Step 6: 接入 HTCondor distributed 最小版

- 新增 Condor submit/runner 内部模块。
- 复用 `prepare_job()`、shared finalization、recorded_data 写入。
- submit 文件采用已验证的 Windows 模式：`executable = workflow.py`、`transfer_executable = True`、sandbox env、stdout/stderr/log、cluster id。
- 成功判定以 rawData `.npz` 存在为准，不读 `cost.json`。
- timeout 需要尝试 `condor_rm`，记录 log tail、cluster id、submit stdout/stderr。
- 默认 pytest 只能 mock HTCondor，不依赖真实环境。

### Step 7: 优化恢复与多代入口

- 增加 `run_generations()`，循环调用当前 `run_one_generation()`。
- 每代后依赖 recorded_data 恢复，不要求完整 optimizer checkpoint。
- 保存轻量 optimization run metadata，不保存 cost 派生文件。
- 历史不足时随机补齐，历史足够时 warm start。

### Step 8: 稳固当前 surrogate baseline

- 增加从最新 checkpoint/model 恢复的读取入口。
- rawData schema 不兼容时降级：跳过不兼容样本或返回 surrogate unavailable，不让 optimize 崩溃。
- historical error 明确使用相对误差。
- 保持 `predict_population() -> (costs, intervals)` API 不变。

### Step 9: 引入 GPSAF/NSGA-III 更完整策略

- 吸收 `20260418 shorten` 中 alpha/beta/gamma、候选去重、uncertainty/residual 选择思路。
- 保留 `20260403` 的 NSGA-III population size/reference points 经验。
- optimizer 不直接调用 workflow 或 synthetic evaluator；真实评估只走 `evaluate_manager.api`。
- surrogate 不可用时回退可解释 baseline。

### Step 10: 后续迁移真实 HFSS backend

- 从 `20260403 hfss_com.py/workflow.py` 迁移 PyAEDT 适配经验。
- 保留 far-field full matrix 重建、axis metadata、solver cleanup、per-job temp/home 隔离。
- 严格拆分：`workflow.py` 只导出 rawData，`calc_cost.py` 才计算目标。
- 真实 HFSS 测试单独标记，不作为默认 `pytest -q` 依赖。
