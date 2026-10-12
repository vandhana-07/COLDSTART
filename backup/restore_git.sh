#!/usr/bin/env bash
# ============================================================
#  restore_git.sh — recover the repo if .git/config is missing
#
#  WHY THIS EXISTS
#  --------------
#  This workspace excludes .git/config from workspace snapshots.
#  .git/config holds `repositoryformatversion`, which git needs to
#  recognise a repository at all. If the snapshot is restored without
#  it, git will report "not a git repository" even though every commit
#  is still present under .git/objects.
#
#  This script rewrites the two files git actually needs. It does NOT
#  touch the commit history, and it never deletes anything.
#
#  USAGE
#  -----
#      cd /home/user/sedhacks26
#      bash backup/restore_git.sh
#
#  Safe to run at any time: if .git/config already exists it does nothing.
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d .git ]; then
    echo "ERROR: no .git directory here. This is not the project root,"
    echo "       or the repository has been lost. Stopping without changes."
    exit 1
fi

if [ -f .git/config ]; then
    echo "OK: .git/config already present — nothing to do."
    git log --oneline | head -5
    exit 0
fi

echo "MISSING: .git/config — rebuilding it now."

cat > .git/config <<'EOF'
[core]
	repositoryformatversion = 0
	filemode = true
	bare = false
	logallrefupdates = true
[user]
	name = COLDSTART Team
	email = team@coldstart.local
EOF

# .git/HEAD and refs are normally intact; only recreate if absent.
if [ ! -f .git/HEAD ]; then
    echo "MISSING: .git/HEAD — restoring to the default branch."
    echo "ref: refs/heads/master" > .git/HEAD
fi

echo "Rebuilt. Verifying the history is intact:"
git log --oneline
echo
echo "Working tree:"
git status --short || true
