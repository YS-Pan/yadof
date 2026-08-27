"""Frozen one-generation real fallback canary for the 082611 boundary."""

from yadof.optimize import posterior_assisted, pymoo_nsga3, qnehvi
from yadof.surrogate import (
    APPLICABILITY_NOT_APPLICABLE,
    PERFORMANCE_NOT_ACCEPTED,
    POSTERIOR_UNCALIBRATED,
    PosteriorExploitationReadiness,
)


class BlockedCanaryPosterior:
    def validate(self, config, problem):
        del config, problem

    def semantic_identity(self, config, problem):
        del config, problem
        return {"component": "blocked-canary-posterior", "component_version": 1}

    def posterior_semantic_identity(self, config, problem):
        del config, problem
        return {
            "capability": "joint-rawdata-posterior-canary",
            "capability_version": 1,
        }

    def exploitation_semantic_identity(self, config, problem):
        del config, problem
        return {
            "capability": "yadof.posterior-exploitation-readiness",
            "capability_version": 1,
            "performance_status": PERFORMANCE_NOT_ACCEPTED,
            "posterior_status": POSTERIOR_UNCALIBRATED,
            "applicability_status": APPLICABILITY_NOT_APPLICABLE,
            "transferable": False,
            "observation_noise_included": False,
        }

    def assess_posterior_exploitation(self, context, population):
        del context
        return PosteriorExploitationReadiness.blocked(
            population,
            applicability_status=APPLICABILITY_NOT_APPLICABLE,
            failure_reasons=("v9 canary deliberately blocks exploitation",),
        )

    def make_rawdata_sampler(self, context, *, draw_count, seed):
        raise AssertionError((context, draw_count, seed))


def build_optimization():
    return posterior_assisted(
        search=pymoo_nsga3(),
        surrogate=BlockedCanaryPosterior(),
        acquisition=qnehvi(
            batch_size=1,
            greedy_restarts=1,
            minimum_unique_support=2,
            low_support_policy="fallback",
        ),
        candidate_pool_size=4,
        posterior_draws=2,
        candidate_chunk_size=2,
        exploration_fraction=0.5,
    )
