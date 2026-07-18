# Module blueprint: prepared jobs

Jobs are generated below the effective workspace jobs directory. A job contains the
task payload, assigned parameter snapshot, `worker_misc.py`, `sitecustomize.py`,
compact version/config provenance, scheduler/local metadata, workflow metadata, and
flat rawData. Submit-side `calc_cost.py`, a copied framework config package, and
authoritative `cost.json` are forbidden. Static hashes ignore assigned values but
capture parameter definitions and task support.
