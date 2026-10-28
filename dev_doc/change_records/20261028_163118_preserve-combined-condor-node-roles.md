# 2026-10-28 16:31 - Preserve combined HTCondor node capabilities

## Context

The numbered LAN worker script replaced `DAEMON_LIST` with `MASTER, STARTD`,
removing an existing submit schedd or central-manager services. Manager
registration also discarded previously declared execution resources. The user
requested that management, submission, and execution coexist without one setup
operation overwriting another.

## Change and rationale

- Updated `admin_tool/htcondor_config/_htcondor_hostname_common.psm1` to detect
  effective capabilities, merge existing daemons, retain the manager identity,
  preserve declared resources on role registration, and preserve flocking targets.
- Added `5_htcondor_enable_submit.ps1` for independent local submission. Resource
  setup accepts submit-only nodes and adds execution while keeping other roles.
- Reject a different primary-manager name before writes or OS/service mutations;
  explicit leave remains the operation for removing roles and switching pools.
- Submission registration checks schedd ads. Existing manager and worker checks
  retain their corresponding collector and startd queries.
- Reused the current-configuration read in resource setup instead of repeating
  manager and allowed-name queries. This removes one bounded redundant read path
  in the shared module without adding another configuration source.
- Updated administrator usage, deployment policy, physical architecture, and the
  focused module blueprint. The independent FRP/CCB suite is outside this change.

## Validation and impact

Windows PowerShell 5.1 offline regression passed 497 checks using the native
HTCondor parser on isolated configuration fixtures. Coverage includes all eight
initial management/submit/execute combinations, all three registration actions
repeated twice, native unmarked submit configurations, resource updates, primary
pool-switch rejection, explicit leave, and actual registration-command routing.
Service, firewall, ACL, DNS, and registration effects were replaced before public
mutators ran. Production configuration hashes, service state, and master PIDs were
unchanged. Evidence is under `temp/htcondor-role-regression/`.

This is a source-checkout administrator-script change; no installed framework
code, package tests, build configuration, or packaged-documentation mechanism was
changed. Verification therefore uses the script suite rather than rebuilding or
reinstalling an unrelated framework wheel. Documentation encoding, links, script
syntax, and whitespace were checked separately.

Source changes do not apply machine configuration. A previously removed schedd
requires running script 5 on the affected machine; a removed local central manager
requires script 2. Script execution retains its existing service-restart behavior.
