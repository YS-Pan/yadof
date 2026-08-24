# Frozen task baselines

These are current-format, runtime-clean task inputs selected explicitly by
`benchmark.toml`:

| Case | Provider | Task | Baseline ID | Task fingerprint | Files | Objectives |
|---|---|---|---|---|---:|---:|
| SAW | `ngspice` | `saw-ladder` | `saw-ladder-9c5f3020778d` | `9c5f3020778d9ed67cf9571745b8119c381a116559e5dcd8dd8b1792c4de9372` | 8 | 5 |
| Chrono | `chrono` | `trebuchet` | `trebuchet-025b5ea5fca1` | `025b5ea5fca1468bbb2acc4a1e4aeffb7554e244181d6d6f309c25518ec991a1` | 10 | 4 |
| test_com | `test-com` | `synthetic-antenna` | `synthetic-antenna-4dc66b0f60bf` | `4dc66b0f60bf018472f992a07fa33e6815a2bf6eb7d295e2bccc848820da226d` | 7 | 4 |

The directory contract is:

```text
baselines/<provider>/<task>-<12-hex-task-fingerprint-prefix>/
  baseline.json
  workspace/
```

`provider` names the simulator or copied adapter used to execute the task, while
`task` names the optimization problem. Both are lowercase kebab-case identifiers
that start with a letter.
The benchmark case ID is a separate matrix label and need not equal either name.

Each baseline was initialized by installed yadof 0.4.0, checked with zero warnings,
and smoke-tested in a separate assembly workspace. The final baseline itself has
zero measured records and zero compatible checkpoints. Its `baseline.json` stores
provenance, smoke costs, objective count, and rawData shape evidence.

Immediately before the benchmark's first public repository import, machine- and
private-workspace names in the provenance display fields were redacted once. The
workspace inputs, baseline IDs, task fingerprints, validation evidence, and
scientific content did not change. The public forms below are immutable.

Never overwrite a baseline ID. Refreshing a task means creating a new task plus
fingerprint-prefix directory under the applicable provider, validating it, and
changing the explicit TOML selection.

The superseded `synthetic-antenna-aa89d46f3d9a` input remains tracked as immutable
historical provenance. Its objective extraction windows and physical anchors
compressed three costs near a soft-cost tail and produced degenerate cost/HV
histories. The first replacement, `synthetic-antenna-c7b0133b3a4e`, corrected the
measurements but left a smooth problem that pure NSGA-III nearly solved within
2,000 evaluations. It also remains immutable and unselected.

The selected replacement preserves the same parameter and rawData contracts. Its
state-aligned physical measurements encode a four-objective Pareto tradeoff plus a
non-separable, multimodal loss involving all 20 variables. Three pure NSGA-III
runs continued making material progress through 10,000 evaluations; the detailed
acceptance evidence is in
[`../verification/20260824-test-com-difficulty-recalibration.md`](../verification/20260824-test-com-difficulty-recalibration.md).

The hidden `.staging/` and `.assembled/` directories at the benchmark root are
Phase-0 reconstruction/validation evidence, not runner inputs. In particular,
`.assembled/` retains the one disposable smoke record per case that proved the
frozen task transfer; the final baseline workspaces remain runtime-clean.
