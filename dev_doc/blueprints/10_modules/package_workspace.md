# Module blueprint: package workspace lifecycle

## Intent

- Give an installed wheel a safe, repeatable way to create, diagnose, and explicitly
  smoke a user-owned task workspace while runtime modules migrate.
- Keep installed package resources immutable and all generated state under an
  explicitly selected workspace.
- Provide a vendor- and simulator-neutral starting point without mistaking
  initialization or diagnostics for real evaluation.

## Functionalities

- `yadof.resources` exposes bundled template names, roots, and decoded manifests by
  `importlib.resources` so wheel/zip-backed resources need no hard-coded install path.
- `yadof.workspace_manifest` reads and writes `.yadof/workspace.json`. Required
  fields are positive workspace/template/rawData schema versions, the creating
  yadof version, and a non-empty template name.
- `yadof.workspace_init` loads all template bytes in memory, validates manifest
  schema/name/safe unique destinations, detects exact existing targets or blocking
  ancestors, creates a sibling temporary workspace, and validates marker, config,
  parameter/objective modules, and workflow syntax before publish.
- A nonexistent root publishes by same-parent directory replacement. An existing
  safe directory publishes with exclusive file creation; the marker is last. Any
  failure removes only files/directories created by that attempt. Newly created
  parent directories and the stage are removed on pre-publication failure.
- Repeating init against a complete matching marker/template returns a confirmation
  without reading user files as a reason to rewrite them. Missing required files or
  a template/version mismatch is an actionable error, never an implicit repair or
  upgrade.
- `yadof.workspace_check` returns an immutable report of findings. It checks root
  accessibility, marker/schema/template provenance, required structure, effective
  config, task parameter/objective imports, workflow syntax, an already-present
  task-local rawData directory, and selected backend executable availability.
- Check imports parameter/cost task modules because their public contracts are
  dynamic Python, but it only parses workflow source. Backend discovery uses
  `sys.executable` or `shutil.which`; it does not invoke external commands.
- `yadof.smoke_test` classifies only exact bundled generic task bytes as safe for
  implicit execution. A task edit or additional asset/adapter is not guessed safe;
  the CLI requires `--real-task` before handing one midpoint row to the packaged
  local evaluator.

## I/O Format

- CLI:

  ```text
  yadof init [PATH]
  yadof check [--workspace PATH]
  yadof smoke-test [--workspace PATH] [--mode local] [--real-task]
  ```

  All default to the current directory. Init returns zero for a new or already
  complete workspace and one for conflicts/validation/publication errors. Check
  returns zero only when its report contains no error finding. Smoke returns zero
  only when its exactly-one run yields at least one finite cost.
- Default generated files:

  ```text
  config.py
  job_template/parameters_constraints.py
  job_template/workflow.py
  job_template/calc_cost.py
  .yadof/workspace.json
  ```

- The template manifest is JSON with `schema_version`, `name`,
  `template_version`, `rawdata_schema_version`, and an ordered `files` list of
  `{source, destination}` mappings.
- The workspace marker JSON contains `workspace_schema_version`, `yadof_version`,
  `template_name`, `template_version`, and `rawdata_schema_version`. It never stores
  package/resource/workspace absolute paths.
- The starter task uses generic names only. Its workflow is runnable pure Python/
  NumPy and writes schema-valid `rawData/response.npz` plus lifecycle metadata when
  explicitly executed, but neither init nor check executes it.

## Non-Obvious Techniques

- Read resource bytes before staging so missing/corrupt package data fails before
  any workspace mutation.
- Treat the marker as a commit record. It is published last into existing roots, so
  a partial file set is never falsely recognized as initialized.
- Use exclusive creation (`O_EXCL`) for every published file; an intervening user or
  concurrent writer becomes a failure instead of being overwritten.
- Track created files and directories separately. Rollback does not recurse through
  or delete pre-existing user directories and never touches unrelated content.
- Do not compare generated files with template bytes during repeated init as a
  pretext for reset. User ownership begins at first successful publication.
- Use the normal config/task validators so init/check cannot drift from runtime
  contracts. Parse workflow AST because importing it could start an expensive or
  destructive task.
- Keep CLI imports lazy. Help/version/docs remain usable in a minimal environment
  even though init/check require the base NumPy-backed job-template dependency.
- Keep check and smoke separate: check syntax-parses but never executes workflow;
  smoke advertises execution/expense, applies the real-task gate, and creates jobs.

## Mutability Profile

- Template content may evolve only with a new `template_version`. Existing user
  workspaces are never automatically upgraded.
- Marker and template-manifest schema versions are stable compatibility boundaries;
  changes require explicit readers/migration policy and tests.
- User `config.py` and `job_template/` files are highly mutable after init.
- Check findings/messages may become richer, but its report-only/no-workflow/no-
  repair boundary and exit-status meaning must remain stable.
