# File blueprint: src/yadof/recorded_data/rawdata_v2.py

## Intent

- Convert validated file-backed or named memory rawData into recorder-owned,
  pickle-free NPZ evidence with conservative memory accounting.

## Functionalities

- Validate direct unique `.npz` basenames and copy array/scalar/string payloads into
  owned values.
- Encode/decode standard NPZ bytes with `allow_pickle=False` semantics.
- Estimate reservation bytes as encoded/owned resident size plus encoding peak and
  fixed overhead so admission covers queued through in-flight lifetime.

## Invariants

- No object array or arbitrary Python object crosses the storage boundary.
- Job or worker cleanup cannot invalidate an accepted envelope.
