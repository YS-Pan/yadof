# 2026-07-04 20:02 - test_com Surrogate Speed Check

## Context
- The surrogate training path was recently changed to improve speed, especially for large rawData fields.
- The requested check used `test_com.py` instead of launching HFSS, with one generation of 200 synthetic individuals.
- The synthetic rawData shape was based on samples under `temp/jobs`: S11 traces plus `Freq x Phi x Theta` gain and axial-ratio grids for three pin states.

## Change
- Extended `project/com_lib/test_com.py` with a default `hfss_like` profile that emits nine HFSS-like rawData blocks: three S11 traces, three `gain_lhcp` 3D grids, and three `axial_ratio` 3D grids.
- Kept the previous summary/curve/surface synthetic output available through `profile="generic"`.
- Updated `user_doc/com_lib/test_com.md` and the job-template blueprint note to document the new profile.
- Ran an isolated surrogate speed test under `temp/surrogate_speed_test_200/` without modifying the project recorded-data archive.

## Rationale
- The existing `test_com.py` could generate scalar, curve, and 2D surface data, but it did not cover the current HFSS-like 3D rawData shape.
- Matching the active `calc_cost.py` rawData names and axes allows surrogate training to be tested on realistic field sizes without requiring AEDT.

## Impact
- The test generation recorded 200 completed synthetic jobs, each with 9 rawData items and 95,937 modeled rawData slots.
- `surrogate.train(generation_index=0)` ran from `2026-07-04T12:01:03.730784+00:00` to `2026-07-04T12:02:01.872718+00:00`.
- Measured surrogate training elapsed time: `58.141904` seconds.
- Training used the current config defaults: 3 ensemble members, 32 epochs, batch size 16, CUDA device, and stochastic query training with 8,192 of 95,937 query points per step.
- Checkpoint and result details were written under `temp/surrogate_speed_test_200/checkpoints/` and `temp/surrogate_speed_test_200/result.json`.
- CPU-only retest on this machine forced `SURROGATE_TORCH_DEVICE = "cpu"` with the same 200 samples and default training scale.
- CPU-only `surrogate.train(generation_index=0)` ran from `2026-07-04T12:09:40.201020+00:00` to `2026-07-04T12:21:26.535866+00:00`.
- CPU-only measured surrogate training elapsed time: `706.334818` seconds, about 11 minutes 46 seconds.
- CPU retest details were written under `temp/surrogate_speed_test_200_cpu/`; PyTorch reported 8 compute threads, 8 interop threads, and the host exposed 16 logical processors.

## Follow-Up
- If future speed comparisons need to be repeatable in CI, turn the temporary speed harness into an explicit benchmark script with fixed reporting and optional CPU/GPU selection.
