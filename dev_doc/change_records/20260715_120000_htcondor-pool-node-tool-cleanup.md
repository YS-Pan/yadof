# 2026-07-15 12:00 - Consolidate HTCondor Pool Node Setup

## Context

The administrator pool setup was an accumulation of a fixed three-machine trial.
It required separate role, resource, execute-directory, and HFSS-compatibility
scripts, each writing a different configuration block. The scripts embedded machine
labels and communicated a manager address through a copied `manager_ip.txt` file.
The corresponding instructions no longer described a general Windows cluster.

## Change

- Replaced the role-specific CMD wrappers and separate configuration scripts with
  `admin_tool/htcondor_pool/htcondor_pool.ps1`.
- The one tool configures a manager or worker in a single managed block, including
  optional execute resources, scratch directory ACLs, worker attributes, firewall
  scope, optional Python access, and one service restart. Its read-only diagnostic
  action replaces the separate slot and diagnosis scripts.
- Replaced the copied manager-IP-file and subnet-scan behavior with the required
  `-ManagerHost` parameter. It is intended to be a stable DNS name resolved by
  every pool node.
- Set the default `NETWORK_INTERFACE` policy to `*` rather than a DHCP-selected
  address, while retaining explicit parameters for firewall/allow scopes.
- Made starter-thread exclusions generic and opt-in. The tool derives the installed
  list at configuration time and can exclude a named variable without embedding an
  HFSS or HTCondor-version-specific list.
- Updated administrator and architecture documentation, marked exploratory HFSS
  records as historical, and pointed current operations at the consolidated tool.

## Rationale

One idempotent configuration block prevents later setup steps from silently
overwriting role settings, resource declarations, or execute-directory attributes.
Stable manager naming and automatic interface selection survive ordinary DHCP
changes without committing a particular cluster's address or computer name.

## Impact

- Administrators now run one parameterized PowerShell tool per pool node instead of
  choosing scripts named after an old machine layout.
- Existing nodes should be reapplied with the new tool after choosing a stable
  manager name and their local resource limits.
- The project runtime remains unchanged: it continues to submit slot-user jobs and
  never imports administrator tooling.

## Follow-Up

- Validate the generic configuration against each live pool before retiring its
  previous local configuration backups.
