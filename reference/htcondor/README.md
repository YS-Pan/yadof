# HTCondor Reference Index

## Purpose

This folder is the current entry point for HTCondor-related reference material.
It consolidates older Windows pool bring-up notes and the HFSS multicore diagnosis
into topic-oriented files that can grow without turning one document into a
catch-all log.

## Read First

1. `deployment_contract.md` - durable deployment and identity policy.
2. `windows_pool_debug.md` - Windows HTCondor bring-up and debugging checklist.
3. `hfss_multicore/README.md` - current HFSS multicore case status.

## Structure

```text
reference/htcondor/
  README.md
  deployment_contract.md
  windows_pool_debug.md
  hfss_multicore/
    README.md
    baseline_diagnosis.md
    20260711_followup.md
    findings_and_next_steps.md
  archive/
    htcondor_windows_debug_reference.md
    hfss_condor_multicore_diagnosis_reference.md
    hfss_condor_multicore_debug_20260711.md
```

## Current Policy Summary

Production distributed evaluation must use the Windows slot-user path:

```text
run_as_owner = False
load_profile = True
```

`run_as_owner=True` is not a viable design target for this project. The intended
deployment is a pool of office/personal Windows workstations. Any workstation may
submit work, any configured workstation may execute work, and each machine is owned
by a different interactive user. The system cannot require every worker to run jobs
as every possible submitter's Windows account.

## Archive Status

Files under `archive/` preserve original notes and may contain conclusions that were
later superseded. Prefer the current documents above for design decisions.
