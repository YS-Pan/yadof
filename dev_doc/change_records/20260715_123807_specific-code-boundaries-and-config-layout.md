# 2026-07-15 12:38 - 明确 specific 代码边界并重组配置

## Context
- 通用 `project/tools/` 和顶层配置文件混入了 HFSS/PyAEDT 内容，使自动通用性检查无法区分框架代码与有意的软件特定扩展。
- `project/test/` 包含当前天线任务的参数、目标、rawData 名称和真实 HFSS 流程测试，导致框架测试随任务文件变化。
- `project/com_lib/hfss_com.py` 落后于当前活动的 `project/job_template/hfss_com.py`。
- package 化待办尚未用项目术语风格明确说明 package 与 workspace 的边界，并包含了不再需要的旧仓库迁移方案。

## Change
- 将 HFSS 参数提取工具移动到 `project/tools/specific/hfss/`，去掉文件名中的重复 `hfss_` 前缀，并修正项目根目录推导、命令名和测试导入。
- 将配置改为 `project/config/key.py`、`project/config/all.py` 与 `project/config/specific/hfss.py`；通用模块统一导入 `project.config.all`，prepared job 复制完整且无缓存的 `config/` package。
- 从 `project/test/` 删除当前任务/HFSS smoke 和目标窗口测试，将记录合同改为通用任务夹具，将通用成本辅助函数测试保留为 `test_cost_misc.py`。软件特定的工具/adapter 测试移到相应 specific 或 `com_lib` 路径。
- 新增 `project/test/README.md`，禁止在通用测试目录中加入当前任务或仿真软件专用测试，并规定当前布局使用 `temp/`、未来 package 布局使用 workspace。
- 用活动的 `project/job_template/hfss_com.py` 完整替换 `project/com_lib/hfss_com.py`，新增 `com_lib` 模块蓝图并同步架构、配置、工具、测试、job template 与用户文档。
- 更新自动通用性 toDo，将 `project/tools/specific/`、`project/config/specific/` 和 `project/com_lib/` 声明为有意的软件特定路径。
- 在 package 化待办中定义 package/workspace，并删除旧仓库兼容、迁移命令和旧入口包装要求。

## Rationale
- 显式的 `specific/<software>/` 边界允许 yadof 保持通用核心，同时继续保存真实软件集成所需的设置、工具和 adapter。
- 通用测试使用中性任务夹具后，可以验证框架合同而不把当前优化问题误当作系统合同。
- prepared job 复制整个 config package，可以让 job-local workflow 使用同一层级结构并保留软件特定配置，同时避免把特定设置放回通用配置文件。

## Impact
- 所有代码中的旧 `project.config_all`/顶层配置导入已经切换；旧 `project/config.py` 和 `project/config_all.py` 路径不再存在。
- 原 HFSS 工具路径不再存在；用户命令改为 `project/tools/specific/hfss/get_para_and_range*.py`。
- 默认 `pytest -q` 不再包含当前任务或真实 simulator 测试；软件特定合同测试需要通过其实际路径显式运行。
- `dev_doc/terminology.md` 按用户要求保持不变，因此本次没有同步其中旧配置路径或加入 package/workspace 术语。

## Follow-Up
- `dev_doc/toDo/20260703 package.md` 仍是未执行的手动待办；未来实施时直接采用新 package/workspace 布局，不提供旧仓库迁移兼容。
