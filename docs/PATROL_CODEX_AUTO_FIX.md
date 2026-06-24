# Patrol to Codex Auto-fix

## What runs automatically

1. Claude patrol reviews the latest article and writes a handoff markdown file.
2. On a review NG, Claude runs `scripts/run_patrol_codex_fix.py --handoff <path>`.
3. The runner validates one article target, creates a temporary worktree, and starts `codex exec` in `workspace-write` mode.
4. Codex may edit only that article. Any other changed file stops the run.
5. The runner runs `npm ci`, `npm run build`, and `npm run check`, then creates a `patrol-auto-fix` PR.

The runner never pushes to `main`. It records local retry state in `.ai-handoff/patrol_auto_fix_state.json`.

## Codex CLI compatibility

The installed Codex CLI was checked on 2026-06-24. It supports `codex exec`, stdin prompts, `--cd`, `--sandbox`, `--ask-for-approval`, and `--output-last-message`. It does **not** provide `--prompt-file`, `--auto-pr`, or `--label` options.

`scripts/run_patrol_codex_fix.py` supplies those missing behaviors safely:

- handoff input: validated file copied into the temporary worktree and read by Codex
- PR creation: wrapper-controlled `gh pr create`
- label: wrapper-controlled `patrol-auto-fix`

## Stop conditions

- The same slug receives two consecutive patrol NG results: no second Codex repair runs; manual intervention is required.
- Codex changes anything other than the handoff target article.
- Build, check, commit, push, or PR creation fails.

When patrol later finds the article clean, it runs:

```powershell
python scripts/run_patrol_codex_fix.py --mark-clean --slug <slug>
```

## Trial mode

The workflow is shipped in manual-merge mode. `PATROL_AUTO_MERGE_ENABLED` is unset/false, so a labeled patrol PR remains open after CI.

Use a real handoff validation without starting Codex:

```powershell
python scripts/run_patrol_codex_fix.py --handoff .ai-handoff/blog-quality-patrol-YYYYMMDD.md --dry-run
```

Run one real repair manually and review its PR before enabling automatic merges.

## Enable automatic merge after the trial

1. In GitHub repository settings, enable **Settings > General > Pull Requests > Allow auto-merge**.
2. Create repository variable **Settings > Secrets and variables > Actions > Variables**:

```text
PATROL_AUTO_MERGE_ENABLED=true
```

3. Confirm that only PRs carrying `patrol-auto-fix` are affected.

To pause the system, set the variable to `false`. To stop one pending PR, add `do-not-merge`; the workflow disables its auto-merge request.

## Rollback

1. Set `PATROL_AUTO_MERGE_ENABLED=false`.
2. Add `do-not-merge` to any open patrol PR.
3. Disable or edit `.github/workflows/auto_merge_patrol_fix.yml` only through a normal reviewed PR.
