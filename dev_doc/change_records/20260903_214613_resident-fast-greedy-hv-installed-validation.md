# 20260903_214613 Resident fast、greedy-HV默认与完整perfect验收

## Context

旧fast在代际与外部解释器边界重复初始化。已有greedy-HV机制仍为可选策略，用户要求迁移常驻会话、完成固定输入吞吐对照，并把六单元perfect实验跟踪到可独立复核的终态。

## Change

交付yadof与yadof-benchmark 0.6.0：删除旧fast任务执行分支，采用版本化create/evaluate/close接口和campaign拥有的worker pool；Chrono外部解释器复用有界内存帧，每次重新构建物理系统；ngspice共享解析后的完整rawData但仍逐候选启动batch进程。三个baseline、共享workflow、perfect oracle、默认模板、测试及依赖范围同步迁移。

公开GPSAF默认值及随包程序改为已有hypervolume机制，显式cluster回归保留，alpha/beta、误差、探索、遗传算子和真实状态恢复不变。用户迁移文档、入口README、架构、蓝图和术语同步更新。

## Evidence and validation

正式实验前安装包完整测试为yadof500passed/100.19秒、benchmark64passed/14.45秒。固定三次48候选/4workers吞吐对照全部rawData/cost及物理失败分类逐位一致；Chrono端到端中位吞吐+79.56%，SAW+2.80%、天线+1.96%，后两者波动较大。完整18单元smoke与6单元真实alpha/beta集成通过。

新正式perfect使用seed101、P200、NSGA-III全50代、GPSAF α3/β3/γ0.5/探索0.1及原遗传设置。6/6有效完成；独立核验39000次正式尝试、45360次oracle物理调用、配对初始种群、全轨迹首次越线及完整领域输出。Chrono/SAW/天线首次越线为8/19/18代，正式预算减少84%/62%/64%；oracle成本及实际命令耗时另列，未据此作普遍加速声明。

新证据报告：[常驻fast与吞吐](../context/surrogate-research-20260830-20260910/20260903_214613_resident-fast-throughput-validation.md)、[HV perfect与到期审查](../context/20260903_214613_greedy-hv-perfect-surrogate-crossings.md)。五份指定旧context全部保留；没有整篇失效依据，原文、图表和论文未移动或修改。

最终文档wheel刷新在终态核验后进行。最终安装身份、文件内容一致性与验收记录见[安装收据](../../../temp/20260903_resident_fast_hv/FINAL_INSTALLATION.json)；Git提交、fetch计数及条件推送见[Git收据](../../../temp/20260903_resident_fast_hv/GIT_COMPLETION.json)。大运行证据留在任务拥有的外层temp目录，未加入Git。

## Impact

旧fast工作区必须按migration_0_6迁移，benchmark依赖yadof>=0.6.0,<0.7。记录、当前成本解释、恢复和后处理数据契约保持。新的单seed/P200结果补充既有多seed/P20研究，不替代学习代理或跨域效果验证。任务开始时工作区干净，没有纳入预存修改。
