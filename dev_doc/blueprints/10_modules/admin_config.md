# Module blueprint: administrator cluster configuration

The root `admin_config.pyw` imports `admin_tool.cluster_config.app`. Administrator
code stays outside the user wheel and core imports; MSI stages the launcher,
administrator subtree and a relative private-runtime `yadof-admin.exe` launcher.

`model.py` owns typed settings, STCP proxy/visitor collections, validation, native
Condor generation, frpc TOML serialization/import, legacy metadata cleanup and
ClassAd adaptation. GUI state JSON stores selections/topology without credentials;
native FRP configuration alone owns secrets. Role and execution are independently
selectable, except worker requires execution. LAN uses selected local IPv4 and an
explicit manager endpoint. STCP uses shared ports, loopback private addresses and
one common private-network name, with unique node ports and symmetric visitors.
CCB is cleared. Runtime eviction owns PREEMPT, STARTD.PREEMPT and retirement policy.

`runtime.py` discovers effective native configuration sources, builds a single-local
plan, validates it using native parsers, snapshots file/lifecycle state, applies
atomically per file, and rolls back on failure. Dynamic includes are rejected.
LOCAL_CONFIG_FILE uses existing Windows short directory paths when needed because
its parser splits on whitespace. Old loaded YADOF_* metadata and attribute
references are removed, retaining unrelated native settings. Staging, backups and
JSON live below ACL-restricted ProgramData/Yadof.
Cleanup processes logical backslash-continuation entries, ignoring whole-line
comments within continuations. It filters complete legacy names from advertised
attribute lists while preserving other attributes, literal strings and executable
paths. Real macro references (including inside strings) and unquoted ClassAd
references that survive managed replacement stop planning with source path,
first entry line, native key and referenced legacy names, without exposing values.

The PowerShell helper manages only the local condor service and Yadof-frpc startup
task, and prepares execute-directory ACLs for slot accounts. The task runs as
SYSTEM. Leaving clears routing, disables local components and retains data. Failed
startup restores files and lifecycle; new execute directories/ACL grants remain.

Tk stays on the main thread. Loading, polling and application run on workers and
return through a queue. Polling is scheduled every ten seconds and never overlaps
itself or an apply. Tab selection is independent of connection mode. A single save
applies the complete form. Local address files remain readable during collector
failure, which clears stale rows. No Machine column appears. Offline tests use
synthetic native configs and deterministic lifecycle failures.
