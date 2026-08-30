# 显式 optimization 重构阶段 2：稳定身份的 EvidenceDataset 与 CostTable

## 状态、授权与进入条件

本文原为已获得单一 Goal 后续精化/执行授权的预测性手动 TODO。Stage 1 完成并归档后，已于
2026-08-30 根据其 committed receipt、状态分类、replay、microbenchmark 和 100 x 20 evidence
精化为下述精确执行合同；不需要新的用户“继续”指示，也不得与其他阶段源码实施并行。

本阶段已于 2026-08-31 完成实现、installed-wheel 验收、fast synthetic benchmark、文档同步、
automatic TODO bounded check 与归档闭环；GPSAF `gamma=0.5` 保持不变。

进入本阶段时记录当前 HEAD、本文 digest、Stage 1 accepted commit/evidence 和当前
recorded-data/query/optimizer 实现。若 Stage 1 未通过，不得用 Dataset 层掩盖 publication
缺口。

## 本次精化输入（2026-08-30）

- 输入 HEAD/Stage 1 accepted commit：
  `f74b1a46644925064be3d8fa310ff9b5d2ef4def`，分支 `main`，worktree/staged diff 均为空；
  post-commit `fetch origin main` 后 behind 0 / ahead 3，因未达到 ahead >= 5 未 push。
- 本文 pre-refinement SHA-256：
  `B103F453BC2D658B1A7A5DAAC9EBC59866100DD5F68170EC7B5AE31BD633FD67`；overall plan
  SHA-256：`510E587EE7686DA3CE94F62F1ECCCDA893379714B0175020536B45810C3238FB`。
- 接受基线是 installed yadof `0.4.2`，import origin 为外层
  `.venv/Lib/site-packages/yadof/__init__.py`；Stage 1 full suite 为
  `388 passed in 81.06s`。Stage 1 同 digest recording harness 已证明 5/5 的 100 rows 均恰好
  commit、7 segments、commit-to-cost median 为正，且 committed-owned queue 有界。
- Stage 1 fast smoke `40/40/40` 和 measured `2000/2000/2000` 均 collected/valid；本阶段继续
  使用 strategy source SHA-256
  `08E4BE42C4E4A8D377866BF8BC21765A0B776A27C32823290F97210FE086CBA7` 的同一完整显式
  NSGA-III + GPSAF + PCA/SVD settings，GPSAF `gamma=0.5` 不变。

## 精化时确认的当前实现事实

- `segment_store.SegmentReference.candidate_id` 已是 catalog、duplicate isolation 与 session
  `_rows` 的真实稳定 evidence key；durable record 本身也包含该值。不能把 `job_name`、physical/
  normalized variables 或 catalog position 提升为替代 identity。
- durable `query.get_historical_results()` 与 live `CampaignSession.historical_results()` 分别返回
  `(job_name, normalized, costs)` tuple，丢掉 candidate identity、失败原因和 interpretation
  fingerprint。`optimize.HistoryRecord` 同样只有 `job_name/x/costs`。
- `get_surrogate_training_data()` 当前先按 job name 构造多个 dict 后再重组 aligned arrays；这对
  duplicate name/transform 不稳，但 surrogate fit public migration 属于 Stage 4。本阶段只让其
  compatibility adapter 在内部使用 identity join，仍返回原 dict shape。
- durable catalog discovery 已能冻结 finalized segment names、逐 candidate 隔离坏 manifest、
  逐 batch lazy decode rawData，并返回 typed diagnostics；无需 DataFrame、数据库或新 persistence。
- Stage 1 live session 已分离 evidence 与 transient interpretation state，并对相同 fingerprint
  缓存成功/失败解释。本阶段应把该缓存作为 CostTable 构造 hint，而不是写回 segment。

## 冻结 public API 与 value types

新增 `yadof.recorded_data.dataset`，并从 `yadof.recorded_data` 导出下列轻量 public surface：

- `EvidenceState`：`pending`、`committed`、`failed`、`derived`；
- `InterpretationStatus`：`succeeded`、`failed`、`not_applicable`、`missing`；
- immutable `EvidenceLineage`、`RawDataHandle`、`EvidenceRow`、`EvidenceDataset`；
- immutable `CostRow`、`CostTable`、`EvidenceCostRow`；
- `get_evidence_dataset(workspace)`、`get_cost_table(workspace)`、
  `calculate_cost_table(dataset, snapshot)` 与 `derive_evidence_row(...)`。

`CampaignSession` 增加 `evidence_dataset()` 与 `cost_table(snapshot=None)`。后者可以把同一
fingerprint 的 transient result 当 hint，并把本次重解释结果更新回 session cache；它仍不修改
durable segment。现有 `get_historical_results()`、`calculate_costs()`、surrogate-training dict 和
`CampaignSession.historical_results()` 保持 compatibility shape，但内部改由 Dataset/CostTable
identity join 产生。

`EvidenceDataset` 精确提供：

- ordered immutable `rows`、`parameter_names`、catalog/session diagnostics 和 source boundary；
- `select(row_ids)` 以显式 identity 重排/子集，重复或未知 ID fail-fast；
- `where(predicate)` stable filter、`copy()` immutable shallow copy；
- `join_costs(table)` 以 `row_id` 校验/连接并返回 dataset order 的 `EvidenceCostRow`，不使用位置；
- 原始 row 的 `row_id == evidence_id == candidate_id`，`design_key` 由 parameter names 与有序
  physical variable values 的 canonical representation 生成。duplicate design 共享 design key，
  但 candidate/evidence/row identity 永远不同。

`derive_evidence_row(parent, operation, ordinal, rawdata_source, parameters=...)` 只处理本阶段明确的
rawData transform：继承 parent physical design/evidence root，创建一条 `EvidenceLineage`，并由
parent row ID、JSON-safe operation parameters、显式 ordinal 与 transformed rawData semantic
content digest 生成 deterministic derived `row_id`。同一 transform 的多 row output 必须传不同
ordinal。变量语义变换、跨多个 evidence parent 的科学 join 或历史等价性推断不在本阶段；需要时
命中暂停边界。

`CostTable` 精确提供 objective names/width、objective schema ID、task interpretation fingerprint、
ordered `CostRow`、typed `statuses`/`valid_mask`、identity-based `select()` 和
`to_optimizer_costs()`。每个 `CostRow.interpretation_id` 绑定 row/evidence identity、task
interpretation fingerprint 与 objective schema。只有 `succeeded` row 拥有有限、正确宽度
`costs`；其他状态保留 `None` 和 bounded diagnostics。`to_optimizer_costs()` 是唯一把非成功 row
映射为正确宽度 `inf` 的 table boundary；history/search 默认只消费 successful committed original
rows。

`optimize.HistoryRecord` 在不破坏现有 `job_name/x/costs` 构造的前提下增加默认字段
`candidate_id`、`row_id`、`design_key`、`interpretation_id`。`history_records()` 先取得 session
Dataset/CostTable，再以 identity join 生成 records；single/multi-objective width 由 CostTable
schema 而不是第一个未检查 tuple 推断。

## 冻结 ownership、visibility 与成本边界

- durable dataset 永远只保存 `SegmentReference`-backed lazy handle；filter/copy/reorder/join 不解码
  rawData。`RawDataHandle.load()` 每次返回新 owned arrays，不缓存，调用者释放返回值即可释放本次
  decode；cost calculation 一次最多 materialize 一个 row。
- live dataset 是调用时 immutable snapshot。它显式包含 accepted pending/failed rows，但 pending
  row 没有可读 handle，不能进入 next-generation history。committed live row 也使用已发布
  `SegmentReference`，不延长 Stage 1 envelope ownership。重新取得 view 后，committed original rows
  与 durable catalog 的 schema/identity/provenance 同义。
- derived row 由调用者显式 materialize，框架在 `derive_evidence_row()` 内取得一个 owned copy 并做
  O(payload bytes) semantic hash；该 copy 的内存生命周期等于 derived dataset/row。普通 view 操作
  不重新 hash。derived/predicted row 没有 recorder API、state 为 `derived`，不得进入 durable
  history 或 optimizer historical adapter。
- catalog/candidate/rawData corruption 在 dataset diagnostics 中隔离；对应 unreadable row 不伪造
  cost。execution failure 为 `not_applicable`，未 committed/无 rawData 为 `missing`，callback
  exception/width/non-finite 为 `failed`。error message 截断到固定上限，原异常不跨 row 传播。
- `get_cost_table(workspace)` 为 convenience：创建一个 coherent temporary generation snapshot，
  使用一个 frozen interpreter 后必定关闭 snapshot。显式 campaign path 必须传已有 snapshot，避免
  current source hot reload 混入同一 table。

## 精确源码、测试与 migration delta

预计直接修改：

- 新增 `src/yadof/recorded_data/dataset.py`；更新 recorded-data public API/query/session/export；
- `optimize/strategy.py` 的 HistoryRecord/adapter 先消费新 view；不迁移 generation loop、surrogate
  fit implementation 或 strategy composition；
- package allowlist、direct Dataset/CostTable tests、现有 recording/query/optimization/surrogate
  compatibility tests；
- current architecture、recorded_data/optimize/tests module blueprint、dataset/query/session/strategy
  file blueprint、terminology、optimization/package/cost user docs 与 change record。

direct tests 必须证明：

- duplicate physical design 有相同 design key、不同 candidate/row identity；filter/copy/reorder 与
  CostTable join 即使顺序不同也按 ID 对齐；
- multi-row derived transform 的 lineage/content/ordinal identity deterministic，改变 content 或
  ordinal 会改变 row ID，且 catalog/segment count 完全不变；
- success、callback exception、wrong width、`NaN`、`+/-inf`、execution failure、pending/missing
  rawData 都得到精确 typed status/mask，只有 optimizer conversion 产生 `inf`；
- cost source hot reload 后 task fingerprint/interpretation IDs/costs 更新，旧 evidence bytes/identity
  不变；
- live pending row 只在 session view 可见，commit 后新 live view 与 new-session durable view 等价；
- corrupt segment 与 corrupt candidate 各自隔离，valid sibling 保留；lazy view operations 的 decode
  count 为零，CostTable 逐 row decode、无全表 rawData retention；
- compatibility queries、current optimizer history、single/multi objective 和 surrogate-training dict
  parity；predicted/transformed rows不进入 recorder。

最终按 installed-package workflow build/reinstall/import-origin，运行 focused tests 与完整 pytest。
fast benchmark 使用 fresh Stage 2 smoke `20 x 2` 与唯一 measured `100 x 20` workspace；两者 strategy
source digest 必须继续为 `08E4BE42…6CBA7`，除 budget 外 policy 相同，measured 必须
collected/valid、attempted/completed/finite `2000/2000/2000`。它仍是结构/回归 gate，不以 HV
improvement 为结论。

## 已知 pre-change 问题

- recorder 已有稳定 `candidate_id` evidence identity，但 optimizer 的
  `HistoryRecord(job_name, x, costs)` 与 surrogate 的独立 session training read 仍主要靠位置
  对齐。
- design variables 可以重复；normalized/physical design key 不是 evidence identity。
  Python filter/copy/reorder 后，数组位置也不能承担 identity。
- rawData evidence、execution status 与当前 task 下的 interpretation status 生命周期不同。
  将所有 invalid row 过早变成 `inf` 会丢失原因和以后重新解释的能力。
- live session 与 durable query 应产生同义 view；新 API 不能成为第二套 persistent history 或
  把 predicted/transformed data 回写 recorder。

## 必须保持的验收 invariant

上述冻结的轻量、workspace-explicit EvidenceDataset/CostTable API 必须保留下列语义：

- evidence row identity 复用现有 durable `candidate_id` 或对它的窄 public value，而不是重新
  发明不兼容 ID；
- design key 只用于 duplicate/equivalence policy，与 sample identity 分离；
- filter、copy、join、reorder 或 user transform 后的 row 保留 parent identity/lineage；若一个
  transform 产生多 row，必须有确定的 derived-row identity，不能依赖新数组位置；
- CostTable 的 interpretation identity 至少绑定 evidence identity、task interpretation
  fingerprint 和 objective schema/width；
- execution/evidence/interpretation status 与 bounded diagnostics 分列；invalid/missing cost 在
  table 内保持 typed mask/status，只有 optimizer adapter 需要固定 shape 时才映射为 `inf`；
- live campaign 与 durable catalog 在相同 finalized/accepted boundary 上提供同一 schema 和
  identity；差异只能来自明确的 publication state；
- view 可只读、owned 或 lazy，但 ownership、rawData decode 生命周期和内存预算必须明确；
- 任何 materialized transformed arrays 都是派生数据，不成为 durable truth。

`calculate_cost(dataset, snapshot)` 一类示意接口应复用 Stage 1 的 frozen interpreter 合同。
重算生成新的 interpretation view，不修改 evidence segment，也不把历史旧 cost 持久化为权威。

## 范围边界

- 新增/整理 public dataset 与 cost-table value types、查询/构造 API 和 optimizer adapter；
- 让 current history/search 先消费新 view，但不在本阶段迁移 surrogate fit 或 generation loop；
- 复用 tolerant segment reader、campaign hot catalog、task snapshot 与 stable identity；
- 明确 rawData lazy decode、copy-on-transform、metadata 暴露和 memory release；
- 同步 tests、architecture、recorded_data/optimize blueprints、terminology、user docs 与 change
  record。

不改变 recorded-data ZIP layout，不实现 DataFrame dependency，不建立数据库，不接受 prediction
作为 evidence，不推断任意 Python transform 的科学等价性。GPSAF `gamma` 保持现状。

## 已冻结的实现选择

Stage 1 evidence 已使下列选择可直接冻结，无需普通用户确认：

- row/table/lineage/handle 采用 frozen slots dataclass 与 typed string enum；
- durable/live committed payload 始终 lazy、每次 load 返回 owned copy；derived transform 明确
  materialize 一个 owned payload，不设置隐式 eager threshold；
- failed execution、pending、missing rawData row 进入同一 dataset 并保留状态；history consumer
  默认只选 committed original + successful interpretation；
- lineage 是 parent row ID、operation、JSON-safe parameters、ordinal 与 content digest 的 immutable
  表达；
- live accepted-but-not-yet-durable row 在 session snapshot 中可见并标为 pending，但无 read handle、
  不进入下一 generation durable history；
- large-field transform 只在显式 `derive_evidence_row()` 做一次 O(payload bytes) ownership copy/hash，
  普通 view 操作不 materialize、不 hash。

若选择会创建第二套持久 truth、改变 objective/parameter width 或要求用户科学判断历史是否
可用，则命中 overall plan 暂停边界。

## 验证

至少覆盖：

- candidate/design/derived-row identity 不混淆，duplicate designs 仍有不同 evidence rows；
- stable filter/copy/reorder/join 和多 row transform，不用位置配对；
- callback exception、width、non-finite、missing rawData 的 typed status/mask；
- cost 修复后新 interpretation identity 与重算结果，旧 evidence 不变；
- live/durable 等价、publication-state 差异、new-session recovery；
- corrupt candidate/segment 隔离、lazy decode ownership 和 bounded memory；
- optimizer adapter 只在边界生成正确宽度 `inf`；
- transformed/predicted data recorder non-entry；
- current history consumers parity，single/multi-objective 和 task fingerprint hot reload。

按开发指南完成 wheel、force reinstall、import-origin、focused/full pytest；local/distributed
只做相称的 query/identity contract tests。再按 overall policy 运行同源 smoke 与唯一 fast
100 x 20 measured benchmark，要求 collected/valid/attempted 2000，不以 HV improvement 为 gate。

## 本次执行结果（2026-08-31）

- 新增 immutable `EvidenceDataset`/`CostTable` public surface、lazy
  `RawDataHandle`、typed evidence/interpretation states、deterministic derived
  lineage，以及 durable/live construction 和 identity join；recorded-data ZIP
  layout、generation loop、surrogate fit 与 search composition 未改变。
- compatibility query/surrogate-training shapes 保持不变但内部按 row ID 对齐；
  `HistoryRecord` 增加带默认值的 candidate/row/design/interpretation identity，history 只接收
  successful committed original rows。
- direct tests `12/12`，recording/session review `37/37`，focused compatibility
  `76/76`；最终 force-installed yadof `0.4.2` full suite 为
  `400 passed in 81.00s`，import origin 为外层 `.venv/Lib/site-packages/yadof/__init__.py`。
- fresh smoke `temp/20260831_002328-stage2-benchmark-smoke` 为 collected/valid
  `40/40/40`；唯一 fresh measured
  `temp/20260831_002514-stage2-benchmark-measured` 为 collected/valid
  `2000/2000/2000`，20 generation records、generation zero `100/100`、contracts match、zero
  issues，runtime `539.1970091 s`。descriptive final HV `0.19862125778923248` 不是 gate。
- 两个 benchmark 的 strategy source SHA-256 均为
  `08E4BE42C4E4A8D377866BF8BC21765A0B776A27C32823290F97210FE086CBA7`；identity 与
  diagnostics 均保留 GPSAF `gamma=0.5`。
- reliable-recording bounded check 证明 pending/committed visibility、durable-reference ownership、
  corruption isolation 与 recorder non-entry 一致；redundancy check 删除 session-local raw-variable/
  cost replay duplication。release-marker/component-configuration checks 未命中，四份 recurring auto
  TODO 均保持 active。进入阶段时 worktree clean，没有 pre-existing user changes。
- architecture、recorded_data/optimize/tests blueprints、dataset/query/session/strategy file
  blueprints、terminology、optimization/package/cost user docs 已同步；change record 为
  `dev_doc/change_records/20260831_003835_add-identity-preserving-evidence-cost-views.md`。

## 完成、归档与自动续跑

精确 TODO 中冻结的 API、tests、documentation 和 benchmark 已全部通过，identity/ownership/
interpretation boundaries 有直接 evidence，automatic TODO check 与 change record 已完成。形成
verified commit 并按仓库规则 fetch/push 判断后，自动进入
[Stage 3 Evaluation Handle](../../toDo/20260830_174609_explicit-optimization-stage-3-evaluation-handle.md)。
