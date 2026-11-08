# File blueprint: src/yadof/tools/user_tools/aedt_parameters/parameter_extraction.py

## Intent

- Convert optimization-enabled variables in one HFSS AEDT project into the current
  workspace `job_template/parameters_constraints.py` contract without requiring
  AEDT when the project text is directly parseable.

## Functionalities

- Resolve an explicit project relative to the workspace root, or require exactly
  one `.aedt` file in `job_template/` when no project is supplied.
- Require confirmation before replacing an existing parameter file.
- Directly decode AEDT bytes with surrogate escapes and recognize both standalone
  Optimetrics variable records and attributes embedded in `VariableProp(...)`.
- Include only variables marked `i=true`, sort names case-insensitively, use
  `Min`/`Max` for continuous ranges, and preserve comma-separated discrete `Level`
  values.
- Fall back to a fresh PyAEDT HFSS session only when direct parsing yields no usable
  parameters; infer a single design or honor the caller's explicit design.
- Generate current `Parameter(name, ranges, unit=...)` declarations, preserve the
  rest of an existing current-format task file, archive it, and atomically publish
  the replacement.
- `read_aedt_parameters(project)` provides strict, text-only previews without a
  workspace or simulator fallback. It reads only Include-checked (`i=true`)
  records from the exact `OptimizationSetup1/Variables` block. Inclusion, ranges
  and units all come from those records, with no search of global properties,
  starting points or another setup. `export_aedt_parameters(project, backup_dir=...)`
  generates a fresh current-format module with empty constraints beside the project,
  even when an existing file is malformed or uses a retired format. Old bytes are
  preserved in the caller-selected backup directory.

## I/O Format

- `extract_parameters(workspace, project=None, design=None, graphical=False,
  verbose=False, confirm=False)` accepts a workspace-like value and extraction
  controls.
- It returns frozen `ParameterExtractionResult(project_path, parameter_count,
  parameter_file, backup_file, used_direct_parser)`.
- Backups are unique timestamped files below
  `.yadof/tool_output/parameter_history/`; the destination is
  `job_template/parameters_constraints.py`.
- The CLI maps these controls to `yadof task hfss extract-parameters --workspace ...
  [--project ...] [--design ...] [--graphical] [--verbose] --yes`.
- The direct preview returns a tuple of frozen `OptParam(name, ranges, value, unit)`
  values. The project-only preview does not read current values, so `value` is
  NaN; bounds and units are authoritative. The direct export returns `ParameterExtractionResult` with
  `used_direct_parser=True` and project-adjacent output paths.

## Non-Obvious Techniques

- Direct parsing is primary because AEDT project syntax needed here is textual and
  this path avoids a licensed simulator launch. AEDT may contain arbitrary embedded
  bytes, so UTF-8 surrogate escapes keep ASCII record syntax searchable.
- Recognize UTF BOMs and AEDT backslash continuations. Bound inline matching at
  the end of `oa(...)`, respecting quoted parentheses, so `sa`/`ta` cannot overwrite
  optimization flags or bounds for the general workspace CLI. The desktop path
  first isolates one exact named setup, then its Variables block, tracking nested
  `$begin`/`$end` markers rather than ending at the first child block. Missing,
  repeated or malformed blocks and duplicate selected-block variable records are
  errors. It never inspects VariableProp records to fill in values or units.
  Strict preview rejects unusable/non-finite enabled bounds and mixed explicit
  units and enumerates integer intervals into at most 100000 discrete values.
  The workspace CLI retains its general parser and fallback behavior.
- Continuous `Level` can describe a wider sampling/focus envelope than the actual
  Optimetrics bounds; continuous output therefore uses `Min`/`Max`. A discrete
  `Level` list is itself the allowed value set.
- AST line metadata replaces only the top-level `PARAMETERS` assignment. Existing
  files must already import/call the current `Parameter` contract; the tool refuses
  implicit migration from retired formats.
- Both export paths compile generated source without executing it, flush a unique
  same-directory temporary file, copy the old bytes into an exclusively created
  backup, then publish through `os.replace`. Backup failure leaves the old file
  intact; publication failure retains both the old file and its backup. Temporary
  files and partial failed backups are cleaned. Backup filenames combine a
  microsecond timestamp with collision handling and never replace prior backups.
- PyAEDT imports are local, output can be suppressed, the fallback session is always
  released, and graphical mode is opt-in.

## Mutability Profile

- Confirmation, workspace path ownership, backup-before-replace, atomic publish,
  and current-contract validation are stable safety boundaries.
- Keep the CLI below the explicit `task hfss` namespace so another software's
  extractor can use its own namespace without ambiguity.
- Direct AEDT syntax recognizers may expand as new files expose additional current
  encodings, but must retain focused parser and CLI regression tests and must not
  turn simulator fallback into the default path.
