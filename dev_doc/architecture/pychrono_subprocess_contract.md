# PyChrono subprocess contract

## Status and scope

This is the canonical protocol contract implemented by the packaged task-local
`chrono_com.py` Project Chrono adapter. The adapter is listed and copied through
the normal packaged-adapter resource workflow.

The contract applies wherever a yadof task launches PyChrono: a prepared local
workflow, an HTCondor execute workflow, or a fast task kernel. PyChrono is an
external simulator installation. The yadof-side process must not import
`pychrono`; the child must not import yadof. The boundary carries JSON and NPZ
files, never pickle or live Python objects.

The evidence chain remains:

```text
normalized/assigned parameters
  -> versioned JSON request
  -> task-owned PyChrono child process
  -> schema-compatible rawData/*.npz + versioned JSON result
  -> current workspace calc_cost.py
  -> objective tuple
```

Mechanical models, bodies, loads, solver choices, measurements, and objective
policy remain task-owned. The packaged adapter owns only the invariant launch,
isolation, protocol, validation, diagnostic, timeout, and publication mechanics.

## Protocol identity and constants

The first protocol version uses these exact values:

| Item | Value |
|---|---|
| Protocol name | `yadof.pychrono-subprocess` |
| Protocol version | JSON integer `1` |
| JSON encoding | UTF-8, no BOM |
| Request filename | `request.json` |
| Result filename | `result.json` |
| Child rawData directory | `rawData/` |
| Maximum encoded request | 1 MiB (`1_048_576` bytes) |
| Maximum encoded result manifest | 256 KiB (`262_144` bytes) |
| Retained stdout tail | 64 KiB (`65_536` bytes) |
| Retained stderr tail | 64 KiB (`65_536` bytes) |

JSON producers must reject non-finite numbers instead of emitting `NaN`,
`Infinity`, or `-Infinity`. JSON consumers must reject malformed UTF-8, duplicate
object keys, a non-object document root, or content beyond the applicable size
limit. Unknown fields may be preserved as diagnostics but must not change the
meaning of required fields. A change to a required field or its meaning requires a
new integer protocol version; there is no best-effort downgrade.

## Runtime and entry-point resolution

The parent resolves the child interpreter only from the explicit machine-level
`YADOF_PYCHRONO_PYTHON` value supplied to the running evaluation environment. It
must:

1. distinguish an absent/empty value as `runtime_not_configured`;
2. reject a non-absolute path as `runtime_invalid`;
3. reject a missing path, directory, or non-executable file as `runtime_invalid`;
4. use the resolved absolute file directly.

The parent must not search `PATH`, run `conda`, activate an environment, mutate its
process-global `PATH`, inspect a user shell profile, or fall back to
`sys.executable`. On POSIX, the executable permission must be present. On Windows,
the configured target is expected to be the dedicated `python.exe` file and must be
launchable as a normal executable. The Windows child-only DLL search path described
below supports that already-selected runtime; it is not an interpreter-selection
mechanism.

The task supplies one child script, conventionally `chrono_worker.py`. The adapter
resolves it against the task payload, requires an existing regular file, and
reports `worker_missing` before launching when it is absent. The child script is
task-owned and may import PyChrono. It must not import yadof.

## Candidate scratch ownership

Each logical evaluation owns a distinct, newly created scratch directory. No two
concurrent evaluations may share it. Its minimum layout is:

```text
<candidate-scratch>/
  request.json
  result.json
  rawData/
```

The adapter owns creation and cleanup. The child owns only content below this
candidate scratch while it is running. The shared Conda prefix, task-source
directory, another candidate's scratch, and the final yadof history are read-only
from the child's perspective. The shared prefix must never receive task data,
caches, bytecode, logs, or mutable state.

The result manifest is the publication marker and is written last. The child writes
each NPZ and the result through a same-directory temporary file followed by atomic
replacement. Temporary or partial files are not evidence. The parent treats every
file as untrusted until the process has exited successfully and the complete result
has been validated.

For prepared local/distributed workflows, the candidate scratch must be below the
prepared job or an explicitly assigned execute scratch root and remain disjoint
from the job's final flat `rawData/`. For fast mode it is the candidate directory
provided by the fast evaluation context. Fast scratch has no durable job or
recovery meaning and is removed after its validated NPZ data has been copied into
memory.

## Launch command and argument handling

The child is launched with an argument vector, never through a shell or a manually
quoted command string:

```text
<absolute-python> -u <absolute-chrono-worker.py>
  --request <absolute-candidate-scratch/request.json>
  --result <absolute-candidate-scratch/result.json>
```

The real command is one flat argument list; the line break above is illustrative.
The operating-system subprocess API owns quoting, including paths containing spaces
or non-ASCII characters. `shell=True`, command concatenation, and an environment
activation wrapper are forbidden. The child working directory is the candidate
scratch.

## Controlled child environment

Build a per-launch copy of the evaluation environment; never mutate `os.environ`
globally. Apply these exact changes to the child copy:

- remove every inherited key whose case-folded name is `pythonpath`;
- set `PYTHONNOUSERSITE=1`;
- set `PYTHONDONTWRITEBYTECODE=1`;
- set `TEMP` and `TMP` to the absolute candidate scratch path.
- on Windows only, replace case-insensitive `PATH` keys in the child copy with one
  canonical `PATH` whose leading entries are the resolved runtime prefix,
  `Library/mingw-w64/bin`, `Library/usr/bin`, `Library/bin`, `Scripts`, and `bin`
  below that prefix, followed by the inherited child `PATH` value.

Do not set `PYTHONHOME`, change the POSIX child `PATH`, or activate Conda. Other
task/administrator-provided environment values remain visible unless a future
version explicitly classifies them as unsafe. The Windows prefix entries provide
process-local native-DLL discovery required by released PyChrono builds; they do not
change the parent/user/machine environment. The absolute interpreter remains the
only runtime selection mechanism.

The child must observe its current working directory and both temporary-directory
variables as its own candidate scratch. It may report interpreter/version/runtime
provenance in result diagnostics, but it must not report secrets or the full child
environment.

## Request schema

Version 1 `request.json` has this shape:

```json
{
  "protocol": "yadof.pychrono-subprocess",
  "protocol_version": 1,
  "request_id": "job-or-evaluation-unique-id",
  "parameters": {
    "assigned": {"mass": 2.5, "contact_model": "SMC"},
    "normalized": {"mass": 0.25}
  },
  "context": {
    "backend": "local",
    "evaluation_id": "job-or-evaluation-unique-id",
    "scratch_dir": ".",
    "rawdata_dir": "rawData"
  },
  "task_context": {}
}
```

Required rules:

- `protocol`, `protocol_version`, and a non-empty `request_id` are required.
- `parameters.assigned` is a JSON object keyed by non-empty parameter names.
- `parameters.normalized` is optional. When present, it is an object whose values
  are finite JSON numbers in `[0, 1]`. It contains only coordinates actually known
  to the caller; a prepared assigned snapshot is not required to reconstruct
  normalized values.
- Assigned values and `task_context` are JSON-only trees of objects, arrays,
  strings, booleans, null, and finite numbers. Object keys are strings. The child
  must not interpret strings as Python expressions or filesystem paths unless the
  task-specific schema explicitly assigns that meaning.
- `context.backend` is exactly `fast`, `local`, or `distributed`.
- `context.evaluation_id` is a non-empty diagnostic identity. It does not authorize
  filesystem access.
- `context.scratch_dir` and `context.rawdata_dir` are the exact relative values `.`
  and `rawData`. The launch working directory supplies their absolute location.
- `task_context` is an optional task-owned JSON object. Protocol machinery passes
  it through without assigning mechanical meaning.

The parent validates and publishes the request atomically before launching. The
child validates the protocol and request before importing PyChrono or constructing
a model, so malformed/version-mismatched requests fail cheaply.

## Result schema and exit codes

On handled success or failure, the child writes `result.json` atomically. A success
manifest has this shape:

```json
{
  "protocol": "yadof.pychrono-subprocess",
  "protocol_version": 1,
  "request_id": "job-or-evaluation-unique-id",
  "status": "ok",
  "rawdata": [
    {
      "path": "rawData/response.npz",
      "size_bytes": 1234,
      "sha256": "64-lowercase-hex-characters"
    }
  ],
  "diagnostics": {}
}
```

An handled error manifest uses `status: "error"`, an empty `rawdata` array, and:

```json
{
  "error": {
    "code": "task_error",
    "message": "bounded human-readable summary"
  }
}
```

`error.code` is a stable task-child category; the parent preserves but does not
reinterpret it. `diagnostics` must be a JSON object and is bounded by the total
manifest limit. Tracebacks and long native diagnostics belong in captured stderr,
not unbounded JSON.

Child exit codes are:

- `0`: success; requires a valid `status: "ok"` manifest and at least one valid NPZ;
- `2`: request, usage, or protocol rejection;
- `3`: handled model/simulation/task failure;
- `4`: handled rawData/result publication failure;
- any other nonzero value or signal: unclassified child process failure/crash.

No nonzero exit can publish evidence. A valid error manifest plus an expected
nonzero code is `child_reported_error`; a nonzero exit without a valid error
manifest is `child_process_error`. Exit zero with a missing/error/malformed
manifest is a protocol failure, not success.

The manifest `request_id` and protocol fields must exactly match the request. Every
`rawdata.path` is a POSIX-style relative path exactly one level below `rawData/`;
the basename must end case-insensitively in `.npz`, contain no separator, and be
unique ignoring case. Absolute paths, `..`, symlinks/reparse-point escapes, and
unlisted files are rejected. The observed file size and SHA-256 digest must match
the manifest before loading.

## NPZ evidence constraints

Every listed NPZ must satisfy yadof's current rawData schema and these trust-boundary
rules:

- load with `allow_pickle=False` only;
- contain a `values` or `data` main array and schema-versioned scalar JSON metadata;
- match the metadata-declared shape and axes;
- use no object, structured, or pickled arrays;
- use finite real numeric main/axis values for successful Project Chrono evidence;
- remain a direct, regular file in the candidate `rawData/` directory;
- leave no extra directory or unlisted regular file in that directory.

The child converts PyChrono/native values to portable NumPy arrays before saving.
It does not write `cost.json`, objective values, Python objects, or a yadof archive.
An invalid or incomplete NPZ invalidates the whole evaluation; valid siblings from
that child invocation are not accepted as partial evidence.

## Diagnostics and failure taxonomy

Stdout and stderr are diagnostic channels, not protocol channels. The parent drains
both without deadlock, decodes retained tails as UTF-8 with replacement for invalid
bytes, retains at most 64 KiB from each, and records whether earlier bytes were
discarded. A large diagnostic stream must not change a valid result into evidence
or permit a failed result to look successful.

The caller exposes one primary failure category plus the child return code,
bounded stdout/stderr tails, and any validated error manifest:

| Category | Meaning |
|---|---|
| `runtime_not_configured` | `YADOF_PYCHRONO_PYTHON` absent or empty |
| `runtime_invalid` | interpreter value not an absolute executable file |
| `worker_missing` | task child entry point absent/not a file |
| `request_invalid` | request cannot satisfy/encode the v1 schema |
| `launch_failed` | OS refused to create the child process |
| `cancelled` | caller cancellation terminated the child tree |
| `timeout` | child exceeded the explicit child timeout |
| `child_reported_error` | valid error manifest plus nonzero handled exit |
| `child_process_error` | nonzero/signal exit without a valid error manifest |
| `result_missing` | exit zero without a result manifest |
| `result_malformed` | result exceeds limit or is invalid UTF-8/JSON/schema |
| `protocol_mismatch` | protocol name/version differs |
| `request_mismatch` | result `request_id` differs |
| `output_path_invalid` | result path escapes or violates flat naming |
| `rawdata_missing` | listed output absent or no output listed |
| `rawdata_invalid` | size/hash/NPZ/rawData schema/content invalid |

The adapter may add details, but it must preserve these distinctions. None of these
failure cases contributes valid rawData or a normal task cost; yadof's existing
per-individual failure path supplies the correct-width infinite execution-failure
sentinel.

## Timeout, cancellation, and process trees

The adapter accepts an explicit child timeout independent of the outer yadof
workflow timeout. A missing child timeout means the outer backend owns the only
deadline; it does not mean that a timed-out outer workflow may leave the child
running. Cancellation and child timeout use the same termination path.

Launch the child in a new process group/session where the platform supports it.
On timeout/cancellation, terminate the exact child process tree, wait only a bounded
cleanup interval, then hard-kill survivors. On Windows the self-contained worker
side may use `taskkill /PID <pid> /T /F`; on POSIX it uses the new process group.
Capture known descendant PIDs before termination when possible so a quickly exiting
root does not orphan them. The outer local/fast backend's existing exact-tree
termination remains a second safety layer.

After timeout/cancellation, ignore and remove partial result/rawData content. A
child or descendant that ignores graceful signals cannot keep the evaluation
pending. Cleanup failure is diagnostic metadata and never converts the outcome to
success.

## Backend-equivalent publication

Validation through manifest digest/paths and NPZ schema is identical in every
backend.

- **Local/distributed prepared workflow:** after full validation, copy or atomically
  replace only the listed direct NPZ files into the prepared job's final flat
  `rawData/`. Then the existing `worker_misc.py` lifecycle and submit-side validator
  handle packaging/transport/recording. The task child never writes final history.
- **Fast:** load every validated NPZ with `allow_pickle=False`, copy its arrays into
  a named in-memory mapping, run the normal named-rawData validation, and only then
  remove candidate scratch. The fast kernel returns that mapping plus bounded JSON
  diagnostics; it never returns cost.

The same NPZ basename, arrays, metadata, units, and meaning must reach the common
recording/current-cost path. Backend transport details must not change scientific
evidence.

## Concurrency and immutability

Concurrent evaluations may use the same absolute interpreter and read-only Conda
prefix. They must use different request/result files, working directories,
temporary-directory environment values, and rawData directories. Adapter code must
not call process-global `chdir`, mutate process-global environment variables, or
use a shared fixed output filename outside candidate scratch.

Task code must not install packages, write bytecode into the task/shared runtime,
or update the shared environment. Runtime provisioning, ACLs, and host availability
remain administrator responsibilities. An HTCondor job may use a configured
absolute interpreter only when that exact execute host can access it; path equality
on another host is not proof of provisioning.

## Executable conformance tests

`tests/test_pychrono_subprocess_contract.py` is the executable contract and adapter
acceptance suite. It launches task-owned fake workers through the public packaged
adapter surface and an absolute Python executable, with no Miniforge or PyChrono
installation. It covers:

- successful JSON/NPZ exchange through paths containing spaces;
- removal of inherited `PYTHONPATH`, user-site/bytecode controls, scratch temp, and
  Windows child-only runtime-prefix DLL search entries with inherited-path retention;
- bounded large-stderr diagnostics;
- malformed/version-mismatched/path-escaping/missing/invalid output;
- handled child error versus an unreported crash;
- timeout with descendant-process termination;
- concurrent evaluations with isolated scratch and evidence.

These cases are the protocol acceptance set for the adapter's public launch
surface. Real mechanics validation remains a separate integration task governed by
the user documentation's cost- and risk-based execution policy.
