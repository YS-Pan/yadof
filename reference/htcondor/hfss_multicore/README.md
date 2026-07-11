# HFSS Multicore Under HTCondor

## Case

The active case concerns HFSS/AEDT runs launched through the YADOF job workflow:

- 08 project: Mixed Order basis functions plus Iterative Solver.
- 09 project: First Order basis functions plus Direct Solver.
- Setup: `Setup1`.
- Workflow: open project, set variables, solve, export flat `rawData/*.npz`.

## Current Conclusion

The 08 project can run multicore through the direct local workflow, but fails under
HTCondor when HFSS uses more than one core. The failure is specific to the
intersection of:

- 08 Mixed Order plus Iterative Solver;
- HFSS multicore solve;
- Windows HTCondor slot-user execution context.

The 09 Direct Solver control works under HTCondor with multiple cores.

## Current Production Guidance

- Use one HFSS core for the 08 Mixed Order plus Iterative Solver profile under
  HTCondor.
- Use the 09 Direct Solver-style profile for multicore HTCondor runs when that
  solver profile is acceptable for the campaign.
- Direct local workflow remains a valid way to run the 08 profile with multiple
  HFSS cores.
- Do not use `run_as_owner=True` as a fix path; it violates the deployment contract
  in `../deployment_contract.md`.

## Files

- `baseline_diagnosis.md` - original controlled matrix and direct-local contrast.
- `20260711_followup.md` - additional debug probes and eliminated hypotheses.
- `findings_and_next_steps.md` - consolidated interpretation and future work that
  respects the deployment contract.

Original source notes are preserved under `../archive/`.
