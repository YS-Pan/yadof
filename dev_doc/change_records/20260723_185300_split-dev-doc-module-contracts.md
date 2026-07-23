# 2026-07-23 18:53 - Split Developer Documentation Module Contracts

## Context

- `dev_doc/README.md` combined the developer entry workflow with detailed contracts
  for six documentation modules, making the entry point unnecessarily long.
- Empty target pages already existed under `dev_doc/skill/` for those contracts.

## Change

- Kept `dev_doc/README.md` as the canonical entry for roles, reading order, the
  development environment, encoding, and cross-module maintenance.
- Moved detailed agent-document, architecture, blueprint, toDo/obsolete,
  terminology, and change-record contracts into their corresponding `skill/` pages
  and linked all six from the entry point.
- Updated the development architecture view and documentation blueprint to describe
  the split.
- Archived two automatic toDos whose default seven-day expiry had passed when they
  were read during this documentation context pass.

## Rationale

- Separating module contracts makes each rule set easier to find and maintain while
  preserving one mandatory entry point and reading order.
- Archiving the expired automatic toDos applies the existing stale-document contract
  without treating their cleanup guidance as active work.

## Impact

- Developer documentation readers must follow links from `dev_doc/README.md` to the
  module contract pages before collecting the corresponding context.
- Packaged documentation gains the six populated `dev_doc/skill/*.md` resources.
- No runtime API, task-authoring behavior, or administrator workflow changes.

## Follow-Up

- None.
