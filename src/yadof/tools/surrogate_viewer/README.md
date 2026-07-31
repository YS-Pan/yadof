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
  每次加载 workspace 时会随机选择一代及其中一个个体。选择后，参数滑块
  会同步到该个体，并同时绘制真实结果和 surrogate 结果；点击
  **Clear real overlay** 回到仅预测模式。
- **Parameters**：每个参数都有独立滑块。滑块内部使用归一化坐标，所以
  参数有不连续合法区间时也不会落入非法间隙；右侧显示实际物理值。
- **rawData output**：选择要查看的输出。viewer 会列出该 rawData 的全部
  维度；勾选零到两个维度作为绘图自变量。每个未勾选维度同时提供
  checkpoint 网格坐标下拉框和数值文本框：可以直接选择已有坐标，也可以
  输入任意有限数值。默认仍优先勾选 `Freq`，没有 `Freq` 时勾选第一个
  维度。勾选控件用对勾和蓝色填充明确表示选中状态。
- 未选择维度时，上图显示一个数值；选择一个维度时显示曲线；选择两个
  维度时显示没有轮廓线的填色等高图。二维真实结果与 surrogate 使用同一
  色标并排显示。曲线继续用淡蓝区域表示 ensemble 成员的逐点最小值到
  最大值；标量显示对应的 ensemble 数值范围。
- 下图始终显示由当前 `calc_cost.py` 动态计算的目标值。

这里有两类不同的输入。**Parameters** 中的连续优化参数可以取训练记录之间
任意合法值，surrogate 会对该新参数向量推理；离散参数仍只取任务定义的合法
水平。rawData 的 `Freq`、`Theta` 等是 conditional INR 的输出查询坐标。
下拉框选择已有网格坐标时，viewer 继续使用原来的完整网格预测和重建路径，
因此已有 checkpoint 的网格点行为不变。文本框输入非网格坐标时，viewer
直接在新坐标上查询同一个 INR decoder，并对 checkpoint 中逐网格点的 target
scaler 做线性插值后恢复物理值；不需要重新训练或迁移 checkpoint。

非网格位置没有 recorded_data 真值，因此上图不会伪造真实曲线/曲面；下方
objective 对比仍来自 checkpoint 完整网格，并在图上明确提示。超出已存轴范围
的数值也会送入 decoder，但属于外推，可靠性通常低于网格范围内插值。当前
checkpoint 只编码前三个 rawData 坐标维度；未来高于三维的数据若要改变第
四维及之后的查询坐标，需要先扩展模型坐标编码。

开启 **Auto refresh** 时，参数滑块停止约 350 ms 后自动预测；关闭后可点击
**Predict now**。
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
色块之间不插值、没有边线或间隙，坐标边界会完整包含最外层色块。绘图区
会平铺到标签页的可用空间，色块会随窗口比例成为矩形；图标题只有一行。

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
- `backend/rawdata.py`、`backend/types.py`：维度描述、0D/1D/2D 切片、
  rawData 适配和数据契约。

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
