# yadof-benchmark simulator-concurrency tuning

## Scope

This is bounded, host-specific throughput evidence for choosing portable
physical-core multipliers in the three packaged benchmark baselines. It is not
algorithm-performance evidence and does not claim that one multiplier is optimal
for every host. Runtime artifacts remain below the outer workspace's ignored
`temp/` tree and are not committed.

- Host: Windows, 8 physical CPU cores / 16 logical CPUs
- Memory: approximately 47.22 GiB total and 32 GiB available before probing
- Local disk: approximately 604.55 GiB free before probing
- Workload per probe: real-only strategy, seed 101, population 200, one generation
- Scheduling: one benchmark cell at a time
- Measured interval: the cell's `02-run` command
- Validity: every probe attempted all 200 planned evaluations and produced valid
  cell evidence; Chrono retained its ordinary tolerated individual failures with
  141 finite results, while ngspice and synthetic each produced 200 finite results

The pre-change installed package expressed simulator capacity as fixed worker
counts plus yadof resource clamping. To measure candidate multipliers without
changing the source between trials, each probe converted the 8-core multiplier
to an integer worker count and disabled that old clamp. The final implementation
instead stores the multiplier, detects physical cores at cell materialization,
and records the resolved count.

## Selected defaults

| Baseline | Selected multiplier | Workers on this host | Selection evidence |
| --- | ---: | ---: | --- |
| `chrono/trebuchet` | 2.0 | 16 | Two selected runs took 21.435 s and 26.306 s (median 23.870 s), versus 46.408 s at the old effective 4 workers: 48.6% lower median runtime. CPU mean was 88.64%/88.25%, p50 98.05%/100%, and p95/peak 100%, establishing CPU as a bottleneck. |
| `ngspice/saw-ladder` | 2.0 | 16 | Three selected runs took 7.493 s, 9.148 s, and 7.364 s (median 7.493 s), versus old effective 8-worker runs of 8.304 s, 8.684 s, and 8.880 s (median 8.684 s): 13.7% lower median runtime. Higher candidates did not improve throughput. |
| `test-com/synthetic-antenna` | 1.0 | 8 | Three 8-worker runs took 12.227 s, 10.461 s, and 10.427 s (median 10.461 s). Below-one and above-one candidates were slower in these short trials, so one physical-core worker per core is retained. |

## Candidate sweep

Chrono candidates were 0.5x/4 workers (46.408 s), 1.0x/8 (30.474 s),
1.25x/10 (28.014 s), 1.5x/12 (27.408 s), 2.0x/16 (21.435 s and
26.306 s), 3.0x/24 (25.615 s), and 4.0x/32 (29.383 s).

ngspice candidates were 1.0x/8 (8.304 s, 8.684 s, and 8.880 s),
1.5x/12 (11.383 s), 2.0x/16 (7.493 s, 9.148 s, and 7.364 s),
3.0x/24 (9.899 s), 4.0x/32 (8.676 s), and 8.0x/64 (10.397 s).

Synthetic candidates were 0.75x/6 (12.488 s), 0.875x/7 (12.859 s),
1.0x/8 (12.227 s, 10.461 s, and 10.427 s), 1.25x/10 (10.718 s),
1.5x/12 (12.486 s), 1.75x/14 (13.011 s), 2.0x/16 (12.841 s),
4.0x/32 (14.707 s), and 8.0x/64 (15.511 s).

The selected Chrono point satisfies the original utilization objective by making
CPU the observed bottleneck. ngspice and synthetic do not sustain full-host CPU,
memory, or disk saturation during this short workload, but extra workers past
their selected points increase overhead and reduce speed. The defaults therefore
optimize observed throughput rather than forcing higher utilization.

## Raw evidence identities

Each listed file is a JSON array of per-probe results including workspace status,
validity/counts, run duration, system CPU/memory/disk samples, process-tree RSS,
and process count. Paths are relative to the outer workspace.

| Summary | Entries | SHA-256 |
| --- | ---: | --- |
| `temp/benchmark-concurrency-probes/20260902_111427/summary.json` | 1 | `9B1348C1213858A7FAAC42BEF2883CD6E1F45B37A1599F1E836BE75D84D62782` |
| `temp/benchmark-concurrency-probes/20260902_111646/summary.json` | 11 | `F7ABC6AC70F973E1F1083856FE22751D0C9EB2558B0774220D0A9613BE641E82` |
| `temp/benchmark-concurrency-probes/20260902_112424/summary.json` | 7 | `FB6005F8C8E347250EF34CBF70E532634A97E4CAB37C3571C879A9F7F5A8B5BA` |
| `temp/benchmark-concurrency-probes/20260902_112815/summary.json` | 6 | `7DBBF7DBF32B95715FC3AD95738D68994AFA7FF6F51E420F71892DC28865CAD5` |
| `temp/benchmark-concurrency-probes/20260902_113135/summary.json` | 2 | `56693D074FA6F14A7E5B42D358659A26C8EE70190A789F0E6F0481AF1FBB08B9` |
| `temp/benchmark-concurrency-probes/20260902_113223/summary.json` | 2 | `1106F0FAB3EBF6DD3BF8C0DB8AF8E601CA7382998EA00F643DE98AE8BF2D5A48` |

## Interpretation boundary

Short-run timing has normal host noise, especially for sub-ten-second ngspice
cells. The repeated selected/current points reduce but do not eliminate that
noise. The physical-core multiplier makes the policy scale across hosts; it does
not guarantee identical saturation or an identical optimum. Baseline authors may
override the positive multiplier after equivalent measurements on a materially
different simulator or host.

## Final installed-package acceptance

After the implementation, fresh workspace
`temp/20260902_115407-benchmark-concurrency-final-acceptance` ran the installed
`yadof 0.5.0` and `yadof-benchmark 0.5.0` packages. Its three real-only cells used
population 200, one generation, seed 101, serial cell scheduling, and the three
packaged baseline multipliers. The workspace completed 3/3 collected and valid in
126.694 seconds with no anomaly or timeout.

State recorded physical-core detection through
`psutil.cpu_count(logical=False)`, 8 physical cores, floor rounding, and resolved
workers 16/16/8 for Chrono/ngspice/synthetic. The corresponding `02-run` commands
took 26.121 s, 9.437 s, and 12.634 s. Every cell attempted all 200 evaluations;
Chrono retained 141 finite results and 59 tolerated failures, while the other two
cells retained 200 finite results each.

Representative recorded yadof job metadata proves that host observation no longer
clamps the explicit cap. Both 2.0x cells record
`fast_resource_cpu_worker_limit=8` as an advisory value while also recording
`fast_worker_configured_max=16`, `fast_worker_count=16`, and
`fast_resource_limits_enforced=false`. Materialized configs contain only the
resolved `FAST_EVALUATION_MAX_WORKERS`; benchmark does not disable resource
observation.

| Artifact below the acceptance workspace | SHA-256 |
| --- | --- |
| `state.json` | `066FC057229D1285403785BBB1BE4D68C23427A81862122C9BA935246F9F8066` |
| `spec.json` | `F1BF48BBD559DA5AA3C8B580A538F4C33B9F26F72079F7B7F764621E03B43EC3` |
| `runtime.json` | `F30119841F291D4A1515CC9354186EA773D822BFAC58C2D13F42BCD9F7B2C9A2` |
| `reports/descriptive-results.json` | `58606DBB24A6AED9F8A41C99F7E47B467AF14BADE9BF5C962ECD34388AEA3D4D` |
| `reports/summary.md` | `009D4E93976DAE75C003F11AE61EB2F9B0DF973800FF3BA09ABA085DFB1280F5` |
