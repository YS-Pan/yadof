# 为 conditional-INR 增加联合 posterior 兼容适配器

## 背景与已验证现状

- 当前 conditional-INR 是一个联合模型 ensemble。runtime 内部 member prediction 的
  形状为 `[member, candidate, flattened_rawdata]`，每个 member 能重构同一候选的全部
  schema-compatible rawData 字段。
- `predict_population()` 当前先对 member rawData 求均值，再调用 current cost；同时逐
  member 计算 cost，仅向 GPSAF/viewer 暴露各目标 min/max interval。package 默认
  `SURROGATE_INR_ENSEMBLE_SIZE` 为 3。
- 用户要求保留现有 conditional-INR 和 GPSAF，只允许为新 posterior 接口做必要的小型
  格式兼容。该适配器不是改善 conditional-INR 拟合或校准的机会。

## 依赖和目标

依赖
[联合 rawData posterior 契约](20260827_082607_joint-rawdata-posterior-contract.md)。

目标是在不改变 conditional-INR 训练、旧 prediction tuple、checkpoint 数学或 GPSAF
选择行为的前提下，把现有 ensemble member rawData predictions 暴露为有限经验联合后验，
用于协议测试、迁移和可选 qNEHVI 兼容实验。

## 已确定的适配语义

### 一个 member 是一个联合 draw

- 每个 draw 先选择一个 ensemble member，然后该 member 一次预测整个输入 population。
- 同一 member index 贯穿所有候选、所有 rawData fields 和由 current cost 导出的所有目标。
- 禁止每个候选、字段或目标独立挑选 member。
- 使用 full-grid reconstruction；不通过 viewer off-grid API 拼出 acquisition rawData。

### 有限支持必须透明

- `posterior_kind = "empirical_ensemble"`。
- `unique_support` 等于可用的有效 member 数；默认通常为 3，但不得硬编码。
- 请求 draw 数超过 member 数时可以按 seeded policy 重采样或循环，但重复 draw 保留来源
  member identity，不能报告成新的独立支持。
- member 推理或 cost projection 失败时记录有效支持下降和 bounded diagnostics；不能像
  当前 interval 路径那样简单跳过失败后仍假装原支持度存在。
- qNEHVI strategy 对过低支持度采用显式 factory/config policy：警告、回退到非 posterior
  候选或拒绝运行。默认策略由 qNEHVI TODO 的 benchmark 决定，不在适配器内偷偷放宽。

### 旧接口完全保留

- `conditional_inr().predict_population()` 继续返回现有 `(mean costs, min/max intervals)`
  行结构。
- GPSAF 继续只用 mean predicted costs，interval 不进入选择。
- `predict_raw_data()` 继续返回 member-mean rawData。
- 不更改现有 model architecture version、training policy 或可恢复 checkpoint signature。
- 新 adapter/component identity 单独进入使用它的新 strategy signature；仅运行 GPSAF 时不
  应使既有 checkpoint 冷失效。

## 建议实现边界

- 在 `surrogate/conditional_inr/` 增加窄 posterior adapter，复用一次 member inference 和
  现有 schema reconstruction；不要复制模型 forward、scaler inverse 或 cost 逻辑。
- 如需开放内部 member rawData 推理，增加一个明确私有/受控函数，返回完整 member-major
  结构；不要改变 `predict_population()` 返回类型。
- public `ConditionalINRComponent` 可通过显式 adapter factory 或 posterior capability
  暴露该功能，但轻量 parent import 仍不得导入 Torch。
- streaming iterator 每次产生一个 member 对整个 population 的完整 rawData draw，并由
  公共 cost projector 立即缩减。

## 限制和文档措辞

- 该经验 ensemble 是联合、自洽的有限样本接口，但不是已校准 posterior。
- 默认 3 个 members 对高维 qNEHVI 通常只有很粗的支持；重复抽取不会增加信息量。
- conditional-INR 使用共享网络预测全部字段，因此 member 内保持当前模型定义的字段
  关联；它没有新 CAE 的显式 global/group/private 分层结构，不能宣称实现了该结构。
- 适配器的存在不意味着 qNEHVI + conditional-INR 是推荐生产组合。推荐组合仍由新模型
  和 benchmark 决定。

## 验证要求

- 对同一 population，adapter 的每个原始 member rawData/cost 与 runtime 内已有 member
  计算逐项一致。
- 证明一个 draw 的 member index 在候选、字段和目标之间不变。
- 请求数大于、小于、等于 ensemble size 时，seed、顺序、重复来源和 `unique_support`
  正确。
- 一个 member 失败时诊断和支持度正确，不能拼接其他 member 的字段补齐。
- 旧 mean rawData、mean costs、intervals、GPSAF selections、checkpoint recovery 和
  viewer tests 完全不变。
- parent import 的 lazy Torch 边界不变。

## 非目标

- 不增加 ensemble size 默认值，不重训历史 checkpoint，不校准 min/max。
- 不向 conditional-INR 加 CAE、group latent 或新的 coordinate trunk。
- 不用 adapter 输出替代新拟合器的 posterior benchmark。
- 不改真实 rawData、worker 或 recorded-data 格式。

## 完成规则

- conditional-INR 能通过统一协议输出诚实标注支持度的联合 member draws；
- 旧 GPSAF 与 viewer 的所有行为和 artifact compatibility 均有回归证明；
- qNEHVI 可以显式选择该 adapter，并在支持度不足时执行已记录 policy；
- 相关 API/blueprint/terminology/user docs 和安装包测试完成，随后将本 TODO 移入
  obsolete。
