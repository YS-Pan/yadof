# Surrogate 研究阶段总结与 yadof 落地（2026-09-10）

这轮研究已经带来可用组件、执行性能与可靠性改进，但尚未找到达到全部稳定性目标的
通用 surrogate。用户决定先收尾，将已有成果留在 yadof，避免继续无限扩展研究。
本文件是根目录入口；详细记录和附件已封存到
[`surrogate-research-20260830-20260910/`](surrogate-research-20260830-20260910/)。
封存表示暂停研究和降低默认上下文读取成本，不表示历史证据失效。

## 研究目的与口径

用户希望用更多模型计算换取更少的昂贵真实仿真，面向未来未知工程任务，而非分别为
三个廉价 baseline 调专用赢家。保留 rawData-first、真实失败容忍、新架构独立成模块；
INR 暂不改动。以累计真实最佳十个体平均成本衡量效率，不能用预测重合率、离线误差
或单次成功代替在线优化结果。原先 1.5 倍 perfect 的要求，后来在 P50/B50/I200
任务中改为五种子中位数不超过匹配 perfect 的两倍；两轮口径不能混用。

主要来源：[复盘yadof surrogate算法研究](codex://threads/01a08033-4625-79e3-af38-6b289f3a3b33)、
[Develop yadof P50 B50 I200 surrogate](codex://threads/01a08589-30b6-7fd3-8d8a-ebc5d33845a4)。
前者追溯 37 个任务、103 条用户直接消息，并区分 6 条转发/委派内容。
用户原始要求、后续采用的合同、agent 自选筛选方法应分别记录，不能反向混为一谈。

## 主要结果

| 阶段 | 已有结果 | 限制与决定 |
|---|---|---|
| 基础 CAE、PCA/SVD | 表示能力与参数→响应预测能力是不同瓶颈；各 domain 收益不同 | 不再以一个全局黑白 gate 否定所有用途；INR/CAE/PCA 均保留 |
| H9 幅值/形状 GP | seed101 三基准通过当时 1.5 倍目标，并精确复现 | 新种子确认仅 4/9；已作为 amplitude_gp opt-in 入包 |
| H21–H26 | H23 开发 4/6，H26 开发 3/6；后者完整 26000 次尝试已审计 | 没有通过原目标；残差树候选继续封存，不推广为默认 |
| P/B/I 分离及 perfect | 135个perfect单元（三基准×九种P/B×五种子）加15个普通参考，共150单元独立审计 | 小批次收益不全来自 surrogate；perfect 是经验对照，不是数学最优上界 |
| N02 联合邻居响应修正 | P50/B50 下，Chrono/SAW 中位数达到2倍内，天线未达到 | 15/15 开发单元已审计，2个SAW种子删失；作为实验组件落地，无全新确认 |

N02 首次达标次数中位数：天线 **3900** / perfect **1300**，Chrono **1900** / **1450**，
SAW **1650** / **1450**。未到达阈值的种子不删除、不当成精确 10000。
原运行的提前停止导致原生完整预算计数报告 failed，保存的独立开发审计通过；两种
状态均保留。这不是全目标成功。

对应证据：

- [基础 CAE/PCA-SVD](surrogate-research-20260830-20260910/20260830_143110_hierarchical-cae-pca-svd-measured-evidence.md)
- [H9 及早期研究交接](surrogate-research-20260830-20260910/20260905_075552_cae-surrogate-sol-research-progress.md)
- [H21–H26 收尾](surrogate-research-20260830-20260910/20260908_211700_cae-surrogate-h26-research-closure.md)
- [五种子 P/B perfect 对照](surrogate-research-20260830-20260910/20260909_152719_five-seed-perfect-surrogate-pb-baseline.md)
- [P50/N02 最新终态与机制发现](surrogate-research-20260830-20260910/20260910_120000_p50b50-research-closure.md)

## yadof 得到的具体进展

既有提交已经落地：greedy-HV GPSAF 选点、Chrono 重复性/真实失败处理、resident fast
会话、rawData 只读共享与弱索引、训练缓冲复用、H9 独立组件、局部准备死锁修复，
以及 P/B/I 分离和 benchmark 提交内存保护。详见
[resident fast 验证](surrogate-research-20260830-20260910/20260903_214613_resident-fast-throughput-validation.md)、
[P/B 与吞吐验证](surrogate-research-20260830-20260910/20260908_224400_population-batch-and-throughput-validation.md)。

本次进一步交付：

- 独立 `retrieval_response()` 实验组件，保留 N02 默认数学流程、完整 rawData、
  owned training 生命周期与无 pickle 检查点；修复 CPU seed 对其他设备 RNG 的副作用。
- H9/N02 可复制的显式优化程序：每次选择前用全部已完成历史训练。H9 使用已验证的
  两字段并行设置；P/B/I 仍由任务配置独立决定。
- `surrogate-complete` 36单元完整对比预设，原 `complete` 18单元保持原定义。
- context 默认只列第一层文件名和目录名；不读取子目录文件名。按名称或直接链接
  判断相关后再进入。benchmark 使用低成本、无继承上下文的监控子 agent。

使用入口：[H9](../../user_doc/amplitude_gp.md)、[N02](../../user_doc/retrieval_response.md)、
[显式程序](../../user_doc/optimization_program_examples.md)、
[benchmark](../../yadof-benchmark/user_doc/README.md)。

## 尚未解决与本次边界

全新种子、三基准通用稳定性仍未证明。邻居覆盖、事件位置错位、低秩形状与极差恢复
之间存在交互；平滑抖动可能损坏极值成本，平均成本误差也可能掩盖完整响应错误。
R01/R02、H23/H26 专用优化仍封存。N02 目前通过 typed predict API 检查响应，尚无
surrogate viewer 路由。没有新增研究循环，也没有修改默认 surrogate。

## 本次完整 benchmark

2026-09-11 00:10（北京时间）完成完整矩阵：**36/36有效，180000次尝试，177097次有限结果**。
三基准×四策略×三种子，P200/B200/I200/G25，每单元5000次，失败计入预算。
原进程中断后保留完整Chrono组，在新工作区补跑另外两个完整基准组；旧运行状态没有改写。

最终真实最佳十个体平均成本Q（越低越好）的三种子中位数：

| 基准 | 普通 | PCA/SVD | H9 | N02 |
|---|---:|---:|---:|---:|
| Chrono | 0.214376 | 0.214922 | 0.190732 | 0.182822 |
| SAW | 0.275309 | 0.252925 | 0.174787 | 0.186106 |
| 天线 | 0.307846 | 0.309583 | 0.290596 | 0.306597 |

H9在本矩阵9/9种子优于普通策略，但模型开销较高；N02在Chrono/SAW有明确收益，天线
配对Q比值中位数约0.999759，基本无收益。两者继续选配；这不是旧P50/perfect目标的全新确认。
本机廉价仿真上的surrogate程序均比普通策略墙钟耗时更长。

yadof安装包全量593项、benchmark全量97项通过；N02与原型数值一致，所有H9/N02单元
的432次训练完成。监控按低成本模型、无继承上下文、5分钟采样、主代理长等待执行；首轮
代理提前结束及外部中断等实际限制也有记录。

详细协议、逐种子Q/N、耗时、中断与补跑证据、监控限制及图表：
[完整benchmark收尾](surrogate-research-20260830-20260910/20260911_001924_installed-surrogate-benchmark.md)。
