# 4+1 Development View

## Source layout

```text
benchmark_automation/
  benchmark.py                 thin CLI
  benchmark_core.py            planning, state, execution, ETA, collection, report
  benchmark.toml               cases, arms, suites, budgets, resources
  baselines/                   editable semantic task templates
  preregistrations/            versioned schema/experiment freezes and validators;
                                not executable suites or result evidence
  strategy_templates/          complete optimization.py arm/case definitions with component kwargs
  tests/                       focused runner and postprocessor tests
  README.md                    operator contract
  AGENTS.md                    bounded agent route
  dev_doc/
    README.md                  maintainer entry and workflow
    skill/                     documentation contracts
    architecture/              current C4 and 4+1 views
    blueprints/                generative project/module/file contracts
    terminology.md             benchmark-specific vocabulary
```

Repository-level pending work, obsolete handoffs, and completed-change history
remain under root `dev_doc/toDo/`, `dev_doc/obsolete/`, and
`dev_doc/change_records/`. The benchmark tree must not add parallel lifecycle
directories or local toDo/change-record contracts.

## Dependency direction

The CLI depends on core; core never depends on CLI. Core may use standard library,
Rich, and installed yadof public surfaces selected for collection. Baseline tasks
and strategy templates are inputs, not import-time runner dependencies. Tests may
mock subprocess/public surfaces but must preserve state and output shapes.

## Change discipline

- CLI syntax/output routing changes update CLI tests and operator examples.
- Planning, identity, state, execution, progress, ETA, collection, or report changes
  update core, focused tests, affected architecture/blueprints/terminology, root
  README/AGENTS, and one root change record.
- Terminal regressions require rendered output and an actual piped child-stream
  test that verifies Rich refreshes occur on the foreground owner thread. Testing
  only `Task.completed` or calling the parser synchronously is insufficient.
- Timing fixtures use fixed UTC times, bounded synthetic prior-run snapshots, and
  small timestamped command event streams. They include cross-arm rejection,
  generation-growth forecasting, and recorded-session replay; development never
  launches a real performance run.
- Benchmark code remains outside wheel/sdist. Tests use the matching regularly
  installed yadof distribution without repository-source injection.
- A preregistration validator may read current tracked baselines/configuration and
  prove a deliberately blocked state, but it never launches a simulator, creates a
  run, treats smoke shapes as rows, or changes the runner matrix. Data and numeric
  threshold seals are later versioned inputs rather than edits that rewrite the
  original Gate 0 claim.
