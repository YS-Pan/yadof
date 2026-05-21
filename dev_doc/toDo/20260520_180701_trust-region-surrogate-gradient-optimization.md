# Trust-Region Surrogate-Based Gradient Optimization

## Context
- This is a long-term research and implementation direction, not a near-term feature.
- The optimizer currently uses evolutionary multi-objective search with surrogate assistance. A future extension could add a local refinement stage after an evolutionary generation or campaign.
- The real optimization problem should still be treated as expensive black-box evaluation. Do not assume the real simulator or workflow has usable gradients.
- The surrogate, however, may be differentiable. Its gradients can be used to propose refined candidates, then real evaluation can verify whether those candidates are actually good.

In optimization terminology, this idea is closest to:

- surrogate-assisted evolutionary optimization,
- surrogate-assisted memetic optimization,
- trust-region surrogate-based optimization,
- model-management optimization,
- gradient-based local search on a surrogate model.

## Goal
- After an evolutionary search phase finds promising individuals, use the differentiable surrogate model to run a few local gradient-based refinement steps.
- Treat the refined points only as candidate proposals.
- Validate selected refined candidates with real expensive evaluations.
- Add the verified results back into the recorded real-evaluation history.
- Repeat this process only when the surrogate is trustworthy enough in the local region.

The intended benefit is to combine:

- evolutionary search for global exploration and Pareto-front diversity,
- surrogate gradients for local precision,
- real evaluations for final truth and correction.

## Guidance
- Keep the real objective black-box. Surrogate gradients must not be presented as gradients of the real workflow.
- Use a trust region around real evaluated samples or elite candidates. Gradient steps should stay local unless real validation expands confidence.
- For multi-objective optimization, choose explicit scalarization or direction-based local goals before taking gradients. Possible choices include weighted sums, achievement scalarizing functions, Tchebycheff-style scalarization, or reference-direction-specific objectives.
- Preserve Pareto diversity. Local refinement should not collapse all candidates toward one scalar optimum.
- Use uncertainty, historical surrogate error, distance to training data, or similar diagnostics to decide whether a local surrogate step is worth trusting.
- Validate refined candidates with real evaluations before treating them as successful improvements.
- Use failed validation as information: shrink trust regions, reduce gradient step counts, or retrain/update the surrogate before trying again.
- Avoid making this feature depend on the current exact module layout. The project may look very different by the time this is implemented.
- Prefer describing the feature in terms of durable workflow concepts: real evaluated samples, surrogate prediction, local candidate refinement, trust region, scalarization, validation, and history update.

One possible future loop:

1. Run evolutionary search until a generation or campaign checkpoint.
2. Select a diverse set of promising real-evaluated anchors.
3. Around each anchor, define a local trust region in normalized variable space.
4. Pick one or more scalarized local objectives for each anchor or reference direction.
5. Use surrogate gradients to run a small number of constrained local optimization steps.
6. Filter refined candidates by bounds, trust-region radius, uncertainty, novelty, and diversity.
7. Run real expensive evaluations for the most promising refined candidates.
8. Record real results, retrain or refresh the surrogate, and adjust trust-region confidence.

## Completion Rule
- This toDo is complete only when the project has a documented and tested workflow for surrogate-gradient local refinement with real-evaluation validation.
- The implementation should include a clear explanation of how multi-objective scalarization, trust-region limits, uncertainty/error checks, and validation feedback are handled.
- If the eventual implementation intentionally chooses a different name or framing, preserve the conceptual link to surrogate-assisted memetic optimization and trust-region surrogate-based optimization in the documentation.
