# File blueprint: src/yadof/optimize/gpsaf/coverage.py

## Intent

- Select an optional GPSAF batch by deterministic predicted hypervolume coverage
  relative to the supplied real history, using the existing finite candidate pool.

## Contract

- Inputs are aligned current-cost means and validity already checked by the
  search primitives, finite real history, a batch count and original infill order.
- Lazily delegate nondominated sorting and hypervolume numerics to pymoo with the
  fixed all-one reference of normalized minimization costs.
- Use diminishing marginal coverage bounds for lazy greedy selection; recompute
  a stale bound before accepting a candidate. Pool order breaks exact gain ties.
- Stop positive-gain selection at `1e-12`, then use valid original infill choices,
  remaining valid pool order and finally invalid rows to fill the requested count.
  A finite cost of one is valid and can be retained by fallback.
- Return candidate indices and bounded gain/reference diagnostics. No surrogate,
  simulator, benchmark, rawData, real evaluator or recorder is accessed.
- Predicted candidates temporarily extend only the private coverage front. They
  never enter real history or the restored optimizer. This policy uses means,
  without uncertainty integration or claims about learned-model performance.
