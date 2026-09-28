# 2026-09-29 03:57 - Add Windows HTCondor control GUI

## Context

The user requested a `.pyw` desktop interface for bounded optimization, Condor
status and machine draining, global job removal on stop, and cost/time/error views.
The package had CLI run and cost/time tools but no operational desktop controller
or separate error viewer.

## Change

- Add an installed `yadof-gui` script, package a `.pyw` launcher, and implement a
  Tk controller under `yadof.tools`.
- Run the existing CLI with explicit workspace and generation range, query Condor
  slot ClassAds on a configurable interval, drain a selected machine gracefully,
  and execute `condor_rm -all` after stopping the launched process tree.
- Invoke the existing cost/time tools and present their history output; derive the
  error view from the time tool's typed failure rows.
- Document the global stop scope and GUI behavior and add headless command tests.
- Make the external wheel test force its local installation when the base Python
  environment already carries the same yadof version.

## Rationale

The GUI uses the package's established run and history boundaries. Worker threads
keep scheduler commands and history rendering from blocking the Tk event loop.
Using the machine ClassAd avoids inferring a drain target from a slot name.

## Impact

The installed package gains an optional Windows desktop entry point. Pool commands
still require the invoking user's HTCondor permissions. `condor_rm -all` has the
requested current-identity-wide scope.

## Verification

The installed-wheel GUI, CLI, packaging, and posterior-strategy focused suite
passed (45 tests, including stop-error and stop-completion ordering cases). GUI initialization
and a read-only live `condor_status` query succeeded. A full installed-package
run passed 598 tests and failed five unrelated existing PyChrono long-path tests
on this Windows host, where those tests cannot create their deliberately long
scratch paths. No optimization, drain, or removal command was run against the pool.
