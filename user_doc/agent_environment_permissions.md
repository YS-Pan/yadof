# AI agent host permissions and Git ownership

This is an optional troubleshooting reference for an AI coding agent acting under
the user's direction. It describes host process identities, sandbox restrictions,
filesystem ACLs, and Git trust/write checks. These mechanisms are not yadof
features, configuration, or runtime policy. The same issues can affect any project
or command executed by an agent.

## Agent shell versus user terminal

An agent's shell may run with a sandbox identity or restricted security token that
differs from the user's interactive terminal, even on the same machine. An
existing directory can therefore be readable to the agent but not writable by the
process that performs real work. Conversely, a repository created by the agent may
be owned by an agent identity that the user's Git process does not automatically
trust.

Read-only commands do not prove that later mutation will succeed. For example,
documentation, status, configuration, or validation commands may pass while a real
command cannot create, replace, or clean up files in an existing generated
directory. Diagnose the actual path and execution identity before attributing this
symptom to application code.

On Windows, a read-only ACL inspection can use:

```powershell
Get-Acl -LiteralPath "C:\absolute\path" | Format-List Owner,AccessToString
```

Confirm that no earlier process still owns a relevant file or lock. Then prefer
one of these narrowly scoped remedies:

1. Ask for explicit user approval to run the exact command outside the agent
   sandbox.
2. Ask the user to run the exact command in their own terminal.
3. If a persistent shared arrangement is intended, grant only the necessary
   identity access to the exact project-owned mutable paths.

Do not broadly weaken a directory tree's ACL, change unrelated ownership, or write
mutable data into an installed package merely to bypass a sandbox boundary.

## Git index write permission

Git updates `.git/index` and normally creates `.git/index.lock` while staging or
committing. An error such as `Unable to create .git/index.lock: Permission denied`
can mean that the current identity cannot write the repository metadata. It does
not by itself prove that a stale lock exists.

Before changing anything:

- confirm the command targets the intended repository;
- check whether another Git process is active;
- inspect ownership and ACLs on the repository and its `.git` directory;
- distinguish a missing write permission from an existing lock file.

Never delete `.git/index.lock` until the exact repository has been verified, no Git
process is using it, and the user has authorized that cleanup. Removing a live lock
can interfere with an active Git operation.

## Git dubious ownership

Git may reject a repository when the current user differs from the repository
owner, reporting `detected dubious ownership`. This is a Git safety check, separate
from filesystem write permission. Bypassing the trust check does not grant ACL
access.

After verifying that the repository is the user's intended and trusted target, a
single command can use an exact, non-persistent exception:

```powershell
git -c "safe.directory=C:/absolute/repository" status
git -c "safe.directory=C:/absolute/repository" add path/to/file
git -c "safe.directory=C:/absolute/repository" commit -m "Message"
```

Prefer this per-command form when only one agent operation needs the exception. A
persistent exact-repository exception is an external Git configuration change and
requires user authorization:

```powershell
git config --global --add safe.directory "C:/absolute/repository"
```

Do not use a wildcard `safe.directory=*`, and do not mark a repository safe before
checking its ownership and contents. If the trusted identity still cannot create
the index lock, resolve the separate `.git` write permission rather than adding
more trust exceptions.

## Handoff

When permissions affect a task, report the exact path, observed owner/identity,
failed operation, and whether the workaround was per-command or persistent. State
explicitly when global Git configuration or filesystem ACLs were left unchanged.
