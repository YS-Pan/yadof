# 2026-07-27 16:00 - Refine Surrogate Band And Time View

## Context

- The surrogate viewer's interactive rawData band showed one standard deviation
  around the ensemble mean rather than the ensemble's actual prediction extent.
- The integrated time view placed error labels at the right edge above their
  horizontal bands, kept the failure-rate line partly translucent, and used a
  redundant `computer:` prefix without per-machine timing context.

## Change

- Changed the interactive surrogate band to each point's finite minimum and maximum
  across ensemble-member curves and relabeled it `ensemble min–max`.
- Moved error-type labels to the left edge and vertically centered them on their
  horizontal bands.
- Raised the failure-rate trend alpha from 0.6 to 1.0.
- Changed machine legend entries to `<machine> (avg. <minutes> min)`, using all
  recorded elapsed-time rows assigned to the machine.
- Updated focused tests, user/agent guidance, architecture, and blueprints.

## Rationale

- Min/max bounds expose the complete ensemble-member range without implying a
  symmetric or normally distributed uncertainty interval.
- Left-centered labels read as direct names for their bands, while the stronger
  failure line and per-machine averages make the time view easier to interpret.

## Impact

- Only read-only viewer/time visualization and their documentation changed.
- Workspace evidence, surrogate checkpoints, cost calculation, command signatures,
  and optimization behavior are unchanged.

## Follow-Up

- None.
