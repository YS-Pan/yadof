# File blueprint: src/yadof/job_template/rawdata_projector.py

## Intent

- Project transient complete rawData function draws through one frozen current-task
  cost definition without copying task loading, callbacks, width logic, or fallback
  policy.

## Functionalities

- Hold an injected `CostInterpreter` and `RawDataSchemaTemplate`.
- Per draw/candidate, validate the exact structured schema, denormalize the matching
  normalized row with frozen parameters, invoke the existing callback, enforce
  objective width, and require finite results.
- Return read-only joint `[draw,candidate,objective]` float64 samples,
  `[draw,candidate]` validity, stable draw/population/objective order, and bounded
  typed diagnostics. Invalid values stay `NaN`.
- Provide a context manager that keeps the workspace/snapshot task interpreter
  frozen for the full projection lifetime.

## Non-Obvious Techniques

- Finite callback results, including indistinguishable task-level
  `error_cost=1.0`, are valid. Schema, callback, width, and non-finite-result
  failures are invalid; the projector never infers fallback provenance from a
  number.
- Failure detail is bounded while total/type counts remain exact.

## Invariants

- No task loader, callback dispatcher, objective counter, recorder, worker,
  transport, history, or posterior backend is duplicated or imported here.
