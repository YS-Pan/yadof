# GPSAF paper-to-implementation acceptance

Authority: the full supplied `GPSAF original full paper.tex`, especially Algorithm 2,
Algorithm 3 and the sections on alpha, beta, replacement and surrogate management.
Read the whole paper; its benchmark rankings are not implementation gates.

Paths below are relative to the checkout. Test functions are in
`tests/test_gpsaf_paper.py` unless another file is named.

| Paper mechanism | Code location | Acceptance |
| --- | --- | --- |
| Compare the corresponding position across alpha infill batches; feasibility, then Pareto, then random ties | `src/yadof/optimize/gpsaf/phases.py:run_alpha_phase` and `tournament.py:tournament_winner` | `test_alpha_only_competes_at_corresponding_positions` rejects pooled survival; `test_feasibility_dominance_and_random_ties` checks constraints, dominance, equality and injected randomness |
| Clone the base algorithm, repeatedly infill/predict/advance beta times; retain the whole search pattern and assign nearest alpha anchors | `gpsaf/phases.py:run_beta_phase`, `pymoo/backend.py` | `test_beta_clusters_all_advances_without_leaking_simulated_state` verifies all beta candidates, nearest-anchor assignments, and unchanged real population/counter |
| One probabilistic knockout winner per nonempty cluster; fresh independent objective/constraint noise per match | `gpsaf/tournament.py:probabilistic_knockout` | `test_pkt_odd_zero_error_and_independent_nonzero_noise` supplies controlled noise, checks odd duplication, deterministic zero error and independent nonzero perturbations |
| Replace with `(cluster_size / maximum_size) ** gamma`; densest always replaces | `gpsaf/tournament.py:replacement_probabilities`, `phases.py:run_beta_phase` | `test_gamma_controls_cluster_replacement` checks the formula; `test_gamma_changes_actual_beta_replacement_for_controlled_clusters` uses sizes 9,3,0,0 and fixed random inputs to change actual selected candidates |
| Initial five-fold error; maximum absolute error per function; five-iteration moving average updated from new truth | `gpsaf/errors.py`, `surrogate/linear_subspace/gpsaf_error.py` | `test_five_fold_bootstrap_uses_held_out_rows_and_maximum_error` proves held-out separation and maximum (not mean) error; `test_maximum_absolute_error_then_five_batch_average` covers residuals, failed observations, the rolling window and interpretation reset |
| Advance the original algorithm only with expensive real evaluations | `optimize/strategy.py` and `pymoo/backend.py:history_population` | `test_replay_advances_once_per_real_generation` compares sequential tells, NSGA-III normalization and n_gen; beta tests prove cloned Individuals do not leak predicted costs |
| Exact simulation oracle has zero approximation error and does not spend formal evaluation budget | `yadof-benchmark/src/yadof_benchmark/perfect_oracle.py` | `yadof-benchmark/tests/test_perfect_oracle.py` checks cost_items payloads, valid all-one values, physical failures, fatal programming errors, empty-data readiness, actual alpha/beta entry and prediction/formal equality with 66 oracle calls but only 24 formal rows |

`tests/test_explicit_search_primitives.py` additionally checks seeded repeatability
and gamma probabilities; the former assertion that gamma must not change
selection is removed. Existing generation-2 population golden values from pooled
archive replay are replaced by state-contract tests and repeatability checks.

Explicit adaptations are normative in `user_doc/gpsaf.md`: normalized distances,
deterministic nearest-anchor ties, independent normal PKT noise (the paper does
not specify a noise family), rawData-to-cost models rather than RBF/Kriging model
selection, task-owned penalties rather than separate baseline constraint vectors,
10% exploration, finite-history replay and neural prequential cold start. Exact
oracle zero is justified by identical kernels/cost interpretation and audited
selected rows; deterministic model intervals alone never justify zero error.

Installed-package unit tests are supplemented by fresh real-runtime evidence:
Chrono historical 105/158 plus normal cases in independent/concurrent/same-process
repeats, all three oracle/direct cost chains, multi-generation perfect-oracle
integration, and normal nonzero-error PCA/SVD integration. Only formal recorded
history enters the paired top-ten stopping statistic. Smoke and integration are
structural evidence and never performance observations.
