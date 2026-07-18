# 4+1 logical view

The logical pipeline is `normalized variables -> assigned task parameters ->
workflow rawData -> current calc_cost -> objective tuple`. Only raw variables,
rawData, lifecycle/provenance metadata, and lightweight generation metadata are
durable. Normalized history and costs are derived through the current task.

Optimizer and surrogate are consumers of the same evidence. The surrogate predicts
rawData before cost and is keyed by effective workspace paths. Local/distributed
evaluators differ only in execution transport. Individual failures yield diagnostic
records and correct-width infinite costs rather than changing generation shape.
