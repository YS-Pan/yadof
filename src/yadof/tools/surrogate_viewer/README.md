# yadof surrogate checkpoint viewer

这是集成在 `yadof.tools.surrogate_viewer` 中的可选只读桌面工具。它访问
yadof workspace，但不修改 checkpoint、真实仿真结果、配置或历史记录。

## 启动

安装 `viewer` extra 后执行：

```powershell
python -m pip install "yadof[viewer]"
yadof view surrogate --workspace "D:\path\to\workspace"
```

也可以不提供 `--workspace`，或使用模块入口
`python -m yadof.tools.surrogate_viewer`；启动后点击 **Browse…** 选择包含
`config.py`、`recorded_data/` 和 `.yadof/surrogate/checkpoints/` 的目录。
训练被跳过、没有模型成员的占位 checkpoint 不会列入可选项。

## 交互预测页

- **Checkpoint**：选择某一代 surrogate。
- **Real generation / Real individual**：选择一条已完成的真实仿真结果。
  选择后，17 个参数滑块会同步到该个体，并同时绘制真实结果和 surrogate
  结果；点击 **Clear real overlay** 回到仅预测模式。
- **Parameters**：每个参数都有独立滑块。滑块内部使用归一化坐标，所以
  参数有不连续合法区间时也不会落入非法间隙；右侧显示实际物理值。
- **rawData curve**：选择要查看的输出。多维数据优先以 `Freq` 为横轴，
  其余维度取最接近 0 的切片；这与示例 HFSS 任务的波束中心比较一致。
- 上图显示 rawData 曲线（蓝色为 surrogate，橙色为真实仿真，淡蓝区域为
  ensemble ±1σ），下图显示由当前 `calc_cost.py` 动态计算的目标值。

滑块停止约 350 ms 后自动预测，也可关闭自动预测并点击 **Predict now**。
模型加载和推理在后台线程执行，不会阻塞界面刷新。

所有只读下拉框聚焦后都可以用 `↑` / `↓` 切换选项。参数滑块点击或用
`Tab` 聚焦后，可以用 `←` / `→` 按归一化范围的 1% 移动，按住 `Shift`
时每次移动 5%。这些交互由 Tkinter 原生焦点机制和显式键绑定实现，不需要
更换 GUI 框架。

## 跨代误差热图页

这个页签与单点预测/曲线图明确分离。点击
**Calculate predictions once** 后：

- x 轴：surrogate checkpoint 的训练代数；
- y 轴：被预测真实个体所属的优化代数；
- 颜色：该单元格所有个体的平均误差；
- **Error** 单独选择 `Relative` 或 `Absolute`；
- **Quantity** 单独选择所有 costs、某一个 cost、所有 rawData，或任意一个
  rawData；
- **Sample** 是每代独立随机抽样比例，默认 10%，每代至少保留一个个体。

图使用离散的 `pcolormesh` 棋盘格，每一个色块的中心与相应代数刻度对齐，
色块之间不插值，坐标边界会完整包含最外层色块。绘图区会平铺到标签页的
可用空间，色块会随窗口比例成为矩形；图标题只有一行。

首次完整计算会让每一个 checkpoint 预测本次从各代抽到的相同个体集合；
页顶进度条显示当前 checkpoint 和样本进度。同一次计算会同时累计每个
“优化代 × checkpoint × cost”和“优化代 × checkpoint × rawData”的
相对/绝对误差 `sum/count`。之后切换 Error 或 Quantity 时，只重新组合这些
内存汇总，不会再次推理模型，通常可立即更新。

单个 rawData 的 error 对该 rawData 中 checkpoint 建模的每一个标量等权；
选择所有 rawData 时，所有建模标量等权，因此数据点更多的 rawData 权重也
更高。relative error 按
`abs(prediction - truth) / max(abs(truth), epsilon)` 计算。
`epsilon` 使用 workspace 的 `SURROGATE_RELATIVE_ERROR_EPS`，它只是接近
零时的分母下限，用来避免除零和异常放大，不是模型输入扰动。

heatmap 的 CUDA 推理会使用比普通单点预测更大的样本批次，以减少小批量
调度开销、提高 GPU 吞吐；若发生显存不足，会自动逐级退回 checkpoint 的
训练配置批量。**Stop** 会在当前推理批次结束后终止，界面继续显示上一次
完整计算的结果；如果尚无完整结果，则恢复为空白提示。

汇总缓存只有几个小数组，当前规模通常仅占几十 KiB，并且不写入硬盘。代价是
它只能直接支持已经累计的均值指标；若以后新增中位数、P90 等需要逐样本
误差分布的指标，必须扩展汇总策略或重新执行一次完整计算。

## 代码结构

- `app.py`：窗口、后台任务和异常汇报的协调器；
- `ui/interactive.py`、`ui/heatmap.py`：两个互相独立的标签页；
- `ui/plots.py`：Matplotlib 绘图；
- `backend/checkpoints.py`：checkpoint 加载和批量推理；
- `backend/workspace.py`：真实记录、抽样和跨代审计；
- `backend/rawdata.py`、`backend/types.py`：rawData 适配和数据契约。

`yadof.tools.surrogate_viewer.backend` 仍是统一的后端导入入口，内部文件
拆分不会要求调用方了解这些子模块。子包根部的便利导出采用延迟加载，因此
普通 `yadof --help` 和 `yadof.tools` 导入不会提前加载 Torch 或 Matplotlib。

## 开发文档

维护或重构查看器前，从 [`dev_doc/README.md`](dev_doc/README.md) 开始。
其中包含精简的读取顺序、当前架构、项目/模块/关键文件蓝图和术语表。这个
文档树有意不建立 `toDo/`、`obsolete/` 或 `change_records/`；当前独立
demo 使用 Git 历史记录已完成变更。

## 工具边界

- viewer backend 复用同一 yadof 包中的 checkpoint、模型和 rawData 内部机制；
  这些包内依赖集中在 `backend/`，不会扩散到 UI 模块。
- 当前会话中只缓存一个交互 checkpoint。切换 checkpoint 时会重新加载。
- 热图只在内存中保存误差和计数汇总；重新加载 workspace 或退出程序后需
  重新计算，目前不会向 workspace 写缓存文件。
- 查看器不会启动 HFSS、不会训练模型，也不会写入历史数据。
