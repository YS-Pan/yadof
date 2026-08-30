# 显式 optimization 重构阶段 6：workspace optimization program 试点

## 状态、授权与依赖

本文是已获单一 Goal 后续精化/执行授权的预测性 TODO。只有 Stage 2--5 的 Dataset/CostTable、
EvaluationHandle、PCA/SVD fit/predict 和 search/select primitives 均通过后，才能在本文内冻结
program entry、scope、snapshot、check 和 resume 设计；不需要新的用户继续指示。

本阶段只证明显式 program 能完整运行 real-only 与 PCA/SVD + GPSAF 两条代表路径。advanced
components 在 Stage 7 迁移，旧 hidden loop 在 Stage 8 才删除。

## 目标职责

workspace `submit/optimization.py` 应在普通 Python 中清楚拥有：

- generation loop 与 stop condition；
- evidence/current-cost/training-data 的显式读取和用户变换；
- surrogate fit/predict；
- search/select；
- evaluation start/wait/cancel 与训练/evaluation 的顺序或 overlap；
- generation state commit、progress 与下一轮。

yadof 提供强制 lifecycle scope，而不是把安全留给任意脚本：

```python
def optimization_program(context):
    with context.run_scope() as run:
        for generation in run.generations():
            with run.generation(generation) as step:
                ...
```

示意名称不冻结。scope 必须拥有 CampaignSession、workspace lock、program/task snapshots、
recording receipts、open evaluation/training handles、state/checkpoint commits、异常 cleanup 和
generation-boundary resume。

## Program freeze 与 task reload

- 一个 `yadof run` 在开始时加载并冻结一份 `optimization.py` program snapshot，以及明确归属
  program 的 helper source；同一命令中不热重载 loop。
- 修改 program 后，只能在完整 generation boundary 停止当前命令，再通过 resume/start
  generation 加载新 program。
- `calc_cost.py`、parameters、evaluation/workflow 等 task content 仍按 generation snapshot
  合同刷新。Stage 6 精化必须明确同一 `submit/` root 内 program helpers 与 interpretation
  helpers 的 snapshot 分类，不能靠 process module cache 偶然决定。
- resume 只恢复 durable evidence、complete generation optimizer state 和 compatible checkpoints；
  不承诺 mid-generation Python stack/local-variable continuation。
- program source fingerprint 是 provenance/cache input；semantic program identity 与注释/path
  变化分离。

## yadof check 与 dry-run

`yadof check` 保持 bounded/read-only。它可以静态编译/解析 program、验证 required declaration/
entry/capabilities 和 paths，但不能调用 program body、start evaluation、fit model、创建 runtime
state 或依赖任意 top-level side effect。

若 import-time validation 无法保证无副作用，精化时优先采用 static declaration/isolated
load contract，并要求 workspace program 把执行放在 entry callable 内。需要真正运行一轮 control
flow 时，提供名称明确、预算显式的 dry-run/smoke；不得把 execution 隐藏在 `check`。

## 试点范围

至少完成两份真实 public-path pilot：

1. real-only：读取 real cost history、search/select、start/wait evaluation、commit generation；
2. PCA/SVD + GPSAF：显式准备 training data、fit/predict、select，并由 program 代码选择顺序或
   有界 overlap。

pilot 必须在 fast/local/distributed common API 下成立；默认演示使用保守顺序，不按 backend
名称隐式切换 overlap。distributed-oriented overlap 只在 explicit code 和 resource 说明中出现。

本阶段允许一个有明确结束条件的 transitional dual path：

- pilot workspace/fixture 选择新 program entry；
- 尚未迁移的 advanced strategies 继续 current path；
- old path 必须尽量调用 Stage 2--5 primitives，而不是继续发展第二套机制；
- ledger/代码注释记录 Stage 7 consumers 与 Stage 8 deletion proof。

不在本阶段切换 package default starter、删除 `build_optimization()`/strategy loop、迁移全部
conditional-INR/CAE/posterior/viewer/benchmark，也不修改 GPSAF `gamma`。

## 精化时必须决定

- program entry/call signature、run/generation context value types；
- source freeze 与 submit-local helper classification；
- progress/metadata/state commit 由 scope 的哪个 boundary 执行；
- user exception、KeyboardInterrupt、cancel 与 resume 语义；
- pilot path 的 explicit opt-in 与 Stage 8 deletion marker；
- check 的 static/isolated validation 与 optional dry-run interface；
- starter/examples 最终 API 的 draft，但本阶段不承诺所有 advanced examples。

这些属于已授权设计。若 pilot 需要放弃 framework lock/commit/cleanup 或依赖 mid-generation
continuation，则停止并重做，而不是降低 invariant。

## 验证

至少覆盖：

- real-only 与 PCA/SVD+GPSAF program 可读数据流；
- ordinary Python/NumPy filter/copy/reorder 与 identity/provenance；
- sequential and explicit overlap ordering；backend 名称不改变 program order；
- run-level program freeze、generation-level cost/evaluator reload、helper isolation；
- stop/resume at complete boundary，拒绝/invalidate incomplete open-handle state；
- exception/KeyboardInterrupt/cancel cleanup，无 lock/process/handle/writer leak；
- `check` read-only/no program execution/no runtime writes；
- pilot/old adapter semantic parity、metadata/state/checkpoint identity；
- fast/local/distributed common API 的 targeted contract/smoke；
- recorder failure、prediction non-entry、GPSAF `gamma` unchanged。

完成 installed-wheel focused/full tests。overall policy 的 fast smoke 与唯一 100 x 20 measured
benchmark 通过新 PCA/SVD+GPSAF program path 运行，证明 pilot 是真实路径而非 mock。local/
distributed 只做小规模 contract/smoke。

## 完成、归档与自动续跑

两条 pilot 已使用真实 public primitives 完成端到端 generation，program/snapshot/check/resume/
scope 合同有直接证据，transitional old-path consumer inventory 已冻结；文档/automatic TODO
check/change record/commit/fetch-push 完成后，归档本文、更新 ledger，并自动进入
[Stage 7 retained capability migration](20260830_220200_explicit-optimization-stage-7-retained-capability-migration.md)。
