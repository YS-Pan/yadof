# 离线滤波 Chrono benchmark 并对比 CAE/INR surrogate

> 已于 2026-08-30 完成。结果与证据边界见
> [Chrono filtered-target surrogate 离线证据](../../context/20260830_155700_chrono-filtered-surrogate-offline-evidence.md)。

## 状态、来源与目标

- 本文是手动 TODO。2026-08-30 用户要求先跳出现有 yadof surrogate 集成框架，复用上次
  benchmark 的 Chrono 数据做一次低成本初期验证：在隔离副本中滤波 rawData，分别训练
  Hierarchical CAE 和 conditional-INR，再用 surrogate viewer 观察拟合效果。
- 本次只回答一个诊断问题：**把 Chrono 的尖峰应力曲线换成确定性的低通派生 target 后，
  CAE/INR 的 held-out 拟合误差和预测尖峰 chatter 是否下降？** 它不回答滤波后的曲线是否更
  接近真实物理量，也不授权把滤波接入 `submit/optimization.py`、workflow、recorded history、
  cost、optimizer 或 yadof package。
- 截图中的物理解释仍是假设。解锁、弹丸释放、接触/recontact 或地面碰撞可能产生不连续，
  但当前没有逐事件对齐证据。实验结果只能支持或削弱“高频 target 使 surrogate 更难拟合”
  这一建模假设，不能证明尖峰的物理来源。
- 本 TODO 与暂停中的
  [抗噪声 Hierarchical CAE 扩展](../../toDo/20260828_082308_noise-robust-regime-specialized-surrogate.md)
  不同：后者明确不做 rawData smoothing；本文只是一次 disposable、offline、非发布实验，
  不重新激活或修改该扩展。

## 已验证的当前证据与数据入口

### 原始 benchmark

权威 benchmark workspace（相对外层 modular workspace）为：

`temp/20260830_094718-hierarchical-cae-base-performance-measured-visible-20260830`

Chrono 对应两个只读 cell：

| cell | design seed | frozen plan SHA-256 | 用途 |
|---|---:|---|---|
| `cells/c0003` | `20260830` | `583e7c043ebb76bb97634d067ed39c9c7dccebcabc0a174cf67c92eac4a515a9` | 首轮实验 |
| `cells/c0004` | `20260831` | `4dbe9838bcd81009d8c041741effa4c727de8e1851c1073fb5914879f4a2e3c8` | 可选独立复现 |

两个 cell 的 frozen partition 均为：planned `train_large=2000`、`validation=200`、
`calibration_reserved_unopened=200`、`test=400`。每个 design seed 的实际完成数相同：
`train_large=1479`、`validation=148`、reserved calibration `148`、`test=295`。本实验不得读取
或使用 `calibration_reserved_unopened`；首轮只使用 `c0003` 的 train/validation/test。

必须把以下文件作为 source receipt 输入，而不是从文件夹顺序重新推断 partition：

- [benchmark spec](../../../../temp/20260830_094718-hierarchical-cae-base-performance-measured-visible-20260830/spec.json)
- [frozen gate plan](../../../../temp/20260830_094718-hierarchical-cae-base-performance-measured-visible-20260830/resources/gate_plan.json)
- [partition manifest](../../../../temp/20260830_094718-hierarchical-cae-base-performance-measured-visible-20260830/postprocessing/base-hierarchical-cae-performance-gate/partition-manifest.json)
- [frozen training/evaluation harness](../../../../temp/20260830_094718-hierarchical-cae-base-performance-measured-visible-20260830/resources/hierarchical_cae_gate.py)

### 尖峰与 viewer 事实

- [Chrono/SAW 尖峰对比 context](../../context/20260830_143418_surrogate-spikes-chrono-vs-saw.md)
  保存了原始截图和证据限制。Chrono 图中的
  `trebuchet_arm_combined_normal_stress` real curve 有少量窄高峰，surrogate curve 有更多分布
  在全 phase 轴上的窄峰 chatter。
- Chrono 任务先把 1 ms 物理时间历史重采样到 513 点 `release_phase`，然后在应力历史上使用
  `preserve_channel_maxima=True`，把每个原始通道最大值重新放回最近的 phase 网格点。这是
  已验证的当前任务行为，可能制造或强化单点尖峰；它原本用于避免重采样低估材料峰值，
  因而不能把简单平滑直接解释为更正确的安全应力。
- 已存在只读 CAE viewer workspace：
  `temp/20260830_chrono-cae-train-large-viewer`。它来自 `c0003`、`train_large`、model seed
  `154538516`，使用 `1479` training rows、`148` validation rows和 3 个 predictor members。
  它可作为 raw-CAE control，不得覆盖。
- 原 benchmark postprocessor 保存了 CAE artifact，但没有保存 conditional-INR artifact。
  因此 raw-INR control 和 filtered-INR 都需离线重训。此前 SAW viewer 已验证同样的重训路径
  可以精确复现 benchmark INR metrics；这只是可复用操作先例，不是 Chrono 结果证据。
- [CAE/PCA-SVD measured context](../../context/20260830_143110_hierarchical-cae-pca-svd-measured-evidence.md)
  已记录当前 CAE 在 Chrono 的 rawData、worst-field 和 ranking 明显弱于 INR。本文不得用
  filtered experiment 改写该 raw benchmark 结论。

## 实验边界与固定比较

### 不修改现有框架

- 所有新脚本、派生数据、checkpoint、报告和 viewer workspace 放在一个新的外层
  `temp/YYYYMMDD_HHMMSS-chrono-filter-surrogate-validation/` 下。
- 原 benchmark、`c0003`/`c0004` segments、已有 viewer workspace、tracked baseline 和 yadof
  source 全部只读。不得就地改 ZIP、NPZ、manifest、checkpoint 或 task 文件。
- 可以在 disposable harness 中复用 frozen postprocessor 的 loader、`_fit_cae()`、
  `_fit_conditional()`、prediction 和 metric 思路，或调用当前 package 内部 checkpoint writer；
  这些用法明确是一次性研究 glue，不得被包装成新的 public API 或写回 package。
- 不运行 Chrono simulator，不启动 optimization campaign，不把派生样本写入任何真实 campaign
  history。viewer workspace 内的 filtered records 只是为了让 read-only viewer 有一致 overlay；
  workspace provenance 必须明确标注它们是 derived targets，不是 simulator truth。

### 四个配对 arms

首轮固定为同一 `c0003` partition、model seed `154538516` 和 frozen gate-plan model settings：

1. `raw-cae`：优先复用已有 CAE viewer checkpoint；
2. `raw-inr`：用未滤波 train/validation rows 重训；
3. `filtered-cae`：用派生 filtered train/validation rows 重训；
4. `filtered-inr`：用同一派生 rows 重训。

四个 arms 使用完全相同的 completed design IDs、normalized parameters、字段集合、split、
training schedule、成员数、model seed、device policy 和 test IDs。不得因某个模型失败而为该
模型另选样本。若 raw-CAE 复用 artifact，必须核对其 manifest、model settings、partition 和
model seed 与本文固定身份完全一致；否则四臂均重训并记录原因。

`c0004` 只在首轮产生值得复核的趋势后作为第二 design-seed replicate 使用。首轮 viewer
印象、filter cutoff 或报告规则冻结后，才可打开 `c0004` test；它不是调参集。

## 派生滤波定义

### 首轮字段范围

首轮只滤波两个 513 点、`release_phase` 对齐的展示/诊断应力曲线：

- `trebuchet_arm_combined_normal_stress.npz` 的 `values`；
- `trebuchet_hanger_combined_normal_stress.npz` 的 `values`。

scalar、release summary、ball kinematics、axes、metadata，以及 cost 使用的
`trebuchet_peak_strength_utilization.npz` 均保持原样。这个有意限制使当前四项 cost 在 raw 与
filtered 副本间应保持相同，避免初期“更平滑”与“改变 objective truth”混在一起。派生前后
必须逐 row 重算 current cost 并断言在严格数值容差内一致；不一致立即停止。

如果两条目标曲线变平滑但 surrogate 仍受未滤波 utilization curve 干扰，可以把“整个 stress
family 都滤波”列为独立后继 arm；它会改变 strength-cost 语义，不能静默并入本首轮，也不能
与原 current-cost metric 直接比较。

### 初始低通候选与选择规则

- 滤波在 normalized `release_phase` 网格上进行，不把 cutoff 写成 Hz。不同 design 的
  `total_time_s` 不同，phase-domain cutoff 不是统一物理频率。
- 初始候选使用 deterministic zero-phase Butterworth low-pass：4 阶、`scipy.signal.sosfiltfilt`，
  normalized cutoff 候选为 Nyquist 的 `0.04`、`0.08`、`0.16`。这些是一次性调研候选，不是
  package default、物理阈值或验收门槛。
- 只允许用 `train_large` 和 `validation` 的 target-side 诊断选择一个 cutoff。选择前固定并
  报告：高频能量/二阶差分 roughness 降幅、RMS distortion、积分变化、原始最大值衰减、
  boundary artifact 和非有限检查。不得查看 test prediction 或 viewer 后再换 cutoff。
- zero-phase 只是为了避免额外 phase lag；它是非因果 offline transform，不能据此主张未来
  runtime 可实时使用。任何 padding、dtype conversion、边界处理和 filter 实现版本都进入
  `filter-plan.json` 与 SHA-256 identity。
- 若全部候选都出现明显 boundary ringing、非有限值或大范围物理形状破坏，首轮以
  `filter-not-selected` 完成并报告；不得为了得到平滑图临时换成未登记方法。新的方法另建
  plan/version。

## 派生数据与 provenance 要求

实验根至少包含：

```text
temp/<timestamp>-chrono-filter-surrogate-validation/
  filter-plan.json
  source-receipt.json
  scripts/
  derived-data/
  workspaces/
    raw-cae/
    raw-inr/
    filtered-cae/
    filtered-inr/
  reports/
    metrics.json
    summary.md
```

- `source-receipt.json` 记录 outer/repository absolute paths、installed yadof/Torch/SciPy 版本、
  source cell、segment list/hash、gate-plan/hash、partition-manifest/hash、design/model seeds、
  completed design IDs、field selectors 和首次 test access 时间。
- 每个 filtered sample 都有 sample ID、source record/array SHA-256、filtered array SHA-256 和
  filter-plan SHA-256 的外部映射。不要给重复或滤波后的 row 新造“独立 simulator design”身份。
- 派生 NPZ 保持 selector、shape `(513,)`、axis values、dtype 表示和 metadata schema；provenance
  放在 experiment receipt/`VIEWER_PROVENANCE.md`，不要通过增加 task metadata 字段改变模型
  schema。
- 若为 viewer 重建 standard recorded segments，使用受检的 writer/repacker 重算全部 manifest
  identity 和 member hash，随后用公开 history/query 路径逐 row 读回。禁止只替换 ZIP 内 NPZ
  而保留旧 hash。
- 每个 viewer workspace 写入 `VIEWER_PROVENANCE.md`，标明 `raw` 或 `filtered-derived`、source
  cell、filter identity、checkpoint identity、训练/test counts，以及“不得运行 optimization、
  不得作为真实 cost/history evidence”。

## 训练、定量检查与 viewer 观察

### 训练与 checkpoint

- CAE/INR 均复用 frozen gate-plan 中对应配置；不得为了 filtered arm 单独增加 capacity、epoch
  或成员数。训练资源、wall time、RSS/CUDA peak、checkpoint size 和失败原因逐 arm 记录。
- checkpoint 必须进入各自 viewer workspace 的正确 active strategy/component namespace。
  CAE 与 INR 不能共用或覆盖 namespace；所有 semantic/checkpoint manifests 可由当前 viewer
  `summary` 发现。
- filtered target 的 train、validation 和 test transform 使用同一个 frozen filter-plan。
  只有 filter-plan 冻结后才能生成 filtered test arrays。

### 必须报告的配对指标

1. **Transform distortion：** filtered-vs-source 的 MAE/RMSE、RMS、积分、total variation、
   二阶差分 roughness、高频能量、最大值衰减和最大值 phase 位移，按字段与 design quantile
   报告。
2. **对 filtered target 的拟合：** CAE/INR 的 field MAE/RMSE、worst-field、roughness ratio、
   高频 leakage、过冲幅度和无对应窄峰计数。
3. **对 source raw truth 的代价：** 同一 predictions 也对未滤波 test arrays 报告误差与峰值
   损失，防止“只要删掉困难 target 就一定更准”的循环定义。
4. **非目标字段与 cost guard：** 未滤波字段的误差不得被省略；raw/filtered dataset 的 current
   costs 必须一致。这里的 cost 只作语义守卫，不是滤波收益指标。
5. **配对性与资源：** 所有 deltas 以相同 design ID 配对，并分别报告 CAE 与 INR。不要把两种
   architecture 的不同基础误差合成一个总平均。

### viewer 检查

先运行每个 workspace 的 `view surrogate summary` 和小比例 `audit`，确认 checkpoint、真实
overlay、字段顺序和 prediction 均可读，再启动 GUI。外层 workspace 命令形状为：

```powershell
& ".\.venv\Scripts\python.exe" -m yadof view surrogate summary `
  --workspace ".\temp\<experiment>\workspaces\filtered-cae"
& ".\.venv\Scripts\python.exe" -m yadof view surrogate audit `
  --workspace ".\temp\<experiment>\workspaces\filtered-cae" `
  --sample-percent 1 --random-seed 20260830 --metric both --quantity all-costs `
  --format text --progress
& ".\.venv\Scripts\python.exe" -m yadof view surrogate gui `
  --workspace ".\temp\<experiment>\workspaces\filtered-cae"
```

对四个 arms 使用同一组预先记录的 test design IDs、同一字段、同一 axis/window 和相同显示
尺度。观察集至少包含原截图对应个体（若能稳定映射）、raw roughness 分位数的低/中/高样本、
最大值插回产生的单点尖峰样本和较平滑样本。样本选择只依赖 source rawData 与固定 seed，
不能按某个模型看起来最好来挑图。

viewer 观察至少记录：真实/预测 broad trend、无对应窄峰、峰值过冲、phase 偏移、边界振铃、
CAE/INR 差异，以及 filtered overlay 与原 raw curve 的肉眼差异。视觉平滑不能替代配对 metric；
viewer 也不训练模型或修改 workspace。

## 结果解释与下一步决定

本实验不设一个强行通过的总 gate。完成后按以下证据分支解释：

- **CAE 与 INR 都明显改善：** 支持“target 高频结构是共同难点”，但仍不证明应该在生产中
  删除物理峰值；下一步应单独决定趋势曲线与未滤波 peak scalar/residual 的双通道任务定义。
- **只有 CAE 改善：** 更可能指向 CAE representation/codec/shared-latent 对尖峰敏感；结果交给
  [基础 CAE 证据研究](../../toDo/20260830_120818_hierarchical-cae-evidence-led-research.md) 作诊断输入，
  不自动修改 CAE architecture。
- **只有 INR 改善：** 说明问题不是 CAE 独有，应检查 conditional coordinate decoder、scaling
  或 field sharing；也不能据此把滤波升为框架通用机制。
- **filtered truth 已平滑但 predictions 仍 chatter：** 削弱“原始尖峰是主要原因”的假设，
  优先查 model/scaling/checkpoint/viewer adaptation，而不是继续加大滤波。
- **视觉更平滑但 raw-truth error、峰值保存或非目标字段明显恶化：** 记录 smoothing tradeoff，
  不进入框架集成。

只有用户看完报告和四个 viewer 后，才决定是否提出新的正式任务：viewer-only 显示滤波、
Chrono task 层的“filtered trend + unfiltered peak scalar”、surrogate transform component，或不再
继续滤波路线。任何正式方案必须重新处理 current cost、checkpoint identity、real/filtered
overlay 和历史兼容，不由本 TODO 预先批准。

## 非目标

- 不修改 `submit/optimization.py` 来假装已有 low-pass API，也不把现有
  `data_filter_mode="frequency"` 当成 smoothing；该模式只影响 CAE training assessment/
  weighting，不改写 rawData。
- 不平滑或覆盖 source benchmark evidence，不重跑失败 designs，不访问 reserved calibration，
  不生成新 Chrono simulator data。
- 不把 filtered viewer workspace 用于 optimization、qNEHVI、posterior calibration、发布 gate
  或默认策略比较。
- 不恢复抗噪声 MoE/regime-specialized TODO，不把 chatter 当作 IID measurement noise，也不
  删除 failure rows 来改善图形。
- 不因一个漂亮个体或单一误差均值声称滤波有效；不把 zero-phase filter 当成未来 causal/
  real-time 实现承诺。

## 完成规则

满足以下条件后，本 TODO 可以移入 `dev_doc/obsolete/todo/`：

- 原 benchmark 和已有 viewer workspace 保持不变，source/filter/partition/checkpoint receipts
  能从新实验根独立复核；
- `c0003` 四个 raw/filtered × CAE/INR arms 使用相同 completed rows、split、model settings 和
  seed 完成，或每个失败 arm 留下可诊断的完整失败记录；
- filter 在 test access 前冻结，reserved calibration 未访问，current-cost equality guard 通过；
- 四个 viewer workspaces 都通过 `summary` 和小比例 `audit`，并能对固定 test designs 作一致
  GUI 对照；
- `summary.md` 同时报告 transform distortion、filtered-target fit、source-raw fit、非目标字段、
  paired resource/metric 与代表性 viewer 观察，没有把视觉平滑写成物理正确性；
- 已明确记录下一步是 formal integration research、只做 viewer 展示、扩大到 `c0004` 复现，
  还是停止路线；真实 simulator、长训练扩展或框架修改仍需新的用户授权和相应文档维护。
