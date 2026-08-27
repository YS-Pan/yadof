# File blueprint: src/yadof/surrogate/hierarchical_cae/modeling.py

## Intent

- Own Torch model construction, staged training, robust aggregation, and full-grid
  member inference for the experimental hierarchical CAE.

## Functionalities

- Encode each field with a scalar/Conv1d/Conv2d codec and form global,
  optional-group, and field-private teacher latents.
- Mask/downweight low-trust field tokens before shared fusion and restrict their
  reconstruction gradient to a gated field-private residual path.
- Train independently initialized parameter predictors over shared codecs; each
  member emits joint latent state, an applicability logit, and field residual logits.
- Compute Smooth L1 per design and field before optional cap/weight aggregation;
  split only by complete design, early-stop stages, and accept fine-tuning only on
  validation improvement.

## Invariants

- A clean residual gate is zero during teacher training.
- No-policy batches reduce to ordinary equal field-macro training.
- One member predicts all candidates/fields in its function draw; observation noise
  remains zero.
