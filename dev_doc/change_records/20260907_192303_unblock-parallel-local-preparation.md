# 2026-09-07 19:23 - Unblock parallel local preparation

## Problem and change

A failure-recovery experiment completed an all-failed batch, then stalled during
a mixed batch. The coordinator retained the task import lock after interpreting
the first successful result. Its remaining worker futures needed the same lock
to read parameters and hash prepared jobs, creating a circular wait.

Local dispatch now reads an immutable parameter template from its generation
snapshot before workers start. Each job receives independent assigned values and
uses the same definition signature for static hashing. Direct point-in-time
preparation remains fresh-loading, and the next generation selects a new template.
This also removes repeated parameter imports within a batch. Assignment arithmetic,
configured concurrency, deterministic result order, committed-evidence boundaries,
and optimizer/surrogate behavior are unchanged.

Template loading and individual preparation errors retain one durable failure
per affected candidate. Cancellation still takes precedence before preparation.
Failed simulator attempts remain visible and later candidates can continue.

## Validation

The wheel built and force-reinstalled successfully, and imports resolved below
the selected environment's `site-packages` without source injection. Focused
acceptance passed 114 tests in 9.12 seconds; the full installed yadof suite passed
544 tests in 119.30 seconds. The unchanged installed benchmark package passed
64 tests in 15.99 seconds. Regression coverage forces cost
interpretation to start before later parallel jobs prepare, using a bounded child
process so a deadlock cannot hang the test run. Additional cases compare continuous,
discrete, mixed and clipped assignments, generated files and static hashes with
fresh preparation, and verify durable per-candidate template failures.

The evidence-preservation automatic toDo was triggered by the observed stalled
finalization path. This bounded fix retains the common coordinator, writer,
backpressure, receipt, cancellation and recording-error contracts. Scientific
surrogate performance acceptance remains separate and unmet.
