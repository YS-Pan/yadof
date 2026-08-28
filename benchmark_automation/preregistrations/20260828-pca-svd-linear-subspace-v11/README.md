# PCA/SVD linear-subspace Gate 0 v11

This preregistration freezes the first package-owned PCA/truncated-SVD codec,
deterministic parameter-to-coefficient ridge predictor, and separate benchmark arm
identities before implementation tests or new measured-case evidence are opened.

The authoritative contract is `linear_subspace_plan.json`. It deliberately keeps
four conclusions separate:

- `pca-reconstruction-oracle` and `svd-reconstruction-oracle` may encode known
  validation rawData and are always `diagnostic_only=true`;
- `pca-ridge-rawdata-surrogate` and `svd-ridge-rawdata-surrogate` receive only
  normalized candidate parameters after fitting real training evidence;
- only a separately budgeted `GPSAF + pca_svd(...)` optimization cell could make
  an optimization-quality observation;
- no arm in this plan supplies posterior calibration or exploitation readiness.

The public factory default uses rank 16, while every v11 comparison arm explicitly
uses rank 32 so historical parity and oracle/deployable gaps share one representation
budget. Rank is rejected below one and otherwise clamped per field. The package
does not perform automatic rank or ridge-alpha search.

`implementation_amendment.json` discloses the explicit `constant_atol=1e-12`
factory/default identity that implements the already-frozen near-constant policy
but was omitted from the base plan's defaults object. It was sealed before any
measured case access and changes no arm, rank, alpha, solver, partition, or gate.

`solver_resource_audit.json` records the bounded synthetic 1000/2000 by 26,645
resource cells sealed by the plan. NumPy exact SVD completed but violated the
predeclared 2x wall-time rule at 2,000 designs; Torch low-rank is therefore the
selected first backend. The receipt contains no case rawData or scientific result.

The source-checkout runner added with the implementation accepts only an explicit
design-level partition manifest and public recorded-data evidence. Its `plan` is
no-write and its `preflight` validates without fitting. A measured `run` remains
blocked until legal case workspaces, sealed thresholds, and separate execution
authority are supplied. No v4/v5 plan, receipt, hash, or result is modified.

Use `partition.template.json` to create a separate sealed partition manifest, then
invoke `python benchmark_automation/pca_svd_validation.py plan` or
`preflight --partition-manifest ...`. The `run` command additionally requires
`--allow-measured-run`, while the manifest independently carries explicit execution
authority and sealed thresholds; the CLI flag is not a substitute for either.
