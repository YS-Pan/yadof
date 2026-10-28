# 2026-07-12 HTCondor Official Docs Deep Dive

> Historical investigation record. The proposed test sequence was completed or
> superseded by the later validated workaround; it is retained as evidence rather
> than as a current deployment procedure.

## Scope

This is a second, version-aware pass through the official HTCondor documentation.
It refines `20260712_official_docs_review.md` and focuses on configuration and
execution differences that can be tested without changing the production identity
contract:

```text
run_as_owner = False
load_profile = True
```

This pass changes documentation only. It does not change project code or worker
configuration and does not run an HFSS simulation.

## Version Baseline

Read date: 2026-07-12.

The locally installed executable reports:

```text
$CondorVersion: 25.4.0 2025-11-12 BuildID: 850019 GitSHA: 6c530282 $
$CondorPlatform: x86_64_Windows10 $
```

It is installed at `C:\condor\bin\condor_version.exe`.

This establishes the version only for the local machine. Every execute worker must
record its own `condor_version`; a mixed-version pool can apply different defaults.

This matters because the `latest` and `25.x` documentation currently describes
HTCondor 25.11.0. The `25.x` documentation is rolling documentation for the feature
series, not a frozen copy of the 25.4 manual. Conclusions below therefore distinguish
long-standing behavior from changes introduced after 25.4.

Official sources used:

- 25.x feature release history, including 25.4.0:
  <https://htcondor.readthedocs.io/en/25.x/version-history/feature-versions-25-x.html>
- Windows platform behavior:
  <https://htcondor.readthedocs.io/en/25.0/platform-specific/microsoft-windows.html>
- Running-job environment:
  <https://htcondor.readthedocs.io/en/24.x/users-manual/env-of-job.html>
- Starter configuration:
  <https://htcondor.readthedocs.io/en/25.x/admin-manual/configuration/starter.html>
- File-system configuration, including nested scratch:
  <https://htcondor.readthedocs.io/en/25.x/admin-manual/configuration/global.html>
- Configuration parsing and precedence:
  <https://htcondor.readthedocs.io/en/latest/admin-manual/introduction-to-configuration.html>
- `condor_config_val`:
  <https://htcondor.readthedocs.io/en/24.x/man-pages/condor_config_val.html>
- Slot types and dynamic provisioning:
  <https://htcondor.readthedocs.io/en/25.0/admin-manual/ep-policy-configuration.html>
- `condor_submit`:
  <https://htcondor.readthedocs.io/en/latest/man-pages/condor_submit.html>
- Job and daemon logging:
  <https://htcondor.readthedocs.io/en/latest/admin-manual/logging.html>
- Job event codes:
  <https://htcondor.readthedocs.io/en/main/codes-other-values/job-event-log-codes.html>
- 25.0 LTS release history:
  <https://htcondor.readthedocs.io/en/25.x/version-history/lts-versions-25-0.html>
- 23.0 LTS release history, used to date the thread-variable behavior:
  <https://htcondor.readthedocs.io/en/latest/version-history/lts-versions-23-0.html>

## Revised Ranking

The most useful next tests are now:

1. Observe and neutralize the final thread-control environment.
2. Set `STARTER_NESTED_SCRATCH=False` on one worker and repeat the same job.
3. Observe the Windows process priority class and test normal priority.
4. Test explicit CPU affinity after recording the actual slot shape.
5. Only then move to visible desktop and broader slot-user ACL experiments.

The first four are tightly scoped HTCondor runtime differences. They provide cleaner
evidence than copying an owner profile or granting broad privileges.

## 1. Thread Environment Still Ranks First, But Precedence Must Be Measured

HTCondor sets common thread-control variables to the number of CPUs provisioned to
the job. This behavior predates 25.4; release history shows the default list was
already being extended in the 23.0 series.

Important distinction:

- the value is based on the slot's provisioned `Cpus`;
- that value is at least `RequestCpus`, but may be larger on a static or rounded
  slot;
- one repository pool setup path creates a non-partitionable static slot, while the
  declared-resource worker setup can create a partitionable slot, so the actual
  matched slot must be read rather than inferred from `request_cpus`;
- the official environment-precedence text explicitly covers `environment`,
  `getenv`, `STARTER_JOB_ENVIRONMENT`, and inherited starter environment;
- it does not explicitly state the precedence between a submit-file value and the
  automatic `STARTER_NUM_THREADS_ENV_VARS` assignment.

Therefore, the earlier suggestion to set `OMP_NUM_THREADS=1` in the submit file is
an experiment, not a documented guarantee.

Required three-step probe:

1. A two-CPU diagnostic job records the final values of:

   ```text
   MKL_NUM_THREADS
   OMP_NUM_THREADS
   OMP_THREAD_LIMIT
   OPENBLAS_NUM_THREADS
   NUMEXPR_NUM_THREADS
   PYTHON_CPU_COUNT
   ```

2. The same job supplies explicit submit values of `1` and records the final values
   again. This establishes precedence on HTCondor 25.4.
3. If the explicit values do not survive, use an isolated worker with:

   ```text
   STARTER_NUM_THREADS_ENV_VARS =
   ```

   Reconfigure the worker, rerun the probe, and then explicitly provide only the
   variables needed by the job.

HFSS experiment interpretation:

- Keep `YADOF_HFSS_JOB_CPUCORE=2` and `request_cpus=2`.
- Change only the generic thread variables to `1`.
- If profile 08 succeeds, restore variables one at a time.
- If the final environment did not actually change, the solve result does not test
  this hypothesis.

## 2. HTCondor 25.4 Changed The Scratch Layout Default

HTCondor 25.4.0 changed `STARTER_NESTED_SCRATCH` to default to `True`.

With `False`, the job scratch is:

```text
$(EXECUTE)\dir_<starter_pid>
```

With `True`, the hierarchy is conceptually:

```text
$(EXECUTE)\dir_<starter_pid>\
  scratch\   job working directory
  user\      user-owned HTCondor metadata and credentials
  htcondor\  system-owned HTCondor files
```

The recorded failing path is:

```text
C:\condor\execute\dir_2368\scratch
```

This confirms that the failing run used the new default layout.

Why it is relevant:

- it is an exact behavior change in the installed HTCondor release;
- it changes the working path, parent directory ownership boundaries, and placement
  of job metadata;
- native Windows applications may resolve parent paths, create sibling state, or
  behave differently with path length and ACL boundaries;
- it can be reversed with one execute-host setting without changing job identity,
  resource requests, HFSS settings, or file-transfer policy.

Recommended experiment on one worker:

```text
STARTER_NESTED_SCRATCH = False
```

After reconfiguration, verify `_CONDOR_SCRATCH_DIR` no longer ends in `\scratch`,
then repeat the exact profile 08 two-core job.

Interpretation:

- success would identify the 25.4 scratch hierarchy as part of the failure;
- failure would eliminate a version-specific HTCondor change at low cost;
- this test should be run before broad ACL changes because it preserves the same
  slot account and privilege level.

### Diagnostic Bug In 25.4

The 25.6.1 release notes say a bug was fixed where
`STARTER_NESTED_SCRATCH=True` broke the `starter_log` submit command. The installed
25.4.0 predates that fix.

Consequences:

- a missing returned `starter_log` under the current nested layout is not proof that
  the starter produced no useful log;
- inspect the worker's normal StarterLog, or temporarily use
  `STARTER_LOG_NAME_APPEND=jobid` for persistent per-job worker logs;
- the `starter_log` submit command becomes more trustworthy after either disabling
  nested scratch for the experiment or upgrading past the documented fix.

This known bug concerns diagnostic transfer, not the HFSS crash itself.

## 3. Windows Jobs Default To Idle Priority Class

The starter documentation says the Windows default for `JOB_RENICE_INCREMENT` is
the idle priority class. A direct desktop workflow normally runs at the owner's
ordinary process priority, so this is another Condor-only runtime difference.

An idle priority should normally affect throughput rather than correctness. However,
it can change thread scheduling and timing in a native multicore solver, so it is a
reasonable race-sensitive diagnostic after the thread and scratch tests.

Required probe:

- record the Windows priority class for the initial Python process, AEDT, and
  `hf3d` if practical;
- confirm whether child solver processes inherit the job's idle priority;
- on one worker, test `JOB_RENICE_INCREMENT=0` and accept the test only after the
  probe confirms that the resulting process priority is no longer idle.

The official manual describes the supported range but does not clearly document the
numeric-to-Windows-priority-class mapping. The process observation is therefore part
of the test, not optional validation.

If normal priority fixes profile 08 multicore, the production decision must balance
solver stability against interactive responsiveness on office workstations.

## 4. Resource Requests Do Not Automatically Mean CPU Binding

The starter documentation says `ASSIGN_CPU_AFFINITY` defaults to `False`.

This produces an important distinction:

- `request_cpus` participates in matching and slot allocation;
- the slot's `Cpus` controls the automatic thread environment;
- without affinity, the Windows process may still be schedulable across all logical
  processors visible to the operating system;
- with `ASSIGN_CPU_AFFINITY=True`, HTCondor binds a partitionable-slot job to the
  requested number of cores and constrains static-slot jobs to their slot CPU set.

Recommended evidence for every probe:

```text
RequestCpus from _CONDOR_JOB_AD
Cpus, SlotType, PartitionableSlot, and DynamicSlot from _CONDOR_MACHINE_AD
process affinity mask
logical processor count visible to Python and hf3d
final thread-control environment
```

Recommended A/B test after the earlier tests:

1. Record the baseline with affinity disabled.
2. Set `ASSIGN_CPU_AFFINITY=True` on one worker.
3. Confirm the actual affinity mask contains the expected two CPUs.
4. Repeat the same profile 08 two-core job.

Affinity should not be combined with the thread-variable change in the first run;
otherwise a success will not identify which mechanism mattered.

## 5. Audit The Effective Configuration, Not Only The Generated File

HTCondor parses configuration in order and later definitions override earlier ones.
In addition, runtime or persistent settings made through `condor_config_val` can
override normal files. A daemon may also still be using old in-memory settings until
it is reconfigured or restarted.

The repository pool generator explicitly sets:

```text
START = TRUE
SUSPEND = FALSE
PREEMPT = FALSE
KILL = FALSE
WANT_SUSPEND = FALSE
WANT_VACATE = FALSE
NUM_SLOTS = 1
SLOT_TYPE_1_PARTITIONABLE = FALSE
```

The separate declared-resource worker setup can instead configure a partitionable
slot. Neither setup sets the principal starter macros identified in this pass. The
effective slot configuration, defaults, and any later local overrides therefore
decide the behavior.

Run these from an administrator shell on each worker, using that worker's real
configuration context:

```text
condor_version
condor_config_val -summary
condor_config_val -verbose STARTER_NUM_THREADS_ENV_VARS
condor_config_val -verbose STARTER_NESTED_SCRATCH
condor_config_val -verbose JOB_RENICE_INCREMENT
condor_config_val -verbose ASSIGN_CPU_AFFINITY
condor_config_val -verbose USE_VISIBLE_DESKTOP
condor_config_val -verbose DYNAMIC_RUN_ACCOUNT_LOCAL_GROUP
condor_config_val -verbose START
condor_config_val -verbose SUSPEND
condor_config_val -verbose PREEMPT
condor_config_val -verbose KILL
condor_config_val -verbose SLOT_TYPE_1
condor_config_val -verbose SLOT_TYPE_1_PARTITIONABLE
```

`-verbose` reports the defining file and line plus raw and expanded values. To
compare with a running daemon, query the daemon separately, for example:

```text
condor_config_val -name <worker> -startd STARTER_NESTED_SCRATCH
condor_config_val -name <worker> -startd ASSIGN_CPU_AFFINITY
```

Do not copy the current 25.11 manual's `-default` examples into a 25.4 procedure:
the 25.x release notes say `condor_config_val -default` was added in 25.8.2.

The audit should be saved with the test result. Otherwise two workers that appear
to have the same checked-in configuration may actually run different defaults or
overrides.

## 6. Use Job Events To Rule Out Policy Interference

The repository intends to disable suspend, preempt, kill, and vacate policy, but the
effective audit above must confirm it.

Inspect the job event log for:

```text
004 JOB_EVICTED
010 JOB_SUSPENDED
011 JOB_UNSUSPENDED
012 JOB_HELD
021 REMOTE_ERROR
```

If none appear and the job reaches a normal termination event with the observed
`hf3d` access-violation result, suspend/vacate policy is not the cause. If any appear,
the event timestamp must be compared with the solver crash timestamp before another
HFSS hypothesis is evaluated.

For temporary worker diagnostics, official options include:

```text
STARTER_LOCAL_LOGGING = True
STARTER_LOG_NAME_APPEND = jobid
STARTER_DEBUG = D_FULLDEBUG D_PROCFAMILY
```

`STARTER_LOG_NAME_APPEND=jobid` creates persistent per-job logs and should be used
only during focused debugging because the files do not naturally collapse into the
normal rotating slot log.

## 7. Windows Identity And Desktop Findings Need Narrower Interpretation

### Dynamic Local Group Replaces The Default Group

`DYNAMIC_RUN_ACCOUNT_LOCAL_GROUP` sets a local group other than the default `Users`
group for `condor-slot<X>`. The documentation describes replacement, not addition.

Therefore an experiment such as:

```text
DYNAMIC_RUN_ACCOUNT_LOCAL_GROUP = AnsysCondorUsers
```

must ensure that `AnsysCondorUsers` has all required baseline read/execute rights in
addition to the narrow Ansys/HFSS cache, temp, license, and runtime ACLs. Otherwise
the experiment can accidentally remove rights that came from `Users` and create a
new failure mode.

This remains preferable to adding slot accounts to `Administrators`.

### Loaded Profile Is Deliberately Fresh Per Job

The Windows manual says a dedicated run-account profile is cleaned before a later
job uses the account. `load_profile=True` gives a valid HKCU hive and profile, but it
does not provide persistent application personalization from one job to the next.

Any durable HFSS requirement should therefore be provisioned per worker or rebuilt
per job. Success that depends on a previous slot job's registry changes is contrary
to the documented isolation behavior.

### Visible Desktop Is Diagnostic Only

`USE_VISIBLE_DESKTOP=True` bypasses the private non-visible desktop and is explicitly
described as useful for debugging applications that do not run under HTCondor.

It remains a lower-priority experiment because AEDT starts successfully and the
failure occurs in `hf3d`. If it fixes the crash, treat it as evidence of a desktop or
window-station dependency, not an automatic production setting for shared office
machines.

## 8. Upgrade Findings

The installed 25.4.0 is a feature-series release. The 25.0 line is the LTS series,
where later 25.0.y releases receive bug fixes without feature-series default changes.

The reviewed 25.x release notes after 25.4 do not list a Windows run-account,
profile-loading, thread-environment, or HFSS-related fix that directly explains the
current crash. An upgrade should therefore not be presented as a known solver fix.

Two version experiments remain useful:

- first set `STARTER_NESTED_SCRATCH=False` on 25.4 to isolate the exact default
  change without replacing HTCondor;
- if a version A/B is later justified, compare one isolated worker on a maintained
  25.0 LTS release or a post-25.6 feature release, preserving all other settings.

A post-25.6 version has a concrete diagnostic advantage: it includes the documented
fix for `starter_log` with nested scratch.

## Proposed Test Sequence

Keep each test to one worker and change one mechanism at a time.

| Step | Change | Must Verify Before HFSS Run | Positive Result Means |
| --- | --- | --- | --- |
| 0 | None | Installed version and effective macros | Baseline is reproducible |
| 1 | Submit thread vars set to 1 | Final process environment is really 1 | Submit-level neutralization works |
| 2 | Empty worker thread-var list | Automatic variables are absent | Starter injection was part of the failure |
| 3 | `STARTER_NESTED_SCRATCH=False` | Scratch no longer ends in `\scratch` | 25.4 scratch layout participates |
| 4 | Normal job priority | Python/AEDT/hf3d are not idle priority | Priority/timing participates |
| 5 | `ASSIGN_CPU_AFFINITY=True` | Affinity mask has the intended two CPUs | CPU visibility/binding participates |
| 6 | `USE_VISIBLE_DESKTOP=True` | Job uses the configured desktop mode | Desktop/window station participates |
| 7 | Custom local group and narrow ACLs | Slot identity remains non-admin | Missing worker ACL participates |

For every row, preserve the same HFSS project, profile 08 settings, two HFSS cores,
Condor CPU request, memory request, and input payload.

## Current Best Assessment

The automatic thread environment remains the strongest semantic match for a failure
that appears only with Condor multicore plus the iterative solver path.

The new highest-value discovery is `STARTER_NESTED_SCRATCH`: the installed 25.4.0
release changed its default, the observed failure path proves the new hierarchy is
active, and the behavior can be rolled back with one worker setting. This should be
tested immediately after the thread-environment probe.

Windows idle process priority is the third Condor-specific difference worth testing.
Profile copying and broad privilege changes should remain later steps because they
change more state and provide less precise evidence.
