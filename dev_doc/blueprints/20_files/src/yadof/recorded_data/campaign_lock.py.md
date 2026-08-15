# File blueprint: src/yadof/recorded_data/campaign_lock.py

## Intent

- Enforce one active campaign per workspace across threads and processes while
  allowing independent workspaces.

## Functionalities

- Acquire a non-blocking OS file lock at `.yadof/campaign.lock` with a process-local
  held-path guard.
- Keep the lock handle alive for the complete campaign and expose a read-only
  inactive assertion for destructive tools.
- Raise `CampaignActiveError` with the exact workspace lock path on contention.

## Invariants

- Lock-file existence alone is never interpreted as ownership.
- A session releases ownership only after its writer has stopped; a timed-out
  shutdown keeps the lock until the background thread actually exits.
