# 持续补全组件自有配置迁移遗漏

## 背景

- 2026-08-28 的直接迁移把 core 配置收敛为声明式 schema，并把 Pymoo、GPSAF、
  conditional-INR 和 hierarchical CAE 的专用参数迁到
  `submit/optimization.py` 显式 factory kwargs 与组件内部 immutable settings。对应实现提交
  是 `6ad22a58dfe09b5bb04683e903f6c0d4e4efa9da`。
- 该提交同时修改 package runtime、scheduler、identity、workspace template、editable
  benchmark inputs、测试、architecture、blueprints、terminology 和 user docs，共跨 68 个
  文件。installed-wheel 聚焦及全量测试、benchmark 无写入 plan 均通过，但如此宽的
  一次性 cutover 仍可能在以后正常工作触及某个边缘路径时暴露遗漏。
- 用户明确要求：未来一旦在正常任务范围内发现这种漏迁移，应直接完成修复，而不是只做
  分析或另留兼容层。

## 目标

- 在以后正常任务自然触及配置、优化、surrogate、workspace/template、benchmark 或对应
  文档/测试时，对已进入范围的文件和直接相关调用链做一次有界迁移一致性检查。
- 发现可证明的漏迁移后，完成最小但完整的修复，使算法/代理专用参数继续只有
  `submit/optimization.py` factory kwargs 这一 workspace 入口，runtime 只消费组件绑定的
  immutable settings。
- 保持 core campaign policy、generation reload、strategy/source provenance、lazy optional
  imports、checkpoint/identity 边界和冻结 benchmark 证据不被补漏工作破坏。

## 客观触发条件

仅比较正常任务已经进入范围的文件、直接调用方/消费者、相关测试/文档和当前 diff。命中
下列任一项时，本 auto TODO 的一次修复触发：

- 已删除的 algorithm/surrogate uppercase key 仍被活动代码、workspace config、template、
  外部 benchmark strategy 或当前说明当作有效配置使用；
- component、backend、scheduler、posterior adapter 或 viewer 仍从完整 `LoadedConfig` 读取
  本应属于 Pymoo、GPSAF、conditional-INR 或 hierarchical CAE 的专用参数；
- factory 之外仍存在 `settings=`、unrestricted `**kwargs`、hidden temporary override、
  legacy alias、warning-only compatibility 或 runtime fallback 等第二配置入口；
- factory 已绑定的 settings 没有贯穿同一 generation 的 validate、semantic identity、run、
  training/recovery，或 runtime/scheduler 又定义了一套会漂移的算法默认值；
- `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG` 被复制进 component settings，或其他经 owner inventory
  证明属于 core 的 population、seed、smoke、archive/recording/path policy 被误迁走；
- package starter、示例、外部 benchmark strategy、architecture、blueprint、terminology、
  user docs 或测试描述的当前入口与实现不一致；
- 新增 algorithm/surrogate 时仍需要在中央 `config.py` 注册其专用字段。

旧键只在完整人工迁移表、明确的 unknown-setting rejection test、append-only change record、
`obsolete/` 文档或冻结 preregistration/run/evidence 中出现，不构成触发。不得为了消除历史
字符串而修改或重写这些证据。

## 修复规则与边界

- 可以用 focused search 确认一个已遇到候选的直接调用、导入、模板、测试和文档影响；不要
  仅为本 TODO 启动无关的全仓库重构或 simulator/benchmark campaign。
- 命中后直接删除漏掉的旧入口，将值迁入对应显式 factory kwargs 和内部 frozen settings，
  并窄传到实际 consumer。不得引入 Pydantic、兼容窗口、自动 workspace rewrite、环境变量
  settings 或算法 temporary override。
- 保持 `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG` 为 core campaign policy。其他 owner 争议先用
  直接 consumer、reload scope、identity 和跨组件证据判断，不按名称猜测。
- 修复 semantic identity 时只纳入真实数学、训练/推理、schema/state compatibility 和明确
  campaign policy；source fingerprint、path、log、provenance 与非语义诊断继续分离。
- 若一个命中跨越多个文件，应完成保证同一合同一致所需的全部直接修改及测试，而不是留下
  半迁移状态。若会触碰冻结 benchmark 证据、需要真实 simulator、改变科学结论或超出用户
  当前权限，则保留证据、报告阻塞并让本文继续 active。
- 行为变化后同步维护适用的 architecture、blueprints、terminology、user docs、迁移表和
  change record，并按开发指南完成 wheel build、force reinstall、import-origin、focused/full
  installed-package tests。仅文档补漏使用文档专用验证例外。

## 每次触发的完成规则

- 已给出具体遗漏、直接证据和影响边界；
- 当前权限内的所有直接相关漏迁移点均已修复，没有新增兼容层或第二入口；
- focused search、相关 tests 与适用的 installed-wheel/benchmark no-write 验收通过；
- 冻结 preregistration、历史 evidence、change records 和 obsolete 文档保持不变；
- 简要报告修改文件、验证结果和任何仍受权限/证据阻塞的范围。

本文是持续性自动检查。一次补漏完成后仍保留在 `toDo/auto/`，供后续正常任务再次触发。

## Obsolete Rule

persistent
