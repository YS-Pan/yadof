# 2026-09-29 20:42 - Default Condor GUI workspace folder

## Context

Without `--workspace`, the HTCondor GUI filled its workspace field with the
current working directory itself. The checkout's initialized workspace lives in
the `workspace` folder below that directory.

## Change

Default the field to `Path.cwd() / "workspace"`. Preserve explicit `--workspace`
selection and the existing validation before running a campaign or viewing history.

## Impact

Launching the GUI with the checkout as its process working directory now selects its
`workspace` folder.
The CLI and other workspace defaults are unchanged.
