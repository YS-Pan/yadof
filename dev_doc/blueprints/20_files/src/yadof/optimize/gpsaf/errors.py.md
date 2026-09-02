# File blueprint: GPSAF prediction error

`GPSAFErrorState` belongs to an explicit program run. Retain up to five maximum
absolute error vectors, including an optional initial estimate; expose their
arithmetic mean. Observe only finite true outcomes paired with immutable prior
predictions. Reset on interpretation change. No recording or hidden history scan.
`initialize_gpsaf_error()` uses a runtime-checkable `GPSAFErrorEstimator` outside
selection. Neural components without an estimator use one prequential warmup;
beta waits while alpha can collect its first error batch.
