# Frozen task baselines

These are current-format, runtime-clean task inputs selected explicitly by
`benchmark.toml`:

| Case | Baseline ID | Task fingerprint | Files | Objectives |
|---|---|---|---:|---:|
| SAW | `20260823-9c5f3020778d` | `9c5f3020778d9ed67cf9571745b8119c381a116559e5dcd8dd8b1792c4de9372` | 8 | 5 |
| Chrono | `20260823-025b5ea5fca1` | `025b5ea5fca1468bbb2acc4a1e4aeffb7554e244181d6d6f309c25518ec991a1` | 10 | 4 |
| test_com | `20260823-aa89d46f3d9a` | `aa89d46f3d9adb27d72208e022775bc1ef1d43bea51a67269621a91e966ef162` | 7 | 4 |

Each baseline was initialized by installed yadof 0.4.0, checked with zero warnings,
and smoke-tested in a separate assembly workspace. The final baseline itself has
zero measured records and zero compatible checkpoints. Its `baseline.json` stores
provenance, smoke costs, objective count, and rawData shape evidence.

Immediately before the benchmark's first public repository import, machine- and
private-workspace names in the provenance display fields were redacted once. The
workspace inputs, baseline IDs, task fingerprints, validation evidence, and
scientific content did not change. The public forms below are immutable.

Never overwrite a baseline ID. Refreshing a task means creating a new date plus
fingerprint-prefix directory, validating it, and changing the explicit TOML
selection.

The hidden `.staging/` and `.assembled/` directories at the benchmark root are
Phase-0 reconstruction/validation evidence, not runner inputs. In particular,
`.assembled/` retains the one disposable smoke record per case that proved the
frozen task transfer; the final baseline workspaces remain runtime-clean.
