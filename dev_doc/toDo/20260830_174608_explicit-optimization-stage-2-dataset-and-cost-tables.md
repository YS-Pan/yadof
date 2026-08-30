# 显式 optimization 重构阶段 2：稳定身份的 EvidenceDataset 与 CostTable

## 状态、授权与进入条件

本文是已获得单一 Goal 后续精化/执行授权的预测性手动 TODO，不是当前 API 规格。Stage 1
完成并归档后，执行者必须根据其 committed receipt、状态分类、replay、microbenchmark 和
100 x 20 evidence 在本文内冻结精确 API、测试与 migration delta；不需要新的用户“继续”
指示，也不得与 Stage 1 源码实施并行。

进入本阶段时记录当前 HEAD、本文 digest、Stage 1 accepted commit/evidence 和当前
recorded-data/query/optimizer 实现。若 Stage 1 未通过，不得用 Dataset 层掩盖 publication
缺口。

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

## 预期精确结果

建立轻量、workspace-explicit 的 EvidenceDataset/CostTable 能力；名称在阶段精化时可以调整，
但必须保留下列语义：

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

## 本阶段预计范围

- 新增/整理 public dataset 与 cost-table value types、查询/构造 API 和 optimizer adapter；
- 让 current history/search 先消费新 view，但不在本阶段迁移 surrogate fit 或 generation loop；
- 复用 tolerant segment reader、campaign hot catalog、task snapshot 与 stable identity；
- 明确 rawData lazy decode、copy-on-transform、metadata 暴露和 memory release；
- 同步 tests、architecture、recorded_data/optimize blueprints、terminology、user docs 与 change
  record。

不改变 recorded-data ZIP layout，不实现 DataFrame dependency，不建立数据库，不接受 prediction
作为 evidence，不推断任意 Python transform 的科学等价性。GPSAF `gamma` 保持现状。

## 精化时必须解决的实现选择

执行者在当时 evidence 下决定并记录，不需要普通用户确认：

- public 名称以及 row/table 是否采用 immutable dataclass、protocol 或其他轻量结构；
- rawData eager/lazy threshold、borrowed view 与 owned copy 的释放规则；
- failed execution/no-rawData row 是否进入同一 dataset，以及 consumer 默认 filter；
- derived-row lineage 的最小 JSON-safe 表达；
- live accepted-but-not-yet-durable rows 是否可见。若可见，必须显式标注 publication state，且
  不能被下一 generation 当作 durable history；
- large-field transform 的 materialization/hash 成本边界。

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

## 完成、归档与自动续跑

精确 TODO 中冻结的 API、tests、documentation 和 benchmark 全部通过，identity/ownership/
interpretation boundaries 有直接 evidence，automatic TODO check、change record、commit 与
fetch/push 判断完成后，将本文移入 `dev_doc/obsolete/todo/`，更新 overall ledger，并自动进入
[Stage 3 Evaluation Handle](20260830_174609_explicit-optimization-stage-3-evaluation-handle.md)。
