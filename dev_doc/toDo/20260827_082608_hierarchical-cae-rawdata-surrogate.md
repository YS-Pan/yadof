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

## 目标架构

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

## 已确定的共享与分组语义

### 默认行为

“默认不分组”的准确含义是：

- `groups=()`，没有显式 semantic group latent；
- 所有被建模字段仍共享一个 `z_global`；
- 每个字段始终拥有自己的 `z_private[i]` 和独立 encoder/decoder；
- fusion gate 或 cross-field attention 可以自动学习强、弱或接近零的共享关系。

默认绝不能把各字段训练为完全独立模型，否则无法捕捉 S11、gain、axial ratio 的关系。

### 可选显式分组

- task-specific 分组应通过 workspace `submit/optimization.py` 中的新 surrogate factory
  参数声明，而不是写入 package global config；示意：

  ```python
  hierarchical_cae(
      groups=(("s11", "gain"),),
  )
  ```

- 首版只支持不重叠的显式组，避免一个字段的多重 group latent 含义不清；如未来有真实
  benchmark 证明需要重叠组，再扩展协议。
- 分组引用稳定的 rawData field identity，而不是依赖数组出现顺序。不同 rank、不同坐标
  网格的字段可以在同一组中。
- 显式组是增强已知结构先验的可选能力，不是捕捉跨字段相关性的前提。

### 分层 latent

对字段 `i`，采用类似：

```text
E_i(Y_i) -> field token t_i
F_global(t_1, ..., t_k) -> z_global
F_group({t_i | i in group g}) -> z_group[g]        # optional
R_i(t_i, z_global, z_group) -> z_private[i]
```

训练时由 rawData encoders 得到 teacher latent；推理时 parameter latent predictor 从 `x`
预测同样的 global/group/private latent。每个 field decoder 接收共享和私有部分。fusion 应
允许 learned gates 或 attention 衰减弱相关通道，private path 则防止负迁移。

## rawData 字段与卷积路径

- 保持现有 job-template 语义：一个字段代表一个连贯的物理量。不能因为坐标相同就把
  无关曲线虚构成 channel，也不能为了统一形状把独立字段永久拼成一张图。
- 每个字段先由 schema adapter 识别 rank、shape、axes、dtype 和稳定 identity，再选择
  field-specific encoder/decoder：标量使用小型 MLP，1-D 使用 Conv1d，2-D 使用 Conv2d；
  Conv3d 仅在显式内存门限和测试存在时启用。其他 rank 必须给出明确 unsupported
  diagnostic，不能静默 flatten 后冒充卷积。
- 不同字段无需同尺寸、同坐标或同采样密度。用于 fusion 的 field token 是固定长度，
  但权威输出必须还原各字段自己的原始 shape、axes、metadata 和数值 dtype 约束。
- batch padding 只允许用于实现层结构对齐，并带显式 mask；不能用 mask 接受本应被
  rawData schema 拒绝的无效证据。

## 网格解码器与 coordinate readout

### 权威固定网格输出

- `ConvGridDecoder[i]` 生成字段 `i` 的完整 checkpoint schema 网格。
- optimizer cost、posterior draw、audit 和 checkpoint recovery 的 full rawData 都走此
  路径，不能先逐坐标查询 coordinate trunk 再拼接。
- 对非规则轴，可在 schema adapter 中保留原坐标并使用 index-grid convolution；模型
  必须把真实轴编码进 latent/readout，不能假设 index 距离等于物理距离。

### 任意坐标查询

- `CoordinateReadout[i](latent_i, coordinates)` 负责 viewer/off-grid 查询。
- 坐标编码覆盖字段的全部轴，不再保留 conditional-INR 当前最多三列坐标的限制。
- 轴编码至少支持显式的 linear normalization；log/periodic 等类型只在 schema 或 factory
  中有明确声明时使用，不能从数值外观猜测。periodic 轴使用 sin/cos 等连续编码。
- 在 stored grid coordinates 上加入 grid-decoder/readout consistency loss。通过验收后，
  选取 checkpoint 网格坐标时两条路径应在定义容差内一致。
- coordinate readout 不改变保存的 rawData schema，也不成为 qNEHVI 计算 cost 的捷径。

## 训练阶段

建议采用分阶段再联合微调，而不是一次从 `x` 端到端盲训：

1. **Manifold pretraining**：field encoders、fusion 和 grid decoders 重构完整 rawData。
2. **Latent regression**：parameter latent predictor 学习从 normalized `x` 到 encoder latent。
3. **End-to-end fine-tuning**：通过完整 rawData 重构损失联合微调 predictor 与 decoders。
4. **Coordinate consistency**：在真实网格和抽取坐标上训练 coordinate readout，并保持与
   grid decoder 一致。

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
- 使用 early stopping、梯度裁剪、mixed precision 的安全门、确定性 seed、训练/推理
  batch 上限和峰值内存诊断。
- checkpoint 保存最小可恢复状态，不复制训练 rawData；包含 model architecture version、
  field schema、group specification、axis encodings、scalers、训练配置和 semantic signature。

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
  [联合 rawData posterior 契约](20260827_082607_joint-rawdata-posterior-contract.md)，
  同时可以提供由 samples 派生的 mean/rawData 诊断视图。
- viewer 通过新的 backend adapter 读取该 checkpoint；UI 不直接导入模型内部类型。
- semantic group specification 属于 task composition identity。改变分组应激活新的可恢复
  namespace，并保留旧 artifacts。

## 验证要求

- 标量、1-D、2-D 以及混合 rank 字段的 schema round trip 和完整 cost round trip。
- 人工构造强相关、弱相关和独立字段：默认无显式 group 时 global latent 应优于完全独立
  ablation；显式 S11/gain group 不得恶化其他字段到预先规定的容差之外。
- field-order permutation 不改变 identity-based grouping 结果。
- 每字段 macro loss 不随其网格点数成比例放大。
- stored-grid coordinate readout 与 grid decoder 一致；off-grid 查询不修改 checkpoint。
- design-level split 无坐标泄漏，early stopping 只看 validation designs。
- checkpoint 原子发布、恢复、namespace 隔离、配置/axis/group 不兼容时冷训练。
- Torch 仍按选择 lazy import；无对应 extra 时错误可操作。

## 非目标

- 不修改现有 conditional-INR 数学或 GPSAF 选择规则。
- 不保证任意 rank/任意大小 tensor 在首版都能卷积建模；不支持的情况必须显式失败。
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
