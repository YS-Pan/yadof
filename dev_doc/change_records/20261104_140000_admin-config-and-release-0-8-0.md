# 2026-11-04 - Administrator cluster GUI and yadof 0.8.0

The requested administrator GUI consolidates resource declarations, LAN membership
and bidirectional FRP STCP configuration. The root admin_config.pyw opens three
tabs with a shared HTCondor port/mode selector, native ClassAd monitoring and local
advertised addresses every ten seconds. Roles include manager, submit and worker;
runtime eviction is explicitly selectable. No Machine column appears.

Configuration generation uses native HTCondor/frpc fields only. GUI selections
live in separate credential-free ProgramData JSON. Existing loaded YADOF_*
metadata is removed while unrelated native settings survive. Native validators
run before mutation. ACL-restricted file/service/task snapshots support rollback;
leaving disables local Condor and the managed FRP startup task. Administrator code
stays outside the user wheel and is distributed by MSI and administrator ZIP.

The release starts from published v0.7.0 in an isolated release/v0.8.0 worktree,
preserving unrelated changes in the original D:/yadof checkout. The private-runtime
MSI gains an administrator launcher/Start menu shortcut. A reproducible build path
can reconstruct the audited runtime from a previous installation only after every
source file matches its published release manifest, excluding unknown files.

Validation covers generated native settings, roles/routing, token-file syntax,
legacy cleanup, local addresses during collector failure and rollback after
startup failure. GUI verification constructs all tabs without touching services.
Package tests use a regularly installed wheel with source injection disabled;
the bundled 3.11.15 runtime receives separate MSI acceptance. Desktop screenshot
automation timed out and is not counted as visual acceptance. Two-machine live
transfer and real cluster service changes are outside this release's local tests.
