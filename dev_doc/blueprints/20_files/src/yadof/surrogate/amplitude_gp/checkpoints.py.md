# Blueprint: surrogate/amplitude_gp/checkpoints.py

## Contract

Publish independent `amplitude-gp` state using shared atomic path/JSON primitives.
Each publication has a unique namespace manifest and artifact directory plus the
root generation alias. Write numeric arrays to a unique owned staging directory,
hash the NPZ, validate finite JSON, check cancellation, then rename and publish
the namespace manifest atomically. Cleanup is restricted to this call's checked
staging path; never remove another publication or evidence.

## Format and recovery

Format v2 also stores all fitted normalized inputs as one numeric array. Validate
its shape/range and require each GP's X to equal its declared selected rows.
The runtime can read this array for exact physical-record reconciliation;
unreleased v1 structural artifacts are incompatible and are never rewritten.

Version the JSON format. Record canonical model identity/settings/backend
versions, exact row/content/provenance identities, per-field transform/map/codec
descriptions, diagnostics and artifact SHA. Load with `allow_pickle=False`.
Require namespace confinement, exact schema, valid kernel bounds, positive
normalization scales, finite numeric arrays, normalized training X and expected
dimensions/cardinality. Reject unexpected arrays and malformed/corrupt artifacts.
Reconstruct only GP central means and PCA inverse transforms using the supplied
owned schema; do not store historical rawData or discover it implicitly.
The runtime chooses compatible manifests; this layer never selects training
rows, evaluates costs, fits or controls an optimization campaign.
