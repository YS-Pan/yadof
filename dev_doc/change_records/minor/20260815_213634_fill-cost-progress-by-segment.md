# 2026-08-15 21:36 - Fill Cost Progress by Segment

## Context

Candidate-count progress correctly ends at the durable-history total, but its total
is intentionally unknown while a one-pass view reads the segments. Rendering the
bar from that unknown total left the bar empty until the final update.

## Change

- Cost-view history now attaches frozen segment position to its string-compatible
  progress message while retaining decoded candidate count as the visible progress
  number.
- The CLI uses that segment position only to fill the bar, showing candidate `N/?`
  during streaming and exact `N/N` at completion.
- Tests cover the independent segment-based bar fill and candidate count.

## Rationale

The frozen segment list is known before decoding begins, so it is a useful visual
progress denominator. It does not replace the durable candidate count and does not
require reading a manifest twice.

## Impact

Each segment remains opened once. Existing ordinary three-argument callbacks still
receive a string message and candidate count; only renderers that recognize the
optional message attributes use the separate bar units.
