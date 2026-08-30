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
