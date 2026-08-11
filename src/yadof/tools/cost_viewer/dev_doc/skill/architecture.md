# Architecture Reading Contract

Read [the architecture index](../architecture/00_architecture_index.md) and every
linked architecture document in full before changing package boundaries, data
flow, public imports, plotting ownership, or future integration points.

Keep the package read-only with respect to recorded evidence. Optional plotting
dependencies must remain outside import-time paths used only for discovery or
summary generation.
