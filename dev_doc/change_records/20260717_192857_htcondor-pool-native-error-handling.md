# 2026-07-17 19:28 - Make Pool Diagnosis Tolerate Missing State

## Context

The Windows pool-node tool uses `ErrorActionPreference = Stop`, while
`condor_config_val` and `condor_status` write expected failures to native stderr.
On a fresh HTCondor installation, an undefined optional macro such as
`STARTD_ATTRS` therefore terminated configuration before the managed block could
be written. Diagnostic mode also stopped before reporting the rest of the node.

## Change

- Capture native exit codes with `ErrorActionPreference = Continue` only around
  the expected `condor_config_val` and `condor_status` calls.
- Continue to return an empty value for undefined macros.
- Let pool-status failures produce the existing warning and retry behavior.
- Document the fresh-install and unavailable-collector behavior.

## Rationale

Missing optional configuration and a collector that is not running yet are normal
states during first-time setup and recovery. They must remain observable without
weakening terminating-error handling for filesystem, ACL, firewall, or service
operations.

## Impact

`admin_tool/htcondor_pool/htcondor_pool.ps1` can now configure and diagnose an
otherwise blank Windows HTCondor installation. No runtime yadof module or pool
configuration contract changed.

## Follow-Up

None.
