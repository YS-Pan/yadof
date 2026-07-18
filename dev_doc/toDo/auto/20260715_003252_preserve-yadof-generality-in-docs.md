# Preserve Yadof's Generality And Report Code Violations

## Context
- Yadof is a general optimization framework. Its core identity is not limited to
  HFSS, to Ansys products, to any other vendor, or to workflows that use only one
  external program.
- A task may use one simulator, custom Python, or multiple programs through multiple
  task-local `*_com.py` adapters.
- Yadof is also not tied to one optimization task, simulator project, or task input
  file.
- Some documentation wording may accidentally present a current HFSS or Ansys
  example, or a current task file, as though it were a framework-wide limitation.

## Goal
- Documentation encountered during normal work should describe Yadof as
  task-agnostic, software-agnostic, vendor-agnostic, and able to coordinate
  multi-program workflows.
- HFSS, Ansys, or a single adapter should be identified as a current example or a
  task-specific implementation wherever that distinction matters.
- Task- or software-specific content discovered in code outside the permitted task
  files and explicitly specific directories should be reported without changing
  that code.

## Guidance

### Documentation Encounters

- When already reading or editing a document for another in-scope task, correct any
  nearby wording that incorrectly implies Yadof is dedicated to HFSS, Ansys, one
  vendor, one optimization task, one simulator project, or one `*_com.py` adapter.
- Make the documentation correction directly; no separate approval or report is
  required before fixing a matching documentation occurrence.
- Documentation may use `.aedt` as a file-type example, but it must not contain a
  concrete task filename.
- Preserve accurate task-specific instructions. A document dedicated to the active
  HFSS adapter may remain HFSS-specific; the correction is needed when wording turns
  that example into a limitation of Yadof itself.
- Prefer durable phrases such as "simulator or custom program," "one or more
  task-local adapters," and "HFSS is one supported example" when they fit the
  surrounding text.
- Do not search the repository solely for this cleanup and do not rewrite unrelated
  documentation just to make every paragraph generic.

### Code Encounters

- Never modify code as an automatic action for this toDo. If normal in-scope work
  exposes code that violates the boundary below, leave the code unchanged and
  report the finding in the current response with its file path and a concise
  explanation.
- These task files may contain content tied to a particular task or software:
  - workspace `job_template/calc_cost.py`
  - workspace `job_template/hfss_com.py`
  - workspace `job_template/workflow.py`
  - workspace `job_template/parameters_constraints.py`
- These directories are also exempt because their explicit responsibility is to
  hold reusable, software-specific settings, tools, or adapter references:
  - workspace task/environment settings
  - `yadof.tools` software-specific modules
  - packaged adapter resources
- Task- or software-specific content in any other code path harms Yadof's
  generality and must be reported. This includes concrete task filenames,
  assumptions tied to one simulator or vendor, and logic that assumes only one
  task-local `*_com.py` adapter.
- Do not report one of the permitted files or anything below the three exempt
  directories merely because it contains task- or software-specific content; that
  specificity belongs there. The exemption does not extend to `tests/` or
  to generic config/tools modules outside the `specific/` subdirectories.

## Completion Rule
- Correct each matching documentation occurrence that normal in-scope work exposes.
- Report each matching code occurrence outside the permitted files and exempt
  directories, but do not modify it under this automatic toDo.
- Keep this automatic toDo active for other incidental occurrences until its
  automatic obsolete policy archives it; one local correction does not imply that
  every document has been reviewed.
