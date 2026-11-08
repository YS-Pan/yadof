# File blueprint: inspection.py

## Responsibility

Own the headless single-case use case below `yadof view surrogate inspect`:
resolve one checkpoint, one completed real result, one rawData item, zero to two
named plot axes, and all fixed coordinates; invoke `SurrogateWorkspace.predict_one`
once; derive the selected prediction/truth/member bounds and finite statistics; and
format a bounded schema-versioned payload.

## Contracts

- `latest` resolves to the highest compatible generation; every other selector is
  exact and missing/ambiguous/incomplete selection raises a typed viewer error.
- Omitted plot axes use GUI defaults (`Freq`, then first); omitted fixed axes use
  the stored coordinate nearest zero. The payload records request, resolved value,
  source, and stored/off-grid state.
- Stored-grid slices may contain recorded truth and error statistics. An off-grid
  backend plot has `truth=null` and `error_summary=null` plus a warning.
- Every JSON number is finite or `null`. Selected plots above 4096 scalars omit all
  inline coordinate/value arrays but retain shapes and finite summaries.
- No output means no writes. Explicit output accepts only a new or empty directory,
  publishes full NPZ/optional one-dimensional CSV/Agg PNG without replacement, and
  publishes a hashed manifest last. Failure never leaves a manifest.

## Boundaries

Do not load a GUI, duplicate model inference, train, execute a workflow, or mutate
workspace evidence. Import `renderer.py` only inside explicit export. Keep the
terminal payload independent from internal checkpoint member samples.
