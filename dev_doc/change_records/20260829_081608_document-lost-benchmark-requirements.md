# 记录 benchmark 重写后遗漏的用户体验与测试要求

## 背景

2026-08-28 的 code-first `yadof-benchmark` 重写保留了核心包边界，但用户在随后完整运行中发现
workspace-level reports/visualizations 为空、performance cell 只有 12 × 20、名称没有日期时间
前缀，并且没有看到 CLI 进度。用户要求从全部相关 Codex task 中恢复旧版开发期间提出的用户体验
和测试方法要求，并写入活动 TODO。

## 本次变更

- 新增
  [`dev_doc/toDo/20260829_081608_restore-benchmark-ux-and-testing-contract.md`](../toDo/20260829_081608_restore-benchmark-ux-and-testing-contract.md)。
- 文档基于本机可访问的全部 user-message benchmark 检索和工具开发 task 全文复核，区分当前实证、
  仍有效要求、已被后续决定取代的旧要求、非目标及可执行验收条件。
- 恢复的重点包括：100 × 20 performance 硬下限、任务难度与 seed 分层、paired fairness、
  日期时间命名、reports/visualizations 可发现性、领域 postprocess、默认 visible CLI、Rich 双进度条、
  有界 inspect/ETA、失败/持久化/恢复语义和 immutable run snapshot。
- 本次没有修改代码、公开 API、architecture、blueprint 或 terminology，也没有启动 simulator。

## 验证

- 定向核对 `temp/full-benchmark-20260828` 的 spec、cell 状态和产物目录，确认 TODO 中“当前缺口”
  的数字与文件事实。
- 检查新增 Markdown 为 UTF-8，可解析相对链接，并运行 Git whitespace 检查。
