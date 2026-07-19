# 4+1 scenarios

## New generic study

Install wheel, `yadof init PATH`, edit workspace config/task, `check`, run one local
smoke, `run`, then inspect cost/time. No repository path is required.

## Resume

`yadof run --workspace PATH --start-generation N --generations M` recovers current
history and workspace-local surrogate checkpoints, records the same campaign
generation context, and does not read another workspace.

## Real distributed campaign

The run command chooses smoke from workspace config unless explicit opposite CLI
flags override it. Smoke submits one unlimited midpoint individual. A finite result
permits generation zero; failure reports recent job metadata and submits no
generation. Skipped smoke activates configured synthetic calibration baselines.

## Failure

Prepare, workflow, timeout, submit, resource exhaustion, version mismatch, invalid
rawData, collection, and record errors are isolated per individual. Strict CLI mode
stops after an all-infinite generation and prints recent diagnostic summaries.

## Clean artifact

Build wheel/sdist, reject example/workspace/runtime/model members, install wheel
into a clean external environment, make site-packages read-only, and run help/version,
init/check/smoke/run/resume/view/history plus mocked distributed tests.
