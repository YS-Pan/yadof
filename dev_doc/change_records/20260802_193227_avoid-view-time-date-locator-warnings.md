# 2026-08-02 19:32 - Avoid View Time Date Locator Warnings

## Context

- `view time` repeatedly emitted a Matplotlib `AutoDateLocator` warning for common
  histories spanning roughly five to six minutes.
- The configured minimum of six ticks left a gap between the minute and second
  locator choices: the minute count was too small, while the available second
  intervals could not stay below the configured maximum tick count.

## Change

- `view_time.py` now asks `AutoDateLocator` for at least five rather than six major
  ticks while retaining the twelve-tick maximum.
- The PNG regression test promotes this specific locator warning to an error.
- The file blueprint records why the five-tick boundary is intentional.

## Rationale

- Five ticks aligns the neighboring default Matplotlib interval tables across time
  units, so automatic selection remains warning-free without hiding warnings or
  hard-coding a duration-specific locator.

## Impact

- `view time` retains concise automatic date labels and the existing plot layout,
  but common short histories no longer print repeated date-locator warnings.

## Follow-Up

- None.
