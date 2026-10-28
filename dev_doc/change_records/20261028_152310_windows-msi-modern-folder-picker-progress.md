# 2026-10-28 15:23 - Modern MSI folder picker and installation progress

## Context

The user requested clicking to choose an installation directory instead of typing,
and a visible installation progress bar. They explicitly preferred the modern
Windows folder window used by the GUI workspace chooser over MSI's classic browser.

## Change and rationale

The Welcome dialog now displays a non-editable, property-bound destination and a
Browse button. An embedded native C UI action opens Windows IFileOpenDialog in
folder mode. It keeps MSI's impersonated action thread and uses no blocked client
owner HWND. Selection updates the directory tree with MsiSetTargetPath; cancelling
leaves the previous path intact. Zig 0.14.1 is a build-time-only dependency.

A modeless ProgressDlg subscribes to real SetProgress, ActionText and ActionData
events before ExecuteAction. Standard installer ErrorDialog controls handle errors.
Full-UI acceptance exposed a deep-path write failure, so the package now derives
the allowed destination length from its longest relative file path and validates
before copying files or removing a previous product. This payload allows 62 UTF-16
code units in the installation directory. The acceptance script checks path depth
before starting. Existing CAB hard links are reused when they already target the
same file, avoiding redundant unlink/relink work during UI rebuilds (one net line
added to that loop). The administrator guide is refreshed even with --reuse-payload.

## Verification

Release: dist/yadof-0.6.0-a2094-win-x64.msi, SHA-256 c71f5e62bcd605d8aa9dc28c2928a850a2b1a322dc723b731de331163fec802d.
The sibling acceptance JSON contains exact evidence and validation scope.
An isolated copy of the final native/UI code passed actual full-UI installation,
CLI/GUI launch, private-runtime/native dependency operations, Tk controller,
foreign-Python isolation and uninstall. All 25,629 installer-owned files were
removed and the existing user product remained installed. The QA copy skipped
Welcome/terminal prompts while retaining the authored progress window. Actual
progress values and changing actions were observed. A prior deliberately deeper
test failed during copy and was rolled back; no owned files remained.

Native path-boundary checks passed for 62/63 UTF-16 code units, including emoji.
An actual silent install rejected an overlong target before InstallInitialize,
without creating that target or replacing the user's installation. A real MSI
session confirmed that the picker's target setter updates INSTALLDIR and the
yadof_env child target. The final repack changes only INSTALLATION.md relative to
the successful full-UI runtime test; native code, UI/execute tables, dependencies
and all other installed file digests match. Source syntax and git diff --check pass.

## Limits

The release remains unsigned and has no clean-VM acceptance. Computer Use could
read control trees but screenshots/click geometry failed, so pixel-level visual
acceptance and the chooser's final confirmation click were not automated. The
modern chooser itself opened with address/navigation/new-folder controls; directory
propagation was verified separately through its actual Windows Installer setter.
This host still logs non-fatal backup-file ACL warnings during removal. Test
operations returned zero and ownership/registration cleanup was verified. No
system ACLs were modified. Source changes remain uncommitted.
