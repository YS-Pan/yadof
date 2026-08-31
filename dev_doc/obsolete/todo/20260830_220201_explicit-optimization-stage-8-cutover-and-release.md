# 显式 optimization 重构阶段 8：删除旧编排并发布 yadof 0.5.0

## 状态、授权与依赖

本文是单一 Goal 的预测性最终 TODO，已获届时精化/执行授权。只有 Stage 7 capability matrix
证明全部 retained consumers 已迁移后，执行者才可在本文内冻结 deletion list、migration note、
starter/examples/docs 和 release acceptance；不需要最终用户再发送“确认”。

若仍存在真实 old-path consumer，不得通过删除测试、alias 或 capability 来强行发布；在本阶段
内完成迁移/修复。只有需要改变保留能力、GPSAF `gamma` 或八阶段目标时才暂停。

## Cutover

删除所有已无消费者的 hidden orchestration，包括经当时 inventory 证实的：

- strategy-owned complete generation loops 与 old `build_optimization()` entry；
- component-internal CampaignSession training-data reads；
- hidden `after_jobs_submitted` overlap callback；
- pilot dual-path selector、compatibility facade、temporary adapter 和 old metadata/state branch；
- 已被 program scope/handle/state primitives 取代的第二套 run/resume/check logic。

删除前对每项给出 direct caller/import/dynamic resource/CLI/template/example/benchmark inventory；
static no-match 不能单独证明 dynamic entry 无消费者。删除后不得保留 warning-only alias、
permanent feature flag 或把旧名字包装到新入口。

## 0.5.0 产品交付

## 2026-08-31 执行前精化：删除证明、最终 API 与串行切片

本次精化的输入 HEAD 为 `24e739bb2f43ea240abfc1654ecb34f7ec80f064`，本文精化前
SHA-256 为 `60A8D4B3547FD365570CCB41466FF987A088B1CE9D0062A098B5B86D8EBB1929`。
Stage 7 的 corrected installed wheel 已通过 `448/448` core tests 与 `21/21` benchmark tests；
最终 measured run 完成 `2000/2000` finite evaluations，并证明 19 个唯一 lag-one
training/checkpoint event。fresh `origin/main` comparison 为 behind 0 / ahead 4，Stage 7 commit
为 `24e739b`，因未达 ahead >= 5 gate 未 push。

pre-deletion direct caller/import/resource inventory 冻结如下：

| removal surface | remaining direct/dynamic consumers before Stage 8 | retained 0.5.0 boundary | deletion proof |
| --- | --- | --- | --- |
| `build_optimization()` inspection/import 与 `OptimizationStrategy.run_generation()` | `optimize.program` 的 legacy inspection、`optimize.api` fallback、`optimize.strategy` loader、workspace check、benchmark planner；其余命中均为 tests/transitional docs | literal `YADOF_OPTIMIZATION_PROGRAM`、一次 frozen entry、program/run/generation scopes | starter、HFSS example、三个 packaged baselines 已无 legacy source；init/check/run 和 benchmark dynamic tests 只接受 explicit program |
| `GPSAFStrategy`/`RealSearchStrategy`、`gpsaf()`/`real_search()` complete wrappers | `optimize.components`、public exports、legacy composition tests | `full_real_search()`、`select_gpsaf_generation()`、`gpsaf_settings()` 与 workspace-owned evaluation/training/commit | public import no-match、structural source no-match、real/GPSAF parity tests |
| posterior complete runner/factory | `PosteriorAssistedStrategy.run_generation()`、`posterior_assisted()` 与 legacy runner tests | `PosteriorAssistedSelector` + `posterior_assisted_selector()` 只做 validate/identity/typed selection；program owns real handoff | blocked/full-real、hard-stop、joint-draw tests and source-checkout example |
| GPSAF phase materializer/dynamic predictor adapter | legacy `run_generation()` 和 phases adapter；explicit Stage 7 caller 已传 typed training data/component | typed `DeterministicSurrogateComponent`、pure freshness/predict, explicit start/finish training | forbidden-session and forbidden-side-effect tests；`legacy-gpsaf-prediction-adapter` no-match |
| conditional posterior session schema fallback | legacy posterior runner only | `make_rawdata_sampler(..., training_data=SurrogateTrainingData)` mandatory | forbidden-session explicit sampler test and session-read no-match |
| `after_jobs_submitted` | legacy optimize runners plus callback-specific evaluation tests; no starter/example/baseline/program signature consumer | `start_evaluation()` handle returned before program starts independent training | remove public/private batch fields and fast/local/distributed/Condor callback forwarding; lifecycle/order tests cover handles directly |
| benchmark legacy strategy AST | benchmark planning and two synthetic test writers only | literal program declaration + statically declared helper closure | planner/unit/baseline/dynamic benchmark tests; docs no longer advertise legacy |

0.5.0 的最终 public naming 同时冻结：`OptimizationResult`、`GenerationContext`、history/signature
values 继续是 explicit program primitives；`OptimizationStrategy`、`OptimizationDefinition`、
`load_workspace_strategy()` 和 strategy-level `evaluate_population()` 删除。posterior selection
component 改名为 `PosteriorAssistedSelector`，factory 改名为
`posterior_assisted_selector()`；旧 class/factory 不保留 alias 或 warning wrapper。Pymoo search
components、GPSAF settings/selection、surrogate factories、qNEHVI acquisition、program scopes 与
evaluation/training handles 保留。`evaluate_manager.evaluate_population()` 仍是独立同步 convenience
API，但不再接受 callback。

产品/版本切片按以下顺序串行执行：

1. 删除 strategy/factory dual path，使 program inspection/freeze/run/check 只接受 literal program；
   删除 complete GPSAF/real/posterior runners并收紧 typed selection/session boundaries。
2. 删除 evaluation callback 的 public/private/backend plumbing，更新 fast/local/distributed fake
   lifecycle tests；不执行真实 HTCondor。
3. benchmark planner 只接受 explicit program，并将独立 `yadof-benchmark` breaking line 从
   `0.2.2` 升为 `0.3.0`、最低 yadof 依赖升为 `>=0.5.0`；三个 baseline 的数学、budget、seed
   和 source program 不作非 cutover 改动。
4. 在 `examples/optimization-programs/` 增加一一配对的 `.py`/`.md`：real-only、sequential
   surrogate、explicit evaluation/training overlap、custom cost/surrogate evidence split、诚实
   blocked posterior fallback。它们是 source-checkout-only 可复制 program，不含 workspace/
   simulator assets；user index 明确依赖和采用方式。
5. 增加 0.4.2 -> 0.5.0 migration，更新 starter、CLI/help、user docs、architecture、blueprints、
   terminology、active handoffs、benchmark docs 与 package/resource/version contracts；yadof 版本
   升为 `0.5.0`。
6. 运行 focused slices；build/force reinstall 后运行 fresh-basetemp core full suite 与 benchmark
   full suite；audit wheel/sdist allowlist、installed docs/resources/version、clean external
   init/check/run、example pair/link/static contracts 和 no-dual-path search。
7. 使用 `test-com/synthetic-antenna` 的同一 explicit PCA/SVD + GPSAF program/source 建立两个新
   scratch workspace：host foreground exact-once smoke `20 x 2` seed 101，随后 exact-once
   measured `100 x 20` seed 101。两者只允许 budget materialization 差异；记录 planned/
   attempted/completed/finite、generation completeness、state/training/checkpoint、issues/anomalies/
   publication failures、source/semantic/strategy digests 与 runtime。
8. 完成 automatic TODO bounded check、change record、本文归档、ledger、最终 diff/staged-check、
   commit/fresh fetch/条件 push。若 fresh `origin/main` 仍 behind 0，Stage 8 closure 应使 ahead
   至少为 5 并触发 normal non-force push；remote ahead/divergence/fetch failure 时不自行整合。

不进入实施的边界继续冻结：不改变 GPSAF `alpha/beta/gamma` 数学或 defaults，不提高 blocked
posterior readiness，不开展 CAE/noise/trust-region/acquisition-protocol 科学研究，不运行真实
simulator、付费资源或 HTCondor。代表 benchmark 只证明 0.5.0 orchestration/recording/regression
完整性，不证明算法优越。

### Starter 与 examples

- package 唯一 starter
  `src/yadof/_resources/templates/default/workspace/submit/optimization.py` 是完整、保守、三 backend
  安全的 program；`yadof init` 只有这一模板，不新增 selector/registry/discovery/CLI option。
- 顶层 source-checkout `examples/` 建立 optimization programs 目录。每个 `.py` 有同 basename
  `.md`，说明背景、适用场景、完整 workspace 依赖、数据流、并发/资源取舍和采用方式。
- examples 至少包括 real-only、顺序 surrogate、显式 evaluation/training overlap 和自定义
  cost/surrogate 数据分流。posterior-assisted 示例必须诚实展示 readiness/fallback；不能暗示
  current blocked state eligible。
- examples 不复制 `config.py`、`calc_cost.py`、`job_template/` 或 simulator assets，不是可单独
  运行 workspace，也不进入 yadof wheel。
- `user_doc/` 增加轻量索引，每例一句用途，并明确 source-checkout-only 可见性。

### CLI、migration 与 docs

- `yadof check` read-only 且不执行 arbitrary program；run/resume 只在 generation boundary；
- 提供 0.4.2 -> 0.5.0 migration：optimization program entry、state/checkpoint rules、removed old
  orchestration、starter adoption、examples 和 compatibility limits；
- migration 明确保留 GPSAF `gamma`；没有 gamma removal/deprecation note；
- architecture、全部相关 module/file blueprints、terminology、user docs、templates、examples、
  CLI help、benchmark docs/strategies 和 package artifacts 与新 current system 一致；
- package version 从 0.4.2 升到 0.5.0，wheel/sdist allowlist 正确。

## 最终 capability matrix

对每项记录 current public entry、program example/fixture、focused tests、checkpoint/state policy、
backend coverage 和 migration status：

- real GA/NSGA-III；
- GPSAF + conditional-INR、PCA/SVD、Hierarchical CAE；
- posterior-assisted/qNEHVI readiness/blocked/full-real fallback；
- fast/local/distributed；
- recorder/query/history/tools/viewers；
- starter/init/check/run/resume；
- benchmark integration。

matrix 必须明确 GPSAF `alpha`/`beta`/`gamma`、seed/archive/duplicate/identity/diagnostics parity。
不要求 scientific TODO 的未获批 real experiments 完成，但其 current opt-in/blocked capability
不能因 cutover 消失。

## 验证与 release gate

- focused tests 覆盖每项 deletion 与 migration；
- full installed-package pytest 使用 fresh task-unique `--basetemp`、disabled cache；
- build wheel、force reinstall、确认 import origin/version/resources/docs；
- wheel/sdist artifact audit，clean external workspace init/check/run smoke；
- fast/local/distributed targeted lifecycle/cleanup/resume contracts；
- no-dual-path consumer/import/resource scan 与 dynamic CLI/template/benchmark tests；
- example `.py`/`.md` 一一对应、索引链接完整、init 只生成唯一 starter；
- overall policy 的同源 fast smoke 与唯一最终 100 x 20 measured benchmark collected/valid、
  attempted 2000、无缺代/缺个体；
- automatic TODO bounded checks、UTF-8/link/reference/diff checks 与 release change record。

真实 simulator、HTCondor full-budget、付费/共享资源执行不在本 Goal 授权内；不能用它们作为
0.5.0 必须 gate。representative single-seed benchmark 是结构/回归证据，不宣称算法优越。

## Goal 完成规则

只有以下全部成立才完成：

- Stage 1--8 TODO 均已归档，overall ledger 有输入、evidence、commit/push 和最终状态；
- retained capability matrix 全部 resolved，无 permanent dual path；
- 0.5.0 installed wheel、full tests、final benchmark、migration、starter/examples/docs 一致；
- 最终 Git diff/staged diff/check/commit/fetch 与条件 push 按 workspace 规则完成；
- 向用户报告 changed files、验证、阶段 commits、pre-existing changes、最终 commit 和 push
  结果。

不需要额外的阶段后或最终确认。完成后将本文移入 `dev_doc/obsolete/todo/`，把 ledger 最后一
行改为 archived/complete，并结束 Goal。若某个实质暂停边界仍未解决，则明确保持 Goal 未完成。

## 2026-08-31 完成证据与最终 capability matrix

Stage 8 已完成并归档。cutover 后 literal `YADOF_OPTIMIZATION_PROGRAM` 是唯一 workspace
entry；0.4.x strategy/factory/callback path 不保留 alias、warning wrapper 或 feature flag。
最终 retained capability matrix 如下：

| capability | current public entry | program example / fixture | focused evidence | checkpoint / state policy | backend and migration status |
| --- | --- | --- | --- | --- | --- |
| real GA / NSGA-III | `full_real_search()`、Pymoo state values | `real_only.py`、package starter | explicit search/composition/program tests；seeded GA/NSGA-III parity | opaque Pymoo state + generation commit；只在完整代边界 resume | fast/local/distributed lifecycle retained；0.4.x `real_search()` removed |
| GPSAF + PCA/SVD | `gpsaf_settings()`、`select_gpsaf_generation()`、typed deterministic component | `sequential_surrogate.py`、`overlapped_surrogate.py`、measured program | settings/identity/selection tests；exact 100 x 20 evidence | training handle owns 19 unique checkpoints；selection recovers exact lag-one rows read-only | three backends use explicit evaluation handle；`gpsaf()`/`GPSAFStrategy` removed |
| conditional-INR / hierarchical CAE | explicit factories consuming `SurrogateTrainingData` | typed fixtures and `split_cost_surrogate_data.py` pattern | conditional adapter、CAE、packaged surrogate tests | component-owned immutable settings and checkpoint repositories；no session schema fallback | retained opt-in capability；no central config or hidden data read |
| posterior-assisted / qNEHVI | `PosteriorAssistedSelector`、`posterior_assisted_selector()`、qNEHVI acquisition primitives | `posterior_assisted_fallback.py` | blocked/full-real、hard-stop、joint-draw、posterior adapter tests | typed readiness remains fail-closed；no false checkpoint eligibility | selection-only across program backends；old complete runner/factory removed |
| evaluation backends | `start_evaluation()` / `EvaluationHandle` and synchronous convenience API | starter plus backend lifecycle fixtures | fast/local/distributed/packaged distributed and cancellation/cleanup tests | one campaign, no open handle at commit; errors close lifecycle | callback-free parity; real HTCondor deliberately not executed |
| recording/query/history/viewers | recorded-data APIs、cost/time/surrogate tools | package/external workspace fixtures | package foundation、recording and viewer suites；benchmark diagnostics | finalized evidence is durable before generation commit；zero benchmark recording failures | shared semantics retained across all backends |
| starter / init / check / run / resume | literal starter and program inspection/freeze/run APIs | unique packaged starter + five paired source examples | static pairing、real-example run、CLI/config/task-loader tests | check is read-only; run/resume load only at generation boundaries | 0.4.2 migration guide documents hard compatibility boundary |
| benchmark integration | `yadof-benchmark 0.3.0` explicit-only planner | three packaged baselines + Stage 8 scratch program | `22/22` installed benchmark tests and exact acceptance runs | cell/runtime/report publication collected and valid | requires `yadof[plot]>=0.5.0`; legacy AST rejected |

GPSAF parity remained explicit: representative settings used `alpha=3`, `beta=3`,
`gamma=0.5`, exploration count 10 and seed 101; archive/duplicate/identity/diagnostics
contracts stayed covered by the focused/full suites. `gamma` remains in validation, identity and
diagnostics and was neither removed nor reinterpreted.

### Verification

- AST parse: 228 Python files, zero syntax failures.
- final focused installed-wheel slices: `188 passed in 63.55s`；core installed-wheel full suite:
  `450 passed in 87.90s`；installed benchmark suite: `22 passed in 1.08s`。
- yadof `0.5.0` and yadof-benchmark `0.3.0` wheels built, force-reinstalled, and imported from
  the outer `.venv/Lib/site-packages`; installed migration and benchmark docs were readable.
- full package acceptance covered wheel/sdist allowlists, source-example exclusion, clean external
  installation and external `init/check/run`; the unique starter remained explicit.
- exact-once smoke `20 x 2` seed 101 completed 40 planned/attempted/completed/finite rows, zero
  issues/publication failures, result runtime `5.7084967 s` and benchmark elapsed `8.682114 s`.
- exact-once measured `100 x 20` seed 101 completed 2000 planned/attempted/completed/finite rows,
  zero issues/anomalies/publication failures, 20 complete generations, 19 training/checkpoint sets
  over 100--1900 rows, and 18 fresh lag-one surrogate generations. Result runtime was
  `645.2844323 s`; benchmark elapsed was `691.144475 s`.
- smoke/measured program SHA-256 was
  `4f5f876226a6076f7ea530dbc65bb927b30a80df217cff4a0ff2c7880676876b` and strategy digest was
  `fcfc93949e7df8e8b61368f6d18882e2cde3d2acc716d1dcef73a4040f9933f5`; normalized workflow
  comparison proved budget-only difference.
- no real simulator, paid/shared resource or HTCondor campaign ran；single-seed evidence is
  orchestration/regression acceptance, not scientific superiority.

### Automatic TODO bounded check

- component configuration: touched factories/settings retained one explicit owner and no second
  config entry；core max-training-lag policy did not migrate into component settings。
- reliable recording: callback removal did not bypass finalizer/backpressure/generation boundaries；
  tests and measured diagnostics exposed no mismatch。
- incidental release markers: old names remain only in migration/rejection/history evidence；real
  package versions are not transitional markers。
- incidental redundancy: this planned cutover removed the proven old orchestration；the bounded
  follow-up found no separate safe one- or two-file cleanup candidate。

对应完成变更记录是
[20260831_175919_cut-over-explicit-optimization-and-release-0-5-0.md](../../change_records/20260831_175919_cut-over-explicit-optimization-and-release-0-5-0.md)。
