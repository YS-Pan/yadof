# Frozen task baselines

These are current-format, runtime-clean task inputs selected explicitly by
`benchmark.toml`:

| Case | Provider | Task | Baseline ID | Task fingerprint | Files | Objectives |
|---|---|---|---|---|---:|---:|
| SAW | `ngspice` | `saw-ladder` | `saw-ladder-3d2025426a97` | `3d2025426a976aa03cf720757bd37314004db8d29b5a922dcfc36c2d0d753c10` | 9 | 5 |
| Chrono | `chrono` | `trebuchet` | `trebuchet-462d1201a592` | `462d1201a592343980c17c9e6e641daaaa8d78e4029f02aee361527996f529fe` | 14 | 4 |
| test_com | `test-com` | `synthetic-antenna` | `synthetic-antenna-0b64f13b9f0b` | `0b64f13b9f0b209f5dd23ce4d7f841119580f47885536db2184cb661d6c088f8` | 8 | 4 |

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

The selected SAW and test_com refreshes preserve their predecessor task and
rawData contracts while adding the common `postprocess.py` interface. The SAW
plot follows the response visualization used by the 20260807 SAW task; the
test_com plot summarizes the three switch states, gain, axial ratio, and design
variables. Their current postprocessors add the runner-supplied prefix to every
artifact when requested. The current runner instead supplies an empty prefix and a
fresh attempt-specific result directory, so each benchmark result is isolated.

The selected Chrono task preserves the parameter and objective counts while adding
Bullet NSC contact between the ground and the arm, hanger/counterweight assembly,
and ball; initially intersecting mechanisms are rejected. The former bundled
release and stress arrays are now 16 semantic rawData fields: nine scalars and
seven independent 513-sample curves. Its workspace also carries the renderer and
a common `postprocess.py` entry point that writes the selected replay video,
poster, trajectory, diagnostics, selected-job ZIP, and manifest as direct files in
the supplied result directory. The current runner gives that
postprocessor a separate attempt directory and writes cost views to the shared
`visualizations/viewcost/` directory. Animation scratch is temporary and does not
create a nested result directory.

`trebuchet-42e80c54ebb5` derives from `trebuchet-20167c28925b`; its scientific
task is unchanged, while its visualization output is now entirely flat.
`trebuchet-462d1201a592` in turn preserves that complete scientific and
visualization input while refreshing only the copied package Chrono adapter. Its
Windows child process uses a candidate-unique short junction targeting the original
physical scratch, so run and workspace depth no longer consume the child
current-directory limit.

The superseded `synthetic-antenna-aa89d46f3d9a` input's objective extraction
windows and physical anchors compressed three costs near a soft-cost tail and
produced degenerate cost/HV histories. The first replacement,
`synthetic-antenna-c7b0133b3a4e`, corrected the measurements but left a smooth
problem that pure NSGA-III nearly solved within 2,000 evaluations.

The selected replacement preserves the same parameter and rawData contracts. Its
state-aligned physical measurements encode a four-objective Pareto tradeoff plus a
non-separable, multimodal loss involving all 20 variables. Three pure NSGA-III
runs continued making material progress through 10,000 evaluations; the detailed
acceptance evidence is in
[`../verification/20260824-test-com-difficulty-recalibration.md`](../verification/20260824-test-com-difficulty-recalibration.md).

Some earlier superseded SAW, Chrono, and test_com baselines were removed after
validation at explicit maintainer request. Baseline removal remains exceptional:
the former `trebuchet-42e80c54ebb5` identity is retained because immutable
benchmark runs diagnose the Windows path failure against that exact input. A
historical run whose baseline was removed cannot be resumed or reconstructed from
this checkout without restoring the relevant Git history.

The hidden `.staging/` and `.assembled/` directories at the benchmark root are
Phase-0 reconstruction/validation evidence, not runner inputs. In particular,
`.assembled/` retains the one disposable smoke record per case that proved the
frozen task transfer; the final baseline workspaces remain runtime-clean.
