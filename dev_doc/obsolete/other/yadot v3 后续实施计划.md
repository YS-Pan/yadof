# yadot v3 后续实施计划

## Summary

当前 `project/` 已经不是空框架，而是一个可运行的 v3 最小闭环：`optimize -> evaluate_manager -> job_template/workflow -> recorded_data -> calc_cost -> surrogate` 已打通，现有 `pytest -q` 为 `6 passed`。  
架构上方向正确，但下一步不能急着搬旧项目的大块代码。优先级应是先把“可恢复、可失败、可中途修改”的底座做稳，再接 HTCondor 和更重的 surrogate。

核心判断：

- 保留 v3 原则：job/workflow 只产 rawData，不保存 `cost.json`。
- 迁移旧项目经验，不迁移旧项目耦合结构。
- `20260403 fanyufei` 主要提供 job snapshot、metadata、HFSS/rawData contract、worker 生存性经验。
- `20260124 combined` 主要提供 HTCondor Windows submit/debug 经验。
- `20260418 shorten` 主要提供 GPSAF/surrogate refresh/INR ensemble 思想，但 archive schema 不能照搬，因为它长期保存 cost。

## Key Changes

1. 稳固当前五大核心 API

- 固定 `recorded_data.api` 的正式函数名，不再依赖多候选适配。
- 固定 `evaluate_manager.api.evaluate_population()` 的失败语义：单个 individual 失败返回 `inf` cost，并写入 error record。
- 让 `optimize` 的变量维度来自 `job_template` 或历史数据，不再依赖单独的 `OPTIMIZE_VARIABLE_COUNT`。
- 让 `evaluate_manager` 默认配置统一读取 `project.config.JOBS_DIR`、timeout、mode。

2. 先补可靠性，再补能力

- 第一步做 `evaluate_manager + recorded_data`，因为这是分布式、恢复、surrogate 训练的共同地基。
- 第二步做 job snapshot/hash 和 metadata，吸收 `20260403` 的 `job_static_hash`。
- 第三步增强 local failure/timeout 测试。
- 第四步再接 HTCondor distributed runner。
- 第五步再升级 surrogate 和 optimize。

3. 后续小步开发顺序

### Step 1: 强化 recorded_data 存储契约

涉及模块：`project/recorded_data`

实现：

- 给 manifest 增加 schema version、写入时间、记录状态字段规范。
- 增加原子写和简单文件锁，避免并发写 manifest 丢数据。
- 明确 completed/error/timeout 记录都可保存 raw variables、job metadata；只有 completed 默认参与 history/training。
- 保持不保存 cost、不保存 normalized variables。

测试：

- completed 记录可动态返回 history。
- error/timeout 记录不会进入默认 optimization history。
- manifest 重复 job、空 manifest、损坏 manifest 有明确错误或恢复行为。

### Step 2: 强化 evaluate_manager 失败隔离

涉及模块：`project/evaluate_manager`

实现：

- `evaluate_population()` 对每个 individual 做顶层 try/except。
- job 创建失败、模板复制失败、workflow 失败、无 rawData、recorded_data 写入失败，都转成单个 failed result。
- failed result 写 metadata，并返回 `(inf,)` 或按目标数量返回 `inf` tuple。
- 抽出 shared finalization helper，后续 local/distributed 共用。

测试：

- 单个 workflow 抛异常时整代继续。
- 单个 job 无 `.npz` 时整代继续。
- recorded_data 写入失败时有清晰 metadata 和返回值。

### Step 3: 统一配置与变量维度来源

涉及模块：`project/config.py`、`project/evaluate_manager`、`project/optimize`

实现：

- `evaluate_manager` 默认 jobs dir 使用 `project.config.JOBS_DIR`。
- optimizer 随机第一代的 variable count 从 `job_template.api.get_parameter_names()` 得到。
- 历史记录存在时优先用历史维度；无历史时用当前参数定义。
- 保留 config 里的 population size、seed、GPSAF 参数。

测试：

- 修改 `PARAMETERS` 数量后，随机第一代宽度自动匹配。
- config jobs dir monkeypatch 后 evaluate_manager 使用新路径。

### Step 4: 加入 job_static_hash 与 run metadata

涉及模块：`project/evaluate_manager/job_files.py`、可选 `project/job_template/api.py`

实现：

- 从 `20260403 prepare_job.py` 迁移 hash 思路。
- hash 包含 workflow、test_com 或未来 `_com.py`、模型文件、参数范围/单位/约束、关键配置。
- hash 排除 rawData、metadata、cache、具体 individual 值、cost artifact。
- 写入 job metadata，并由 recorded_data 长期保存。

测试：

- individual 值变化不改变 static hash。
- workflow 或参数范围变化会改变 static hash。
- hash 字段进入 recorded_data record。

### Step 5: 建立 rawData contract helper

涉及模块：`project/job_template`

实现：

- 提供轻量 rawData metadata/axis/shape 读取与校验 helper。
- 先不接 HFSS，只服务当前 `test_com.py` 与未来 `calc_cost.py`。
- 保留 `rawData/` flat root 约束。
- 为未来 HFSS 的 far-field/grid/trace contract 留出清晰入口。

测试：

- `.npz` 缺 metadata、shape 不一致、rawData 子目录，均有明确失败。
- 当前 test workflow 仍通过。

### Step 6: 接入 HTCondor distributed 最小版

涉及模块：`project/evaluate_manager`

实现：

- 新增 Condor submit/runner 内部模块。
- 复用 `prepare_job()`、shared finalization、recorded_data 写入。
- submit 文件采用已验证的 Windows 模式：`executable = workflow.py`、`transfer_executable = True`、sandbox env、stdout/stderr/log、cluster id。
- 成功判定改为 rawData `.npz` 存在，不读 `cost.json`。
- timeout 尝试 `condor_rm`，记录 log tail、cluster id、submit stdout/stderr。

测试：

- 无 HTCondor 环境下 distributed 测试可 mock。
- submit 文件内容符合 reference 中验证过的 Windows 经验。
- condor log terminal markers 能转成 done/error/timeout metadata。

### Step 7: 优化恢复与多代入口

涉及模块：`project/optimize`

实现：

- 增加 `run_generations()`，循环调用当前 `run_one_generation()`。
- 每代后依赖 recorded_data 恢复，不要求完美 optimizer checkpoint。
- 保存轻量 optimization run metadata，不保存 cost 派生文件。
- 历史不足时随机补齐，历史足够时 warm start。

测试：

- 连跑多代后可从 recorded_data 继续。
- 中途手动清空最后未完成 job 不影响继续。
- surrogate 失败时退回 history/random 生成。

### Step 8: 稳固当前 surrogate baseline

涉及模块：`project/surrogate`

实现：

- 增加从最新 checkpoint/model 恢复的读取入口。
- rawData schema 不兼容时降级：跳过不兼容样本或返回 surrogate unavailable，而不是让 optimize 崩。
- historical error 明确使用相对误差。
- 保持 `predict_population() -> (costs, intervals)` API 不变。

测试：

- checkpoint 写出后新进程可恢复。
- rawData shape/key 变化时不会打断真实评估。
- 小 cost 和大 cost 的同等比例误差返回同等量级 relative error。

### Step 9: 引入 GPSAF/NSGA-III 更完整策略

涉及模块：`project/optimize`

实现：

- 从 `20260418 shorten` 吸收 alpha/beta/gamma、候选去重、uncertainty/residual 选择思想。
- 从 `20260403` 保留 NSGA-III population size/reference points 经验。
- 不让 optimizer 直接调用 workflow 或 synthetic evaluator。
- 所有真实评估仍只走 `evaluate_manager.api`。

测试：

- 有历史和 surrogate 时走 GPSAF candidate path。
- surrogate 不可用时退回可解释 baseline。
- 多目标 cost tuple 支持 Pareto/NSGA-III 选择。

### Step 10: 后续再迁移真实 HFSS backend

涉及模块：`project/job_template`，可选新增 `hfss_com.py`

实现：

- 从 `20260403 hfss_com.py/workflow.py` 迁移 PyAEDT 适配经验。
- 保留 far-field full matrix 重建、axis metadata、solver cleanup、per-job temp/home 隔离。
- 严格拆分：`workflow.py` 只导出 rawData，`calc_cost.py` 才计算目标。
- 本步骤不影响核心框架 API。

测试：

- 可先用 mock PyAEDT contract 测试 rawData 输出。
- 真实 HFSS 测试单独标记，不作为默认 pytest 依赖。

## Test Plan

每个 step 都应至少补一个小测试，避免一次性大重构。默认测试保持不依赖 HTCondor、不依赖真实仿真软件。

验收顺序：

- `pytest -q` 始终通过。
- 无任何核心路径生成 `cost.json`。
- job 目录不复制 `calc_cost.py`。
- completed history 的 normalized variables 和 costs 都能动态重算。
- 单个 individual 失败不会终止整代。
- local 与 distributed 最终都走同一套 recorded_data 写入逻辑。

## Assumptions

- 近期优先目标是把 v3 架构做稳，而不是马上接真实 HFSS。
- 旧项目 runtime 数据格式可以作为参考，但不能覆盖 v3 的“不长期保存 cost”原则。
- `tools/` 暂时不作为核心依赖；后续可单独补参数生成、查看、备份工具。
- INR/deep ensemble surrogate 是后续增强项；当前 RBF/IDW rawData surrogate 可先作为轻量 baseline 保留。
