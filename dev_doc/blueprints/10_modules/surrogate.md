# Module blueprint: surrogate

`yadof.surrogate` trains a conditional INR deep ensemble from workspace history,
predicts rawData, derives current costs, returns member min/max intervals, and
records error audits. Runtime and one-task training schedules are keyed by effective
workspace paths. Checkpoints contain auxiliary arrays and model artifacts and are
recoverable only against compatible current parameters/rawData schema; current
`calc_cost.py` is always reapplied after recovery.
