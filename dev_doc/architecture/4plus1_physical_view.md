# 4+1 physical view

## Submit host

The submit host contains the installed yadof distribution and one or more writable
workspaces. Local and fast evaluation run on this host. Distributed evaluation also
requires HTCondor client access, but scheduler deployment remains outside yadof.

Normal wheel installation places `condor_gui.pyw` beside `yadof-gui.exe` in the
Windows Python environment's `Scripts/` directory. Double-clicking the `.pyw`
invokes that executable and its installed framework, independently of the source
checkout, fixed drive letters, and the Python chosen by file associations.

Submit-side workspace job staging is distinct from execute-host scratch. Local
capacity observations may influence concurrency, but they are planning inputs rather
than task evidence.

## Execute hosts

HTCondor execute hosts receive self-contained prepared jobs and run them under
administrator-defined identity, profile, software, license, network, and scratch
policy. They need the task's runtime dependencies but do not receive or import the
yadof package.

Current administrator procedures and troubleshooting material live in
`admin_tool/admin_doc/htcondor/`; the executable node tool remains in
`admin_tool/htcondor_pool/`.

Submit, central-manager, and execute services can coexist on a host. The numbered
LAN tools under `admin_tool/htcondor_config/` add capabilities while preserving
existing services, declared resources, and pool affiliation. Explicit leave
removes those capabilities; these administrator operations remain outside the
installed framework and its runtime imports.

## External simulator runtimes

A simulator-specific Python environment is a separately provisioned executable
runtime on each host that may evaluate the task. It is selected explicitly and
remains read-only to ordinary task execution. Yadof does not activate that
environment, install itself into it, or share live Python objects with it.

Each invocation receives unique writable candidate scratch disjoint from the
shared runtime and final workspace evidence. The adapter publishes only complete,
validated rawData into the normal backend result. PyChrono provisioning and
validation procedures live in `admin_tool/admin_doc/pychrono/`; adapter use belongs
in `user_doc/adapters/chrono_com.md`.

## Prepared job contents

A prepared local/distributed job contains the assigned task inputs and the small
package-owned worker support required for lifecycle and evidence transport. It does
not contain submit-side cost or optimization code, a yadof distribution, or an
implicit copy of unrelated workspace content.

The job owns runtime artifacts and diagnostics only until accepted evidence is
copied under recorder ownership. Execute scratch and fast candidate scratch are
ephemeral and carry no durable history meaning.

## Durable workspace layout

```text
<workspace>/
  config.py
  submit/                  task cost and optimization composition
  job_template/            evaluate-side task definition and assets
  jobs/                    prepared local/distributed executions
  recorded_data/           immutable candidate evidence and metadata events
  .yadof/                  identity, campaign lock, active strategy, program completion
  <configured state>       checkpoints, logs, and tool output
```

User-created task, debugging, and export directories may coexist with reserved
framework paths. They become task inputs only when explicitly referenced.

Recorded segments are immutable and atomically published. Temporary, unrelated, or
corrupt files are not treated as successful evidence. Fast evaluations have no
durable candidate directory but enter the same recorder through owned memory-backed
rawData.

## Package artifacts

An administrator-built Windows MSI may additionally deploy a self-contained
`yadof_env` prefix and per-user launchers/shortcuts. The MSI owns only its program
files; explicit writable workspaces and external solver/pool environments remain
separate. This private runtime does not inherit system or user Python packages.
Its deployment builder remains under `admin_tool/windows_installer/`, outside
the framework wheel and runtime imports.

The wheel contains installed framework code and declared package resources. Package
resources remain read-only and are never copied wholesale into jobs. Optional
viewer dependencies and source stay on the user/submit host. Source-checkout-only
examples, benchmark automation, administrator resources, and generated runtime
artifacts are excluded from installed runtime behavior.
