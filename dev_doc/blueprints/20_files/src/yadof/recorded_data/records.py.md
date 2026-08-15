# File blueprint: src/yadof/recorded_data/records.py

## Intent

- Construct candidate envelopes and publish immutable evidence or diagnostic
  metadata events through workspace-explicit public APIs.

## Functionalities

- Scrub/canonicalize candidate metadata, promote campaign/run/generation and task
  fingerprints, and preserve raw variables as source truth.
- Build recorder-owned envelopes from file or memory sources.
- Provide direct bounded segment publication for standalone callers while rejecting
  duplicate candidate identities and active-campaign conflicts.
- Publish unique immutable optimization and surrogate metadata JSON events and list
  them tolerantly.

## Invariants

- Normalized variables and current costs are never source evidence fields.
- Public direct publication never overwrites a candidate or a prior event.
- Campaign execution uses `CampaignSession`, not repeated direct publication.
