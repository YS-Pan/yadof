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

- `admin_doc/`: administrator deployment, configuration, troubleshooting, and
  historical reference documentation. Start with `admin_doc/README.md`.
- `htcondor_pool/`: executable Windows scripts for setting up, configuring, and
  diagnosing HTCondor manager and worker machines. Start with
  `htcondor_pool/README.md`.
- `pychrono_runtime/`: executable scripts for the pinned, auditable all-users
  Miniforge and PyChrono installation workflow. The canonical procedure is in
  `admin_doc/pychrono/README.md`.

Users must not use these scripts to create or repair an environment. They should
use the already-configured environment through the user workflow and the tools in
`src/yadof/tools/`.
