# 2026-09-05 07:55 - Preserve surrogate research handoff context

## Context

The user is transferring the unfinished CAE/general-surrogate study from the
`Improve CAE surrogate performance` task to a new GPT-6 Astra task. Its research
ledger lived outside the checkout at outer-workspace
`temp/cae-surrogate-progress.md`. The user requested that this existing evidence
be moved into repository context and that the successor maintain a separate log.

## Change

- Moved the existing English ledger to
  `context/20260905_075552_cae-surrogate-sol-research-progress.md`, relative to
  `dev_doc/`, without changing its bytes. Its SHA-256 is
  `4f4710f5e54c7829349a81a9309e2160a1bad674bcbf44cbf364f5a87c63f819`.
- Updated the task-owned Goal contract and prompt in the outer workspace to
  English, referenced the context location, and reserved a new Astra progress
  log. The archived ledger remains historical evidence, including its revoked
  optimizer-scope amendment; it does not become current authorization.
- Audited existing surrogate-viewer documentation and the old task's recorded
  actions. User and developer entry routes already exist; the old task read the
  operational instructions. No CLI invocation or explicit rejection of that tool
  was found in the inspected records. No duplicate documentation route was added.
- Documented the available headless tool in the task-owned handoff with its
  actual applicability: summary discovered ten compatible checkpoints in the
  clean current-CAE Chrono workspace, whereas the custom joint/tail draft's
  workspace returned `NO_COMPATIBLE_CHECKPOINT`.

## Validation and impact

The move's source and destination hashes match, and the former source path is
absent. The three installed terminal-mode help commands succeeded. Read-only
summary probes returned the expected compatible-CAE result and structured
unsupported-draft result; they neither trained models nor launched simulators.
Task-owned probe outputs are retained outside the repository.

This is content-only context preservation and handoff maintenance. No algorithm,
runtime behavior, scientific acceptance conclusion, documentation mechanism, or
existing route changed. UTF-8, references, evidence hashes, and Git whitespace
checks provide proportionate validation under the documentation-only exception;
no wheel replacement or software test run is required for this relocation.

The research remains unfinished. The successor's acceptance contract and fresh
working log remain outside this historical context record.
