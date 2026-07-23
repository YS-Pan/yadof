# File blueprint: src/yadof/evaluate_manager/worker_files/worker_misc.py

## Intent

Provide the small, dependency-free helper copied directly into every prepared job.
It lets task workflows read environment policy, create job-local profile/temp paths,
write atomic lifecycle metadata, report runtime identity, manage flat rawData, and
create the distributed transfer archive without importing yadof on an execute node.

## Public behavior

- Environment helpers parse bounded integer/float/bool values.
- `bootstrap_home_dirs()` redirects volatile profile/temp paths below the job.
- `runtime_identity()` captures user, Python, platform, scratch, and selected
  environment diagnostics without failing when `whoami` is unavailable.
- `write_json()` atomically replaces workflow metadata through a `.tmp` file.
- `prepare_rawdata_dir()` creates/clears the output directory, rejects nested
  directories, and removes a stale transfer zip.
- `raw_data_file_names()` reports sorted direct `.npz` filenames.
- `write_rawdata_transfer_zip()` always publishes the requested zip atomically,
  stores direct `.npz` members with basename-only archive names, and raises after
  publication if any directory or non-`.npz` entry exists.
- `RAWDATA_SCHEMA_VERSION` lets the packaged generic workflow write current rawData
  without importing yadof.

## Dependencies and constraints

The file uses Python standard library only and is copied as a plain file beside
`workflow.py`. It must remain executable under the worker Python versions supported
by the package and must not import yadof, submit-side config, recorded data, or cost
logic. Its archive is transport-only; durable archival remains recorded_data's job.

## Invariants

- `rawData/` is flat and contains only direct `.npz` files.
- `rawData.zip` members never contain `rawData/` or any path separator.
- Archive and metadata replacement do not expose partial target files.
- Helper failures remain visible to workflow/Condor rather than silently omitting
  invalid output.
