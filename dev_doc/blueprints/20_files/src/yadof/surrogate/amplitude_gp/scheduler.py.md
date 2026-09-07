# Blueprint: surrogate/amplitude_gp/scheduler.py

## Contract

Own at most one pending training handle for each workspace/strategy/settings key.
Start receives explicit caller data and the generation snapshot/session, skips
insufficient rows, and reports already-running work without duplicating fits.
Finish waits on the original worker, reports completion/cancellation/failure,
releases the handle even on errors, and removes only that pending reference.
No scheduler reconstructs evidence from a session.

Freshness compares compatible completed generation age with configured lag.
The active ensure operation may wait and, if still needed, start and finish a fit;
pure selection freshness remains the shared read-only component protocol.
Workspace deactivation drains each pending handle, reports errors, and clears
by the owned workspace root without rereading a possibly edited/invalid live
configuration. Waiting preserves a supplied workspace context's configured paths.
Deactivation removes
only this component's schedules and cached states. Status records carry action,
requested/pending/completed generation and bounded error text.
