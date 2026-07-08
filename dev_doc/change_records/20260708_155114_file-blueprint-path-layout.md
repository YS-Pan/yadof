# 2026-07-08 15:51 - File Blueprint Path Layout

## Context
- File-level blueprints under `dev_doc/blueprints/20_files/` encoded source paths in a single filename, such as `project_surrogate_runtime.py.md`.
- This made the folder harder to scan and did not match the actual source tree shape.

## Change
- Moved file-level blueprints into a directory hierarchy that mirrors source paths under `blueprints/20_files/`.
- Updated the dev-doc reading and maintenance rules to require mirrored source-path folders for future file-level blueprints.
- Updated the development view and dev-doc blueprint to document the new layout.

## Rationale
- Mirroring source paths makes file-level documentation easier to find and avoids long synthetic filenames that duplicate path information with underscores.

## Impact
- Existing file-level blueprints now live at paths such as `dev_doc/blueprints/20_files/project/surrogate/runtime.py.md`.
- Future file-level blueprints should append `.md` to the source filename inside the mirrored folder path.

## Follow-Up
- None.