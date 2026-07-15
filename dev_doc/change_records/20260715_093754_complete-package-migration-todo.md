# 2026-07-15 09:37 - 完善 package 化迁移待办

## Context
- `dev_doc/toDo/20260703 package.md` 只初步提出了安装 package、增加 CLI、保留文档和生成用户工作目录，尚未说明安装代码与工作区的边界、配置和任务文件如何加载、运行数据写到哪里、旧工作区如何迁移以及如何验收。
- 当前实现依赖 `project.*` 导入、源码树相对路径和放在框架目录内的 `config.py`/`job_template`，这些隐含条件在安装到 `site-packages` 后不再成立。

## Change
- 沿用原文的中文编号格式扩充 package 化待办，没有改成标准 toDo 模板。
- 补充了 package/导入命名、只读安装包与可写 workspace 分层、精简 job template、配置叠加、CLI 命令族、幂等初始化、workspace context、持久化路径、文档资源、可选依赖、旧工作区迁移、实施顺序和验收测试。
- 明确 package 化不得改变 `normalized variables -> rawData -> cost` 合同，也不得把框架绑定到 HFSS、Ansys、单一任务或单一 adapter。

## Rationale
- package 化不只是移动文件；如果不先规定 workspace、任务装载和路径所有权，已安装模块会错误地把 package 目录当作用户项目目录，多个任务也会互相污染。
- 把完成条件写入待办，可以让后续实现按可验证的阶段推进，并覆盖 wheel 安装态而不只是源码树运行态。

## Impact
- 只修改未来工作说明和本变更记录；当前代码、运行布局、公共 API 和用户操作方式均未改变。
- 后续执行该待办时会影响 package 构建、CLI、全部核心模块的路径/导入方式、用户文档、架构和蓝图。

## Follow-Up
- 本次没有执行 package 化。只有用户明确触发该手动 toDo 后，才应按其中的阶段和完成标准实施，并在全部完成后将它移入 `dev_doc/obsolete/`。
