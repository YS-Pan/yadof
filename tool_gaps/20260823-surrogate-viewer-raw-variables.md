# yadof-tools gap: surrogate summary/audit cannot parse mapped raw variables

## Resolution

Resolved on 2026-08-23 by yadof commit
`0665541155009787c938cbf15df177e8c9488fb8`, which was built into the 0.4.0 wheel,
force-reinstalled into the development environment, fully tested (`274 passed`), and pushed
to `origin/main`.

`SurrogateWorkspace._load_real_results()` now accepts the persisted name-to-value
mapping and reconstructs the tuple in the task's declared parameter order. It
isolates missing, malformed, and non-mapping rows. This fixes both the visible
`float("x0")` failure and the latent lexicographic-order error for names such as
`x1`, `x10`, and `x2`.

The old canary workspace was rechecked read-only: summary and cost/rawData audits
all exited 0 and returned finite schema-versioned JSON. New runs
`20260823T060003Z-post-viewer-fix-9e43d5c3327b` and
`20260823T060119Z-post-viewer-fix-ba5ad9cc3103` then satisfied the complete public
summary/audit structural contract.

## Observed contract failure

Installed yadof version: `0.4.0`.

The corrected structural canary completed three GPSAF generations. Public
generation metadata reports sources `gpsaf_random`, `gpsaf_offspring`, and
`gpsaf_surrogate`; generation 2 has `surrogate_used=true`. Public surrogate
training metadata reports completed conditional-INR checkpoints. Nevertheless,
both supported JSON inspection commands exit 1:

```powershell
python -m yadof view surrogate summary `
  --workspace <gpsaf-workspace> --format json

python -m yadof view surrogate audit `
  --workspace <gpsaf-workspace> --sample-percent 10 --random-seed 20260823 `
  --metric both --quantity all-costs --format json
```

Observed stderr:

```text
yadof: error: could not create surrogate summary report: could not convert string to float: 'x0'
```

The audit fails through the same workspace-history loading path. Append-only
command metadata and logs are under run
`20260823T052537Z-canary-third-gen-8f3b38ad1fa4`, collection `collect-0001`.

## Narrow root cause

The public recorded-data contract returns `record["raw_variables"]` as a mapping
from parameter name (for example `x0`) to value. The installed surrogate viewer's
workspace loader iterates that mapping directly and applies `float()` to its keys,
so it attempts `float("x0")` before normalization.

## Implemented reusable yadof-tools task

The repair was implemented in the yadof source checkout, not in this benchmark:

1. It accepts the public mapped `raw_variables` representation and reconstructs values
   in the task's declared parameter order.
2. It accepts only the current persisted mapping contract and isolates invalid rows.
3. Regression coverage records mapped payloads, publishes a compatible
   conditional-INR checkpoint, and verifies both `summary --format
   json` and cost/rawData `audit --format json` produce finite schema-versioned JSON.
4. The yadof build, wheel force-reinstall, import-origin, full-test, old-canary, and
   benchmark structural acceptance workflows all passed.

The benchmark deliberately does not monkey-patch the installed package, read model
files privately, or rewrite measured records to bypass this gap.
