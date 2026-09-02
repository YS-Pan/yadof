# File blueprint: standalone ngspice adapter

Run an explicitly configured ngspice executable against a task-local netlist,
validate solver output, parse real AC/transient raw data, and return structured
numeric arrays and diagnostics without depending on installed yadof in task code.

`NgspiceSimulationError` is a specific `NgspiceError` subtype for solver failure
and solver timeout. Missing executable, task interface, and raw-format errors
retain the ordinary error type. A task may explicitly declare the simulation
subtype in `PHYSICAL_FAILURE_TYPES` so a real oracle can represent physical
failures consistently without masking programming or deployment faults.

Keep the benchmark's copied standalone adapter synchronized with this resource.
