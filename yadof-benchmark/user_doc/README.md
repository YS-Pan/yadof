# yadof-benchmark user guide

Use this guide for the installed `yadof-benchmark` package. The shortest route is:

1. Read [workspace.md](workspace.md) before creating or editing a workspace.
2. Read [api.md](api.md) while writing `benchmark.py`.
3. Read [baselines.md](baselines.md) to choose packaged baseline IDs or provide a
   separate baseline collection.
4. Read [run_and_recovery.md](run_and_recovery.md) before execution, interruption,
   resume, or evidence review.

Measured `run` and `resume` commands use a visible process window by default,
whether a human or an AI agent starts them. An already visible terminal may run the
command in the foreground; an agent detaching a long run must create a normal
visible console. A hidden launch is an explicit exception that requires the user's
request, not an agent convenience.

The workflow contract is Python-only. `check` and `plan` import and execute the
workspace's `benchmark.py`, so planning code should be deterministic and should not
start simulators, mutate external state, or perform expensive work. Measured work
belongs to strategy execution; visualization and analysis belong to declared
postprocessors.

List and read the version-matched installed documents with:

```powershell
yadof-benchmark docs list
yadof-benchmark docs show api.md
```
