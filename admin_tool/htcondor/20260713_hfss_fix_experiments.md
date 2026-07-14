# 2026-07-13 HFSS Multicore Fix Experiments

## Outcome

The profile 08 HTCondor multicore crash is reproducibly avoided by preventing the
Windows starter from injecting `OMP_THREAD_LIMIT` into jobs. The validated worker
setting is:

```text
STARTER_NUM_THREADS_ENV_VARS = CUBACORES GOMAXPROCS JULIA_NUM_THREADS MKL_NUM_THREADS NUMEXPR_NUM_THREADS OMP_NUM_THREADS OPENBLAS_NUM_THREADS PYTHON_CPU_COUNT ROOT_MAX_THREADS TF_LOOP_PARALLEL_ITERATIONS TF_NUM_THREADS
```

This is the HTCondor 25.4 default list with only `OMP_THREAD_LIMIT` removed. It
preserves the production identity contract:

```text
run_as_owner = False
load_profile = True
```

The evidence identifies the trigger at the integration boundary: the exact HFSS
2024.1 Mixed Order plus Iterative Solver profile crashes when `OMP_THREAD_LIMIT=2`
is injected by HTCondor. It does not establish the faulty internal code path inside
`hf3d.exe`.

## Successful Fix Runs

Cluster `4245` disabled the entire `STARTER_NUM_THREADS_ENV_VARS` list. It completed
all three pin states, returned 0, and produced all nine expected `.npz` files.

Cluster `4246` removed only `OMP_THREAD_LIMIT` while retaining these observed
values:

```text
MKL_NUM_THREADS=2
NUMEXPR_NUM_THREADS=2
OMP_NUM_THREADS=2
OPENBLAS_NUM_THREADS=2
PYTHON_CPU_COUNT=2
OMP_THREAD_LIMIT=<absent>
```

It also completed all three solves, returned 0, and produced all nine expected
files. Solve times were approximately 2 minutes per pin state, consistent with the
successful direct-local reference.

The setting was then applied permanently to this worker with
`configure_worker_hfss_compat.ps1`. Cluster `4248` was submitted without a
temporary configuration wrapper and passed the same three-pin-state acceptance
test. Its final environment retained the other thread values at 2 and left
`OMP_THREAD_LIMIT` absent.

Evidence directories:

- `project/jobs/job_20260713_051047_151163_no_thread_auto`
- `project/jobs/job_20260713_051840_024995_no_omp_thread_limit`
- `project/jobs/job_20260713_053351_445748_permanent_omp_fix`
- `temp/htcondor_hfss_fix_20260712/hfss_no_thread_auto_experiment.json`
- `temp/htcondor_hfss_fix_20260712/hfss_no_omp_thread_limit_experiment.json`
- `temp/htcondor_hfss_fix_20260712/hfss_permanent_omp_fix_experiment.json`

## Controlled Matrix

| Cluster | Change | Result | Interpretation |
| ---: | --- | --- | --- |
| 4231 | Two-CPU environment/process probe | done | Confirmed all starter thread variables were 2 and priority was idle. |
| 4232 | Submit thread values set to 1 | done | Confirmed submit values override automatic values on 25.4. |
| 4233 | Fresh two-core HFSS baseline | `0xC0000005` | Reproduced the original failure. |
| 4234 | Native thread variables set to 1 | `SOLVER_OUT_OF_MEMORY` | Changing values reaches HFSS, but 1 is not a valid fix. |
| 4235 | `STARTER_NESTED_SCRATCH=False` | `0xC0000005` | Nested scratch is not the trigger. |
| 4236 | Normal-priority process probe | done | Confirmed the worker override changed child priority. |
| 4237 | `JOB_RENICE_INCREMENT=0` | `0xC0000005` | Idle priority is not the trigger. |
| 4238 | CPU-affinity process probe | done | Confirmed a two-CPU affinity mask. |
| 4239 | `ASSIGN_CPU_AFFINITY=True` | `0xC0000005` | Lack of CPU binding is not the trigger. |
| 4240 | `USE_VISIBLE_DESKTOP=True` | `0xC0000005` | The hidden desktop is not the trigger. |
| 4241 | Initial `SLOT1_USER` attempt | `0xC0000005` | Macro did not apply to the dynamic slot; not a valid identity test. |
| 4242 | Dynamic-slot identity probe with bare user | removed | Starter rejected `(null)\ysPan`; full Windows account name was required. |
| 4243 | Corrected dynamic-slot identity probe | done | Confirmed Condor could run the probe as `DESKTOP-DERG5LD\ysPan`. |
| 4244 | HFSS under Condor as `ysPan` | `0xC0000005` | Dynamic slot-user identity is not the root cause. |
| 4245 | Disable all automatic thread variables | done | First complete HTCondor multicore success for profile 08. |
| 4246 | Remove only `OMP_THREAD_LIMIT` | done | Minimal successful worker setting. |
| 4247 | Submit `OMP_THREAD_LIMIT=` | `0xC0000005` | Empty submit value was replaced with 2; job-level removal does not work. |
| 4248 | Permanent worker setting acceptance | done | Returned 0 and produced all nine outputs under `condor-slot1_1`. |

Every worker-setting experiment restored the original local configuration in a
`finally` block before the next case. The unrelated held job `4205.0` was not
modified. After the controlled matrix, the validated setting was applied
permanently to the local worker; `4248` tested that final state.

## Why The Fix Belongs On The Worker

HTCondor constructs the final thread environment in the starter. The attempted
submit line:

```text
OMP_THREAD_LIMIT=
```

did not remove the variable. Cluster `4247` recorded the final value as 2 and
reproduced the crash. Therefore the verified control point is the execute worker's
`STARTER_NUM_THREADS_ENV_VARS`, not YADOF's submit environment.

Apply the setting on every worker that may execute HFSS jobs:

```cmd
admin_tool\htcondor_pool\setup_worker_hfss_compat.cmd
```

The normal pool and declared-resource setup scripts also emit the setting. Verify
after deployment:

```powershell
condor_config_val STARTER_NUM_THREADS_ENV_VARS
```

The output must not contain `OMP_THREAD_LIMIT`. A two-CPU probe or job metadata
should still show `OMP_NUM_THREADS=2` and the other retained values.

## Upgrade Note

This override spells out the retained HTCondor 25.4 list. HTCondor may add new
default thread-variable names in later releases. After an upgrade, compare the new
official default with this list, preserve new safe entries as appropriate, and keep
`OMP_THREAD_LIMIT` excluded until the same HFSS profile passes a controlled test
with it present.

## Official Documentation Basis

Read on 2026-07-12 and 2026-07-13:

- Running-job environment and automatic thread variables:
  <https://htcondor.readthedocs.io/en/main/users-manual/env-of-job.html>
- Windows starter, slot accounts, profiles, and desktops:
  <https://htcondor.readthedocs.io/en/latest/platform-specific/microsoft-windows.html>
- Global configuration, including `SLOT<N>_USER`:
  <https://htcondor.readthedocs.io/en/25.x/admin-manual/configuration/global.html>
- Starter configuration:
  <https://htcondor.readthedocs.io/en/25.x/admin-manual/configuration/starter.html>
- Partitionable and dynamic slots:
  <https://htcondor.readthedocs.io/en/25.0/admin-manual/ep-policy-configuration.html>

The documentation says HTCondor sets common threading variables to provisioned
CPUs and allows administrators to configure the list. The HFSS-specific
incompatibility and the minimal exclusion were established by the real jobs above,
not asserted by the HTCondor manual.
