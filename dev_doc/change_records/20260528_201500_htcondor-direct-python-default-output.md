# 2026-05-28 20:15 - HTCondor Direct Python Default Output

## Context
- Windows workers cannot reliably execute `.py` files directly under HTCondor, so the submit file must use an explicit Python executable.
- A generated CMD launcher caused Windows command parsing errors in the worker environment.
- Listing optional outputs such as PyAEDT `batch.log` in `transfer_output_files` can hold jobs when the optional file is absent.

## Change
- Kept the HTCondor submit file on direct Python execution: `executable = <worker python>` and `arguments = workflow.py`.
- Removed the generated CMD launcher path.
- Omitted `transfer_output_files` so HTCondor returns generated outputs by default, including `batch.log` when PyAEDT creates it, without creating or clearing `batch.log`.
- Left `transfer_executable = False` because the Python executable is installed on each worker.
- Read returned stdout/stderr tails with a Windows-codepage fallback so localized command errors remain readable in job metadata.

## Consequences
- Worker command syntax no longer depends on `cmd.exe`.
- Optional PyAEDT logs can return when generated, while missing optional outputs should not create transfer holds.
- Existing submitted jobs are unchanged; clear old held jobs and resubmit after syncing this code to the submit machine.
