# Module blueprint: application

## Intent

Coordinate the desktop process without absorbing tab layout, plotting, checkpoint,
or record logic.

## Functionalities

- Accept `--workspace` from `yadof view surrogate` or the nested module parser and
  construct the Tk root.
- Configure the top-level window and shared styles.
- Build the workspace header, two-tab notebook, and status footer.
- Load/replace one `SurrogateWorkspace`.
- Own one executor worker and one main-thread callback queue.
- Submit interactive prediction and cross-generation audit work.
- Suppress stale results using monotonic request serials.
- Set and clear the cooperative audit cancellation event.
- Convert backend/Tk exceptions into status text and visible dialogs.
- Cancel pending work and shut down safely.

## I/O Format

Input is an optional workspace path plus user intents emitted by tab components.
Backend work returns immutable `PredictionResult` or
`CrossGenerationErrorAudit` values. UI mutation is performed only by callbacks
drained on the Tk thread.

## Non-Obvious Techniques

- `Future.cancel()` cannot stop already-running inference; prediction serials are
  therefore authoritative for ignoring superseded results.
- Audit cancellation is a separate `threading.Event` checked inside backend batch
  loops.
- The executor has one worker on purpose: model loads and accelerator inference do
  not race one another.
- Unexpected Tk callback exceptions are routed through
  `report_callback_exception` so console-only errors are also visible in the GUI.

## Mutability Profile

Window copy and top-level presentation may change freely. The main-thread-only UI
rule, stale-result suppression, explicit workspace selection, lazy optional
dependency boundary, and separation from tab/backend responsibilities should
remain stable.
