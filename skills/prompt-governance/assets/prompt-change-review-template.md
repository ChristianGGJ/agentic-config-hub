# Prompt Change Review

> Attach this to every PR that adds, edits, or removes a production prompt.
> Reviewers approve on evidence, not vibes. A change with no eval delta is not reviewable.

## 1. Summary

- **Prompt:** `<slug>` (e.g. `summarizer`)
- **Version:** `<old>` -> `<new>` (semver: MAJOR = behavior/contract change, MINOR = capability add, PATCH = wording fix)
- **Author / owner:**
- **Target model:** `<family + tier>` (record the exact model id you tested against; note if it differs from production)
- **Reason for change:** (bug, quality gap, new requirement, model migration, cost change)

## 2. Diff Rationale (What + Why + How)

- **What changed:** one line per meaningful edit.
- **Why:** the failure mode or requirement each edit addresses.
- **How you know it helps:** the eval evidence below, not intuition.

## 3. Eval Evidence (required)

Run the golden dataset against both versions with the same runner and dataset version.

| Metric | Old version | New version | Delta | Threshold | Pass? |
|---|---|---|---|---|---|
| Weighted pass rate |  |  |  |  |  |
| Exact-match cases |  |  |  |  |  |
| Schema-valid cases |  |  |  |  |  |
| Judge score (if used) |  |  |  |  |  |
| p50 / p95 latency |  |  |  |  |  |
| Cost per call |  |  |  |  |  |

- Golden dataset version: `<dataset ref/commit>`
- Runner command: `python scripts/eval_runner.py --golden <path> --threshold <t> --json`
- New failures introduced (case ids + reason):
- Previously failing cases now fixed (case ids):

> If the new version regresses ANY case that the old version passed, list each one and justify why the net change is still an improvement, or do not merge.

## 4. Blast Radius

- Features / endpoints that consume this prompt:
- Downstream parsers or contracts that depend on the output shape (breaks if MAJOR):
- Does this require a golden-dataset update? (a behavior change usually does) yes / no
- Model-version assumption: does this prompt depend on current model behavior that a model update could shift? yes / no

## 5. Rollout Plan

- Promotion path: dev -> staging -> production
- Rollout mode: full cutover / A/B test / canary %
- If A/B: success metric, minimum sample size, and decision date (define BEFORE launch)
- Rollback trigger + command (see SKILL.md "Production Monitoring + Rollback")
- Monitoring window post-deploy: 24-48h

## 6. Reviewer Checklist

- [ ] Eval evidence attached and reproducible (dataset version pinned)
- [ ] No unexplained regression vs. current production version
- [ ] Golden dataset updated if behavior changed
- [ ] Output contract unchanged, or consumers updated for a MAJOR bump
- [ ] Rollback path verified (previous version still present in registry)
- [ ] Owner and semver bump correct in the registry entry
