# 2026-07-09 17:30 - HTCondor Direct Workflow Submit

## Context
- The Windows HTCondor debug reference verified that direct `.py` submission works on the target setup: the submit file should name the job-local script as `executable` and use `transfer_executable = True`.
- Current code and docs still preserved an older interpreter-as-executable path, including config entries that could generate `executable = python` plus a workflow argument line.

## Change
- Removed `HTCONDOR_PYTHON_EXE` and `HTCONDOR_EXECUTABLE_MODE` from the active config surface and evaluate-manager accessors.
- Changed the HTCondor runner and manual probe tools to generate submit files with `executable = workflow.py`, no workflow argument line, and `transfer_executable = True`.
- Updated tests, current architecture docs, blueprints, terminology, user docs, and HTCondor pool helper wording to reflect the direct `.py` submit contract.

## Rationale
- Treating Python itself as the HTCondor submit executable was the fragile pattern from the Windows debugging session.
- The durable rule is to submit the job-local `.py` payload directly, keep Windows sandbox environment redirects, keep `run_as_owner = False`/`load_profile = True`, and leave Python interpreter access as a worker environment prerequisite rather than a submit-file setting.

## Impact
- New distributed jobs and diagnostic probes no longer rely on a configured worker Python executable path in `job.sub`.
- Worker-side Python ACL helper scripts remain useful for ensuring slot users can execute transferred `.py` jobs, but they do not define the submit executable.
- Historical change records and obsolete notes remain historical; this record supersedes earlier recommendations that promoted the interpreter-as-executable pattern.

## Follow-Up
- Real-pool smoke tests should still verify `whoami`, execute scratch, `sys.executable`, output transfer, and Condor history/recorded command when validating a Windows HTCondor installation.