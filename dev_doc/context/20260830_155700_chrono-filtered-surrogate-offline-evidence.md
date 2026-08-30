# Chrono filtered-target surrogate 离线证据

## 角色与边界

本文保存 2026-08-30 完成的 `c0003` Chrono stress filtered-target 离线实验。它回答一个受限问题：
只平滑两条 513 点 stress 曲线后，Hierarchical CAE 或 conditional INR 的配对 test 拟合和
预测 chatter 是否同时明显改善。本文是 measured context，不是滤波物理有效性证明、当前架构
契约、production integration 决定、simulator 授权或新的模型默认值。

已完成的原任务归档于
[offline filtered Chrono surrogate validation TODO](../obsolete/todo/20260830_151259_validate-filtered-chrono-surrogates-offline.md)。
实验没有修改 benchmark source、recorded history、cost、optimizer、yadof package 或 simulator
状态，也没有读取 `c0004`。

## Artifact 与 source 身份

权威外层实验目录（相对 modular workspace）：

`temp/20260830_152530-chrono-filter-surrogate-validation`

主要复核入口：

- [source receipt](../../../temp/20260830_152530-chrono-filter-surrogate-validation/source-receipt.json)
- [frozen filter plan](../../../temp/20260830_152530-chrono-filter-surrogate-validation/filter-plan.json)
- [paired metrics](../../../temp/20260830_152530-chrono-filter-surrogate-validation/reports/metrics.json)
- [summary](../../../temp/20260830_152530-chrono-filter-surrogate-validation/reports/summary.md)
- [viewer validation](../../../temp/20260830_152530-chrono-filter-surrogate-validation/reports/viewer-validation/validation.json)
- [GUI observations](../../../temp/20260830_152530-chrono-filter-surrogate-validation/reports/gui-observations.md)
- [fixed test selections](../../../temp/20260830_152530-chrono-filter-surrogate-validation/reports/selected-test-designs.json)
- [derived-data map](../../../temp/20260830_152530-chrono-filter-surrogate-validation/derived-data/filtered-sample-map.jsonl)

来源是已完成 benchmark 的 `c0003`、design seed `20260830`、model seed `154538516`。
本次使用 installed yadof `0.4.2`、Python `3.13.11`、Torch `2.10.0+cu128`、SciPy
`1.18.0`。关键身份为：

| item | SHA-256 |
| --- | --- |
| design plan | `583e7c043ebb76bb97634d067ed39c9c7dccebcabc0a174cf67c92eac4a515a9` |
| gate plan | `3dd87e3fc99d1b40a143bb957de7000e5d061d87a6c934c6d1b240834198f7f4` |
| partition manifest | `3452b140c6f03faa344068d7b35d4f37038297a24d9fe18ab425296e954e2add` |
| frozen source harness | `f27a8157068b7a5cb33e56057d450325363b922cd0c32e3a67e527e05b105166` |
| filter plan identity | `9ba990995922b550bd4301b3e21c692754adb42b9c8d8356e870163c2b9981c4` |
| reused raw-CAE gate manifest | `5ab8cfbac6f5b5da8e1e05bc4d7a3769a5bbe5f75f4f1b716bce3a5cbaa83a7a` |
| reused raw-CAE model | `53ccccc83e49dce8d0af68f6ab7275dd03d806b720b79cf6fa867894f087b6bd` |
| reused raw-CAE scalers | `5876f9e32ad24fb10deb0e198469235ab07e2359609d54512df29560f11892fd` |

source receipt 固定了 182 个 segment 的路径、大小和 hash。completed rows 为 train-large
`1479`、validation `148`、reserved calibration `148`、test `295`；reserved calibration 的
rawData 从未访问。filter plan 于 `2026-08-30T15:38:32+08:00` 已冻结，test rawData 首次访问为
`2026-08-30T15:39:07+08:00`。

首次 `prepare` 暴露 disposable harness 的 INR input-dimension 属性错误。该错误在任何 test
rawData 访问前修正；旧 plan/receipt 没有删除，而是保存在
`reports/pretest-superseded-script-1/`。随后重新冻结的上述 filter identity 才是本实验的
权威计划。

## Frozen transform 与 guards

候选为 deterministic zero-phase fourth-order Butterworth low-pass，cutoff 是 Nyquist 的
`0.04`、`0.08`、`0.16`，只用 train-large 和 validation 选择。按预声明的
`largest_cutoff_first` 规则选择 `0.16`。实现是 SciPy SOS `butter` 加 `sosfiltfilt`，内部
`float64` 计算、输出恢复 source dtype。

仅变换以下 `values` arrays：

- `trebuchet_arm_combined_normal_stress.npz`；
- `trebuchet_hanger_combined_normal_stress.npz`。

axes、metadata、所有非目标字段和 `trebuchet_peak_strength_utilization.npz` 保持原样。
train+validation 的 1,627 rows 与 test 的 295 rows 均逐 row 重算四项 current cost；
raw/filtered 最大绝对差为 `0`，exact-equality guard 通过。没有启动 simulator。

选择集 transform 中位数如下；数值为比例，越大的 roughness/HF reduction 表示压制越强：

| field | relative RMS distortion | roughness reduction | HF-energy reduction | peak attenuation |
| --- | ---: | ---: | ---: | ---: |
| arm stress / train | 0.0396 | 0.9827 | 0.9944 | 0.7987 |
| hanger stress / train | 0.0388 | 0.9712 | 0.9867 | 0.6563 |
| arm stress / validation | 0.0395 | 0.9818 | 0.9929 | 0.7821 |
| hanger stress / validation | 0.0381 | 0.9610 | 0.9798 | 0.5629 |

这说明 transform 确实去除了大部分二阶粗糙度和固定频带能量，同时也大幅削弱 peak。
它不是轻微去噪，也不能视作更接近 simulator truth。

## 四臂训练与配对结果

四个 arms 为 raw/filtered × CAE/INR。raw CAE 复用已验证 checkpoint；filtered CAE、raw INR、
filtered INR 使用 frozen architecture settings 与 model seed 重新训练。每个 architecture 内
raw/filtered 使用相同 completed rows、split 和设置。CAE checkpoint 为 1,627 samples、3 members、
875,032 parameters；INR checkpoint 为 1,479 samples、3 members、601,635 parameters。

主要 test 指标：

| architecture | filtered-target std. RMSE ratio, filtered/raw model | unmatched narrow-peak median ratio | source-raw target std. RMSE, raw/filtered model | 结论 |
| --- | ---: | ---: | ---: | --- |
| CAE | 0.9937 | 0.1450 | 2.6227 / 2.6151 | 未明显改善 |
| INR | 0.9985 | 0.1769 | 2.6744 / 2.6723 | 未明显改善 |

滤波后模型的 unmatched narrow peaks 明显减少，但预声明解释要求同时取得足够的配对
filtered-target fit 改善；CAE 只有约 `0.63%` RMSE 改善，INR 只有约 `0.15%`，均未达到
`10%` fit 门槛。source-raw target error 也基本不变，因此不能把 chatter 降低解释为总体
预测能力改善。

非目标字段 macro standardized RMSE 从 raw 到 filtered model 分别为 CAE
`1806.30 -> 1839.57`、INR `389.15 -> 410.81`；worst fields 分别为 `ball_vz` 与 `ball_z`。
这些极大 standardized 值受 raw-train near-zero scales 放大，但至少没有提供 filter route
改善非目标预测的证据。完整 per-field、raw/filtered truth、roughness、HF leakage、overshoot、
unmatched peaks、cost 和资源指标均保存在 `metrics.json`。

资源记录：raw CAE 复用训练来源 wall `92.25 s`；新训练 filtered CAE `84.28 s`、raw INR
`122.36 s`、filtered INR `134.05 s`。peak CUDA 分别约 `135.8 MiB`（CAE）和 `354.1 MiB`
（INR）；checkpoint 约 `3.69 MiB`（CAE）和 `2.38 MiB`（INR）。没有 arm failure。

## Viewer 与目视证据

四个独立 workspace 均通过 installed `view surrogate summary` 和固定
`sample-percent=1`、seed `20260830`、`quantity=all-costs` audit。每个 summary 发现 1 个正确
component namespace 的 checkpoint、generation 12/13 共 295 个 completed results，以及相同
顺序的 16 个 rawData items。

四个 GUI 都成功加载固定 test design：generation 12、individual 156、
`fast_20260830_100005_349574_156_a13def1a`。同一 `release_phase` axis 下，raw CAE 预测出现许多
与 raw truth peak 位置不一致的窄 spike；filtered CAE chatter 大幅下降，但仍漏掉主要 peak。
raw/filtered INR 本来较平滑，也同样漏掉大 peak。双字段、同轴同 y-scale 的固定 PNG 为：

- [generation 12 / individual 156](../../../temp/20260830_152530-chrono-filter-surrogate-validation/reports/overlays/12_156_screenshot-generation-12-population-156.png)
- [largest narrow-peak score](../../../temp/20260830_152530-chrono-filter-surrogate-validation/reports/overlays/12_168_largest-narrow-peak-score.png)

视觉平滑不代表物理正确。unlock、release、contact/recontact 或 collision 的来源仍未验证。

## 结论与下一步边界

证据分支为 `neither-clearly-improved`。本实验支持“滤波可以压制 CAE chatter”，但不支持
“raw target spikes 是两个 architecture 拟合困难的主要原因”，也不支持 production filter
integration。按原 TODO 规则不运行 `c0004` replicate；当前路线停止。

后续若另行授权，应优先分离 model/scaling/checkpoint/viewer adaptation 问题，并保留 raw truth
与 simulator event/state 的可追溯性。任何 formal integration、真实 simulator 复核、改变 cost
truth、扩大字段范围或长期训练都需要新的 TODO 与相应文档维护。
