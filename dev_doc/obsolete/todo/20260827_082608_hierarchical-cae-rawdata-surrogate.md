# 新增分层 CAE + Parameter Latent Predictor + Coordinate Readout 拟合器

## 背景与需求

- 用户要求新增一个模块化 rawData 拟合器，不替换或重写当前 conditional-INR。
- 生产关注约 1000--2000 个真实设计样本时的拟合效果，不要求几十个样本下有竞争力。
- 每次真实评估一般小于一核时，代理训练可以占用有意义但受控的计算预算；不能假设真实
  评估像大型气动仿真那样昂贵到可以忽略任意代理开销。
- rawData 字段可能形状和坐标不同，但具有物理相关性。例如 1-D S11 与 2-D gain 强
  相关，与 axial ratio 弱相关。简单拼接网格或按相同坐标卷积无法表达这种关系。
- 用户选择 convolutional autoencoder + parameter latent predictor + coordinate trunk；
  PCA/SVD 只允许作为基线、初始化或秩估计，不作为生产默认拟合器。

### 已核对的 benchmark baseline 数据形态

首版 schema 和 codec 验收以当前 `benchmark_automation/baselines/` 为事实来源，而不是以
“任意 tensor”作为隐含承诺：

| baseline | stable field selectors | main shape | main dtype / axes |
|---|---|---|---|
| SAW ladder | `s21_db.npz/data`、`s11_db.npz/data` | 各 `[1201]` | `float64`，固定 frequency 轴 |
| Chrono trebuchet | 9 个 `*.npz/values` 标量 | 各 `[]` | `float64` |
| Chrono trebuchet | 7 个 `*.npz/values` phase curves | 各 `[513]` | `float64`，固定 release-phase 轴 |
| synthetic antenna | 3 个 `s11_pinState*.npz/data` | 各 `[5]` | `float64`，固定 `Freq` 轴 |
| synthetic antenna | 3 个 `gain_lhcp_pinState*.npz/data` | 各 `[1,73,73]` | `float64`，固定 `Freq/Phi/Theta` 轴 |
| synthetic antenna | 3 个 `axial_ratio_pinState*.npz/data` | 各 `[5,73,73]` | `float64`，固定 `Freq/Phi/Theta` 轴 |

这里的 selector 是已批准的 `(NPZ basename including .npz, main array key)`；显示时用
`basename/key` 简写。baseline template 自身没有 1000--2000 条训练记录，这张表只确定
首版数据契约，不构成模型性能证据。

## 最终目标架构与首个垂直 MVP

新增独立组件（工作名 `hierarchical_cae()`，最终命名应在实现时与公开 API 一致），其
权威推理路径为：

```text
normalized parameters x
  -> typed parameter encoder / latent predictor
  -> global + optional group + field-private latent state
  -> field-specific convolutional grid decoders
  -> complete schema-compatible rawData
  -> current calc_cost.py when a cost is requested
```

coordinate readout 使用同一 latent state 提供 off-grid 查询，但不取代完整网格解码器。

首个可运行 MVP 有意比最终图简单：

```text
per-field convolutional codecs
  + one shared parameter-predictor backbone
  + global / optional-group / field-private output heads
  + per-field full-grid decoders
```

首版不加入 cross-field attention、复杂 fusion gate、native Conv3d 或完整模型 ensemble。
这些结构只有在预登记消融表明简单架构不足时才进入下一 gate。coordinate trunk 保留为
用户已选定的后续组成，但排在 full-grid decoder 达到拟合门槛之后；它不阻塞第一个
rawData-to-cost/qNEHVI 垂直切片。

## 已确定的共享与分组语义

### 默认行为

“默认不分组”的准确含义是：

- `groups=()`，没有显式 semantic group latent；
- 所有被建模字段仍共享一个 `z_global`；
- 每个字段始终拥有自己的 `z_private[i]` 和独立 encoder/decoder；
- shared parameter-predictor backbone 可以从同一参数状态联合预测全部 field latents，从而
  学习跨字段关系；首版不要求 attention 才能做到这一点。

默认绝不能把各字段训练为完全独立模型，否则无法捕捉 S11、gain、axial ratio 的关系。

### 可选显式分组

- task-specific 分组在首个 MVP 就支持，通过 workspace `submit/optimization.py` 中的新
  surrogate factory 参数声明，而不是写入 package global config；示意：

  ```python
  hierarchical_cae(
      groups=((
          ("s11_pinState1.npz", "data"),
          ("gain_lhcp_pinState1.npz", "data"),
      ),),
  )
  ```

- 首版只支持不重叠的显式组，避免一个字段的多重 group latent 含义不清；如未来有真实
  benchmark 证明需要重叠组，再扩展协议。
- 分组引用稳定的 rawData field identity，而不是依赖数组出现顺序。不同 rank、不同坐标
  网格的字段可以在同一组中。
- 显式组是增强已知结构先验的可选能力，不是捕捉跨字段相关性的前提。
- `groups=()` 不创建 group heads、group parameters 或 group-state checkpoint payload；相对
  同 latent 尺寸的显式分组，默认路径少量更快且更省内存。显式组的增量开销主要是小型
  group head/fusion 和附加 latent，不应接近卷积 codec 的成本；仍须在 benchmark 中报告
  参数量、训练墙钟和峰值内存，不能只凭理论判断为“免费”。

### 分层 latent

首个 MVP 对字段 `i` 采用固定 selector 顺序和轻量 MLP heads，类似：

```text
E_i(Y_i) -> field token t_i
ordered concat(t_1, ..., t_k) -> lightweight teacher fusion targets
P_shared(x) -> h(x)
P_global(h) -> z_global
P_group[g](h) -> z_group[g]                         # optional, first-MVP supported
P_private[i](h) -> z_private[i]
D_i(z_global, optional z_group[g], z_private[i]) -> Y_i
```

训练时由 rawData encoders 得到 teacher latent；推理时 parameter latent predictor 从 `x`
预测同样的 global/group/private latent。每个 field decoder 接收共享和私有部分，private
path 防止负迁移。只有该简单结构的 validation/ablation 证明无法表达所需强弱相关时，才
比较 learned gates 或 attention；不得一开始同时叠加两者。

## rawData 字段与卷积路径

- 保持现有 job-template 语义：一个字段代表一个连贯的物理量。不能因为坐标相同就把
  无关曲线虚构成 channel，也不能为了统一形状把独立字段永久拼成一张图。
- 每个字段先由 schema adapter 识别 selector、rank、shape、axes 和 dtype，再选择
  field-specific encoder/decoder：标量使用小型 MLP，1-D 使用 Conv1d，2-D 使用 Conv2d。
- baseline 天线字段的 main array 是 rank 3。首版通过 selector-keyed `field_layouts` 明确
  轴角色：把 `Freq` 作为 channel/condition axis，把 `Phi/Theta` 作为 Conv2d spatial axes，
  decoder 最终还原 `[Freq,Phi,Theta]` 原 shape。不得仅因某轴长度为 1 或 5 就猜测它是
  channel；没有明确 layout 的 rank-3 字段给出 actionable unsupported diagnostic。native
  Conv3d 延后到 benchmark 证明该布局表达不足时再考虑。
  概念配置例如：

  ```python
  field_layouts={
      ("gain_lhcp_pinState1.npz", "data"): {
          "channel_axes": ("Freq",),
          "spatial_axes": ("Phi", "Theta"),
      },
  }
  ```

  最终公开类型可以更严格，但不得退化为按 field 名称硬编码天线规则。
- 不同字段无需同尺寸、同坐标或同采样密度。用于 fusion 的 field token 是固定长度，
  但权威输出必须还原各字段自己的原始 shape、axes、metadata 和数值 dtype 约束。
- 首版只接受每个 semantic signature 下固定的 selector 集合、main shape、axis arrays 和
  template。batch padding 只允许用于固定 schema 内的实现对齐，并带显式 mask；不能用
  mask 接受缺失字段、可变 shape 或本应被 rawData schema 拒绝的证据。

## 网格解码器与 coordinate readout

### 权威固定网格输出

- `ConvGridDecoder[i]` 生成字段 `i` 的完整 checkpoint schema 网格。
- optimizer cost、posterior draw、audit 和 checkpoint recovery 的 full rawData 都走此
  路径，不能先逐坐标查询 coordinate trunk 再拼接。
- 对非规则轴，可在 schema adapter 中保留原坐标并使用 index-grid convolution；模型
  必须把真实轴编码进 latent/readout，不能假设 index 距离等于物理距离。

### 任意坐标查询

- coordinate readout 是 full-grid MVP 之后的独立 gate。原始科学验收顺序要求 grid decoder、
  current-cost round trip 和目标规模拟合先通过；Gate 0 v6 后仅允许以
  `experimental / performance-not-accepted` 身份完成这一框架阶段，不改变该顺序的生产含义。
- `CoordinateReadout[i](latent_i, coordinates)` 负责 viewer/off-grid 查询。
- 坐标编码覆盖字段的全部轴，不再保留 conditional-INR 当前最多三列坐标的限制。
- 轴编码至少支持显式的 linear normalization；log/periodic 等类型只在 schema 或 factory
  中有明确声明时使用，不能从数值外观猜测。periodic 轴使用 sin/cos 等连续编码。
- 在 stored grid coordinates 上加入 grid-decoder/readout consistency loss。通过验收后，
  选取 checkpoint 网格坐标时两条路径应在定义容差内一致。
- coordinate readout 不改变保存的 rawData schema，也不成为 qNEHVI 计算 cost 的捷径。

## 训练阶段

建议采用分阶段和可停止 gates，而不是一次从 `x` 端到端盲训：

1. **Schema/benchmark freeze**：先固定 baseline field inventory、layout、split、指标、资源
   预算和停止条件。
2. **Per-field manifold pretraining**：各 field encoder/decoder 重构完整 rawData；共享只用
   简单 ordered-token fusion。
3. **Latent regression**：shared parameter predictor 与 global/group/private heads 学习从
   normalized `x` 到 encoder latent。
4. **Full-grid fine-tuning gate**：只有 validation 证明端到端微调带来稳定收益时才联合微调
   predictor 与 decoders；否则保留冻结 codec，减少训练波动。
5. **Coordinate-readout gate**：在真实网格和抽取坐标上训练 coordinate readout，并保持与
   grid decoder 一致；不影响前四阶段的 qNEHVI 可用性。

训练/验证/测试必须按完整 design row 切分；绝不能把同一设计的不同坐标拆到不同 split，
否则会产生严重泄漏。

## 损失、归一化与细节要求

- 保留 real-only 训练：只用兼容的真实记录或对真实 design rows 的可复现 bootstrap，
  不创建 synthetic target。
- 每个字段先在自己的有效网格内归一化并平均，再对字段做等权 macro-average，防止点数
  更多的 2-D gain 支配 1-D S11。显式 semantic group 不改变该默认字段公平性。
- 基础重构损失可采用标准化后的 Smooth L1/MSE。梯度、频谱或多尺度结构损失只能作为
  有 benchmark 的通用可配置项；不得让 task-specific 物理权重进入 package。
- constant/near-constant 字段、极端 scale、非有限历史和小 batch 行为需要显式数值策略。
- parameter encoder 必须遵循 yadof 当前 normalized variable 和离散/分段参数语义；不要
  假设所有维度在物理空间连续。
- 首版 main arrays 限于 benchmark 所覆盖的 finite real floating data。complex main array
  以后必须显式选择 real/imag（或 magnitude/phase）双通道表示并进入 semantic identity，
  不得静默取实部；缺失字段、可变 shape 和随 design 变化的 axes 同样延后。
- 使用 early stopping、梯度裁剪、mixed precision 的安全门、确定性 seed、训练/推理
  batch 上限和峰值内存诊断。
- checkpoint 保存最小可恢复状态，不复制训练 rawData；包含 model architecture version、
  field selectors/schema/layouts、group specification、axis encodings、scalers、训练配置和
  semantic signature。

首个 posterior MVP 共享一套已训练的 codecs，并对 parameter predictor/backbone + heads 做
独立初始化或 design-row bootstrap ensemble。它比每个 member 复制完整 CAE 更便宜，也能
让每个 predictor member 对所有字段给出一个联合函数；只有 held-out calibration/decision
benchmark 证明 decoder/codec epistemic uncertainty 不可忽略时，才升级为完整模型 ensemble。

## 2026-08-27 quality/regime 抗噪 MVP 追加边界

在 formal dataset/test 尚未出现时，Gate 0 已新增不可变 v2 预注册，而没有修改 v1 的
inventory/splits/seeds。当前 Chrono 证据更符合参数决定的 chatter/failure regime，不解释为
measurement noise；不得按 cost 过滤、平滑或改写原始 rawData。

本 TODO 的实际实现同时要求：

- core 只拥有版本化、JSON-safe 的 assessment/policy、字段权重、validation、semantic
  identity/checkpoint/diagnostics；Chrono release/cutoff/contact/recontact 规则由 task policy
  声明，不能以未追踪 callback 或字段名硬编码进入 core；
- 损失先形成 design × field 矩阵，再做 capped/weighted macro aggregation；no-policy 默认
  明确退化为普通等权 field macro，noisy curves 不会连带丢弃同一设计的有效 scalars；
- noisy/低可信 token 在 teacher fusion 前 mask/downweight，chatter 高频残差只经过
  field-private gated residual；smooth target 的 residual gate 为零，从结构上限制 clean
  target 高频泄漏；
- parameter predictor 提供未校准 `P(smooth)`/applicability head。policy/version、标签语义、
  权重/阈值、head/loss 配置全部进入 identity/checkpoint；本 TODO 不提前做 082609 概率校准；
- regime uncertainty 仍是 epistemic/结构状态不确定性，observation noise 保持 zero；同一
  posterior member/draw 必须跨 candidates/fields 保持身份。

预登记消融固定为 `无门控 / 仅稳健加权 / shared-latent 隔离 / gated residual`。只有 held-out
证据仍显示明显 clean-target 泄漏，才允许后续 gate 比较 mixture-of-experts；本轮不实现。

## 2026-08-27 实施与 Gate 4 结果

本轮已完成并保留一个可安装、可恢复的 experimental full-grid MVP：stable-selector schema、
scalar/Conv1d/Conv2d codecs、global/optional-group/field-private latent、共享 codecs 的 predictor
ensemble、完整 rawData/current-cost 推理、原子 checkpoint/recovery、persistent finite posterior
draw，以及上述 quality/regime 协议、稳健 design × field loss、shared-token 隔离、gated private
residual 和未校准 applicability API。现有 conditional-INR 训练与 checkpoint 语义未修改。

实验严格只启动了一个真实数据 campaign 和一个 validation 长进程：

- campaign `hierarchical-cae-gate4-v2-20260827` 的 6 个 cell 全部完成，合计 12000 次 attempted
  real evaluations；每个 case 从可解释证据中封存 2800 个 design，固定为 development 6600、
  calibration 600、offline-test 1200。权威清单位于
  `temp/hierarchical_cae_gate4_runs/hierarchical-cae-gate4-v2-20260827/dataset_seal/sealed_dataset_manifest.json`
  （SHA-256 `2d1af1439e8e82899a3a6a59a798ba8aefc1c51562a8f3f2d8f8e59b18b4d5c9`）。
- Gate 0 v3 固化 task diagnostic 路径与 dataset seal；v4 保留首次 0-cell/exit-1 失败证据，且只
  修复 conditional-INR benchmark metadata adapter 后冻结 116-cell `validation_plan_v2.json`。
  同一 validation 进程完成 116/116 cells、exit 0、wall 10501.691 s；validation summary SHA-256
  为 `f672bfa115238718388a17d66b4aaf63066f07a6072bf4a9c96a9e4250aeb0f2`。validation 未启动
  simulator，也未打开 calibration/offline-test locator。
- Gate 0 v5 只使用 development-validation 证据封存 082608 representation/quality 数值门槛，
  并把判定固化到 `validation_decision.json`；它没有放宽门槛来制造通过。

Gate 4 的 full-grid 判定为 **失败**。生产候选相对 conditional-INR 的五 seed 均值如下；
列依次为 field-macro MAE ratio、RMSE ratio、current-cost macro MAE ratio、最差单字段 RMSE
ratio：

| case / production arm | train=1000 | train=2000 |
|---|---|---|
| SAW / `groups-none` | 1.14577 / 0.98156 / 0.96824 / 1.02985 | 1.15204 / 0.95774 / 1.07139 / 0.98648 |
| Chrono / `gated-private-residual` | 1.16701 / 0.99810 / 0.92417 / 2.64995 | 1.26278 / 1.00331 / 0.98644 / 3.85268 |
| test-com / `groups-none` | 1.14817 / 1.06881 / 0.65736 / 2.69171 | 0.89732 / 0.83051 / 0.51594 / 2.76786 |

Chrono gated arm 的 clean-target 高频泄漏率为 0.37714/0.36857，smooth predicted/real 高频
roughness median ratio 为 2.4013/2.3137；两种训练规模下的泄漏分别比 shared-latent
isolation 高 5.60%/2.38%。分类诊断本身达到 validation 门槛（AUPRC 0.3204/0.37278、Brier
0.08130/0.07671、ECE 0.05262/0.03684），但不能抵消 representation、clean leakage、smooth
roughness 和 gated-ablation 的失败。

因此在 v5 决定时，本 TODO 保持 active，coordinate readout/viewer adapter、offline test、
082609 calibration 与 082611 qNEHVI exploitation 均被阻塞。下一 architecture gate 可在新版本
预注册中比较有界 regime-specialized/mixture-of-experts 方案；这是 v5 证据触发的后续工作，
不属于本 MVP，也不能修改 v5 的冻结含义。

## Gate 0 v6--v7 实验性框架续行（2026-08-27）

用户随后明确决定：v5 性能失败继续冻结，但不再阻塞本日剩余的框架完整性工作。Gate 0 v6
在首次 offline-test access 前绑定 commit
`df17efbff8e9b2f44c0a672b1fd0d59aeeb83ed9`、source hashes、一个既有 seed `69168527`、三个
case、train=1000/2000 和 12-cell plan；coordinate/performance threshold 有意保持 `null`，
且禁止本执行单元调性能或实现 successor architecture。

在此窄授权下已完成：

- architecture version 2 的 per-field coordinate trunk 使用与 full-grid decoder 相同的
  member-level global/group/private latent；base readout 加同一 applicability gate 控制的
  field-private residual，并在 development train/validation 上独立分阶段训练；
- linear/log/periodic 显式轴编码覆盖所有声明轴，只允许轴域内查询；stored-grid consistency
  loss 与只读 `predict_field_at_coordinates()` API 不改变 checkpoint state；
- viewer backend 能在 active strategy 下发现单一 conditional-INR 或 hierarchical-CAE
  namespace；hierarchical checkpoint 的 full-grid 仍是 cost/audit/optimizer 权威路径，
  coordinate readout 只服务 viewer/off-grid；
- 唯一 v6 offline 长进程 session `33861` 完成 12/12 cells、exit 0、wall 1466.907 s，读取三个
  case 共 1200 个 offline-test designs；未读取 calibration locator、未启动 simulator、test
  没有参与训练或 early stopping。权威目录为
  `temp/hierarchical_cae_gate4_runs/hierarchical-cae-gate4-v2-20260827/experimental_offline_v6`，
  `offline_summary.json` SHA-256 为
  `84eed10dc6051374af871a84d5334c988268a029fdf2e18ed5f2bdec8cd93096`，`run_spec.json`
  SHA-256 为 `599410e4e8fcce79709eef3f9da3568c2030cb76c03168b6d4553ef096311482`；
- 首次 sandbox launch 在创建该精确 output directory 时因混合 ACL 以 exit 1 结束，发生在
  locator access/training 之前且产生 0 cells；v7 单独保留 receipt，随后只创建该目录并以
  host identity 运行未改动 runner 一次，没有重复 model/test 计算。

v7 的六个 coordinate cells 均给出有限 stored/off-grid 查询且 query 前后 state digest 相同；
最大 sampled coordinate-vs-grid standardized RMSE 为 0.63776。单 seed 的 candidate/
conditional field-macro MAE ratio 为：Chrono 1.20186/1.29294、SAW 1.29201/1.14690、
test-com 1.15099/0.89248（train=1000/2000）。这些数值只证明机制执行，不能制定或通过
post-access threshold，也不能反转 v5 的 `full_grid_gate_passed=false`。

因此当前精确状态是：coordinate/viewer/offline-test **框架机制完成**，但 CAE 与 coordinate
性能均为 **未验收**；082608 继续 active、不得归档。性能调优和 successor architecture 已明确
延后为独立工作。082609 只能在另行预登记 calibration access、冻结由 development-only 数据
得到的 durable experimental checkpoint/state signature 后推进实验性 calibration framework；
082611 可以准备 typed capability plumbing，但当前 head 不得控制 exploitation。

## 数据规模与调度目标

- 验收重点是 1000 和 2000 个设计附近，不设置小样本性能门槛。
- 初始 warm-up 建议在约 300--500 个兼容设计后开始；这是待 benchmark 调整的起始区间，
  不是硬保证或固定公共默认。
- refresh 可从新增 100--200 个设计或训练集增长约 10% 的触发策略开始比较；同样是调优
  候选，不应在没有成本测量前承诺。
- 训练墙钟、CPU/GPU 峰值内存和采集推理开销必须与“小于一核时/真实评估”的实际任务
  比例一起记录。不能沿用“代理计算免费”的大型 CFD 假设。

## PCA/SVD 的位置

- 为每个字段或拼接后的标准化训练矩阵实现只读 benchmark baseline，用于估计可压缩秩、
  检查数据管线和比较 CAE 是否真正带来非线性表示收益。
- 可以用 PCA/SVD 初始化 latent dimension 搜索，但生产预测仍由 CAE/predictor/decoder
  完成。
- 不增加一个可被误选为生产默认的 PCA surrogate factory，除非后续用户单独批准。

## 模块与兼容边界

- 新私有 package、checkpoint method、component namespace 和 semantic identity 与
  `conditional_inr/` 完全分离；不得加载或覆盖其权重。
- 现有 `conditional_inr()` factory、GPSAF 组合和 viewer 行为保持不变。
- 新 component 实现
  [联合 rawData posterior 契约](../obsolete/20260827_082607_joint-rawdata-posterior-contract.md)，
  同时可以提供由 samples 派生的 mean/rawData 诊断视图。
- viewer 通过新的 backend adapter 读取该 checkpoint；UI 不直接导入模型内部类型。
- semantic group specification 属于 task composition identity。改变分组应激活新的可恢复
  namespace，并保留旧 artifacts。

## 验证要求

- 标量、1-D、2-D 以及混合 rank 字段的 schema round trip 和完整 cost round trip。
- 人工构造强相关、弱相关和独立字段：默认无显式 group 时 global latent 应优于完全独立
  ablation；显式 S11/gain group 不得恶化其他字段到预先规定的容差之外。
- field-order permutation 不改变 identity-based grouping 结果。
- 当前三个 benchmark baselines 的 selector/shape/layout round trip 全部通过；天线 rank-3
  fields 通过显式 channel/spatial layout 还原，未声明 rank-3 layout 被明确拒绝。
- 每字段 macro loss 不随其网格点数成比例放大。
- stored-grid coordinate readout 与 grid decoder 一致；off-grid 查询不修改 checkpoint。
- design-level split 无坐标泄漏，early stopping 只看 validation designs。
- checkpoint 原子发布、恢复、namespace 隔离、配置/axis/group 不兼容时冷训练。
- Torch 仍按选择 lazy import；无对应 extra 时错误可操作。
- quality assessment 的显式诊断优先级、task diagnostic declarative rules、shape fallback、
  no-policy 普通行为、design × field cap/weight、shared mask、clean residual gate 和
  applicability API/identity/checkpoint 全部有测试。

## 非目标

- 不修改现有 conditional-INR 数学或 GPSAF 选择规则。
- 不保证任意 rank/任意大小 tensor 在首版都能卷积建模；不支持的情况必须显式失败。
- 首版不支持 complex、缺失字段、可变 shape/axes 或 native Conv3d；不得以静默 coercion
  伪装支持。
- 不将 coordinate readout 作为权威 full-grid/cost 路径。
- 不优化或保存直接的 `parameters -> cost` 模型。
- 不以少于约 300 个样本的结果作为上线阻塞条件。

## 完成规则

- 新组件能够在安装后的 yadof 中独立选择、训练、恢复并预测完整 rawData；
- 默认无显式 group 仍能通过 global latent 捕捉跨字段关系，显式分组行为有测试和文档；
- 1000--2000 设计的离线 benchmark 达到
  [验收 TODO](20260827_082612_validate-new-surrogate-and-qnehvi.md) 预先登记的门槛；
- coordinate viewer adapter、配置、架构、blueprints、terminology、user docs、artifact 和
  installed-wheel 测试已更新；
- 现有 conditional-INR/GPSAF 回归测试保持通过，随后将本 TODO 移入 obsolete。

当前已满足组件、full-grid rawData、checkpoint、posterior/quality 协议，以及 experimental
coordinate readout/viewer/offline-test 的框架与文档测试部分。Gate 0 v5 仍明确
`full_grid_gate_passed=false`，v6/v7 也明确 `performance_accepted=false` 和
`coordinate_performance_accepted=false`；因此 1000--2000 design 科学性能及最终归档两项
completion rule 尚未满足，不得移动到 `obsolete/`。
