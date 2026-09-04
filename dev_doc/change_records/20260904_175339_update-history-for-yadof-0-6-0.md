# 2026-09-04 17:53 - 补充 yadof 0.6.0 简史

## Context

`dev_doc/history.md` 只概括到 0.5.0。最近的 substantive change records 已记录 yadof 与
独立 `yadof-benchmark` 交付 0.6.0，以及该版本形成的常驻 fast 执行边界和 GPSAF 默认选择
变化，因此主要版本简史需要同步。

## Change

- 在 `dev_doc/history.md` 增加 0.6.0 里程碑，概括版本化 fast 会话、campaign-owned worker
  pool、外部解释器复用及逐候选物理系统重建边界。
- 记录 GPSAF 默认 infill selection 迁移到 greedy hypervolume，同时保留显式 cluster/PKT
  路径，并注明独立 benchmark 包同步版本和旧 fast workspace 的迁移要求。
- 继续把 0.5.1 视为 0.5 系列的维护发布；其具体修复保留在 change records 中，不把简史
  扩展成逐补丁版本清单。

## Rationale

简史按主要版本呈现能力和代码组织变化。0.6.0 同时改变执行生命周期、默认优化选择和
workspace 迁移边界，已经构成新的主要里程碑；详细验证数据仍由原 change record 与 context
文档保存。

## Validation

按内容型文档变更检查 UTF-8、相对链接、版本事实、最终 diff 与 Git whitespace。没有修改
代码、测试、构建配置、package-resource mapping 或文档命令，因此适用开发指南的
documentation-only validation 例外，不重建 wheel、不重装 package，也不运行软件测试。

## Impact

仅开发者简史和本条完成记录发生变化；当前架构、blueprints、术语、用户运行说明及软件
行为均未改变。
