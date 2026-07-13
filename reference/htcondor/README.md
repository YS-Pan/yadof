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
4. `20260712_official_docs_review.md` - official HTCondor documentation findings
   and candidate next experiments for the HFSS multicore case.
5. `20260712_official_docs_deep_dive.md` - version-aware follow-up for HTCondor
   25.4, including nested scratch, Windows process priority, effective-config audit,
   and a refined experiment order.
6. `20260713_hfss_fix_experiments.md` - real Condor/HFSS experiment matrix and the
   validated `OMP_THREAD_LIMIT` worker fix.

## Structure

```text
reference/htcondor/
  README.md
  20260712_official_docs_review.md
  20260712_official_docs_deep_dive.md
  20260713_hfss_fix_experiments.md
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

## Adding New Files

When adding HTCondor reference material:

- Put current, decision-relevant notes in this folder or an active topic subfolder,
  not under `archive/`.
- Use a dated filename such as `YYYYMMDD_short_topic.md` for investigation notes
  tied to a specific debug pass.
- Update this README's `Read First` or `Structure` section when the new file should
  be discoverable by future maintainers.
- Include source links and the read date when summarizing external documentation.
- Move or leave older material under `archive/` only when it is preserved as
  historical evidence rather than current guidance.
