# yadot v3 后续实施计划 v3

## 本轮已完成

### recorded_data 模块拆分与 Git 跟踪策略

- 将 `project/recorded_data/api.py` 拆成简洁 public facade，并把实现拆到 `paths.py`、`manifest_store.py`、`rawdata_store.py`、`records.py`、`query.py`、`utils.py`。
- `api.py` 继续导出原有 public API，兼容现有测试中对 `MODULE_DIR`、`MANIFEST_PATH`、`RAWDATA_ROOT` 的 monkeypatch 用法。
- `.gitignore` 保持只忽略 generated data：`manifest.json`、manifest lock/tmp、`rawData/**`、`__pycache__`、`.pyc`；`recorded_data` 下的 Python 源码和 `rawData/.gitkeep` 仍可被 Git 跟踪。

### Step 5: rawData contract helper 基线

- 新增 `project/job_template/rawdata_contract.py`，集中处理 rawData `.npz` 的加载、metadata 解析、shape/axis 校验和 rawData 根目录 flat 约束。
- `calc_cost.py` 改为复用 rawData contract helper，不再自带分散的 metadata/load helper。
- `workflow.py` 在写出 rawData 后调用目录级校验，保证默认 pipeline 输出满足 contract。
- 新增 `project/test/test_rawdata_contract.py`，覆盖 metadata 缺失、shape 不一致、rawData 子目录等失败场景。

### metadata 与 job_static_hash 保留

- `project/evaluate_manager/local_runner.py` finalization 时会先读取已有 `metadata.json` 或 `metaData.json`，再合并运行状态字段，避免覆盖 `prepare_job()` 写入的 `job_static_hash`。
- `project/test/test_real_local_pipeline.py` 增加回归断言，确保 recorded record 的 `job_metadata` 中保留 `job_static_hash`。

### Step 10: HFSS backend 文件迁移，暂不接入 workflow

- 从 reference 迁移 `hfss_com.py` 到 `project/job_template/hfss_com.py`。
- 只做必要兼容修改：模块说明明确它是 optional adapter；导出 `.npz` 时同时保留旧 `meta` 和 v3 风格 `metadata` 字段。
- 未修改默认 `workflow.py` 去调用 `hfss_com`，默认测试也不会 import PyAEDT 或启动 HFSS。

## 本轮验证

- `pytest -q`：24 passed。
- `python -m compileall -q project\job_template project\recorded_data project\evaluate_manager`：通过。
- `git status --short --ignored -uall project\recorded_data`：源码文件可见，`manifest.json`、rawData 数据文件和 pycache 均为 ignored。

## 尚未完成内容

### Step 5: rawData contract 深化

- 继续把 contract 对齐真实 HFSS 输出：更完整的 axis metadata、unit/frequency/polarization 语义、far-field matrix 形状约定。
- 增加 schema version 和向后兼容策略；旧 rawData 或不兼容 rawData 应能被明确跳过或给出可诊断错误。
- 考虑在 `recorded_data` 写入时也进行轻量 rawData contract 校验，避免坏数据进入长期记录。

### Step 6: 接入 HTCondor distributed 最小版

- 新增 Condor submit/runner 内部模块，复用 `prepare_job()`、shared finalization 和 `recorded_data` 写入。
- submit 文件沿用已验证的 Windows 模式：`executable = workflow.py`、`transfer_executable = True`、sandbox env、stdout/stderr/log、cluster id。
- 成功判定仍以 rawData `.npz` 存在为准，不读取 `cost.json`。
- timeout 需要尝试 `condor_rm`，并记录 log tail、cluster id、submit stdout/stderr。
- 默认 pytest 只能 mock HTCondor，不依赖真实 Condor 环境。

### Step 7: 优化恢复与多代入口

- 增加 `run_generations()`，循环调用当前 `run_one_generation()`。
- 每代后依赖 `recorded_data` 恢复，不要求完整 optimizer checkpoint。
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

### Step 10: 真实 HFSS backend 后续接入边界

- 本轮只迁移了 `hfss_com.py` 文件，尚未把真实 HFSS backend 接到默认 pipeline。
- 后续接入时必须继续遵守新要求：默认 `workflow.py` 不直接改成调用 `hfss_com`；默认 `pytest -q` 不启动 HFSS。
- 真实 HFSS 测试需要单独标记，并在无 HFSS/PyAEDT 环境时自动 skip。
- workflow 仍应只负责导出 rawData；`calc_cost.py` 才负责目标计算。
- 还需要保留/验证 far-field full matrix 重建、axis metadata、solver cleanup、per-job temp/home 隔离。
