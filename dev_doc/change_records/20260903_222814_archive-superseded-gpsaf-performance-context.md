# 2026-09-03 22:28 - 归档已被替代的 GPSAF 性能 context

## 背景与决定

用户在 resident-fast / greedy-HV 任务完成后明确要求移除过时 context，尤其是已不能代表当前 GPSAF 性能的 benchmark 记录。本次完整复读五份相关旧报告，对照当前安装版 GPSAF 规范、架构及两份最新实验报告，重新判断其活跃用途。首次审查把“仍能解释历史”作为全部保留的理由；本次按用户要求，让已经退出当前配置或性能评估用途的记录进入历史归档。

## 归档范围

以下文件从 `dev_doc/context/` 原样移入 `dev_doc/obsolete/context/`，文件名与字节不变：

| 归档原件 | 退出活跃 context 的原因 |
|---|---|
| [旧正式 benchmark](../obsolete/context/20260902_082800_yadof-benchmark-formal-results-summary.md) | 测量的是旧 GPSAF + PCA/SVD 配置及旧执行通路。其负向性能和训练计时不能评价当前默认 greedy-HV GPSAF；用户不再需要它充当当前性能入口。新 perfect-oracle 结果也不构成对新版学习型代理的重新验收。 |
| [旧 simulator 并发扫描](../obsolete/context/20260902_114845_yadof-benchmark-simulator-concurrency-tuning.md) | 扫描基于旧 fast 进程生命周期。常驻 worker / simulator 会话改变了主要开销，旧绝对计时与最优点不能用于当前吞吐估算。2/2/1 倍数仍是现有配置，但新版最优并发尚未重新测量。 |
| [天线 cluster 配置筛选](../obsolete/context/20260903_091320_synthetic-gpsaf-memory-tuning.md) | P20/α1/β10 推荐针对旧 cluster/PKT 选择及研究用内存调用方式；greedy-HV 机制验证和新的正式运行已经接管当前选择器性能依据。这些配置排序不直接适用于当前默认。 |
| [SAW/Chrono cluster 配置迁移](../obsolete/context/20260903_121353_saw-chrono-gpsaf-configuration-transfer.md) | α1/α3 与强 P20 的比较针对旧 cluster；后续同池消融已定位覆盖收益的选择损失，greedy-HV 的独立验证和正式结果提供当前依据。旧推荐与性能不足结论不再作为当前 GPSAF 判断。 |

天线筛选和 SAW/Chrono 迁移的同名 PNG 一起原样归档，共四份 Markdown、两张图。没有删除或改写外层 `temp/` 中的实验数据、冻结源码、wheel、收据或原始日志。

## 继续保留与更新

- [当前六单元正式结果](../context/20260903_214613_greedy-hv-perfect-surrogate-crossings.md)与[resident-fast 吞吐报告](../context/surrogate-research-20260830-20260910/20260903_214613_resident-fast-throughput-validation.md)删除“旧报告全部保持活跃”的结论，改为本次复审状态；运行时首次审查收据保持历史原样。
- [greedy-HV 机制与五种子验证](../context/surrogate-research-20260830-20260910/20260903_153222_chrono-gpsaf-mechanism-and-independent-validation.md)保留，因为当前仍采用该机制，其同池消融、P20/β10 独立五种子、失败归一化风险及领域反例没有被 P200/β3 单种子正式运行替代。更新现行默认值及实验适用范围，保留全部测量数值。
- GPSAF 论文/验收对照及离线模型、rawData、posterior 校准 context 保持不变。选择器和执行通路改进没有替代它们的研究对象或当前用途。

归档不否定旧实验的历史真实性，也不把 perfect oracle 的表现外推为学习代理效果。当前默认值以用户规范为准，实验结论继续受各自 seed、预算、模型及计时边界限制。

## 链接与验证

活跃报告已移除四份旧报告的原活跃路径引用。旧 change records 按 append-only 契约保持不变；其中指向旧 `dev_doc/context/` 文件的历史链接，按上表解析到 `dev_doc/obsolete/context/`。归档原件中的外部相对链接仍采用原 `dev_doc/context/` 基址，例如 `../../../temp/` 指向外层工作区的 `temp/`；同名附图和两份报告间的链接随文件一起移动。

本次检查原件及附图 SHA-256、其余已有 context/历史记录不变性、UTF-8、活跃报告与本记录的本地链接、归档原始基址下的证据链接和 Git diff。核验脚本及逐链接目标映射保存在外层 `temp/20260903_context_cleanup/`。

本次仅改变文档内容和归档位置，不改变代码、包资源映射、文档机制、架构或用户运行契约。为使下一任务通过 `yadof docs` 立即看到清理结果，构建并 force-reinstall yadof wheel，核对 site-packages 来源、活跃/归档路径以及安装资源字节。benchmark 包无需重装；按开发指南的文档例外不运行软件测试或真实 benchmark。
