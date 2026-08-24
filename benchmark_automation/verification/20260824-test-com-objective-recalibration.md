# 2026-08-24 test_com objective recalibration

## Scope

The 100-individual, 20-generation benchmark run `p20x100-0823` used immutable
baseline `synthetic-antenna-aa89d46f3d9a`. Its six `test-com` cost views showed
four nearly horizontal cost bands and final hypervolume near `1e-4`. This record
diagnoses that task definition and validates its immutable replacement
`synthetic-antenna-c7b0133b3a4e`.

All optimization validations below used the installed yadof 0.4.0 distribution,
fast evaluation, pure real-evaluation NSGA-III, 100 individuals, 20 generations,
and no surrogate component.

## Diagnosis

A deterministic vectorized audit sampled 100,000 parameter vectors uniformly from
the declared 20-dimensional unit box. Under the old `calc_cost.py`, the objective
means were `0.87836`, `0.99792`, `0.00728`, and `0.94806`; their standard
deviations were only `0.01756`, `0.0000817`, `0.000405`, and `0.00888`. The
cumulative hypervolume of the first 5,000 random samples was `6.019e-5` against
reference `(1, 1, 1, 1)`.

The synthetic adapter was responsive; the information was lost at task-owned
rawData interpretation and calibration:

- S11 used the maximum of every five-point trace, which selected the off-resonance
  baseline rather than each state’s resonance.
- gain coverage took the minimum across the complete `-60..60` degree sector even
  though the three synthetic main beams are deliberately centered at `-30`, `30`,
  and `0` degrees.
- the back-lobe response lies roughly between `-24` and `-20` dB, but its old
  `goal=-5` and `worst=5` anchors placed every design in the good tail.
- axial ratio sampled theta zero for every state and then selected the maximum over
  the entire frequency band, although states 1 and 2 are centered at `-14` and
  `14` degrees and the task operating frequency is 2.44 GHz.

The old real-search cells also recorded only 820–840 new rows from 2,000 nominal
population slots. Generation metadata shows that the remaining slots were prior
population members rather than simulator errors; after the objective recalibration,
validation recorded 100 new rows in every generation.

## Replacement objectives

The replacement changes only `submit/calc_cost.py`; the 20 parameters, rawData
shapes, evaluator, copied `test_com.py`, workflow, and objective count remain
unchanged.

| Objective | Physical measurement | Goal | Worst |
|---|---|---:|---:|
| `cost_s11_resonance` | worst, across pin states, of each state’s best in-band S11 | -8.0 dB | -5.5 dB |
| `cost_beam_gain` | worst gain at each state’s expected beam theta, phi 90°, 2.44 GHz | -1.5 dB | -4.0 dB |
| `cost_back_lobe` | worst gain in the existing ±back-lobe windows | -22.5 dB | -20.5 dB |
| `cost_axial_ratio_at_2p44` | worst axial ratio at each state’s expected beam theta, phi 90°, 2.44 GHz | 8.0 dB | 16.5 dB |

These are fixed physical anchors; runtime history is never used for normalization.
On the same 100,000-point audit, the replacement objective means were `0.43826`,
`0.53054`, `0.37298`, and `0.52045`, with standard deviations `0.25722`,
`0.21977`, `0.25253`, and `0.26480`. Pairwise cost correlations stayed between
`-0.287` and `0.107`. The first 5,000 random samples produced HV `0.77529`.

## Full real-only validation

Each run completed all 2,000 evaluations with no ignored history issue.

| Seed | Generation-0 HV | Final HV | Last-five-generation HV gain | Mean cost, gen 0 | Mean cost, gen 19 |
|---:|---:|---:|---:|---:|---:|
| 104729 | 0.653800 | 0.883343 | 0.008942 (1.01%) | 0.455368 | 0.175867 |
| 130363 | 0.617511 | 0.859691 | 0.019339 (2.25%) | 0.478066 | 0.220316 |
| 155921 | 0.534069 | 0.868129 | 0.023038 (2.65%) | 0.451627 | 0.225870 |

The three seeds therefore show a broad initial objective distribution, sustained
multi-generation improvement, a non-degenerate Pareto front, and consistent final
HV. Twenty generations are long enough to approach a plateau without making the
problem trivial at initialization.

## Baseline acceptance

- Fingerprint: `c7b0133b3a4edb71055474119291a03a2b9e99ecff2f02cacd38cc385e448e47`
- `yadof check`: passed, zero warnings, 20 parameters, 4 objectives.
- Disposable midpoint smoke costs: `(0.40121093, 0.55818660, 0.22616523, 0.65835231)`.
- Final baseline workspace: zero recorded rows and zero checkpoint files.
- `benchmark.toml` selects the new fingerprint-derived path; the prior baseline
  remains immutable historical provenance.

The packaged `test_com.py` adapter was not changed because the audit demonstrated
adequate parameter-dependent physical variation. The defect and remedy are both
specific to this synthetic antenna optimization task’s objective policy.
