# Administrator Resources

`admin_tool/` contains resources for people who configure and maintain the environment
in which yadof runs. It is intentionally separate from `src/yadof/tools/`, which
contains only tools that users run while preparing, executing, or inspecting an
optimization campaign.

## Administrator Responsibilities

Administrators install yadof and its dependencies, and configure or maintain the
HTCondor cluster's software and hardware. They may run the scripts in this folder
because those scripts can change machine configuration, services, firewall rules,
worker resources, and execution directories.

## Contents

- `htcondor_doc/`: deployment policy, operational guidance, investigations, and
  historical evidence for the HTCondor environment.
- `htcondor_pool/`: executable Windows scripts for setting up, configuring, and
  diagnosing HTCondor manager and worker machines. Start with
  `htcondor_pool/README.md`.
- `pychrono_runtime/`: the pinned, auditable all-users Miniforge and PyChrono
  installation workflow. It requires a separately verified official installer and
  an explicit UAC-elevated run.

Users must not use these scripts to create or repair an environment. They should
use the already-configured environment through the user workflow and the tools in
`src/yadof/tools/`.
