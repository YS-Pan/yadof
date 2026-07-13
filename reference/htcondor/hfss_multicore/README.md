# HFSS Multicore Under HTCondor

## Case

The active case concerns HFSS/AEDT runs launched through the YADOF job workflow:

- 08 project: Mixed Order basis functions plus Iterative Solver.
- 09 project: First Order basis functions plus Direct Solver.
- Setup: `Setup1`.
- Workflow: open project, set variables, solve, export flat `rawData/*.npz`.

## Resolved Conclusion

The 08 project can run multicore through HTCondor after removing
`OMP_THREAD_LIMIT` from the Windows starter's automatic thread-variable list. The
failure was specific to the intersection of:

- 08 Mixed Order plus Iterative Solver;
- HFSS multicore solve;
- Windows HTCondor slot-user execution context.

HTCondor 25.4 automatically set `OMP_THREAD_LIMIT` to the slot's provisioned CPUs.
With two CPUs this produced the repeatable `hf3d` access violation. Retaining all
other default thread variables but omitting `OMP_THREAD_LIMIT` completed three
controlled three-pin-state runs, including one after permanent worker deployment.

The 09 Direct Solver control works under HTCondor with multiple cores.

## Production Guidance

- Apply `setup_worker_hfss_compat.cmd` on every HFSS execute worker.
- Verify `condor_config_val STARTER_NUM_THREADS_ENV_VARS` does not contain
  `OMP_THREAD_LIMIT`.
- Keep `run_as_owner=False` and `load_profile=True`.
- Use the 09 Direct Solver-style profile for multicore HTCondor runs when that
  solver profile is acceptable for the campaign.
- Direct local workflow remains a valid way to run the 08 profile with multiple
  HFSS cores.
- Do not use `run_as_owner=True` as a fix path; it violates the deployment contract
  in `../deployment_contract.md`.

The previous one-core restriction remains a fallback only for workers that have
not yet received or validated the compatibility setting.

## Files

- `baseline_diagnosis.md` - original controlled matrix and direct-local contrast.
- `20260711_followup.md` - additional debug probes and eliminated hypotheses.
- `findings_and_next_steps.md` - consolidated interpretation and future work that
  respects the deployment contract.
- `../20260713_hfss_fix_experiments.md` - successful fix runs, full experiment
  matrix, and worker deployment setting.

Original source notes are preserved under `../archive/`.
