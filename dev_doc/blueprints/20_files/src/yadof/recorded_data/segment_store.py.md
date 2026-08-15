# File blueprint: src/yadof/recorded_data/segment_store.py

## Intent

- Publish and discover immutable, independently readable v2 evidence segments.

## I/O format

- Standard ZIP under `v2/segments/<run>/<generation>/` with candidate-scoped JSON
  metadata, stored NPZ members, and `manifest.json` last.
- Same-directory temporary ZIP followed by atomic rename is the sole publication
  boundary; temporary and legacy files are ignored by discovery.

## Functionalities

- Give every candidate a stable campaign/run/generation/population/job identity.
- Validate manifest/schema/member mappings, declared sizes, and metadata identity;
  return segment/candidate diagnostics while retaining readable siblings.
- Produce stable sorted catalog references and deterministic first-wins handling of
  duplicate identities.

## Invariants

- A publication contains one run/generation, no duplicate candidates, and respects
  the caller-selected micro-batch count/byte bounds.
- Publication never opens, copies, or rewrites an older segment.
- Central-directory or manifest failure skips only its segment; candidate/member
  corruption skips only that candidate when possible.
