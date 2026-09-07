# Blueprint: surrogate/amplitude_gp/settings.py

## Contract

One frozen, slotted `AmplitudeGPSettings` owns every scientific factory parameter.
Defaults and interpretation are normative in
[amplitude_gp.md](../../../../../../../user_doc/amplitude_gp.md).
Validate positive integral rank/cap/iteration/sample values, uint32 seed, finite
real transforms and scales, bounded fractions and supported Matérn smoothness.
Reject booleans as numbers. Positive ordered kernel bounds must enclose their
initial values; canonicalize accepted bounds to tuples and numeric values to
built-in types. The shared default is immutable. `semantic_parameters()` returns
JSON-compatible complete settings; no mutable global model policy, backend
imports or workspace reads occur here.
