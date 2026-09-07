# 2026-09-07 09:20 - Shared rawData and reusable training buffers

## Context

Repeated full-history materialization decoded and copied previously seen rawData,
retained repeated static axes/metadata, and allocated several full-field matrices
for amplitude/shape GP fitting. The user authorized read-only sample sharing,
training-buffer reuse and static sharing, excluded disk decompression caches and
memory mapping, and did not require compatibility with historical results.

## Change

- Structured samples isolate external mutable storage with immutable byte-backed
  arrays. Validated samples and exact-schema static objects are reused; explicit
  mutable exports remain independent.
- Dataset/campaign weak indexes reuse decoded committed samples while training
  consumers hold them. Candidate/member and file identity prevent stale cache
  hits. Costs and normalized variables continue to follow current task snapshots.
- Amplitude GP fills one float64 matrix per field, normalizes it in place, lets
  PCA center it in place, and releases it before the next field. Direct buffer
  hashing avoids full byte-copy temporaries.
- The coherent pre-existing amplitude GP source, public integration, optional
  dependencies, documentation and acceptance tests are included in this change.

## Rationale and impact

Sharing spans the common submit-side training path for fast/local/distributed;
benchmark programs and worker transports need no additional policy or API.
Weak ownership avoids a strong second complete history, at the cost of decoding
again after all previous training inputs are released. A schema can retain its
one template row. Full-field fitting still scales with data size. Row counts,
precision, GP selection and numerical settings remain unchanged. No historical
result compatibility branches, disk cache or memory mapping were added.

## Verification

The wheel built and force-reinstalled successfully; yadof and yadof-benchmark
imports resolved below the selected environment's `site-packages`, with source
injection disabled. Focused acceptance passed 120 tests in 21.65 seconds; full
yadof acceptance passed 541 tests in 121.24 seconds. The independent installed
benchmark package passed all 64 tests in 14.65 seconds without code changes or
reinstallation. Tests cover ownership, scalar/multidimensional schema drift,
concurrent reuse, incremental decode, file invalidation, weak-reference release,
current cost/range reinterpretation, fit-buffer lifetime, cancellation and
fast/local/distributed execution fixtures.

A task-local deterministic probe used 128 rows with one 32768-value float64 field
and an equally sized coordinate axis, GP limit 8, PCA rank 3, and 3 optimizer
iterations. These are single-run synthetic measurements of newly traced
allocations, not process RSS or a full simulator benchmark:

| Operation | Before peak MiB | After peak MiB | Before seconds | After seconds |
| --- | ---: | ---: | ---: | ---: |
| Initial input construction | 129.18 | 64.50 | 0.1301 | 0.1035 |
| Rewrap retained training input | 65.01 | 0.14 | 0.0833 | 0.0257 |
| Fit amplitude GP | 106.89 | 42.39 | 0.2262 | 0.2160 |

The resulting initial training value retained 32.50 MiB instead of 64.30 MiB.
All 128 samples were reused during rewrapping, with one axis and one metadata
object instead of 128 each. Content digests matched and all 65536 predicted values
at the two probe inputs were exactly equal (maximum absolute difference zero).
No full physical simulator campaign was launched for this change.
