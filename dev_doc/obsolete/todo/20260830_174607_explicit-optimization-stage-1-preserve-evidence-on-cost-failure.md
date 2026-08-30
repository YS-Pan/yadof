# 显式 optimization 重构阶段 1：先可靠发布 evidence，再解释 cost

## 状态、授权与依赖

本文是八阶段系列中唯一已精化的首阶段 TODO。2026-08-30 用户授权由一个明确点名全部阶段
文件的 Goal 依次精化并执行整个系列；该 Goal 触发本文后，可以直接实施，无需在本阶段完成
后等待用户确认。完成、归档、更新 overall-plan ledger 和提交后，自动进入
[阶段 2](../../toDo/20260830_174608_explicit-optimization-stage-2-dataset-and-cost-tables.md)。

该授权只覆盖本文定义的源码/测试/文档、installed-wheel 验收和 fast synthetic benchmark。
不授权真实 simulator、HTCondor full-budget run、用户 workspace/evidence 迁移或删除。GPSAF
`gamma` 在本阶段及整个重构中保持不变。

## 本次执行输入（2026-08-30）

- 输入 HEAD：`17c3e95b3a24184977b300972661a48650632ac7`，分支 `main`，启动时 tracked
  worktree 与 staged diff 均为空；本地相对当时 tracking ref `origin/main` ahead 2。
- 本 TODO SHA-256：
  `6A01CBD81B41A06E98A271B80F6E4E5111A68320A46F7E272E0685F2C603CABB`；overall plan
  SHA-256：`7A6DEDB02F0E538B02BF3FE5490A4DF515AC34C900235FB7E55FFE405876E7D7`。
- pre-change 接受输入是 force-installed yadof `0.4.2`，import origin 为外层
  `.venv/Lib/site-packages/yadof/__init__.py`。task-unique harness 保存在外层 workspace
  `temp/stage1_recording_microbenchmark.py`，harness SHA-256 为
  `c3f6a5cc142d80b6790701b8c39d72df1861653d490d1891853b210a16ffcd34`，输入 SHA-256 为
  `7ba18420708260b32bc5f31d69875d0e988685f2ada636328a6d136c6e2d233b`，结果保存在
  `temp/stage1-recording-20260830_223600934/pre-change.json`。
- 一次 warm-up 后五次 100-row 标准小 envelope 重复均得到 100 个唯一 durable rows、7 个
  segments、occupancy `[16, 16, 16, 16, 16, 16, 4]`。median wall 为 `0.2101266 s`，
  throughput 为 `475.9036 candidate/s`，completion-to-commit median/p95 为
  `26.3029/42.9794 ms`，signed commit-to-cost median/p95 为 `-25.3994/-12.3591 ms`；负值直接
  证明 current cost 在 commit 前完成。median process peak RSS 为 `47,587,328 bytes`，相对
  repetition-start RSS 的 median sampled delta 为 `86,016 bytes`；recorder peak unpublished
  count 为 20，peak unpublished reservation 约 1.43 MiB。
- 后续 post-change 必须使用同一未修改 harness/input digest；15% target 以五次重复的 median
  wall `0.2101266 s` 与 segments/candidate `0.07` 为 baseline，可靠性 hard gates 仍优先。

## 已验证的当前事实

- `evaluate_manager/finalizer.py` 当前在把 owned evidence 交给 recorder 前运行
  `calc_cost.py`。cost exception、native crash、`os._exit()`、OOM 或 orchestration process
  终止都可能让合法 rawData 在 durable publication 前丢失。
- recorder queue admission/accepted-current-row 只代表内存 ownership，不代表 immutable
  segment 已原子发布或可由新 session recovery discovery。
- fast parent 当前按单个 completion finalization 后再补 worker；若直接改成“offer 一个、等一个
  receipt、算一个 cost”，可能把 recorder micro-batch 退化为 singleton segment 并降低 worker
  refill throughput。
- point-in-time `calculate_cost()` 与冻结 `CostInterpreter.calculate_costs()` 必须共享 callback
  exception、objective width 和 finite-value 合同；只在 finalizer 做有限性检查会让历史重解释
  再次接纳 `NaN`。
- 当前 recorder 已有 bounded count/byte backpressure、same-directory atomic segment rename、
  retained-batch retry、writer-death fatal propagation 和 campaign lock。这些正确机制应复用，
  不建立第二个 recorder 或新持久格式。

## 本阶段精确结果

每个取得合法 rawData 的真实 evaluation 必须满足：

```text
backend completion
  -> validate rawData
  -> transfer/copy to yadof-owned evidence
  -> enqueue into a bounded prepared-evidence group
  -> publish one immutable segment/batch
  -> resolve committed receipt(s)
  -> calculate current cost in deterministic candidate order
  -> expose the interpreted result
```

`validate` 证明 schema；`own` 证明 worker/job/scratch 立即消失也不丢 payload；`committed` 只在
segment 已通过现有原子 publication 且新 session 可发现后成立。本阶段不新增掉电级 `fsync`
承诺。

这是一种 bounded two-phase coordinator，不是逐 candidate 串行等待：

1. evaluation completion 可以继续准备多个 owned envelopes；
2. coordinator 按现有 count/byte targets 或显式 flush boundary 形成 bounded group commit；
3. receipt 状态至少区分 pending、committed、failed，并能关联 group 与 candidate；
4. group commit 后，parent 以稳定 population/candidate 顺序运行 current-cost interpretation；
5. 已 commit、尚未解释的队列仍受 count/byte 或等价显式预算约束，不能把 publication
   backpressure 转移成另一条无界内存队列；
6. writer death、oversized envelope 或同一 retained group 重试耗尽必须一次性唤醒所有相关
   waiter，传播 `RecordingError` 并阻止后续 evaluation。

允许同一 group 中较早完成的 candidate 等待 batching；不允许为追求 batching 无限等待。
evaluation/population boundary 必须主动 flush 并收口所有 receipt。

## Evidence、execution 与 interpretation 状态

三个状态域独立：

- execution 描述 workflow/evaluator 是否产生合法 payload；
- evidence 描述 payload 是否 validated/owned/committed；
- interpretation 描述当前 task snapshot 下 cost 是否成功。

rawData 无效时，candidate 保持现有失败形状且没有 completed evidence。rawData 已 commit、
cost 失败时：

- durable evidence 仍是 completed，并保留 rawData 与 evidence provenance；
- current evaluation 返回正确 objective width 的 `inf`，但 `inf` 只是 optimizer adapter 的
  失败表示，不写成 authoritative cost；
- callback exception、width mismatch、`NaN`/`+/-inf` 都是 interpretation failure；
- failure stage、bounded diagnostics 和耗时保存在 live/generation interpretation diagnostics，
  不反向重写 immutable evidence segment；
- 修正 `calc_cost.py` 后，下一 generation snapshot 可以从同一 evidence 重算有限 cost。

commit 后而 cost 完成前发生进程终止时，evidence 必须可恢复，interpretation 可以缺失。cost
callback 因而具有 at-least-once/replay 语义：user docs 必须要求它 deterministic、无不可重放
外部副作用。框架不因成功解释而删除或覆盖 evidence。

## 精确修改边界

预计涉及但不预先冻结内部文件拆分：

- `evaluate_manager/finalizer.py` 及直接 coordinator/callers：分离 prepare evidence、
  publication receipt 与 interpretation，保持 ordered result/failure width；
- `recorded_data/session.py`、writer/segment-store 的窄边界：可等待 committed receipt、group
  flush、waiter wakeup 和 bounded committed-but-uninterpreted ownership；
- `job_template/api.py`：统一 point-in-time 与 frozen interpreter 的 exception/width/finite
  合同；
- 直接 tests、architecture、evaluate_manager/recorded_data/optimize blueprints、terminology、
  user docs 和 change record。

允许新增窄内部 DTO/state machine，但不得在本阶段：

- 改变 campaign/generation loop、strategy public composition、surrogate session 读取或包版本；
- 全面设计 Dataset/CostTable 或 public Evaluation Handle；
- 改动 recorded-data 物理格式、GPSAF 数学/settings 或任一 optimize/surrogate 能力；
- 把 predicted data 写入 recorder，或把 recorder failure 降级为 individual `inf`。

内部 API 名称由实施证据决定，无需用户再次确认；关键 ownership/receipt/failure 选择必须写入
change record，并同步 current architecture/blueprints。

## Pre-change measurement 与工程 gates

任何源码修改前，在当前 installed wheel 上运行一个 task-unique、bounded recording
microbenchmark，并保存 harness/命令、输入 digest、warm-up、重复次数和以下 baseline：

- standard small-envelope 的 rows/segment 与 segments/candidate；
- candidate throughput 和 wall time；
- completion-to-commit、commit-to-cost 的 median/p95 latency；
- unpublished、committed-but-uninterpreted 的最大 count/bytes；
- process peak RSS。

同一 harness 改后重跑。建议一轮 warm-up 后至少五次短重复，报告 median 和 spread。以下是
工程 gate，不是 optimizer performance gate：

- hard：全部 rows 恰好 commit 一次、无 history gap/duplicate、无一个 row 一个 segment 的
  系统性退化，100-row standard case 的平均 segment occupancy 必须大于 1；
- hard：两个 pending 队列都不超过配置/明确预算，peak memory 不通过隐藏无界 buffer 增长；
- hard：writer/oversize/retry failure 在 bounded time 内唤醒 waiter 且不开始后续 evaluation；
- target：median wall time、segments/candidate 相对 baseline 的回归均不超过 15%；超出时先
  redesign/定位，不能用删除 batching 或放宽可靠性换取通过；
- report：p95 commit/cost latency 与 RSS 的变化即使通过 target 也写入 change record。

若机器噪声使 15% 结论不稳定，增加同一 bounded harness 的重复并报告区间；不得在看到
post-change 结果后静默改变 gate。若可靠性与该 target 确实无法兼得，命中 overall plan 的实质
权衡暂停边界。

## 测试与 installed-package 验收

至少覆盖：

- cost callback success/exception/hang-isolation test、objective width、`NaN`/`+/-inf`；
- normal cost 只在对应 receipt committed 后开始；
- commit 后/cost 前的子进程终止，新 session 仍发现 rawData；仅 enqueue 后终止不能误报
  committed；
- same group 多 row receipt、out-of-order completion、deterministic interpretation/result order；
- writer transient retry、retry exhausted、unexpected death、oversized envelope、full count/byte
  backpressure 与 shutdown tail；
- rawData invalid、execution failure、interpretation failure 的独立 status/diagnostics；
- 修复 cost 后跨 generation 重解释；
- fast/local/distributed 小规模 contract/smoke，证明同一 publication-before-cost/fatal recorder
  语义与 cleanup；local/distributed 不跑全预算；
- normal success path、hot catalog、tolerant read、campaign lock 和 existing segment format 回归。

按 development guide 使用 host build/force reinstall、确认 import origin，运行 focused tests 和
完整 installed-package pytest。pytest 使用 fresh task-unique absolute `--basetemp` 且禁用 cache。

## Fast synthetic benchmark

按 [overall plan](../../context/20260830_193335_explicit-optimization-overall-plan.md) 的共同政策：

- fresh smoke workspace：`test-com/synthetic-antenna`，population 20、generations 2、seed 101；
- fresh measured workspace：同一 baseline/strategy/postprocessors，population 100、
  generations 20、seed 101；
- strategy 冻结为 NSGA-III + GPSAF + PCA/SVD 的完整显式 factory settings；GPSAF `gamma`
  使用当前值且不改 validation/identity/diagnostics；
- `check`、`plan --json` 证明 smoke/measured 仅预算不同；
- measured 必须 collected/valid、attempted 2000、无缺代/缺个体；不要求 HV improvement。

使用 Goal 明确授权的 Windows host foreground execution，只启动一次 measured run，并跟随同一
terminal/session 到最终退出码。partial progress 不是结果。该 benchmark 之外不启动真实
simulator 或 full-budget local/distributed work。

## 完成证据（2026-08-30）

### 实施与 ownership 决策

- 新增 population-scoped `ResultFinalizationCoordinator`：backend completion 先验证并转移
  rawData ownership，再按既有 segment count/byte target 分组提交，等待 committed receipt，最后
  以稳定 population index 顺序使用一个冻结 `CostInterpreter` 解释 current cost。fast、local、
  distributed 三条真实 evaluation path 共用该 coordinator；单 row `finalize_result()` 仅是兼容
  facade。
- `CampaignSession.submit_evidence()` 返回带 candidate/group identity 的
  `PublicationReceipt`。receipt 只在原子 segment publication 后转为 `committed`；oversize、重试
  耗尽、writer death 或 recorder admission failure 转为 `failed` 并唤醒 waiter。completed evidence
  segment 不包含 derived cost，live session 单独保存 interpretation state/diagnostics。
- committed-but-uninterpreted payload 复用既有 unpublished count/byte 上限；超出 owned-retention
  预算时立即丢弃内存 envelope ownership，后续从 immutable segment reference 读取，而不是建立
  第二条无界队列。
- cost callback exception、objective-width mismatch 和 `NaN`/`+/-inf` 共用 point-in-time 与 frozen
  interpreter 的同一 validation contract。interpretation failure 保留 durable `completed` evidence，
  live result 标记 `cost_interpretation` error；只有 optimizer adapter 补正确宽度的 `inf`。
- Condor result callback 对 `RecordingError` 保持 execution-fatal，不把可靠发布失败降级为单个
  candidate failure。rawData validation/execution failure 与 evidence/interpretation state 保持独立。

### Recording microbenchmark

- post-change 使用未修改的 harness/input digest：
  `c3f6a5cc142d80b6790701b8c39d72df1861653d490d1891853b210a16ffcd34` /
  `7ba18420708260b32bc5f31d69875d0e988685f2ada636328a6d136c6e2d233b`；结果为外层 workspace
  `temp/stage1-recording-post-20260830_231248051/post-change.json`。
- 五次重复全部得到 100 个唯一 durable rows、7 segments、occupancy
  `[16, 16, 16, 16, 16, 16, 4]`；mean occupancy `14.2857`，segments/candidate 仍为 `0.07`。
  median wall `0.2101266 -> 0.1353709 s`（改善约 `35.6%`），throughput
  `475.9036 -> 738.7112 candidate/s`。一轮有 `0.8407237 s` host-noise outlier，但预注册的五次
  median gate 与其余四轮保持稳定，未重跑或改 gate。
- completion-to-commit median/p95 从 `26.3029/42.9794 ms` 降至
  `12.9687/19.9571 ms`；signed commit-to-cost median/p95 从
  `-25.3994/-12.3591 ms` 变为 `+0.33655/+2.10816 ms`，直接证明解释只在 commit 后开始。
- median peak RSS `47,587,328 -> 47,607,808 bytes`，median sampled delta
  `86,016 -> 196,608 bytes`。peak unpublished 与 committed-owned 均为 16 candidates、约
  `1.145 MiB`，低于 32 candidates / 32 MiB budget；结束时两个 backlog、failed receipts 和
  interpretation failures 均为零。全部 hard/15% target gates 通过。

### Installed-package tests 与 benchmark

- host wheel build、force reinstall 与 import-origin 检查成功；接受对象仍是 yadof `0.4.2`，来自
  外层 `.venv/Lib/site-packages/yadof/__init__.py`。focused recovery/backend/finite-value tests
  通过；最终 installed-package full suite 为 `388 passed in 81.06s`。覆盖 grouped receipts、
  out-of-order stable interpretation、bounded ownership、writer failure/wakeup、adapter `inf`、
  rawData/execution/interpretation 状态分离、修正 cost 后 replay，以及子进程 commit 后
  `os._exit()`/hang 与 enqueue-only loss 的恢复差异。
- fresh fast synthetic smoke workspace
  `temp/20260830_232119-stage1-benchmark-smoke` 得到 attempted/completed/finite
  `40/40/40`；fresh measured workspace `temp/20260830_232119-stage1-benchmark-measured` 得到
  `2000/2000/2000`，20/20 generations、generation-zero 100/100、objective/rawData contracts
  match、zero failed/non-finite、cell/pairing `collected=true`、`valid=true`。measured runtime
  `601.8183 s`，descriptive final hypervolume `0.2057025861`；该单 seed 值不是算法优越性结论。
- smoke/measured strategy source bytes相同，SHA-256
  `08E4BE42C4E4A8D377866BF8BC21765A0B776A27C32823290F97210FE086CBA7`；除
  `20 x 2` 与 `100 x 20` budget 外 baseline、seed 101、NSGA-III/GPSAF/PCA-SVD explicit settings
  和 postprocessor policy 相同。identity/diagnostics 中 GPSAF `gamma=0.5` 保持不变。

### Automatic TODO bounded check

- reliable-recording consistency 直接触发：原 cost-before-publication 不一致已由 receipt、
  backpressure、writer-fatal 和 recovery tests 修复；持续 TODO 保持 active。
- 对改动源码、直接 callers/tests/docs 的 bounded redundancy review 未找到可证明且可安全删除的
  incidental redundancy。单-row facade、point-in-time/frozen validation 入口以及 backend failure
  isolation 分别承担兼容、共享合同和故障边界，予以保留。
- 未新增 component-owned config key、legacy alias 或第二 settings 入口；component configuration
  migration 未触发。package version 保持 `0.4.2`，`0.5.0` 只存在于已授权 Stage 8 roadmap，未出现
  incidental release marker。四份 recurring auto TODO 均保持 active、文件不变。

对应 change record 为
`dev_doc/change_records/20260830_234247_stage-1-evidence-first-finalization.md`。启动时 worktree
clean，无用户或其他任务的 pre-existing changes 被并入。

## 完成、归档与自动续跑

完成要求：

- publication-before-cost、bounded group commit、receipt/wakeup、replay、状态分离和恢复行为
  均有直接测试；
- pre/post microbenchmark 通过 hard gates/target 并记录全部指标；
- installed wheel、full pytest、fast 100 x 20 benchmark 均成功；
- current architecture、blueprints、terminology、user docs、overall ledger 和 change record
  一致；
- 自动 TODO bounded check 完成，形成一个已验证 commit，并按仓库规则 fetch/push 判断。

随后将本文原样移入 `dev_doc/obsolete/todo/`，更新 overall ledger 的归档链接，不等待普通
用户确认，立即读取并精化 Stage 2。
