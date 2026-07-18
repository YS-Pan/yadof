# Module blueprint: optimize

`yadof.optimize` owns workspace-explicit generation APIs, history warm start,
pymoo GA/NSGA-III candidate mechanics, GPSAF alpha/beta/gamma pressure, exploration
quota, real-evaluation validation, and lightweight generation metadata. Config is
loaded once per generation. `run_generations` supports start/resume, stable run and
optimization identities, temporary config overrides, and optional immediate
all-infinite failure.
