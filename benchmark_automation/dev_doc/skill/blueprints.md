# Blueprint Contract

## Purpose

Blueprints are generative descriptions. A maintainer should be able to recreate a
module with the same role and external behavior from its blueprint even if source
is unavailable. They describe intent, I/O, algorithms, failure behavior,
non-obvious techniques, and mutability boundaries rather than paraphrasing code.

## Reading

List all files under `../blueprints/`. Read `00_project.md` for project-wide or
cross-module work. Read every module blueprint matching changed concepts. Read a
file blueprint only when work reaches that exceptional file.

## Maintenance

Update a blueprint when intent, responsibilities, dependencies, input/output
shapes, state machines, progress/ETA algorithms, evidence policy, or mutability
changes. Keep ordinary implementation trivia in source/tests.
