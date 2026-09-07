# Blueprint: surrogate/amplitude_gp/component.py

## Contract

Provide the lightweight immutable `AmplitudeGPComponent` and explicit
keyword-only `amplitude_gp()` factory. One settings value controls validation,
semantic identity, training, state recovery and prediction. Factory construction
loads no GP backend. Validate selected optional distributions on use.

Implement the shared deterministic component protocol and explicit low-level
fit/start-fit/recover/predict operations by lazy calls into the independent
runtime/scheduler. Caller-owned data, context snapshot and session must pass
unchanged. Selection requires compatible raw content, schema, parameters,
settings, strategy, runtime and priority interpretation, and returns the typed
rawData/current-cost DTO. Expose neither an initial GPSAF error estimator nor
posterior/applicability/readiness methods. The program owns whether it finishes
a current-prefix fit before selection or uses an allowed lagged model.
