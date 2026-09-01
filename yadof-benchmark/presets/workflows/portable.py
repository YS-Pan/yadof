"""Packaged portable benchmark: runnable without external simulator software."""
from yadof_benchmark import Benchmark


def build_benchmark(benchmark: Benchmark) -> None:
    benchmark.configure(
        name="portable-canonical-strategy-smoke",
        evidence="structural",
        fail_fast=True,
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
        "portable-synthetic-antenna",
        baselines=["test-com/synthetic-antenna"],
        strategies=["real-only-nsga3", "gpsaf-pca-svd-nsga3"],
        seeds=[101],
        population=12,
        generations=2,
        reference="real-only-nsga3",
    )
