# Same-seed structural repeatability check

Two `test_com` structural canaries used seed `20260816`:

- `20260823T052026Z-first-canary-7784fbff5014`
- `20260823T052537Z-canary-third-gen-8f3b38ad1fa4`

After reconstructing generation 0 in public `population_index` order, all four
case/arm observations have the same normalized-population fingerprint:

```text
cf5385900f3479d16a01a924248ac20b1c3a640dfec86561787470eaa3882ca4
```

The generated declared-input fingerprints also match between repeats:

```text
real-search             48761dc3cc1879787eb05ddab92889369a58989f71b7e212494ed9eb276f0dc6
gpsaf-conditional-inr   a37d80f799648c4eea724bc9dbee7995155093fa2c806b62627c499e86ee20d8
```

The base planned command templates match exactly. Generation-0 recalculated cost
sets match exactly; only their recorded row order differs because fast workers may
finish concurrently. Both repeats have unchanged pre/post task-input fingerprints.

The second run intentionally differs after the two-generation boundary: the
corrected runner executes the declared third generation when public metadata shows
that no prior generation used the surrogate. That third generation reports
`source=gpsaf_surrogate` and `surrogate_used=true`.
