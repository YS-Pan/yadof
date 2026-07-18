# Module blueprint: evaluate_manager

`yadof.evaluate_manager` composes package worker support with one workspace task,
materializes assigned parameters, and executes locally or through HTCondor. Both
paths produce `JobResult`, validate flat rawData, record provenance, dynamically
derive costs, and isolate per-individual failures.

Distributed support preserves concrete CPU/memory/disk requests, workspace-local
calibration, bounded yadof memory/disk resubmission, automatic/fixed scheduler
execution limits, unlimited smoke, whole-generation deadlines, final ClassAd data,
output restoration, and Windows slot-user policy. Worker `sitecustomize.py` verifies
the installed yadof version before task execution. The module diagnoses but never
repairs HTCondor.
