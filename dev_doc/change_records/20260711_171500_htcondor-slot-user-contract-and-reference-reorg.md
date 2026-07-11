# 2026-07-11 17:15 - HTCondor Slot-User Contract And Reference Reorg

## Context

Follow-up HFSS/HTCondor debugging showed that `run_as_owner=True` would be the most
direct local experiment for separating desktop-owner state from slot-user state.
The user clarified that owner execution is not compatible with the intended
deployment: many office/personal workstations may both submit and execute jobs, and
each machine has a different interactive owner.

## Change

- Documented the durable Windows HTCondor identity contract in current architecture,
  project blueprint, evaluate_manager blueprint, and terminology.
- Made `run_as_owner=False` plus `load_profile=True` the documented normal path for
  distributed Windows jobs.
- Reorganized HTCondor reference material under `reference/htcondor/`, with a
  deployment contract, Windows pool debug guide, HFSS multicore case folder, and
  archived original source notes.
- Left short root-level redirect notes at the old reference filenames.

## Rationale

The project must support a pool where any configured workstation may submit or
execute jobs without requiring cross-machine user credential fan-out. Debugging and
fixes must therefore make the slot-user path work, rather than escaping to owner
execution.

## Impact

- Future HTCondor/HFSS diagnosis should reproduce behavior under slot users.
- Owner-mode `condor_credd` setup is not a normal prerequisite or fix direction.
- Current reference docs now separate deployment policy, Windows pool debugging, and
  the HFSS multicore case for easier extension.

## Follow-Up

Continue investigating the 08 Mixed Order plus Iterative Solver multicore failure
only through slot-user-compatible paths, such as worker preflight, neutral AEDT/ACF
state, targeted DSO options, or task-level one-core policy for that solver profile.
