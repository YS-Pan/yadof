# Gate 0 v2：quality/regime 抗噪追加预注册

此目录是 `20260827-new-surrogate-qnehvi` Gate 0 v1 的不可变追加版本。v1 的 schema
inventory、2800-design split、seed registry、baseline/task/source hash 和 zero-observation-noise
边界继续有效；本版本不覆盖或重解释 v1 文件。

v2 在任何未来 offline test/formal result 被读取前，新增以下冻结边界：

- 通用、JSON-safe、进入 semantic identity/checkpoint 的 quality/regime protocol；
- task-owned Chrono diagnostic rules，core 不含 Chrono 字段名、cost threshold 或任意 callback；
- design × field 稳健聚合、shared-latent 隔离、gated field-private residual 与未校准
  applicability head；
- clean-target 高频泄漏、predicted/real roughness inflation、classifier AUPRC/概率校准、
  smooth/chatter/boundary 分层指标；
- `无门控 / 仅稳健加权 / shared-latent 隔离 / gated residual` 四臂消融。

`noise_audit_evidence.json` 只是只读动机证据，不是 validation/threshold pilot。所有数值验收
门槛仍为 `null`，因此本版本保持 `formal_test_ready=false`，coordinate readout 也保持 blocked，
直到 full-grid representation 与合法阈值封存 gate 通过。

只读验证命令：

```powershell
& ".\.venv\Scripts\python.exe" `
  ".\20260822 yadof\benchmark_automation\preregistrations\20260827-new-surrogate-qnehvi-v2\validate.py" `
  --pretty
```

validator 会先执行 v1 validator，再检查 v2 完整性、policy/metrics/ablations、全部 threshold
仍为 null，以及没有 formal dataset/test access 声明；不会启动 simulator。
