# Packaged adapters

Authoritative adapter source files live in `src/yadof/_resources/adapters/` in a
source checkout and become read-only package resources in an installed distribution.
List them and copy only the selected file into a user-owned workspace:

```powershell
yadof task adapters
yadof task copy-adapter hfss_com.py --workspace D:\work\study-a
```

Copying never overwrites a different user file; repeating a byte-identical copy is
idempotent. The active task imports the local file from `job_template/`, so prepared
jobs remain self-contained and never depend on a source checkout.

- [hfss_com.md](hfss_com.md) describes the optional HFSS/PyAEDT adapter.
- [test_com.md](test_com.md) describes the pure-Python simulator stand-in.

New framework adapters belong in package resources with matching user documentation.
Task-only project names, designs, objectives, and private credentials stay in the
workspace rather than the reusable adapter.
