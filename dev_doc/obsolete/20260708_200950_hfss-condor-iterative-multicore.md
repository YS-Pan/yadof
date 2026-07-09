# Archived completion note

Completed on 2026-07-09 by controlled HTCondor diagnostics. See `dev_doc/change_records/20260709_154004_hfss-condor-multicore-diagnosis.md` for the matrix, Windows Event Log evidence, and recommendation.

The completion outcome is documented reproducibility rather than a code-side solver fix: the 08 Mixed Order + Iterative Solver AEDT crashes `hf3d.exe` with access violation `0xc0000005` under HTCondor when HFSS uses more than one core, while 08 one-core and 09 Direct Solver 2/6-core controls succeed under the same runner and worker.

---
# HFSS Condor Iterative Solver Multi-Core Diagnosis

## Context
- `temp/huangzetao20260708.aedt` and `temp/huangzetao20260709.aedt` both complete normally when opened and solved manually in Ansys Electronics Desktop.
- The important solver difference is that `huangzetao20260708.aedt` uses `Setup1` with Mixed Order basis functions and the Iterative Solver, while `huangzetao20260709.aedt` uses First Order basis functions and the Direct Solver.
- In HTCondor runs, the 08 project fails in multi-core mode with `hf3d` exiting as `-1073741819` / `0xC0000005`, while 09 completes. The 08 project also completes when restricted to one core.
- A failed 08 job folder can complete when its `workflow.py` is run manually outside HTCondor, which means the AEDT file and workflow logic are not sufficient by themselves to reproduce the failure. The Condor runtime user, scratch/profile directories, submit environment, DSO/HPC options, and requested resources are part of the failure surface.
- A local smoke test found that the old quoted HTCondor `environment` string used semicolon-separated variables. In HTCondor quoted environment syntax, entries should be whitespace-separated; the old Windows syntax uses `|`. This has now been fixed in config, and `workflow.py` now reads HFSS defaults from job-local config before applying environment overrides.
- This can produce a resource mismatch where HTCondor allocates fewer CPUs than PyAEDT/HFSS is configured to use. That mismatch is especially suspicious for the 08 Iterative Solver path.

## Goal
- Keep the 08 solver settings: Mixed Order basis functions and Iterative Solver.
- Make the 08 project run successfully through HTCondor with multiple cores.
- Identify whether the root cause is project configuration, HTCondor submit syntax, Condor Windows user/profile isolation, PyAEDT-generated DSO/HPC configuration, HFSS temp directory handling, resource under-requesting, or an Ansys HFSS iterative-solver crash that needs a documented workaround.

## Guidance
- Completed related cleanup: submit environment syntax is now whitespace-separated, `HTCONDOR_REQUEST_CPUS` and `HFSS_JOB_CPUCORE` live in config, runtime HFSS values are written to metadata, and prepared jobs copy both `config.py` and `config_all.py`. Start future multi-core interpretation from jobs produced after this cleanup.
- Keep `request_cpus` and runtime `YADOF_HFSS_JOB_CPUCORE` equal in controlled tests. Each test must record both the Condor submit value and the runtime metadata value.
- Relevant files:
  - `project/config.py` for key run overrides and `project/config_all.py` for full defaults, including `HTCONDOR_REQUEST_CPUS`, `HTCONDOR_REQUEST_MEMORY`, `HTCONDOR_ENVIRONMENT`, and HFSS runtime defaults.
  - `project/evaluate_manager/condor_runner.py` for submit file generation.
  - `project/job_template/workflow.py` for `YADOF_HFSS_JOB_CPUCORE`, temporary directories, and runtime metadata.
  - `project/job_template/hfss_com.py` for the PyAEDT `analyze_setup` call.
  - `project/com_lib/hfss_com.py` if shared HFSS adapter logic is updated together with the template copy.
- Use a 5 minute polling interval after job submission for long-running HTCondor smoke tests.
- Preserve the 09 Direct Solver project as a control case. It should continue to complete under the same Condor runner after submit syntax changes.

Recommended test sequence:

1. Submit 08 from a job produced after the config cleanup with `request_cpus = 1` and runtime HFSS job cores equal to 1. This is the one-core control.
2. Submit 08 with matched `request_cpus` / runtime HFSS job core values of 2, 3, 4, and 6. Do not compare these runs to old jobs where the runtime core count did not match the submit request.
3. Repeat the failing core count with larger `HTCONDOR_REQUEST_MEMORY`, such as `16GB` and `32GB`, and record `MemoryUsage`, disk usage, `batch.log`, and `individual_metadata.json`.
4. Repeat 09 with corrected syntax at the same core counts as the 08 tests to keep a Direct Solver control.
5. If 08 still fails only in Condor multi-core mode, test whether the Condor Windows user/profile is the trigger:
   - compare `run_as_owner=False` versus a safe `run_as_owner=True` configuration if the local HTCondor installation supports it;
   - compare the generated AEDT/PyAEDT user profile and DSO configuration under the Condor slot user with the profile used by the normal desktop user;
   - keep `load_profile` constraints in mind because `condor_runner.py` currently rejects incompatible Windows combinations.
6. If the profile test does not explain the failure, test fixed PyAEDT/HFSS HPC configuration:
   - create or copy a stable ACF file into the job folder;
   - use `analyze_setup(..., acf_file=...)` or `set_hpc_from_file(...)` instead of relying only on a generated temporary DSO configuration;
   - test whether limiting `allowed_distribution_types` avoids the Iterative Solver distributed path that crashes under Condor.
7. Verify whether HFSS actually uses a job-local temp directory. If logs show a fixed machine-specific temp path instead, add a reliable per-job temp configuration and repeat the smallest failing multi-core 08 test.
8. If all resource, environment, profile, ACF, and temp-directory tests are controlled and 08 still crashes only in HTCondor multi-core mode, document the Ansys-side failure signature and keep a workaround path. Possible workarounds include using one core for this solver mode, using Direct Solver when acceptable, or using a restricted DSO/HPC configuration that avoids the crashing Iterative Solver path.

For each test, archive or record:

- the generated `job.sub`;
- `condor.log`, `stdout.log`, `stderr.log`, and `batch.log`;
- `individual_metadata.json`;
- the effective runtime values for user, working directory, Condor scratch directory, requested CPUs, HFSS job core count, memory, disk, solver type, and AEDT project hash;
- whether raw data files were produced and whether `analyze_setup` returned success.

## Completion Rule
- This toDo is complete only when 08 can run through HTCondor with more than one core while preserving Mixed Order plus Iterative Solver, or when the project has a documented, reproducible reason why that exact configuration cannot be made stable under HTCondor.
- Completion should include a change record explaining the root cause, the tested matrix, the final recommended configuration, and any remaining Ansys/PyAEDT/HTCondor limitations.
- If code changes are required, update the relevant architecture and blueprint documents after the implementation.
