# HTCondor Windows Single-Node Pool Debug Reference (Revised After Direct `.py` Execution Validation)

## 1. Purpose, Scope, and Final Proven Outcome

This document consolidates the earlier debugging record and updates it with the most important new result from the latest smoke test.

The target machine was repurposed from an older HTCondor cluster member into a new standalone single-node pool.

The machine was verified to provide all of the following roles locally:

- central manager functions: `collector`, `negotiator`
- submit-side function: `schedd`
- execute-side function: `startd`
- coordinating daemon: `master`

The final proven state was stronger than just “the daemons started”:

- `condor_status` returned the local slot
- `condor_status -collector`, `-negotiator`, `-schedd`, and `-startd` returned healthy local information
- `condor_submit` succeeded
- `condor_wait` succeeded
- the job ran under `C:\condor\execute\...\scratch`
- `getpass.getuser()` returned `condor-slot1_1`
- `whoami` returned `desktop-derg5ld\\condor-slot1_1`
- `condor_history` recorded the command as `payload.py`
- `sys.executable` inside the job was still `C:\Program Files\Python313\python.exe`

That combination is critical. It proves all of the following at the same time:

1. the single-node pool was healthy
2. the job did not run as the submit user `ysPan`
3. HTCondor on this Windows setup successfully ran a `.py` file directly as the submit `executable`
4. a direct-`.py` submit design worked better than the earlier absolute-interpreter submit design

---

## 2. Final Architecture That Was Actually Verified

The final working machine was a self-contained local pool on one Windows host.

The effective role layout was:

- `MASTER`
- `COLLECTOR`
- `NEGOTIATOR`
- `SCHEDD`
- `STARTD`

The key role settings that made the pool self-contained were:

- `CONDOR_HOST = $(FULL_HOSTNAME)`
- `COLLECTOR_HOST = $(CONDOR_HOST)`
- `DAEMON_LIST = MASTER COLLECTOR NEGOTIATOR SCHEDD STARTD`

This was the decisive break from the machine’s previous life as a node inside another pool.

---

## 3. Terminology That Must Be Kept Straight

A lot of confusion came from mixing several different concepts that live in different parts of the HTCondor pipeline.

### 3.1 Pool health

This means the daemons and local pool topology are correct.

Typical evidence:

- `condor_status`
- `condor_status -collector`
- `condor_status -negotiator`
- `condor_status -schedd`
- `condor_status -startd`
- `condor_who -daemons -diagnostic`
- `sc query condor`

### 3.2 Submit-side identity and authentication

This is about whether the submit side is allowed to submit jobs and whether Windows-side credential storage requirements are satisfied.

Typical evidence:

- `condor_submit`
- `condor_store_cred`
- credential-related submit errors

### 3.3 Execute-side job identity

This is about the account under which the job process actually runs on the execute side.

Typical evidence:

- `whoami` inside the job
- `getpass.getuser()` inside the job
- starter/startd behavior
- whether the job scratch directory is under the execute directory

### 3.4 Submit executable design

This is about what the submit description names as `executable` and how HTCondor launches the payload.

This is a separate issue from both pool health and runtime identity.

Typical possibilities:

- `executable = payload.py`
- `executable = run.cmd`
- `executable = C:\...\python.exe` with `arguments = payload.py`

These designs are not equivalent in practice on Windows.

### 3.5 Dedicated run account / slot user / submit user

These are not interchangeable.

- **submit user**: the Windows account that submits the job, such as `ysPan`
- **run_as_owner = True` path**: job runs as the submit user
- **slot user / dedicated run account path**: job runs as a temporary or dedicated low-privilege execute-side account such as `condor-slot1_1`

If these concepts are not kept separate, the debugging story becomes misleading.

---

## 4. The Official Model vs. What Was Observed

The official documentation and the observed behavior matched well once the pieces were separated correctly.

### 4.1 Official Windows identity model

On Windows, HTCondor by default runs jobs using dedicated low-privilege run accounts rather than the submitting user’s login account. Running jobs as the submitting user is the alternate path, not the default path.

That means the target behavior in this session was actually aligned with the documented default Windows model: temporary low-privilege execution, not owner execution.

### 4.2 Official meaning of `run_as_owner`

On Windows, `run_as_owner` defaults to `False`. Setting it to `True` is the explicit way to request execution as the submitter’s Windows login. Also, `load_profile` may not be used together with `run_as_owner`.

### 4.3 Official role of `condor_credd` and `condor_store_cred`

The documentation says that running jobs as the submitting user on Windows requires a `condor_credd` and stored user credentials.

### 4.4 Observed nuance in this specific setup

In the real debugging session, a submit attempt failed first with:

`No credential stored for ysPan@DESKTOP-DERG5LD`

After credentials were stored, the final successful execution still ran as `condor-slot1_1`, not as `ysPan`.

So the operational lesson for this setup is:

- submit-side credential requirements may still appear in the workflow
- that does **not** by itself prove that execute-side identity is owner execution
- the final execution identity must be verified from inside the job payload

This remains one of the most important lessons from the session.

---

## 5. Initial State Before the Real Fixes

The machine was not initially a clean standalone pool. It had stale configuration from an older external pool.

The important pre-fix state was:

- `DAEMON_LIST = MASTER SCHEDD STARTD`
- `CONDOR_HOST = 192.168.31.201`
- `COLLECTOR_HOST = 192.168.31.201`
- no local collector was running
- no local negotiator was running

Local evidence showed that the machine itself had:

- a local `master`
- a local `schedd`
- a local `startd`
- no local `collector`
- no local `negotiator`

The logs repeatedly showed attempts to contact the old remote central manager at `192.168.31.201:9618`.

So the real starting point was not “broken single-node pool”. It was “healthy submit+execute node still pointed at an old external manager”.

---

## 6. What the Early Failures Actually Meant

### 6.1 `condor_status` communication errors did not mean HTCondor was globally broken

When `condor_status` tried to talk to the configured collector, it failed because the configured collector was remote and stale.

This was a topology/configuration problem, not a generic daemon crash.

### 6.2 Missing `.collector_address` was expected before a local collector existed

Before the local collector was enabled, the default `COLLECTOR_ADDRESS_FILE` path existed only conceptually. The file itself was absent because no local collector daemon was running.

That was evidence of the current role set, not a separate mystery.

### 6.3 Repeated timeout messages were a symptom, not the root cause

Logs showing repeated failed connections to `192.168.31.201:9618` were downstream symptoms of stale `CONDOR_HOST` and `COLLECTOR_HOST`.

The root cause was role/topology misconfiguration, not a random networking problem.

---

## 7. What Fixed the Pool Layer

The pool layer became correct only after the machine was reconfigured to be self-contained.

### 7.1 Required configuration changes

The key changes were:

- replace the stale remote `CONDOR_HOST`
- replace the stale remote `COLLECTOR_HOST`
- extend `DAEMON_LIST` to include `COLLECTOR` and `NEGOTIATOR`

### 7.2 Why these changes mattered

- `CONDOR_HOST` defines the pool’s central manager identity
- `COLLECTOR_HOST` tells clients and daemons where the collector is
- `DAEMON_LIST` determines which daemons actually start locally

A machine cannot behave as a true standalone pool if the manager host still points to another machine.

### 7.3 Post-fix confirmation

After restart and reconfiguration, the local machine successfully showed:

- local collector
- local negotiator
- local schedd
- local startd

This was confirmed by `condor_who -daemons -diagnostic` and by the family of `condor_status` commands.

---

## 8. The Most Important Conceptual Split: Pool Health vs. Job Identity vs. Submit Executable Design

This deserves its own section because it is easy to collapse these into one issue.

### 8.1 Pool health asks

- Are the daemons running?
- Is the collector reachable?
- Is negotiation happening?
- Is the slot visible?
- Is the schedd visible?

### 8.2 Job identity asks

- Which account actually ran the process?
- Was the job owner impersonated?
- Was a slot user used?
- Did the job land in execute scratch as expected?

### 8.3 Submit executable design asks

- What exactly is written in `executable = ...`?
- Does HTCondor accept and launch that file type correctly on this platform?
- Is the executable transferred or resolved locally?
- Does the design rely on fragile quoting or path assumptions?

A system can fail pool health before job identity even becomes relevant.
A system can also pass pool health and still fail the executable design.
A system can also pass both and still fail the identity target.

The debugging session had all three layers.

---

## 9. The Submit-Side Credential Surprise

After the pool became healthy, job submission still failed with:

`No credential stored for ysPan@DESKTOP-DERG5LD`

This was the first major surprise because the target execute identity was a slot user, not the submit user.

The key lesson is:

- do not treat this error as proof that the final runtime identity must be owner execution
- treat it first as a submit-path prerequisite or Windows-side credential gating condition in the local environment
- keep checking the final runtime identity using payload evidence, not assumptions

In this session, that distinction mattered a lot.

---

## 10. Why `run_as_owner = False` Still Mattered

The final working submit file kept:

```text
run_as_owner = False
```

This was the correct explicit statement of policy for the target behavior.

It served three roles:

1. it documented the intended identity policy in the submit description
2. it prevented silent drift toward the owner-execution path
3. it made the final observed `condor-slot1_1` result consistent with the submit description

However, the session also showed that this setting alone did not remove all Windows-side credential friction from the end-to-end path.

So the correct lesson is:

- `run_as_owner = False` is necessary for the intended identity policy
- it is not a magic replacement for every Windows-side prerequisite encountered during submission

---

## 11. The Absolute-Interpreter Executable Design Was Fragile

One major blocker appeared when the submit description tried to make an absolute Python interpreter path the HTCondor executable:

```text
executable = "C:\Program Files\Python313\python.exe"
arguments = payload.py
```

That design failed in this environment.

### 11.1 Why it was fragile

Several things became harder when the submit description directly treated an absolute interpreter path as the HTCondor executable on Windows:

- path handling became more brittle
- quoting became more sensitive
- file transfer semantics became less obvious
- the job became more dependent on execute-side layout assumptions

### 11.2 What the later evidence changed

The earlier document concluded that the robust replacement should be a launcher such as `run.cmd`.
That conclusion was too narrow.

The later successful smoke test showed that a cleaner design worked:

```text
executable = payload.py
transfer_executable = True
```

The job completed successfully, `condor_history` showed `payload.py`, and the payload still ran under the expected Python interpreter on the execute side.

### 11.3 Revised conclusion

For this Windows HTCondor setup, the main rule is not “always use `run.cmd`”.
The more accurate rule is:

- avoid the fragile absolute-interpreter submit design first
- prefer a job-local executable design
- test direct `.py` submission early, because it may work cleanly
- keep a launcher script as a fallback pattern, not as the only recommended pattern

---

## 12. The Final Working Submit Pattern That Was Actually Re-Verified

The later smoke test succeeded with this pattern:

```text
universe = vanilla
executable = payload.py
initialdir = .
getenv = False
environment = "USERPROFILE=._home;HOME=._home;APPDATA=._appdata;LOCALAPPDATA=._localappdata;TEMP=._tmp;TMP=._tmp"
load_profile = True
run_as_owner = False
requirements = (OpSys == "WINDOWS")
should_transfer_files = YES
when_to_transfer_output = ON_EXIT
transfer_executable = True
output = job.out
error = job.err
log = job.log
request_cpus = 1
queue
```

This pattern is important because it is both simpler and more directly validated than the earlier launcher-based draft.

### 12.1 What this pattern proved

It proved that, in this environment:

- a `.py` file can be named directly as the job executable
- `transfer_executable = True` works correctly with that `.py` payload
- the execute-side runtime still used the intended Python installation
- the job still ran under a temporary slot account
- output transfer still worked normally

### 12.2 What this pattern did **not** prove

It did **not** prove that every Windows HTCondor deployment will behave identically.

So the correct wording is:

- this pattern is proven on this machine and should be the first thing to try for similar Windows single-node pool debugging
- if it fails elsewhere, fall back to a launcher-based design and compare behavior

---

## 13. Why `load_profile = True` Was Worth Keeping

The final successful design used:

```text
load_profile = True
```

This was a good stabilizer for Windows jobs running under temporary accounts.

Practical reasons to keep it:

- profile-related directories are less surprising
- application-data behavior is less brittle
- some Windows applications behave badly without expected profile initialization
- it aligns better with explicit sandbox environment redirection

Also remember the submit-manual rule:

- `load_profile` may not be combined with `run_as_owner`

That is another reason to keep identity policy explicit and coherent.

---

## 14. Sandbox Environment Directories Were Not Cosmetic

The working job explicitly redirected key environment variables into job-local directories:

- `USERPROFILE=._home`
- `HOME=._home`
- `APPDATA=._appdata`
- `LOCALAPPDATA=._localappdata`
- `TEMP=._tmp`
- `TMP=._tmp`

This was not just cleanup polish. It had real debugging value.

### 14.1 Why this helped

- reduced dependence on the default profile layout of temporary run accounts
- kept temp files and app-data usage inside the job sandbox
- made output easier to reason about
- reduced accidental coupling to the submit machine’s interactive desktop environment

### 14.2 Long-term recommendation

For Windows smoke tests and many Windows batch jobs, treat sandboxed profile and temp paths as a recommended default unless a job has a strong reason not to.

---

## 15. What a Real Smoke Test Must Capture

A smoke test is not complete if it only proves that `condor_submit` and `condor_wait` return success.

The payload must record enough evidence to answer these questions:

- Who am I?
- Where am I running?
- What interpreter actually launched me?
- What command does HTCondor record for the job?
- Did output transfer back correctly?

At minimum, the payload or surrounding driver should capture:

- `getpass.getuser()`
- `whoami`
- `os.getcwd()`
- `sys.executable`
- `platform.platform()`
- timestamp
- `condor_history` for the finished job

Without that evidence, a submit/complete cycle can look healthy while still hiding identity-policy mistakes or incorrect assumptions about the executable design.

---

## 16. The Strongest Evidence in This Session

The most trustworthy pieces of evidence were not assumptions. They were direct observations.

### 16.1 Pool-health evidence

- `condor_who -daemons -diagnostic` showed local collector, negotiator, schedd, and startd alive
- `condor_status` showed the local slot
- `condor_status -collector` showed a local pool
- `condor_status -schedd` showed the local submit daemon
- `condor_status -startd` showed the local execute daemon

### 16.2 Runtime-identity evidence

- job scratch directory under `C:\condor\execute\...\scratch`
- `getpass.getuser() == condor-slot1_1`
- `whoami == desktop-derg5ld\\condor-slot1_1`

### 16.3 Executable-design evidence

- `condor_submit` succeeded with `executable = payload.py`
- `condor_wait` succeeded
- `condor_history` showed `CMD = payload.py`
- `sys.executable` inside the job was `C:\Program Files\Python313\python.exe`

### 16.4 Why this matters

These observations are much stronger than reasoning from a single configuration knob or from an earlier failed submit pattern.

---

## 17. What Not to Over-Interpret

Several things in the debugging path looked more alarming than they really were.

### 17.1 One transient communication error is not automatically a config failure

Temporary `CEDAR` communication errors can happen during daemon startup, restart windows, or registration lag.

Do not immediately roll back configuration after a single transient error.

### 17.2 Missing optional directories are not always bugs

For example, `LOCAL_CONFIG_DIR = C:\condor\config` was configured but the directory was absent. That is not necessarily fatal; it simply means there are no extra drop-in config files being read from that location.

### 17.3 `condor_store_cred` did not prove owner execution

This was one of the easiest wrong conclusions to draw. The final run disproved it.

### 17.4 A successful submit is not enough

Only the payload-level identity report established that the job ran under the slot user.

### 17.5 A failed submit pattern should not be promoted to a universal Windows rule

The earlier absolute-interpreter pattern failed.
That did **not** mean the only reliable alternative was `run.cmd`.
The later direct-`.py` success showed that Windows HTCondor behavior in this area is trickier and more permissive than the earlier conclusion suggested.

---

## 18. Configuration Macros and Knobs Worth Remembering

The following are especially relevant for future Windows debugging, even if not all of them required active changes in this session.

### 18.1 Topology and role

- `CONDOR_HOST`
- `COLLECTOR_HOST`
- `DAEMON_LIST`

### 18.2 Identity policy and owner execution

- `run_as_owner`
- `load_profile`
- `STARTER_ALLOW_RUNAS_OWNER`

### 18.3 Dedicated execute account handling

- `SLOT<N>_USER`
- `DEDICATED_EXECUTE_ACCOUNT_REGEXP`
- `DYNAMIC_RUN_ACCOUNT_LOCAL_GROUP`

### 18.4 Submit executable behavior

- `executable`
- `arguments`
- `transfer_executable`
- `transfer_input_files`
- `should_transfer_files`
- `when_to_transfer_output`

These become especially important when choosing between direct executable submission, launcher scripts, and interpreter-based submission.

---

## 19. Recommended Debugging Order for Future Windows Pools

This order worked well and should be reused.

### Step 1: verify the pool itself

Check:

- `sc query condor`
- `condor_who -daemons -diagnostic`
- `condor_status`
- `condor_status -collector`
- `condor_status -negotiator`
- `condor_status -schedd`
- `condor_status -startd`
- `condor_q`

If these are not healthy, do not debug job identity yet.

### Step 2: verify local topology assumptions

Check:

- `CONDOR_HOST`
- `COLLECTOR_HOST`
- `DAEMON_LIST`
- whether stale remote manager addresses are still present

### Step 3: verify submit-path prerequisites

If submission fails, classify the error before changing identity policy.

Examples:

- missing Windows credential storage
- fragile executable-path design
- file transfer issue
- environment/profile issue

### Step 4: test executable design in this order

Recommended order for this environment:

1. try direct executable submission first, for example `executable = payload.py`
2. keep `transfer_executable = True` if the payload itself is the transferred executable
3. avoid starting with `executable = C:\...\python.exe` unless there is a strong reason
4. if direct `.py` submission fails, use a launcher such as `run.cmd` as the next fallback

### Step 5: verify runtime identity from inside the job

Only now should you decide whether the execute-side identity is correct.

### Step 6: verify command interpretation after completion

Use `condor_history` to confirm what HTCondor recorded as the job command.

This helps distinguish “job ran somehow” from “job ran through the exact submit pattern you intended to validate”.

---

## 20. Minimal Reliable Success Criteria

A new Windows single-node pool should not be considered “really working” until all of the following are true:

1. `condor_status` works
2. `condor_status -collector` works
3. `condor_status -negotiator` works
4. `condor_status -schedd` works
5. `condor_status -startd` works
6. `condor_submit` works
7. `condor_wait` works
8. output transfer works
9. the payload proves it ran in execute scratch
10. `whoami` shows `condor-slot...` for the temporary-account target path
11. `condor_history` confirms the intended submit executable form

If all eleven are true, then:

- the local pool topology is healthy
- negotiation is healthy
- submission is healthy
- execution is healthy
- transfer is healthy
- identity policy is behaving as intended
- the tested executable design is actually the one that succeeded

---

## 21. Practical Takeaways for Future Work

### 21.1 When bringing up a recycled Windows node, suspect stale pool topology first

If the machine was previously part of another pool, stale `CONDOR_HOST` and `COLLECTOR_HOST` values are one of the first things to check.

### 21.2 For this environment, prefer direct `.py` executable submission before adding a launcher

Use:

- `executable = payload.py`
- `transfer_executable = True`
- explicit output and error files
- explicit sandbox environment

This is now the most directly validated Windows smoke-test strategy for this setup.

### 21.3 Treat `run.cmd` as a fallback pattern, not the only robust pattern

A launcher is still useful when direct file execution fails or when a more complex setup sequence is needed.
But the latest evidence shows that it should not automatically be the first recommendation.

### 21.4 Avoid assuming that an absolute interpreter path is the simplest design

The `executable = C:\...\python.exe` plus `arguments = payload.py` pattern looked straightforward, but it was the fragile one in this session.

### 21.5 Validate identity from inside the payload, not from assumptions

Do not infer the runtime account only from:

- submit errors
- `run_as_owner`
- documentation defaults
- starter policy guesses

Always capture `whoami`.

### 21.6 Keep “submit credentials”, “executable design”, and “execute identity” as separate checklist items

They are related, but not equivalent.
Mixing them caused real confusion in this session.

---

## 22. Suggested Reusable File Set

The following types of files are worth preserving for future Windows HTCondor work:

- a pool reconfiguration script for converting a recycled node into a standalone pool
- a local environment inspection script
- a smoke-test submit generator
- a smoke-test payload that records identity, cwd, interpreter, platform, and command interpretation evidence
- a debugging reference like this one

This set provides a repeatable bring-up path instead of one-off manual experimentation.

---

## 23. Final Summary

This debugging session was not a single bug. It was a sequence of distinct layers:

1. stale external-pool topology on a recycled node
2. local single-node pool completion
3. Windows submit-side credential friction
4. fragile absolute-interpreter executable design
5. successful direct-`.py` executable submission
6. final verification of temporary slot-user execution

The most important durable lessons are:

- fix pool topology before debugging job identity
- separate submit-side credential issues from execute-side identity issues
- separate executable-design issues from both of those
- for this setup, try direct `executable = payload.py` first
- keep a launcher-based design as a fallback, not as the only recommendation
- verify the final runtime account from inside the payload
- treat `condor-slot...` plus execute scratch as the decisive evidence for the temporary-user target path
- use `condor_history` to confirm the exact submit command form that really worked

---

## 24. One-Sentence Bottom Line

For this Windows HTCondor bring-up, the most reliable validated path was:

**healthy local pool + explicit role configuration + direct `payload.py` executable submission + sandboxed Windows environment + payload identity reporting + final confirmation that the job ran as `condor-slot...` inside execute scratch.**
