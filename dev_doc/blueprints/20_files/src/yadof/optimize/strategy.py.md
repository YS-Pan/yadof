# File blueprint: src/yadof/optimize/strategy.py

## Intent

- Define backend-neutral population, history, generation-context, result, and
  semantic-signature values used by explicit programs and components.

## Functionalities

- Build deterministic JSON semantic identity/signature from selected component
  identity plus parameter/objective names.
- Adapt current session history by joining evidence and costs on row identity, then
  expose candidate/row/design/interpretation IDs alongside the compatible
  `job_name/x/costs` fields.

## Invariants

- No concrete pymoo or Torch type crosses this boundary.
- Program source is frozen once by `program.py`. Package config/registries never
  select a competing complete method.
- Surrogate predictions cannot become accepted results without real evaluation.
- Pending, failed, or derived rows and non-successful cost interpretations cannot
  become committed optimizer history.
