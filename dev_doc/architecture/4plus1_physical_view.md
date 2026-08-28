# 4+1 physical view

## Submit host

The submit host contains the installed yadof distribution and one or more writable
workspaces. Local and fast evaluation run on this host. Distributed evaluation also
requires HTCondor client access, but scheduler deployment remains outside yadof.

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
  .yadof/                  workspace identity and campaign lock
  <configured state>       checkpoints, logs, and tool output
```

User-created task, debugging, and export directories may coexist with reserved
framework paths. They become task inputs only when explicitly referenced.

Recorded segments are immutable and atomically published. Temporary, unrelated, or
corrupt files are not treated as successful evidence. Fast evaluations have no
durable candidate directory but enter the same recorder through owned memory-backed
rawData.

## Package artifacts

The wheel contains installed framework code and declared package resources. Package
resources remain read-only and are never copied wholesale into jobs. Optional
viewer dependencies and source stay on the user/submit host. Source-checkout-only
examples, benchmark automation, administrator resources, and generated runtime
artifacts are excluded from installed runtime behavior.
