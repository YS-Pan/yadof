# File blueprint: src/yadof/tools/hfss/parameter_extraction.py

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

## Non-Obvious Techniques

- Direct parsing is primary because AEDT project syntax needed here is textual and
  this path avoids a licensed simulator launch. AEDT may contain arbitrary embedded
  bytes, so UTF-8 surrogate escapes keep ASCII record syntax searchable.
- Continuous `Level` can describe a wider sampling/focus envelope than the actual
  Optimetrics bounds; continuous output therefore uses `Min`/`Max`. A discrete
  `Level` list is itself the allowed value set.
- AST line metadata replaces only the top-level `PARAMETERS` assignment. Existing
  files must already import/call the current `Parameter` contract; the tool refuses
  implicit migration from retired formats.
- New content is written to a same-directory temporary file, the old file is copied
  to history, and `os.replace` performs the final atomic publication. The temporary
  file is cleaned on all exits.
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
