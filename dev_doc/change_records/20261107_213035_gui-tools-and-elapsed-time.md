# 2026-11-07 - GUI tools folder and optimization elapsed time

## Context

The user requested a tools-folder shortcut and a launch-scoped elapsed-time display
for the installed 0.8.0 GUI. The selected source checkout and its development
environment identify as 0.7.0. The explicitly identified installation at
`C:/Users/A2092/AppData/Local/Programs/Yadof` identifies as 0.8.0 in both runtime
and distribution metadata. All 242 tracked package source/resource files match
the checkout HEAD except `_version.py`; there are no extra runtime files. In
particular its original GUI is byte-for-byte identical after newline normalization.

## Change

- Add **tools** beside the history-view buttons. It opens the GUI installation's
  `yadof/tools` directory with Windows Explorer, without requiring a workspace.
- Show **仿真总耗时** beside generation progress. An accepted start resets and
  starts a monotonic clock, including startup and smoke. Clicking stop freezes it
  immediately; normal/failed exit and launch failure also freeze it. Subsequent
  starts begin at zero. Durations use `HH:MM:SS` below one day and `D+HH:MM:SS`
  from one day onward, for example `1+02:03:04`.
- Refresh on the existing Tk event pump; no additional timer threads, callback
  chains, history writes or core execution changes are introduced.
- Update the GUI user guide and tools/test blueprints, and add focused tests for
  installed-directory selection, open failure, timing lifecycle and day rollover.

## Distribution boundary

Implementation changes remain in `src/yadof/`. An isolated build under
`temp/gui-080-20261107/` combines the verified clean source baseline, the installed
0.8.0 version and documentation, and only this GUI change. This preserves 0.8.0
and avoids bundling unrelated worktree changes. Installed source is never edited
directly; installation uses a regularly built wheel. The separate administrator
application and runtime dependencies are outside this GUI update.

## Validation

- GUI-focused installed-wheel tests: 60 passed, including real Tk controls with
  fake workers/commands and a controlled clock.
- The complete isolated 0.8.0 run passed 663 tests and failed only the 0.7.0
  baseline's hard-coded version assertion. The isolated 0.8.0 test copy updates
  that expected version; the original checkout's 0.7.0 test remains unchanged.
  After reinstalling the final wheel, that test plus the complete GUI suite passed
  together: 61 passed. All 664 distinct tests have therefore passed with the
  release-appropriate version expectation.
- The rebuilt wheel preserves the original 0.8.0 distribution metadata and
  dependency declarations exactly. Its only changed non-document runtime member
  is `yadof/tools/condor_gui.py`.
- Windows Computer Use returned `window capture timed out: timed out waiting on
  channel` twice. Screenshot inspection is unavailable and is not claimed as
  visual acceptance; the GUI opened only for that check was closed without
  starting any optimization.
- The user's private installation was updated with pip `--force-reinstall
  --no-deps --no-compile`. Its real Tk controls pass separate Python 3.11.15
  acceptance for tools, start, day rollover, stop, restart and natural completion,
  with all task/pool workers replaced by fakes. The installed 828 package members
  match the wheel exactly, and the only non-document runtime difference from the
  previous installation is the GUI module. Backup and acceptance evidence remain
  under `temp/gui-080-20261107/`.
