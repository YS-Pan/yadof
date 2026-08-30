# Posterior calibration 与 qNEHVI structural evidence

## 角色与边界

本文保存 posterior-assisted EHVI/qNEHVI 活动 TODO 依赖的已完成实验：v8 exact-state held-out
calibration、v9 blocked-readiness real canary 和 v10 structural release run。它不是 future-work
queue、性能接受、exploitation 授权、正式 optimization-quality 证据或默认策略推荐。

活动工作入口是
[Posterior-assisted EHVI/qNEHVI TODO](../toDo/20260828_121904_surrogate-qnehvi-remaining-work.md)。
当前 architecture、blueprints、code 和用户指令优先于本文；旧 preregistration 中的 gate/status
只保持对应 experiment 的历史含义。

## Provenance 与 artifact 可用性

### Tracked provenance

- [v8 calibration change record](../change_records/20260828_010422_coherent-posterior-calibration-framework-fail-closed.md)
- [v8 archived handoff](../obsolete/20260827_082609_coherent-posterior-sampling-calibration.md)
- [v9 qNEHVI framework change record](../change_records/20260828_020622_qnehvi-posterior-assisted-framework.md)
- [v9 archived handoff](../obsolete/20260827_082611_qnehvi-acquisition-strategy.md)
- [v10 integrated release change record](../change_records/20260828_032749_integrated-acceptance-release-framework.md)
- [v10 archived handoff](../obsolete/20260827_082612_validate-new-surrogate-and-qnehvi.md)

历史文件提到的 `benchmark_automation/preregistrations/20260828-*` 目录已不在迁移时的当前
HEAD；不得把那些旧相对路径写成仍可访问的 current artifact。v8/v9 的可追溯身份由上述
append-only records、archived handoffs、commit/signature/hash 和冻结结果共同提供。

### 仍可访问的 v10 structural run

仓库 ignored evidence root：
`temp/20260827_192319-082612-v10-structural-release-5762ec48fe39`。

迁移时已核对：

- [report.md](../../temp/20260827_192319-082612-v10-structural-release-5762ec48fe39/report.md)
- [report.json](../../temp/20260827_192319-082612-v10-structural-release-5762ec48fe39/report.json)
- [run spec](../../temp/20260827_192319-082612-v10-structural-release-5762ec48fe39/run_spec.json)
- [collection](../../temp/20260827_192319-082612-v10-structural-release-5762ec48fe39/evidence/collect-0001/collection.json)

该 evidence tree 含 mixed-ACL cell workspace；根级 report/spec/collection 是本上下文的首选
入口。若 ignored tree 以后被清理，以 tracked v10 change record/archived handoff 为 provenance，
不要把路径消失解释成实验结论失效。

## v8 exact-state held-out calibration

### 条件与完整性（已验证事实）

- 从 v7 tree `f8a684f39e3b85469d33c15085e7e877e7c6ca35` 出发，先用 development
  train/validation 建立 3 cases × train=1000/2000 的六个 durable checkpoints。过程完成
  6/6 cells、exit 0、wall 471.144 s，没有打开 calibration/offline-test，也没有启动 simulator。
- Pre-access commit 为 `d845c57aedce4f8e0ee77925f72bd8cadf5fd973`；v8 plan SHA-256 为
  `6b03b2f019bd6d1e9993259c3837843c4d7eefa387164b2a477007f6694240fb`；checkpoint
  bundle summary SHA-256 为
  `1c5cb5ea4f37f7e596a79c402ab6fb9a9fe16541ebf16c3866024f4cf9429028`。
- 唯一正式 calibration process 使用 600 个独立 calibration designs，完成 6/6 cells、
  exit 0、wall 428.213 s；没有打开 offline-test，也没有启动 simulator。
- 每个完整 rawData member 均通过当前 task `calc_cost.py`；current-cost projection invalid
  counts 均为 0；每个 cell 完成 bounded q=1/q=2 qLogNEHVI decision proxy。External summary
  SHA-256 为 `e8d4997323498557eb6c69807a46f889b21ebf8bc8d25313315848fc83f3533d`。

### 结果（已验证事实）

- 六个 cell 的 cross-fitted field-macro coverage error 均改善，最大 ensemble-mean shift 仅
  `1.3322676295501878e-15`；这说明 calibration wrapper 没有移动 posterior mean。
- 每个 rawData candidate 仍至少失败一个冻结的 energy、current-cost 或 acquisition check；
  因此 usable rawData calibrated capability 为 0/6。
- 所有六个 artifacts 只暴露 identity field scales，`rawdata_status=uncalibrated`、
  `transferable=false`，且不暴露可用于 exploitation 的 applicability coefficients。
- Chrono labels 为 19 smooth / 181 chatter-or-failure；在 design-level two-fold 和 minimum
  class count 10 下，train=1000/2000 两个 applicability fits 均 fail closed，因此 Chrono
  usable applicability capability 为 0/2。SAW 与 synthetic test-com 没有 quality policy，
  applicability 明确为 `not-applicable`。

### 支持的解释

Coherent calibration framework 与 held-out evaluation mechanism 已经可运行，但这些 exact
states 没有可用于 qNEHVI 的 calibrated/transferable posterior 或 applicability capability。
Coverage improvement 不能覆盖其余 frozen check 的失败，也不能把 identity artifacts 迁移到
successor state。该结论是 exact-state capability evidence，不是对所有 CAE architecture 的
性能判决。

## v9 blocked-readiness real canary

### 条件与结果（已验证事实）

- 一个 foreground-generated `test_com` workspace 运行一代，population=2、seed=82611；
  posterior readiness 被有意设为 blocked。
- 2/2 real local evaluations 完成并在一个 segment 中 durable publish；recorder
  offered/admitted/published 为 2/2/2，无 write/fatal failure。
- Public metadata 为 `surrogate_used=false`，source
  `posterior_assisted_real_random`，fallback reason
  `typed-exploitation-capability-blocked`，handoff `common-real-evaluate-population`。
- Cost view 读取两条 completed rows、0 ignored issue、2-row Pareto front。

该 canary 只证明 typed blocker、full-real fallback、common evaluator 和 recorder 边界能运行；
它没有进入 eligible path，不能支持 posterior selection 或 optimization-quality claim。

## v10 structural release run

### 条件与结果（已验证事实）

- Candidate installed wheel 的 `structural-full` preflight 为 13/13。
- 唯一 real structural runner 完成 9/9 cells、99/99 attempted evaluations、96 completed
  records、3 个显式 Chrono finite error-cost records、0 timeout、0 all-infinite generation。
- 82/82 structural checks 通过，`contract_satisfied=true`；覆盖 rawData shape、declared inputs、
  objective width、generation sequence、checkpoint、surrogate summary/audit、paired generation-0
  population 和 isolated workspace。
- 三个 disposable smoke cells 保留 attempted-count alignment warning；
  `evaluation_normalized_hv_auc` 与 `checkpoint_training_cutoff` 是当时明确的 public-tool gaps。

该 run 只执行 existing NSGA-III 和 conditional-INR + GPSAF baseline arms；没有 qNEHVI arm，
没有 posterior-assisted eligible path，也没有 optimizer-ranking 解释。

## 未运行的正式 optimization evidence

当时 `performance` 只有一个 no-write plan：三 cases × 两 baseline arms × 一 seed，共 6 cells，
每 cell 100 individuals × 20 generations，计划 12,000 attempted evaluations。它不包含
posterior-assisted arm，formal suite 没有启动。

因此下列结论仍未获得真实实验支持：

- 任一 exact posterior 对真实 candidate selection 的净收益；
- qNEHVI 相对 GPSAF 或 real NSGA-III 的同预算 HV/HV-AUC 收益；
- CAE + GPSAF 与 CAE + qNEHVI 的 attribution；
- posterior projection/acquisition 的代表性总工程成本和跨 seed 稳定性。

这些缺口是活动 EHVI/qNEHVI TODO 的 future work。Synthetic/fake backend evidence、blocked canary
和 structural baseline run 都不能替代正式 optimization-quality evidence。
