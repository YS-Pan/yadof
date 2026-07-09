# 2026-07-09 18:45 - Portability And Temp Directory Contract

## Context
- `dev_doc/obsolete/20260709 path.md` preserved two durable rules: do not hard-code machine-specific absolute paths, and do not require users to create new system environment variables before using the project.
- Those rules were not yet stated clearly in the current architecture and blueprint documents.
- The repository also needed a root scratch directory that exists in fresh checkouts while keeping scratch files out of git.

## Change
- Added the portability rule to the development and physical architecture views.
- Added the same rule to the project, config, and tools blueprints.
- Changed `.gitignore` so `temp/` contents are ignored while `temp/.gitkeep` remains tracked.

## Rationale
- Current documents should carry facts that still matter; `obsolete/` is archival and is not read by default.
- Requiring fixed install paths or new system environment variables would make the project fragile across workstations.
- Git cannot track a truly empty directory, so a `.gitkeep` placeholder is the standard way to preserve the root `temp/` directory.

## Impact
- Future code and tool changes should use repository-relative paths, explicit arguments, standard install discovery, or environment variables already provided by external installers.
- Disposable diagnostics and manual scratch files can be placed under `temp/` without being committed.