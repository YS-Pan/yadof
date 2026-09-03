# 2026-09-03 09:13 — 保存合成天线纯内存 GPSAF 调参证据

## Context

用户要求参考已有 GPSAF 诊断，用纯内存合成天线执行一系列裁剪 benchmark，寻找合适
算法配置，并将结果写入 context。前置实验显示默认 P200、α3/β3 的完美 oracle 收益较弱。

## Change

新增 [实验 context](../context/20260903_091320_synthetic-gpsaf-memory-tuning.md) 和
验证轨迹图，保存 54 个已完成 cells、冻结配置、全部计数、逐 seed 结果、对照归因、
适用范围及可重放证据位置。临时脚本和全部实验数组保留在所选外层工作区
`temp/20260903_synthetic_gpsaf_tuning`。

使用共同初始化 200、后续 P20/B20、α1/β10/γ0.5、探索比例 0.1 的原规则 GPSAF，
在 4 个未用于本轮调参的 seeds 上用 1440–1920 个入选设计同时严格超过对应
NSGA-III P200/10000 的 top-10 和 HV，理想 oracle 评估预算倍数为 5.21–6.94。
同时保存 pooled-mean、均值 GA、P20 real NSGA-III 对照，明确批量和目标选择也贡献收益。

## Rationale

需要把运行条件和双指标结果跨会话保存，防止仅凭 top-10 认为所有收益都来自 surrogate，
或将纯内存 perfect-oracle 数字当成真实模型/其他 simulator 的墙钟承诺。
本次确立实验科学证据，因此 change record 放在 substantive 根目录。

## Impact and validation

- 仅新增内容型 context、图和本记录；未修改包源码、测试、公开行为或默认配置。
- 54/54 cells 完成，累计实验预算 125000、实际 rawData kernel 调用 423340，正式
  recorded evaluations 为 0。两个验证分区使用独立进程和输出目录。
- 校准的三条轨迹共 14000 行入选 X/F 与已有实验逐位一致。
- 全部 54 cells 完成数组、边界、去重、配对初始化、逐代 top-10 和最终 HV 复核；
  已安装源文件 hash 各阶段一致。图像已目视检查。
- 使用 content-only 文档例外，无 wheel 重装或 pytest；执行 UTF-8、链接/hash 和 diff 检查。
- 起始仓库干净，无既有未提交修改需要合并；正常 Git 提交和 fetch/push 门槛依外层
  工作区指令执行，具体提交及推送状态由完成汇报给出。
