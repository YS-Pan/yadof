# Frozen task baselines

These are current-format, runtime-clean task inputs selected explicitly by
`benchmark.toml`:

| Case | Provider | Task | Baseline ID | Task fingerprint | Files | Objectives |
|---|---|---|---|---|---:|---:|
| SAW | `ngspice` | `saw-ladder` | `saw-ladder-b736a99a7dc1` | `b736a99a7dc188cae5f74bceb772ef06005f2baead13864fc0be194db2c21948` | 9 | 5 |
| Chrono | `chrono` | `trebuchet` | `trebuchet-20167c28925b` | `20167c28925bd9ff0e0476cb305e1f258a57dfd9098ea6e5afc44b61cee0b306` | 14 | 4 |
| test_com | `test-com` | `synthetic-antenna` | `synthetic-antenna-29b314e9304e` | `29b314e9304e8ed8b976ac10299a2da9421fe255fa3c60e4e90346e8eb3545ff` | 8 | 4 |

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
variables.

The selected Chrono task preserves the parameter and objective counts while adding
Bullet NSC contact between the ground and the arm, hanger/counterweight assembly,
and ball; initially intersecting mechanisms are rejected. The former bundled
release and stress arrays are now 16 semantic rawData fields: nine scalars and
seven independent 513-sample curves. Its workspace also carries the renderer and
a common `postprocess.py` entry point that writes the selected replay video,
poster, trajectory, and diagnostics into the same per-attempt directory as
`benchmark-cost.png`.

`trebuchet-20167c28925b` derives from `trebuchet-ac34a09c5fb9` and changes only
the frozen usage documentation for this unified output contract. At explicit
maintainer request, both that predecessor and the earlier
`trebuchet-025b5ea5fca1` directory were removed so the checkout retains only the
current Trebuchet workspace. Historical run specifications still identify those
baselines, but they cannot be resumed or reconstructed from this checkout.

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

At explicit maintainer request, the superseded SAW baseline
`saw-ladder-9c5f3020778d` and test_com baselines
`synthetic-antenna-aa89d46f3d9a`, `synthetic-antenna-c7b0133b3a4e`, and
`synthetic-antenna-4dc66b0f60bf` were removed. Together with the Chrono cleanup
above, every provider now retains only its selected workspace. Historical run
specifications and verification documents still identify removed baselines, but
such runs cannot be resumed or reconstructed from this checkout.

The hidden `.staging/` and `.assembled/` directories at the benchmark root are
Phase-0 reconstruction/validation evidence, not runner inputs. In particular,
`.assembled/` retains the one disposable smoke record per case that proved the
frozen task transfer; the final baseline workspaces remain runtime-clean.
