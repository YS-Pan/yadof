# 2026-08-15 21:21 - Report Cost-View Candidates

## Context

`view cost` began showing its progress in segment units after history processing was
made one-open-per-segment. A user could correctly see 10,001 plotted records but
incorrectly infer data loss from a `651/651` progress frame.

## Change

- Progress now advances by the count of candidates decoded in the streamed history
  pass.
- The terminal displays `N/?` while the exact total is still unknowable without a
  second ZIP scan, then ends with the exact `N/N` candidate count.
- The callback contract accepts an absent total, and tests cover both the streamed
  candidate reports and the final exact count.

## Rationale

Existing optimization-event metadata is not a complete durable-history index: in
the observed workspace it named 10,000 candidates while 10,001 completed records
were available. Discovering the exact count before processing would therefore need
to reopen every segment manifest, defeating the one-pass performance improvement.

## Impact

Cost-view history still opens each segment once. The only added work is a candidate
counter and normal progress callbacks; no metadata pre-scan, extra ZIP opening, or
extra rawData retention is introduced.
