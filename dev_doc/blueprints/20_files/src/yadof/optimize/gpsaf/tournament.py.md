# File blueprint: GPSAF tournaments

Implement paper Sections III-A/B without pymoo imports. Objectives minimize;
constraints satisfy G<=0. Choose minimum total positive violation if no feasible
competitor exists, otherwise a random nondominated feasible candidate. Explicit
invalid rows lose to feasible rows. PKT shuffles once, duplicates a random
competitor in odd rounds and draws independent normal error perturbations per
objective/constraint/competitor/match. Zero scale consumes no noise draws.
Compute empty-cluster probability zero and otherwise `(size/max_size)**gamma`.
Inject the RNG so tests can prove tie, noise and replacement behavior directly.
