# 04 — Git and Team Workflow (mandatory)

## Initial setup — one person only
Run from the directory where the repository should be created. Replace `YOUR_GITHUB_REPO_URL`.
```bash
git clone YOUR_GITHUB_REPO_URL ReliefRoute
cd ReliefRoute
git switch -c dev
git add .
git commit -m "chore: establish ReliefRoute scaffold and v1 contracts"
git push -u origin dev
```
If repo is empty and already cloned, skip `git clone`. Protect `main` in GitHub settings and use `dev` as integration branch.

## Every member: first setup
```bash
git fetch origin
git switch dev
git pull --ff-only origin dev
git switch -c feat/<short-task-name>
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
python -m pip install -e '.[dev,agent,telegram,db]'
pytest
```

## Work loop
```bash
git status
git add <only-your-files>
git commit -m "feat(scope): concise change"
git fetch origin
git rebase origin/dev
pytest
git push -u origin feat/<short-task-name>
```
Open a PR from feature branch to `dev`; request review from a teammate. Never force-push shared branches. If rebase conflicts, resolve carefully, run tests, then `git rebase --continue`. Do not use `git push --force` on `dev` or `main`.

## Branch ownership
- A: `feat/agent-*`, `fix/agent-*`
- B: `feat/service-*`, `feat/api-*`, `feat/db-*`
- C: `feat/ui-*`, `feat/bot-*`, `feat/demo-*`
- Shared model/schema changes: coordinate in team chat before editing; one designated editor/PR at a time.

## PR checklist
- [ ] Scope is small and has one owner.
- [ ] Public contract unchanged OR docs + model + tests updated together.
- [ ] No secrets, personal tokens, or `.env` committed.
- [ ] `pytest` passes.
- [ ] No fake data presented as live.
- [ ] Errors are explicit and observable.
- [ ] Reviewer understands integration impact.

## Contract change protocol
1. Propose field/signature change in team chat.
2. Edit `shared/models.py`/`shared/contracts.py` and relevant docs in one PR.
3. Update contract tests.
4. Get approval from A, B, and C (at least acknowledgement from all owners).
5. Merge; dependent branches rebase and adapt before feature merge.

## Integration cadence for deadline day
- Every 45–60 minutes: merge only passing PRs into `dev`.
- After every merge: run `pytest` on `dev`.
- Freeze contracts early; after the freeze, only backward-compatible changes unless all owners agree.
- Keep `main` as the demo/release branch. Merge `dev` to `main` only after clean-start acceptance test.

## Emergency integration
If time is short, do not merge broken features. Disable a provider behind an explicit unavailable status; keep the vertical slice working.
