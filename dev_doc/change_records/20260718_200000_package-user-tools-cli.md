# 2026-07-18 20:00 - Package User Tools CLI

## Context

- Cost/time plots, history cleanup, adapter copying, and HFSS parameter extraction
  were source-tree scripts rather than installed commands.

## Change

- Copied and adapted cost/time/history tooling into `yadof.tools`, with explicit
  workspace selection and current recorded-data APIs.
- Added `yadof view cost`, `yadof view time`, `yadof history clear`, `yadof task
  adapters`, `yadof task copy-adapter`, and `yadof task extract-parameters`.
- Packaged generic and HFSS adapters as immutable resources; copy and extraction
  operations write only to the selected workspace and retain parameter history.
- Removed the repository script entry points and covered confirmation, isolation,
  plotting, adapter collision, and extraction behavior with package tests.

## Rationale

- One CLI gives installed users stable discovery and error handling while explicit
  workspace arguments prevent tools from modifying an incidental current directory.

## Impact

- User-facing inspection and task setup no longer require repository paths or batch
  launchers.
- Destructive history cleanup requires both an explicit workspace and confirmation.
