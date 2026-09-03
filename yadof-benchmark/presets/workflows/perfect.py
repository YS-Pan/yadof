"""Paired seed-101, 200-by-50 real NSGA-III versus perfect GPSAF."""
from yadof_benchmark import Benchmark
from yadof_benchmark.perfect_protocol import write_summary


def final_summary(context):
    return write_summary(context)


def build_benchmark(benchmark: Benchmark) -> None:
    benchmark.configure(name="perfect-gpsaf-top10", evidence="performance", fail_fast=False, cell_concurrency=1)
    benchmark.strategy("real-nsga3", "resources/strategies/top10-real-nsga3/optimization.py", name="NSGA-III")
    benchmark.strategy("perfect-gpsaf", "resources/strategies/top10-perfect-gpsaf/optimization.py", name="GPSAF with perfect surrogate")
    benchmark.compare("paired-top10", baselines=["chrono/trebuchet", "ngspice/saw-ladder", "test-com/synthetic-antenna"],
                      strategies=["real-nsga3", "perfect-gpsaf"], reference="real-nsga3",
                      seeds=[101], population=200, generations=50, stop_on_top10_reference=True)
    benchmark.postprocess("perfect-summary", final_summary, run_on_failure=True)
