# 2026-11-08 - Scope the AEDT desktop exporter to OptimizationSetup1

## Context

The user specified that the `.pyw` exporter must read only variables whose Include
box is checked in `OptimizationSetup1`, rather than searching other project
settings. Those setup-specific bounds may differ from the global `oa` attributes.

## Change

- The desktop preview/export APIs isolate one exact `OptimizationSetup1` block
  and its `Variables` block, matching nested AEDT begin/end markers.
- Only records with `i=true` are exported. Inclusion, Min/Max, discrete Level and
  units come from those records; global variable properties and other setups are
  never used to fill in or override them. Current values are not required or read.
- Missing, duplicate, malformed or empty target blocks stop the export before any
  backup or output replacement. The existing general workspace CLI is unchanged.
- The interface and current user/module documentation state this selection rule.

## Validation

Focused installed-package checks cover conflicting global/setup bounds, unchecked
variables, other setup names including prefix lookalikes, nested block endings,
empty/missing/malformed targets, units without a global fallback, discrete levels,
BOMs, backup preservation and the GUI error path. Real-project acceptance uses
disposable copies so existing task parameters and AEDT files remain intact.

- Focused installed-package parser/export/GUI/CLI suite: 57 passed.
- Real MMT2D copy: 29 selected variables, including Ah1 `[2, 7] mm` and discrete
  N `[1, 2, 3, 4, 5]`; unchecked `guide_len_Y` was excluded. Backup bytes and the
  original workspace parameter-file hash were verified.
- The full regression pass had 702 successes and five initial failures. Four
  needed source examples/reference files omitted from the isolated staging tree;
  one fake subprocess exceeded its timeout under concurrent load. After supplying
  those unchanged fixtures, all five failed cases passed on focused recheck.
- The user explicitly authorized direct replacement of the installed tool while
  MMT2D was running. Tested exporter modules and their documentation were deployed
  from the built 0.8.0 wheel with backups below
  `temp/aedt-setup1/installed-tool-before/`, and installed RECORD checksums updated.
  Version, configuration, evaluation API and Condor controller hashes were
  unchanged. The active optimization process remained alive after replacement.
- The installed runtime's tools-folder launcher, actual Tk preview (29 variables)
  and project-copy export were verified. Existing tool windows must reopen to
  load the updated modules.
