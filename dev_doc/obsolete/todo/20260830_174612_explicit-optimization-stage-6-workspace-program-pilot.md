# 显式 optimization 重构阶段 6：workspace optimization program 试点

## 本次精化输入（2026-08-31）

- 输入 HEAD/Stage 5 accepted commit 为
  `b68e9597d641c96775ef1fc72f5615587f3f0990`，分支 `main`，worktree/staged diff 均为空；
  Stage 5 post-commit fresh fetch 为 `origin/main=38c091d264cc47d9457878d76d8a784b97e7e45b`、
  behind 0 / ahead 2，未达到 ahead >= 5 push gate。
- 本文 pre-refinement SHA-256 为
  `E86DADCB5558C3A05107CE74213F5868AE1154287B201E25275EBB297C3554E1`；overall plan
  SHA-256 为 `F6EE0F193D34A54EA79D5FB6FC207CBCE183CD0E7D91A3740B531EFA8C1431AB`。
- 接受基线是 installed yadof `0.4.2`、外层 `.venv/Lib/site-packages/yadof/__init__.py`；Stage 5
  full suite 为 `429 passed in 94.96s`，search/GPSAF/posterior measured 为 collected/valid
  `2000/2000/2000/2000`、zero issues/anomalies/publication failures。Stage 6 pre-change program/
  check/snapshot/evaluation/search/surrogate focused baseline 为 `64 passed in 16.09s`。

## 精化时确认的当前实现事实

- `run_generations()` 已正确在一个 `CampaignSession` 下按 generation reload config、建立
  `GenerationTaskSnapshot`、读取 committed history、执行 strategy、等待 generation handles、记录
  metadata 并关闭 writer/lock；可靠 lifecycle 不需要第二套 session/recorder。
- `GenerationTaskSnapshot` 当前复制完整 `submit/`，所以 `optimization.py` 及其任意 sibling helper
  每 generation 重载，并与 `calc_cost.py` 一起进入 interpretation/optimization fingerprint。program
  source、interpretation source 尚未分类。
- `yadof check` 对 workflow 只做 AST parse，却会 import `optimization.py` 并调用
  `build_optimization()`。因此 optimization top-level/build side effect 当前可在 read-only check 中执行；
  Stage 6 必须把检查收敛为静态声明/语法验证。
- Stage 3 public `prepare_evaluation()` / `start_evaluation()` / `EvaluationHandle` 已统一 fast/local/
  distributed；`CampaignSession` 的 generation handle registry 已区分 abnormal-cancel evaluation 与
  normal-wait training。program scope 应只绑定这些 owner，而不是包装新的 backend handle。
- generation resume 当前从 durable evidence、strategy semantic signature、generation metadata 与
  compatible surrogate checkpoint 重建；arbitrary pymoo/Python locals 本来就不 durable。Stage 6 只需
  原子发布 framework-owned complete-generation pointer，不接受 user/prediction payload checkpoint。

## 冻结 explicit opt-in 与静态声明

Stage 6 public pilot 通过 `submit/optimization.py` 顶层的唯一 literal 声明显式 opt-in：

```python
YADOF_OPTIMIZATION_PROGRAM = {
    "api": "yadof.optimize.program/v1",
    "entry": "optimization_program",
    "helpers": ("optimization_helpers.py",),
    "identity": {"program": "pca-svd-gpsaf-pilot", "version": 1},
    "capabilities": ("real-evaluation", "pca-svd", "gpsaf"),
}
```

- 声明必须可由 `ast.literal_eval()` 读取，只允许 exact `api/entry/helpers/identity/capabilities` keys；
  entry 是本文件的 sync function，helpers 是 `submit/` 下 canonical relative `.py` files，不允许 absolute、
  `..`、duplicate、`optimization.py` 自指或越界 symlink。
- explicit program 文件顶层只允许 docstring、imports、function/class definitions、该声明与其他 literal
  constants；component construction、文件写入、evaluation/training 或任意 call 必须在 entry/function body。
  declared helper 同样 static compile，并只允许 declarations/imports/literal constants 在顶层。
- program `identity` 与 capabilities、parameter names、objective names 形成 semantic signature；source
  bytes/path/comment 只形成独立 source fingerprint/provenance。用户负责 identity 随科学/控制语义改变而
  改变；framework 不执行代码猜测语义。
- 没有该声明时，文件是 transitional legacy `build_optimization()` path。Stage 6 不改变 default starter；
  legacy check 只静态确认 syntax 与 top-level callable declaration，不再执行 factory。run 时仍完整
  load/validate strategy，advanced consumers 留待 Stage 7。

## 冻结 source snapshot 与 helper 分类

- public `freeze_workspace_program()` 在 optimization run 开始时解析声明并把 `optimization.py` 与 exact
  declared helpers 复制到唯一 temporary program snapshot；CLI 在 optional smoke 前冻结并把同一 snapshot
  交给 run，public `run_generations()`/`run_one_generation()` direct call 则在自身入口冻结。
- entry 在该 frozen source root 内 fresh isolated load 一次；整个命令不再观察 live program/helper edit。
  undeclared sibling import 因未进入 snapshot 而 fail closed。snapshot 在 program return、普通 exception、
  `KeyboardInterrupt`/`SystemExit` 后都关闭。
- program source files 从每-generation task snapshot 的 submit copy/hash 中排除；`calc_cost.py` 及未声明的
  interpretation helpers 继续 generation reload。task snapshot source hashes 合并 frozen program hashes，
  但 interpretation fingerprint 只绑定 generation task sources，optimization fingerprint 只绑定 frozen
  program source fingerprint，task snapshot ID 同时绑定二者。
- legacy path 继续当前 complete-submit generation snapshot 与 hot strategy reload，作为 Stage 8 有终止条件
  的 dual path；program path 不通过 legacy loader。

## 冻结 program/run/generation API 与 commit point

entry signature 固定为 `optimization_program(context)`，其中 public
`OptimizationProgramContext.run_scope()` 只能创建并进入一次 `OptimizationRunScope`：

```python
def optimization_program(context):
    with context.run_scope() as run:
        for generation_index in run.generations():
            with run.generation(generation_index) as step:
                ...
                step.commit(step.result(...))
```

- run scope 独占 `CampaignSession`、workspace campaign lock、writer、program snapshot identity、CLI max
  generation range 与 results；program 可以通过 break/return 提前满足自己的 stop condition，但不能越过
  CLI 明确的最大 range、重复/out-of-order generation 或建立第二个 scope。
- generation scope 在 enter 时 generation-reload live config、建立 classified task snapshot、读取
  `EvidenceDataset`/current `CostTable`/history/problem，发布 active semantic namespace，并形成现有
  `GenerationContext`。它公开 `.context`、`.evidence_dataset()`、`.cost_table()`、
  `.prepare_evaluation(population, ...)`、`.result(...)` 和一次性 `.commit(result)`。
- workspace program 直接调用 Stage 4 surrogate methods、Stage 5 search/select primitives 和 Stage 3
  public `start_evaluation(batch)`/handle。`.prepare_evaluation()` 只绑定 exact campaign session/snapshot；
  backend 名称不改变调用顺序或自动 overlap。
- `step.commit()` 只暂存一个 validated `OptimizationResult`；generation context 正常 exit 才是 commit
  point：先 normal-resolve wait-policy training，要求没有未关闭的 cancel-policy evaluation handle，确认
  durable recording boundary，然后写 generation metadata 与 atomic complete-generation pointer，最后把
  result 加入 run。没有 commit、generation mismatch、wrong width/count、open evaluation 或 boundary
  failure 均不发布 completed pointer。
- user exception、`KeyboardInterrupt`/`SystemExit`、evaluation/recording failure 立即离开 entry；run/session
  cleanup 取消/关闭 handles、writer/snapshots/lock 后原异常继续传播，不把 incomplete generation 改写为
  success。training wait handle 可由正常 scope boundary finish；显式程序也可自行 wait/close。

## 冻结 generation-boundary resume

- `.yadof/optimization/program-completion.json` 只原子记录 schema、program semantic signature、last
  completed generation、frozen source fingerprint、task snapshot ID 与 timestamp；不接受 arbitrary user
  state、candidate、prediction、rawData 或 pymoo payload。
- 相同 semantic signature 的下一命令只允许从 `last_completed_generation + 1` 继续；重复/跳过 generation
  fail closed。若上次 generation incomplete，pointer 保持前一 complete boundary，因此 exact next index 可
  重试并从 durable evidence/history 重建。source-only edit 保持 resume-compatible并产生新 provenance；
  semantic identity switch 建立新 namespace，不复用旧 pointer/checkpoint。
- fresh/migrated program 没有 compatible pointer 时允许 caller 明确给出初始 start generation；之后同一
  signature 严格连续。该合同不承诺 mid-generation stack/local continuation。

## 冻结两条 pilot、parity 与 benchmark delta

- real-only pilot 在 workspace entry 中创建 search，调用 `full_real_search()`，显式
  prepare/start/wait/close evaluation，再构造并 commit result；同一 program 在 fast/local/distributed
  targeted contract 中保持相同调用顺序。
- PCA/SVD+GPSAF pilot 显式读取/copy/select/reorder dataset row IDs、建立 current cost table 与
  `SurrogateTrainingData`，按 workspace 写出的 conservative 顺序执行 selection -> real evaluation ->
  synchronous fit。generation 0 走 full-real warmup；后续程序代码用 public fork/search/bind/combine/
  select/advance/compose primitives 实现 current alpha/beta/exploration，`gamma` 只进入 identity/diagnostics，
  不新增数学。
- 在 generic primitives 新增 public `combine_predicted_cost_rows()`，只合并 same semantic identity 的
  exact candidate-bound rows；不新增 hidden GPSAF loop。program helper 负责 alpha/beta iteration 和
  diagnostics，从而 pilot 确实拥有 control flow。
- 修改前冻结 legacy real-only 与 PCA/SVD+GPSAF fixed-seed population/metadata golden；pilot 与 legacy
  adapter 在相同 seed/history/settings 下 exact population/selection parity。direct tests 另证 fast/local/
  distributed evaluation batch mode 不改变 program event order，distributed 不启动真实 HTCondor。
- fast benchmark 新建 Stage 6 smoke `20 x 2` 与唯一 measured `100 x 20` workspace，使用 explicit
  declaration/program helper 而非 `build_optimization()`；expanded plans 除 budget/path 外同源，继续用
  synthetic antenna、seed 101、PCA/SVD rank 16、GPSAF alpha/beta 3、exploration 0.1、`gamma=0.5`。
  measured 必须 collected/valid `2000/2000/2000/2000`、zero anomalies/publication failures，并审计
  program source freeze/fingerprint、20 complete pointers/generation metadata、training/checkpoint、search
  diagnostics。single-seed HV 仍不作算法优劣 gate。

## Transitional consumer inventory 与 Stage 8 deletion marker

- explicit program opt-in：仅 Stage 6 public tests/pilot/benchmark；default starter 与 existing workspaces
  不自动 rewrite。
- legacy `build_optimization()` consumers：default starter、conditional-INR、hierarchical CAE、posterior/
  qNEHVI、viewer/tools/benchmark legacy fixtures；Stage 7 必须逐项迁移/保留 capability evidence。
- Stage 8 deletion proof：上述 inventory 清零、default starter/examples 切换、check 不再接受 legacy、
  `run_generations()` legacy dispatch 与 `OptimizationStrategy.run_generation()` hidden loop 删除。Stage 6
  不添加新的 legacy consumer 或第二 recorder/evaluator/search backend。

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

## 本次执行结果（2026-08-31）

- 新增 `optimize/program.py`：`YADOF_OPTIMIZATION_PROGRAM` v1 只接受 exact literal
  `api/entry/helpers/identity/capabilities`，静态验证 explicit program/helper 顶层与路径，不 import/
  调用 program；无声明时只静态识别 transitional `build_optimization()`。program entry 与 exact
  helpers 在 CLI optional smoke 前或 direct API 入口冻结一次、isolated load 一次，source fingerprint
  与 semantic signature 分离，undeclared helper import fail closed。
- 新增 framework-created one-use `OptimizationProgramContext`、`OptimizationRunScope` 与
  `ProgramGenerationScope`，直接复用现有 `CampaignSession`、lock、writer 与 generation handle
  registry。scope 强制 ordered bounded generation、一次 commit、result shape、normal-wait training、
  closed evaluation handle、recording flush、strict generation metadata 与异常 cleanup；user exception/
  interrupt 不会发布成功边界。
- 新增 `.yadof/optimization/program-completion.json` 原子 complete-generation pointer。相同 program
  signature 只允许从前一 complete generation + 1 继续；source-only edit 记录新 provenance，semantic
  identity switch 使用不同 namespace。pointer 不保存 Python locals、candidate/prediction/rawData 或
  pymoo payload，incomplete generation 从 durable evidence/history 重建。
- `GenerationTaskSnapshot` 把 frozen program sources 与 generation-reloaded cost/parameters/evaluation/
  workflow sources 分类：program 文件不再重复复制，但 hashes/fingerprint 合并进完整 provenance/
  task snapshot ID。CLI 与 public API 对 explicit path 直接 dispatch；legacy path 保持 Stage 8 有终止
  条件的 compatibility，未新增第二 executor/recorder/evaluator。
- 新增 public `combine_predicted_cost_rows()`，按 candidate ID 从 prediction superset 投影并合并
  same-semantics rows；GPSAF alpha/beta 使用该公共 primitive，拒绝 missing/duplicate/mixed semantics，
  未改变 `gamma` 数学。real-only 与 PCA/SVD+GPSAF program fixtures 直接使用 Stage 2--5 public data/
  fit/search/evaluation primitives；ordinary NumPy row reorder 由 workspace helper 拥有。
- independent `yadof-benchmark` 升级到 `0.2.2`。planner 静态识别 explicit declaration，strategy
  digest 同时绑定 ordered relative entry/helper paths 与 bytes，cell materialization 复制 exact source
  set；legacy single-file fixtures 仍可运行。focused benchmark compatibility 为 `4 passed in 0.39s`，
  final installed benchmark suite 为 `21 passed in 1.02s`。
- program/check/snapshot/evaluation/search/surrogate focused installed-wheel acceptance 为
  `69 passed in 18.65s`；final yadof installed-wheel full suite 为 `443 passed in 94.11s`。最终 import
  origin 是外层 `.venv/Lib/site-packages/yadof/__init__.py`，version `0.4.2`；benchmark import origin
  同样来自 site-packages，version `0.2.2`。
- fresh smoke `temp/20260831_121405-stage6-benchmark-smoke` 仅执行一次 host foreground run，
  collected/valid `40/40/40/40`、zero issues/anomalies/publication failures；optimization command
  `9.0020409 s`、cell runtime `11.8459609 s`、benchmark elapsed `12.345 s`。fresh measured
  `temp/20260831_121405-stage6-benchmark-measured` 也仅执行一次 host foreground run，collected/valid
  `2000/2000/2000/2000`、zero issues/anomalies/publication failures；optimization command
  `635.0217210 s`、cell runtime `665.9498404 s`、benchmark elapsed `681.297 s`。single-seed performance
  是 descriptive evidence，不作 HV/算法优劣 gate。
- measured 20/20 strict generation metadata、training metadata、checkpoint aliases/manifests/artifacts
  与 final completion generation 19 完整；smoke 对应 2/2 与 final generation 1。generation 0 均是
  full-real warmup，measured generation 1--19 均使用 explicit PCA/SVD+GPSAF alpha/beta 3、exploration
  0.1、`gamma=0.5`，每轮 NumPy reverse-row transform 与 synchronous fit 可审计；training sample
  count 从 100 增至 2000，全部 recording failure counters 为零。
- smoke/measured program/helper bytes 相同，仅 budget/path 不同。program SHA-256
  `E626C62D90BF27FB7538C6C3EC8D234BCCEA1CEDD2C7F92A48FD97C2A8E1655A`、helper SHA-256
  `A436D2DAD34B40886C7B39E38985049D455FE8212A3B3E5486A48B21C129AD5F`、benchmark strategy digest
  `7017FE12845BACDDBCA496916E29B605C53639C77BD06C99A0248E1F9BE080A9`、program signature
  `403FC869DE3AF65C51E5752262156C2159CD3B1B7138937498B62E25D12E7ECC`、program source fingerprint
  `2D4F4782D761390AB9A44CE94198D99862C4E3F5FFD224B5BCABEACD63E2B2F0`。
- bounded automatic TODO check：reliable-recording 自然命中检查范围，但 explicit scopes 复用现有
  writer/finalizer、commit 前 flush，measured 2,000 rows 全部发布，未发现不一致；redundancy check
  确认公共 combiner 替代 GPSAF private merge，program 没有第二 executor/recorder；另在已进入范围的
  benchmark `planning.py`/`storage.py` 合并重复 `pathlib` import（两文件各净减 1 行，final 21 tests
  通过）。legacy dual path 是 Stage 7/8 明确待迁移/删除边界，当前没有其他可安全删除项；
  release-marker check 只命中真实 protocol
  v1 与明确 Stage 7/8 migration/deletion marker，不是 incidental edition label；component-configuration
  check 只见 explicit program/factory kwargs + identity 与 core campaign policy，无 uppercase/hidden/
  fallback 第二入口。四份 recurring auto TODO 均保持 active。
- architecture、blueprints、terminology、user docs 与 benchmark docs 已同步；change record 为
  `dev_doc/change_records/20260831_125908_add-explicit-workspace-optimization-program.md`。本文
  post-refinement/pre-implementation SHA-256 为
  `310BC26A45A120D408C14DAA2576A59FBE2DF9183AE14C79E13A90AB974570FF`；进入阶段时 worktree
  clean，无 pre-existing user changes。

## 完成、归档与自动续跑

两条 pilot 已使用真实 public primitives 完成端到端 generation，program/snapshot/check/resume/
scope 合同有直接证据，transitional old-path consumer inventory 已冻结；文档/automatic TODO
check/change record/commit/fetch-push 完成后，归档本文、更新 ledger，并自动进入
[Stage 7 retained capability migration](../../toDo/20260830_220200_explicit-optimization-stage-7-retained-capability-migration.md)。
