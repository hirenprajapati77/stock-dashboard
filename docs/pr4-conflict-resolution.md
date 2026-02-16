# PR #4 Conflict Resolution Guide

This repository cannot auto-resolve PR conflicts from GitHub unless the target branch is fetched locally.

## Conflicting files reported by GitHub

- `backend/app/services/rotation_alerts.py`
- `backend/app/services/screener_service.py`
- `backend/app/services/sector_service.py`
- `frontend/LABEL_REPLACEMENTS.md`
- `frontend/dashboard.js`
- `frontend/rotation.js`

## Fast path (recommended)

Run:

```bash
bash scripts/resolve_pr4_conflicts.sh
```

Then open each conflicted file and resolve markers (`<<<<<<<`, `=======`, `>>>>>>>`), run tests, and push.

## Manual path

```bash
git fetch origin
git checkout <your-pr-branch>
git merge origin/work
# OR: git rebase origin/work
```

If conflicts appear, resolve each file and complete merge/rebase:

```bash
git add backend/app/services/rotation_alerts.py \
        backend/app/services/screener_service.py \
        backend/app/services/sector_service.py \
        frontend/LABEL_REPLACEMENTS.md \
        frontend/dashboard.js \
        frontend/rotation.js

git commit -m "Resolve PR #4 merge conflicts"
# OR if rebasing:
# git rebase --continue

git push
```
