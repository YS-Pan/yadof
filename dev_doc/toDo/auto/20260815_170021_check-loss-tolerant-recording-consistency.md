# 持续检查 loss-tolerant recording v2 一致性

## 背景

- [loss-tolerant evaluation recording 变更记录](../../change_records/20260815_165136_unify-loss-tolerant-evaluation-recording.md)
  描述了一次较大的持久化与求值链路重构：fast/local/distributed 统一经过
  `JobResult` finalizer，在 current cost 返回后才向有界 recorder 提交 owned
  envelope；workspace 使用一个 campaign session、OS lock 和后台 segment writer；
  历史格式改为 immutable v2 ZIP segments，并加入 generation task snapshot、hot
  history、容错查询和 recording-loss counters。
- 完整设计与验收边界保存在已归档的
  [原实施 toDo](../../obsolete/20260813_165610_unify-loss-tolerant-evaluation-recording.md)。
- 这次修改同时跨越 evaluation backend、optimizer、resource calibration、
  surrogate、viewer、history clear、文档和测试，后续修改可能暴露遗漏的调用路径、
  新旧语义不一致或实现与文档不一致。

## 目标

- 在日常任务自然接触本次重构相关代码、测试、文档或运行故障时，对已进入范围的证据
  做一次有界一致性检查。
- 如果发现由这次重构引入或遗留的具体问题，明确报告问题、影响和证据，并在当前授权
  与安全边界内修复；不要只增加兼容包装或隐藏异常。
- 让 current cost、recording loss、campaign lifetime、task snapshot、v2 format 和
  各消费者始终保持同一份可验证的契约。

## 指导

### 触发与范围

- 仅当正常任务已经读取、修改或诊断上述重构直接相关的实现、测试或文档时，检查当前
  diff、直接调用方/消费者和相邻测试。不要为了本 toDo 单独扫描整个仓库、重放真实
  simulator 或启动无关的大型重构。
- 客观匹配包括：回归测试或运行失败；backend 绕过 common finalizer；有效 cost 被
  recorder 故障改变；同一 generation 混用 live task 文件；campaign lock/writer 生命周期
  泄漏；旧 JSONL/global-ZIP 路径重新成为生产读写入口；segment 被覆盖或非容错读取；
  optimizer/resource/surrogate/viewer 使用了与 active session 不一致的历史；以及当前文档、
  blueprint、公开 API、wheel 内容和实现互相矛盾。
- 版本无关的普通缺陷、纯性能设想或仅凭代码外观产生的怀疑不构成触发。无法证明问题
  来自本次重构时，按正常任务处理，不要把它强行归因到本 toDo。

### 报告与修复

- 发现匹配时，先说明具体不一致、可复现证据、受影响路径以及它违反的 v2 契约，再实施
  最小完整修复。修复应删除错误分支或统一到既有边界，不应恢复已删除的旧存储链路。
- 同步修改直接相关测试；行为或契约变化时，按项目规则更新 architecture、blueprint、
  terminology、user documentation 和 change record。运行最接近的回归测试，并按影响面
  扩展到安装态测试。
- recording loss 必须保持非致命且可诊断，但 simulator、task rawData、current cost 和
  非 history 文件系统错误不能被误报为 harmless recording loss。
- 如果修复需要新的用户授权、真实外部资源、破坏性迁移或明显超出当前任务范围，仍须
  报告已确认的问题和建议边界；不要擅自扩大权限或用未验证 workaround 掩盖它。
- 没有客观匹配时不产生额外修改，也不需要为了证明检查发生而汇报本 toDo。

## Completion Rule（完成规则）

- 对一次自然触发而言：已报告一个有证据的 v2 重构一致性问题，完成当前权限与范围内的
  最小完整修复，并通过与风险相称的测试；若受外部授权阻塞，则已明确报告阻塞、影响和
  后续所需决定。
- 本 toDo 是持续性的；一次问题修复后仍保留在 `toDo/auto/`，供未来任务继续检查。

## Obsolete Rule（过期规则）

persistent
