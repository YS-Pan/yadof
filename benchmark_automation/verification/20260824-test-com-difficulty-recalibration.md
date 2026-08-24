# 2026-08-24 test_com difficulty recalibration

## Scope

Baseline `synthetic-antenna-c7b0133b3a4e` fixed the original synthetic antenna
task's degenerate objective scaling, but its smooth landscape was too easy for an
optimizer benchmark: three pure NSGA-III validations already reached hypervolume
`0.8597`-`0.8833` after 2,000 real evaluations. This record validates the harder,
immutable replacement `synthetic-antenna-4dc66b0f60bf`.

All acceptance runs used installed yadof 0.4.0, fast evaluation, pure
real-evaluation NSGA-III, 200 individuals, 50 generations, and no surrogate. Each
run therefore attempted and publicly recorded 10,000 evaluations.

## Difficulty model

The replacement preserves the 20 unit-box parameters, four objectives, rawData
names and shapes, evaluator, and workflow. The task-local `test_com.py` now forms
four intermediate positions as follows:

- `x0..x2` map through the standard positive four-objective spherical direction,
  creating an explicit Pareto tradeoff rather than four simultaneously minimizable
  costs.
- `x3..x19` contribute a shared rugged loss after a cyclic non-separable mixing
  (`0.72*z + 0.24*roll(z,1) - 0.16*roll(z,4)`). A squared term gives a unique
  central optimum, while a `1-cos(4*pi*mixed)` term creates many inferior basins.
- The direction plus `3.2` times the rugged loss is encoded back into actual S11,
  beam-gain, back-lobe, and axial-ratio rawData. `calc_cost.py` still extracts
  state-aligned physical measurements; it does not read positions directly.

The fixed cost anchors correspond to intermediate positions `0.12` (goal) and
`0.92` (worst):

| Objective | Physical measurement | Goal | Worst |
|---|---|---:|---:|
| `cost_s11_resonance` | worst state resonance | -8.5 dB | -5.5 dB |
| `cost_beam_gain` | worst expected-beam gain | -1.0 dB | -5.0 dB |
| `cost_back_lobe` | worst existing back-lobe window | -23.5 dB | -20.5 dB |
| `cost_axial_ratio_at_2p44` | worst expected-beam axial ratio at 2.44 GHz | 7.0 dB | 17.0 dB |

This keeps the optimization contract physical and inspectable while making every
parameter relevant to either Pareto position or distance from the Pareto set.

## Static audit

A deterministic audit of 100,000 uniformly sampled parameter vectors produced
objective means `(0.65018, 0.65126, 0.75606, 0.86913)` and standard deviations
`(0.22068, 0.22035, 0.21076, 0.16278)`. Pairwise correlations ranged from
`-0.298` to `0.434`, so the four costs are neither flat nor duplicate signals.

On the ideal zero-rugged-loss Pareto surface, the minimum sampled average cost was
`0.28118`. The deliberate objective conflict therefore prevents the benchmark
from being solved merely by finding an individual with all four costs near zero;
none of the 30,000 acceptance rows had average cost below `0.1`.

## Full real-only validation

The cumulative public hypervolume below uses reference `(1, 1, 1, 1)`. “Final-10
gain” is the absolute and relative improvement from generation 39 through 49.

| Seed | HV at 1k | HV at 2k | HV at 4k | HV at 6k | HV at 8k | HV at 10k | Final-10 gain | Best avg at 2k | Best avg at 10k |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 104729 | 0.088241 | 0.151260 | 0.279787 | 0.369445 | 0.413929 | 0.439783 | 0.025853 (5.88%) | 0.332100 | 0.290028 |
| 130363 | 0.084306 | 0.169212 | 0.294121 | 0.373008 | 0.418279 | 0.440903 | 0.022624 (5.13%) | 0.334144 | 0.288742 |
| 155921 | 0.081198 | 0.163779 | 0.301584 | 0.370384 | 0.408858 | 0.434693 | 0.025837 (5.94%) | 0.343895 | 0.292030 |

All three seeds improved throughout the full budget. Their final-five-generation
HV gains remained `2.25%`-`2.85%`, which places the useful convergence scale near
10,000 evaluations instead of 2,000 without making the search stationary at the
target budget.

As an external difficulty reference, the historical SAW pure-real cells at 2,000
evaluations ended with HV `0.1817`, `0.1943`, and `0.3165`, and best average costs
`0.2997`, `0.2909`, and `0.2615`. The hard `test_com` cells at the same count had
HV `0.1513`, `0.1692`, and `0.1638`, and best average costs `0.3321`, `0.3341`,
and `0.3439`. The new early-budget difficulty is therefore comparable to, and
slightly harder than, the accepted SAW task.

The benchmark performance matrix intentionally remains at 100 individuals by 20
generations per arm. That common 2,000-real-evaluation budget now measures the
algorithms before pure NSGA-III convergence, where conditional-INR assistance can
be meaningful; the separate 200-by-50 acceptance runs establish the task's
convergence scale.

## Baseline acceptance

- Fingerprint: `4dc66b0f60bf018472f992a07fa33e6815a2bf6eb7d295e2bccc848820da226d`.
- `yadof check`: passed with zero warnings, 20 parameters, and 4 objectives.
- Disposable midpoint smoke costs: `(0.25742364, 0.25742364, 0.46674049, 0.76459948)`.
- All three full runs recorded 10,000/10,000 evaluations with zero failures,
  timeouts, or ignored-history issues.
- Final baseline workspace contains zero recorded rows and zero checkpoint files.
- `benchmark.toml` selects the new fingerprint-derived path; both prior baseline
  identities remain unchanged as historical provenance.

The packaged yadof `test_com.py` remains unchanged. The difficulty model is local
to this benchmark task because it defines benchmark science rather than a general
adapter behavior.
