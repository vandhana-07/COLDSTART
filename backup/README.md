# backup/ — safety net and working rules

## If git stops recognising the repository

Run this from the project root:

```bash
bash backup/restore_git.sh
```

It rebuilds `.git/config` (and `.git/HEAD` if needed) and then prints the history
so you can see the commits are intact. It never deletes anything and does nothing
if the config is already present. **Tested** by deleting `.git/config` and running
it — history and identity both survived.

Why it might be needed: this workspace excludes `.git/config` from workspace
snapshots, and `.git/config` is where git keeps the user identity and repository
flags.

## Working rules agreed for this project

These exist because a physics file (`app/engine/optimizer.py`) was once overwritten
during a fix, and with no version control in place the previous version was
unrecoverable.

1. **Commit after each task**, with a message that names the task, e.g.
   `Task A: optimizer brute-force verification`.
2. **Check `git status` is clean before modifying an existing file**, so the last
   known-good state is always one commit away.
3. **Edit the specific functions that need changing — do not overwrite whole files.**
4. **If a file genuinely must be replaced**, copy the old one to
   `backup/<filename>.bak` **first**, and say so out loud.
5. **Never run** `git reset --hard`, `git push --force`, `git clean`, or delete
   `.git`.
6. **Show `git log --oneline` at the end of a task** so every checkpoint is visible.

## What is version-controlled

Tracked: `app/`, `audit/`, `verify/`, `tests/`, `bench/`, `ppt/`, and this folder.

Ignored: `cache/` (real API responses used as the offline fallback), bytecode,
virtualenvs, `node_modules/`, and temp files. See `.gitignore`.

> **Consequence of ignoring `cache/`:** a fresh clone has no offline data, so the
> first run needs network. If demo-day wifi is a risk, consider tracking `cache/`
> so OFFLINE MODE has something to fall back to.
