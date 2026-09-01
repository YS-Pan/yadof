"""Packaged complete benchmark: explicit long-running measured campaign."""
from yadof_benchmark import Benchmark


def build_benchmark(benchmark: Benchmark) -> None:
    benchmark.configure(
        name="complete-packaged-baseline-pca-svd-performance",
        evidence="performance",
        fail_fast=False,
        cell_concurrency=1,
    )
    benchmark.strategy(
        "real-only-nsga3",
        "resources/strategies/real-only-nsga3/optimization.py",
        name="Real-only NSGA-III",
    )
    benchmark.strategy(
        "gpsaf-pca-svd-nsga3",
        "resources/strategies/gpsaf-pca-svd-nsga3/optimization.py",
        name="Explicit NSGA-III + GPSAF + PCA/SVD",
    )
    benchmark.compare(
        "all-packaged-baselines",
        baselines=[
            "chrono/trebuchet",
            "ngspice/saw-ladder",
            "test-com/synthetic-antenna",
        ],
        strategies=["real-only-nsga3", "gpsaf-pca-svd-nsga3"],
        seeds=[101, 102, 103],
        population=200,
        generations=25,
        reference="real-only-nsga3",
    )
