# 4+1 Scenarios

## Scenario 1: First Local Generation
1. User edits `project/job_template/parameters_constraints.py`, `workflow.py`, and `calc_cost.py`.
2. User calls `project.optimize.api.run_one_generation()`.
3. `optimize` has no history, so it samples normalized candidates.
4. `evaluate_manager` prepares jobs with run/generation context and runs `workflow.py`.
5. `workflow.py` writes each individual's start/end metadata inside the job folder.
6. `recorded_data` stores raw variables, rawData, compact metadata, optimization index, and generation index.
7. Three bounded costs are calculated dynamically and returned to `optimize`.

## Scenario 2: Resume From History
1. `optimize` asks `recorded_data` for historical optimization results.
2. `recorded_data` normalizes stored raw variables with current parameter ranges.
3. `recorded_data` recalculates costs with current `calc_cost.py`.
4. `optimize` seeds the optimizer state from compatible historical records.

## Scenario 3: Use Surrogate Assistance
1. User increases `OPTIMIZE_SURROGATE_ALPHA` or `OPTIMIZE_SURROGATE_BETA`.
2. `optimize` trains `surrogate` from completed records.
3. `surrogate` flattens recorded rawData, trains or refreshes the conditional INR ensemble, and writes a generation checkpoint plus member artifacts.
4. `surrogate` predicts rawData for candidate pools.
5. `surrogate` calculates predicted costs and intervals through `job_template.api`.
6. `optimize` selects a real population and sends it to `evaluate_manager`.

## Scenario 4: Evaluation Failure
1. One job preparation, workflow run, timeout, or recording step fails.
2. `evaluate_manager` combines workflow-owned metadata, when present, with runner diagnostics and records best effort.
3. The failed individual receives `inf` costs.
4. Other individuals in the generation continue.
5. Failure records remain visible in `recorded_data`, but default history excludes non-completed records.

## Scenario 5: Modify Task Mid-Campaign
1. User changes parameter ranges, workflow, simulator file, or `calc_cost.py`.
2. New jobs get a different static hash when copied static inputs change.
3. Old rawData remains stored.
4. Historical normalized variables and costs are recalculated under the current task definition.
5. If the change makes old rawData semantically invalid, the user manually removes or ignores old records.

## Scenario 6: Future Distributed Evaluation
1. `evaluate_manager` selects distributed mode.
2. It prepares the same job folder contract.
3. HTCondor workers run workflow logic and write rawData plus `individual_metadata.json`.
4. Finalization reuses the local-mode status interpretation and `recorded_data` write path.
5. Optimizer receives the same cost tuple shape as in local mode.

## Scenario 7: Code Change With Documentation Update
1. AI or user changes source behavior, module contracts, persistence behavior, or important implementation technique.
2. The relevant `dev_doc/architecture/` files are updated when the change affects system views, dependencies, data flow, or workflow.
3. The relevant `dev_doc/prompt/` files are updated when the change affects module intent, I/O, non-obvious techniques, or mutability boundaries.
4. A new file is appended under `dev_doc/change_records/` with a date-time prefix and a short description.
5. `dev_doc/terminology.md` is updated if the change corrects a concept or introduces a non-obvious name.
