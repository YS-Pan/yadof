# Module blueprint: HTCondor LAN node configuration

## Intent and ownership

`admin_tool/htcondor_config/` is a source-checkout administrator tool, separate from
the installed yadof framework and the independent FRP/CCB script suite. Its
numbered PowerShell entries configure a Windows node's management, submission,
execution, or explicit pool-leave capabilities.

## Role composition

- Read effective `DAEMON_LIST` as well as the existing primary-role marker. A
  native schedd without yadof metadata is still an existing submit node.
- Manager registration adds `COLLECTOR`, `NEGOTIATOR`, and `SCHEDD`; worker
  registration adds `STARTD`; submit registration adds `SCHEDD`. Merge and
  deduplicate existing daemons, including unrelated configured services.
- Preserve the Manager primary-role label when adding worker or submit service
  to a manager. The label is routing metadata, not an exclusive capability enum.
- Preserve explicit resource declarations and execute paths on every role
  registration. Resource changes enable execution while retaining submission and
  management. Preserve existing flocking values across either operation.
- Reject a different primary manager name before writing configuration, changing
  ACL/firewall state, or restarting a service. Explicit leave removes roles and
  flocking and permits deliberate registration into a different primary pool.

## I/O and operational boundaries

The shared `_htcondor_hostname_common.psm1` discovers the local installation,
selects an explicit cluster adapter, reads effective configuration, composes the
capability union, and replaces only its managed block in the local configuration.
Timestamped local backups preserve previous contents. Manager names remain names;
the local interface selector is a Windows GUID. Resource inputs use logical CPUs
and MiB, with disk converted to Condor KiB.

Entries elevate interactively, restart the Condor service, and check the requested
advertisement type. Submission is checked through schedd ads, execution through
startd ads, and management through the collector. Source edits alone do not apply
configuration or restore capabilities already removed on another machine.

## Verification and mutability

Offline tests call the real role/resource/leave mutators against isolated fixture
configuration and the native Condor parser. Replace all OS/service/network
mutations before invoking those functions. Cover the eight initial capability
combinations, repeated additions, unmarked schedds, declared-resource retention,
resource updates, rejected pool switches, and explicit leave. Verify production
configuration hashes, service state, and master PIDs remain unchanged.

Keep administrator usage details in the suite README and deployment contract.
Pool policy can evolve here without introducing administrator commands or runtime
dependencies in `src/yadof/`.
