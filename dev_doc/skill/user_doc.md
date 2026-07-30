# User Documentation Contract

## Purpose And Boundary

`user_doc/` is the companion documentation home for the user's task-authoring and
runtime workflow. Its primary reader and executor is an AI coding agent acting
under a human user's direction. The user normally supplies goals, reviews
assumptions and results, and authorizes real execution rather than personally
following every documented command. The directory name identifies the role whose
workflow and authority the documents serve, not the literal reader.

Detailed task-authoring instructions belong under `user_doc/`; do not duplicate
them in `dev_doc/`. The user package-foundation document owns the installed command
surface and the boundary between immutable package code and writable task
workspaces. Its instructions are written directly for the user-directed AI agent.

## Reading Contract

Every full `dev_doc/` context pass must read `../../user_doc/README.md` and follow
its instructions. Framework changes can affect how a user's AI assistant prepares
tasks, so developer context is incomplete without that user-workflow pass.

Reading `user_doc/` alone must not trigger a `dev_doc/` pass. User-workflow task
setup documentation is allowed to stand on its own.

## Maintenance Contract

Update the relevant `user_doc/` pages whenever a framework or documentation change
alters task-authoring behavior, supported installed commands, workspace ownership,
configuration, validation, smoke testing, execution, adapters, workflow output, or
cost calculation. Keep administrator-only installation and HTCondor pool operations
under `admin_tool/`.
