"""Complete baseline matrix with two research-derived optional components."""
from yadof_benchmark import Benchmark

def build_benchmark(benchmark: Benchmark) -> None:
    benchmark.configure(name="surrogate-complete", evidence="performance", fail_fast=False,
                        cell_concurrency=2)
    benchmark.strategy("real-only-nsga3", "resources/strategies/real-only-nsga3/optimization.py",
                       name="Real-only NSGA-III")
    benchmark.strategy("gpsaf-pca-svd-nsga3", "resources/strategies/gpsaf-pca-svd-nsga3/optimization.py",
                       name="GPSAF + PCA/SVD")
    benchmark.strategy("gpsaf-amplitude-gp-nsga3", "resources/strategies/gpsaf-amplitude-gp-nsga3/optimization.py",
                       name="GPSAF + amplitude/shape GP", slow_surrogate=True)
    benchmark.strategy("gpsaf-retrieval-response-nsga3", "resources/strategies/gpsaf-retrieval-response-nsga3/optimization.py",
                       name="GPSAF + retrieval response (experimental)", slow_surrogate=True)
    benchmark.compare("all-packaged-baselines", baselines=["chrono/trebuchet", "ngspice/saw-ladder",
        "test-com/synthetic-antenna"], strategies=["real-only-nsga3", "gpsaf-pca-svd-nsga3",
        "gpsaf-amplitude-gp-nsga3", "gpsaf-retrieval-response-nsga3"], seeds=[101,102,103],
        population=200, generations=25, reference="real-only-nsga3")
