cd "C:\Users\15090\Desktop\projects\20260501 yadot\20260510 recombine"

@'
from project.optimize.api import run_generations

results = run_generations(
    20,
    start_generation=0,
    population_size=500,  # 不写则使用 project/config.py 里的 OPTIMIZE_POPULATION_SIZE
)

for r in results:
    print(
        f"gen={r.generation_index} "
        f"source={r.source} "
        f"surrogate={r.surrogate_used} "
        f"history={r.history_count} "
        f"costs={r.costs[:2]}"
    )
'@ | python -
