# 常驻 fast 迁移与固定候选吞吐对照

本证据集记录2026-09-03的resident-fast迁移、固定候选吞吐对照及安装验收。配套的[greedy-HV perfect六单元报告](20260903_214613_greedy-hv-perfect-surrogate-crossings.md)记录已独立核验的正式实验与本次context到期审查。

## 已验证的结论

在相同物理输入、相同48个候选、4workers、3次重复的端到端计时下，Chrono 的中位尝试吞吐由3.468增至6.227次/秒（+79.6%）。SAW为6.586→6.770（+2.8%），天线为9.310→9.492（+2.0%）；后两项重复波动较大，不能据此声称明显或普遍加速。

三项任务所有对应成功样本的完整 rawData 和当前成本逐位一致，失败类别也一致。迁移复用进程、模块和原生库，每次仍重新执行物理计算，没有结果缓存、低精度替代或物理状态热启动。

## 实现与边界

- fast 使用明确的 `YADOF_FAST_API="yadof.fast.session/v1"` 与 `create_evaluation_session(context)`；对象实现 `evaluate_rawdata(parameters, context)` 和 `close()`。只有旧模块级函数的任务会得到明确迁移错误，没有静默兼容执行。
- campaign 拥有有界 worker pool。每个 worker 只加载一次任务模块并创建一次会话，在兼容候选和代之间复用；独立评估作用域关闭自己拥有的 pool。
- 评估定义、环境、worker 上限或 timeout 改变会关闭受影响会话；仅成本解释变化保留会话。候选上下文、参数与 scratch 独立；关闭 campaign 时先关闭句柄与 pool，再清理快照。
- 声明的物理失败保留可用会话；程序/协议错误会替换 worker。超时、崩溃及取消清理进程树，并释放 Windows 进程句柄。正常成功不再逐响应杀死属于会话的 simulator 子进程。
- Chrono 每个 fast worker 复用一个外部 PyChrono 解释器，通过有界 JSON 头与完整数值数组内存帧交换结果。每次回调重新构建 `ChSystemNSC()` 并设置 `SetMinBounceSpeed(0.15)`；scalar、轨迹及应力字段保持完整。
- Windows 长 TEMP/TMP 可使 venv 启动器在 Python 启动前阻塞。常驻 adapter 先使用可启动的短临时路径，再在 child 内切换到任务拥有的会话/候选 scratch。常驻协议不创建外部 junction；原有独立 one-shot JSON/NPZ API 保留自己的生命周期。
- ngspice 仍是每候选一次 batch 子进程；改进在于 rawfile 解析后直接返回 memory rawData，多向量共享一次解析，移除 NPZ 写读往返。
- 三项 baseline 的 workflow 与 fast 使用同一任务会话核心。默认模板也提供显式会话；fast 验证不会构造会话或启动仿真器。
- perfect oracle 通过同一 fast runner 使用独立的 campaign-owned pool，返回结果不接入 recorder。成本仍经 `StructuredRawDataSample.cost_items()` 调用当前成本链；审计区分 query、cache hit、新物理调用与 wall time。

## 冻结与计时口径

原版本为 yadof0.5.1 / yadof-benchmark0.5.0，接受的新版本均为0.6.0。吞吐测量完成后才切换 GPSAF 默认值；固定候选 probe 本身不使用 surrogate 或优化选择。Python3.13.11、NumPy2.5.2、pymoo0.6.2、psutil7.2.2；外部 PyChrono10.0.0（py313h418371c_0）及 ngspice46 的可执行文件/原生库身份见冻结文件。

每项任务48个固定归一化候选，其中开头含A/B/A；每次分3代、每代16个候选，4workers，单候选超时60秒，禁用 smoke，重试0，结果缓存0，原生线程变量固定1。三次重复各使用全新工作区。候选文件 SHA-256 为 `6e55b1fd21381c52c43354bbdbd2a632b8648fa1e3a2235ad56a4d1ac4d487d7`。

冷启动段为第1代16个候选的 prepare/start/wait/handle-close 区间，包含该批首次 worker/session/native 初始化；稳态段是随后两代的相同区间，总计32次尝试。两者的代快照创建和 generation commit 在该区间之外。端到端则从 `run_generations()` 调用前计时至其返回，包括完整作用域、代快照、评估、正式 recorder/current-cost、各代提交及 campaign 关闭。前置材料化/检查和后置独立 rawData 导出核验在端到端计时之外。

## 数值与速率

rawData比较计数为三次重复合计的旧/新文件对；每一对只计一次。每个版本共432次尝试、402次成功、30次声明的物理失败，重试0；432次尝试均有实际kernel调用。

| 任务 | 每次尝试/成功/物理失败 | 比较 rawData 文件 | 比较数组 | 容差 |
|---|---:|---:|---:|---|
| Chrono | 48/38/10 | 1,824 | 4,446 | dtype、shape、bytes、cost全等 |
| SAW | 48/48/0 | 288 | 864 | 同上 |
| 天线 | 48/48/0 | 1,296 | 8,640 | 同上 |

下表单位为尝试/秒，列出中位数，方括号为三次重复的最小值和最大值，不是置信区间。

| 任务 | 计时段 | 旧版 | 常驻版 | 中位速率变化 |
|---|---|---:|---:|---:|
| Chrono | 冷启动 | 3.520 [3.360,3.963] | 8.389 [6.954,8.570] | +138.3% |
| Chrono | 稳态 | 4.056 [3.614,4.319] | 10.033 [7.048,10.261] | +147.3% |
| Chrono | 端到端 | 3.468 [3.403,3.628] | 6.227 [5.519,6.948] | +79.6% |
| SAW | 冷启动 | 16.588 [11.162,18.395] | 22.886 [21.259,23.377] | +38.0% |
| SAW | 稳态 | 6.408 [5.935,18.143] | 38.292 [7.055,44.228] | +497.6% |
| SAW | 端到端 | 6.586 [6.427,9.606] | 6.770 [5.628,17.493] | +2.8% |
| 天线 | 冷启动 | 13.851 [12.429,13.910] | 15.631 [15.357,15.730] | +12.8% |
| 天线 | 稳态 | 14.665 [10.338,14.739] | 23.286 [21.088,23.289] | +58.8% |
| 天线 | 端到端 | 9.310 [8.070,12.492] | 9.492 [5.822,11.107] | +2.0% |

Chrono 成功吞吐的冷/稳态/端到端中位数分别为旧版3.080/3.042/2.745与新版7.340/7.525/4.930次/秒；另两项无失败，成功与尝试速率相同。端到端速率的旧/新变异系数分别为Chrono0.033/0.115、SAW0.238/0.657、天线0.229/0.307。

较快的批内区间不代表完整调用得到同等比例改善；端到端还覆盖其他已声明边界。这里没有对各项额外耗时做单独因果归因，也没有根据结果追加重复挑选有利的运行。4workers 的比较不能直接外推为其他并发下的最优配置。

## 接受前问题与最终验收

接受前 `throughput/new/` 的 Chrono 缺少需要的 `os` 导入，0/48成功，不能作为物理加速证据。修复、重建重装和真实物理核验后，另建 `throughput/new-fixed/` 完整重复三项测量，原失败目录保留。初次天线 local 检查还暴露了既有 workflow 对 `None` 做 `int()` 的退出错误；修复后在新目录重新完成等价验证。

真实物理 gate 包括三项A/B/A、旧/新A与fast/local的完整 rawData/cost 比较，以及 Chrono 同一 worker/外部解释器经历物理失败后再次成功。正式实验前的安装包全套验收为 yadof **500passed，100.19秒**；benchmark **64passed，14.45秒**。此前失败的版本断言、模板文件集合及配置替换断言均有保留日志，并通过重新构建安装后完整复验。

安装来自成功构建的 wheel，导入路径位于外层 `.venv/Lib/site-packages`；没有修改 site-packages、editable 安装或注入仓库 `src`。另有18单元 complete 机械 smoke（P200/G1，3600尝试）和六单元真实 perfect 集成（P20/G3上限，320尝试），其数值仅用于结构验收。

## 证据入口

运行时 Git 基线为 `9078f4ef56bd66fa46ae5a408a01170405cd5c6d`；当时的未提交实现由源文件哈希、源码归档和 wheel 固定。相同0.6.0版本号不等价于相同文件内容，重现应使用对应冻结轮。

完整资料见外层 `temp/20260903_resident_fast_hv/`：`OLD_FREEZE.json`、`OLD_NATIVE_IDENTITY.json`、`NEW_FAST_FREEZE.json`、`PHYSICAL_EQUIVALENCE.json`、`THROUGHPUT_COMPARISON.json`、各版本 `*-wheels/` 与源码归档、全部测量工作区，以及固定的 `probe_program.py` / `measure_throughput.py` / `compare_throughput.py`。正式 HV 基准使用单独的 `FORMAL_WORKSPACE.json`、`formal-source.zip`、`formal-wheels/` 和 `runtime_lock.json`。

这是跨会话证据；当前行为以[迁移指南](../../user_doc/migration_0_6.md)、[fast用户契约](../../user_doc/optimization_workflow.md)和架构为准。

## 吞吐完整重复值

以下各格均按重复0、1、2排序，单位为秒。成功吞吐的分子为成功数量；尝试吞吐的分子包含声明的物理失败，重试为0。所有原始速率、标准差、变异系数和逐位比较计数保留在 THROUGHPUT_COMPARISON.json。

| 任务 | 版本 | 冷启动16次耗时 | 稳态32次耗时 | 端到端48次耗时 |
|---|---|---|---|---|
| Chrono | 旧版 | 4.762281 / 4.037495 / 4.544945 | 7.888658 / 8.853832 / 7.409945 | 13.232020 / 14.104394 / 13.840947 |
| Chrono | 常驻版 | 1.907350 / 2.300988 / 1.867084 | 3.189379 / 4.540421 / 3.118705 | 7.708395 / 8.697030 / 6.908455 |
| SAW | 旧版 | 0.964556 / 1.433414 / 0.869802 | 1.763787 / 4.994116 / 5.392053 | 4.997079 / 7.468570 / 7.288290 |
| SAW | 常驻版 | 0.684446 / 0.752609 / 0.699118 | 0.723521 / 0.835674 / 4.535528 | 2.743895 / 8.528366 / 7.089929 |
| 天线 | 旧版 | 1.287341 / 1.155120 / 1.150219 | 3.095489 / 2.171071 / 2.182049 | 5.947972 / 5.155558 / 3.842364 |
| 天线 | 常驻版 | 1.041873 / 1.017195 / 1.023594 | 1.517439 / 1.374196 / 1.374040 | 5.056626 / 8.244413 / 4.321740 |

| 任务 | 冷启动速率比 | 稳态速率比 | 端到端速率比 |
|---|---:|---:|---:|
| Chrono | 2.382859× | 2.473415× | 1.795568× |
| SAW | 1.379675× | 5.976150× | 1.027978× |
| 天线 | 1.128494× | 1.587872× | 1.019565× |

## 可复现入口与最终安装

所有相对命令从包含checkout与`.venv`的外层工作区执行。以下是保存的测量入口；复现需恢复相应冻结wheel/仿真器身份并使用新的证据根与工作区，不能对已完成目录再启动一次运行：

```powershell
& ".\.venv\Scripts\python.exe" ".\temp\20260903_resident_fast_hv\run_measurements.py" old
& ".\.venv\Scripts\python.exe" ".\temp\20260903_resident_fast_hv\run_measurements.py" new-fixed
& ".\.venv\Scripts\python.exe" ".\temp\20260903_resident_fast_hv\compare_throughput.py"
```

输入、完整参数、计时边界及脚本SHA见[旧版冻结](../../../temp/20260903_resident_fast_hv/OLD_FREEZE.json)与[接受的新fast冻结](../../../temp/20260903_resident_fast_hv/NEW_FAST_FREEZE.json)；[仿真器原生身份](../../../temp/20260903_resident_fast_hv/OLD_NATIVE_IDENTITY.json)、[真实物理等价核验](../../../temp/20260903_resident_fast_hv/PHYSICAL_EQUIVALENCE.json)、[全部逐次测量与比较](../../../temp/20260903_resident_fast_hv/THROUGHPUT_COMPARISON.json)保留机器可读结果。源快照和wheel分别位于[旧源码](../../../temp/20260903_resident_fast_hv/old-source.zip)、[新fast源码](../../../temp/20260903_resident_fast_hv/new-fast-source.zip)、[旧wheel目录](../../../temp/20260903_resident_fast_hv/old-wheels/)及[新fast wheel目录](../../../temp/20260903_resident_fast_hv/new-fast-wheels/)。

生命周期与真实物理检查包括成本重新解释、模型/config代际失效、超时/崩溃替换、主动取消、关闭/进程树清理、跨工作区隔离及未构造会话的静态验证。完整安装包测试日志为[yadof实验前验收](../../../temp/20260903_resident_fast_hv/yadof-full-tests-fixed.log)和[benchmark实验前验收](../../../temp/20260903_resident_fast_hv/benchmark-full-tests-fixed.log)。结构门槛的独立收据是[18单元smoke](../../../temp/20260903_resident_fast_hv/SMOKE_VERIFICATION.json)与[6单元alpha/beta集成](../../../temp/20260903_resident_fast_hv/INTEGRATION_VERIFICATION.json)。

正式实验结束并通过独立核验后才刷新最终文档wheel。[最终安装与代码字节核对](../../../temp/20260903_resident_fast_hv/FINAL_INSTALLATION.json)记录最终wheel指纹、导入来源、文档可见性及最后的验收结果；它与测量时的冻结wheel身份分开保存。[Git交付收据](../../../temp/20260903_resident_fast_hv/GIT_COMPLETION.json)记录最终提交和按既定规则进行的fetch/count/push结果。

## Context到期审查

用户在本报告完成后要求移除已经失去当前参考用途的旧性能 context。复审已将旧正式 benchmark、旧 fast 并发扫描、天线配置筛选、SAW/Chrono 配置迁移四份报告及两张附图原样移入 `dev_doc/obsolete/context/`。旧计时不再作为常驻版性能依据；当前吞吐使用本报告的固定候选对照，当前 GPSAF 正式结果使用[配套六单元报告](20260903_214613_greedy-hv-perfect-surrogate-crossings.md)。本次没有重新扫描常驻版的最优 worker 数。

仍保留 [greedy-HV 五种子机制验证](20260903_153222_chrono-gpsaf-mechanism-and-independent-validation.md)，其证据直接解释当前采用的选择机制。逐项理由和原件位置见[复审归档记录](../change_records/20260903_222814_archive-superseded-gpsaf-performance-context.md)。此前运行目录内的 `CONTEXT_REVIEW.json` 与 `CONTEXT_REVIEW_INPUTS.json` 是首次审查的冻结收据，保持不变，不再代表当前归档状态。
