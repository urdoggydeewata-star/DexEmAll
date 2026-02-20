Git hook setup
==============

This repository includes a tracked `post-commit` hook at:

- `config/hooks/post-commit`

What it does
------------

- After each non-changelog commit, it appends a player-facing mechanics summary line to `MECHANICS_CHANGELOG.txt`.
- It then creates an automatic follow-up commit containing that changelog update.
- It skips changelog-only/hook-only commits to avoid loops.

Enable it locally
-----------------

Run this once in the repo root:

```bash
git config core.hooksPath config/hooks
chmod +x config/hooks/post-commit
```
