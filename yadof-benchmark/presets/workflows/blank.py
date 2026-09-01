"""Explicit blank yadof-benchmark authoring workspace."""
from yadof_benchmark import Benchmark


def build_benchmark(benchmark: Benchmark) -> None:
    """Register strategies and comparisons before running this workspace."""
    # benchmark.configure(name="my-benchmark", evidence="structural")
    # benchmark.strategy(
    #     "algorithm-id",
    #     "resources/strategies/algorithm-id/optimization.py",
    #     name="Human-readable algorithm name",
    # )
    # benchmark.compare(
    #     "main",
    #     baselines=["test-com/synthetic-antenna"],
    #     strategies=["algorithm-id"],
    #     seeds=[101],
    #     population=12,
    #     generations=2,
    # )
    pass
