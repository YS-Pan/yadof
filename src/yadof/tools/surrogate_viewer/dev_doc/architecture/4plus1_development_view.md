# 4+1 development view

## Source Layout

```text
src/yadof/tools/surrogate_viewer/
  __init__.py               lazy optional backend exports
  app.py                    application coordinator and module CLI entry
  __main__.py               python -m yadof.tools.surrogate_viewer entry
  backend/
    __init__.py             public viewer-backend exports
    checkpoints.py          checkpoint discovery/loading/inference
    rawdata.py              rawData schema and plotting adapters
    types.py                immutable transfer and aggregate types
    workspace.py            records, prediction facade, audit orchestration
  ui/
    heatmap.py              audit tab and last-complete state
    interactive.py          interactive controls and selection state
    plots.py                Matplotlib components
    style.py                visual constants and ttk styles
    widgets.py              shared toggles, scrolling, and keyboard controls
  dev_doc/                  relatively independent viewer documentation
tests/test_surrogate_viewer.py
```

## Development Rules

- Keep `app.py` as a coordinator; tab-specific widgets belong in their tab module.
- Keep yadof record/checkpoint/rawData mechanics below `backend/`.
- Add shared helpers only after two real callers require identical semantics.
- Keep transfer values explicit and immutable rather than passing live Tk widgets
  or loaded model objects across boundaries.
- Do not create a generic `utils.py`; place helpers with the domain contract they
  implement.
- Preserve the `yadof.tools.surrogate_viewer.backend` import surface when splitting
  internal files.
- Keep the viewer package root and yadof CLI parser light; optional GUI/model
  dependencies load only after the viewer is selected.
- Treat unrelated dirty-worktree changes as user-owned.

## Dependency And Installation Rules

The viewer is part of the yadof wheel and is executed from the repository sibling
`.venv` only after building and force-reinstalling that wheel. Its optional
dependency group is `viewer` (Torch + Matplotlib); Tkinter comes from the Python
installation. Package-internal checkpoint/rawData imports remain confined to the
backend adapter. Core yadof runtime and CLI parser construction must not import the
viewer GUI or optional dependencies.

## Verification

The default focused checks are:

```powershell
& "..\.venv\Scripts\python.exe" -m compileall -q `
  src\yadof\tools\surrogate_viewer
& "..\.venv\Scripts\python.exe" -m pytest tests\test_surrogate_viewer.py -q
& "..\.venv\Scripts\python.exe" -m yadof.tools.surrogate_viewer --help
& "..\.venv\Scripts\yadof.exe" view surrogate --help
```

Changes to checkpoint loading or audit inference should also run a small seeded
sample against a real compatible workspace. GUI changes should construct a hidden
Tk root when possible and verify selector mappings, keyboard handlers, plot artist
type, title shape, axis bounds, and aspect behavior.

Do not start a simulator or optimization as part of viewer acceptance.

## Documentation Rules

`dev_doc/README.md` is the canonical viewer-documentation entry. Architecture is
read fully; blueprints are targeted. This compact tree intentionally has no local
toDo, obsolete, or change-record lifecycle; package-wide records remain in yadof's
root `dev_doc/`.
