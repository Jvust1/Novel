# Project Safety Policy

Status: **REQUIRED**  
Version: **1.0**  
Effective: **2026-08-28**

This policy is a repository-wide safety gate for ChatGPT, Codex, agents, automations, scripts, and other assistant-driven GitHub operations performed on the user's behalf.

## 1. Authority and precedence

- Project-specific governance, release gates, frozen-asset rules, approval checkpoints, and evidence requirements remain authoritative.
- This policy may add safeguards but must never weaken a stricter project rule.
- When rules conflict, the stricter / more conservative rule wins.
- Ambiguity must fail closed: stop and surface the uncertainty instead of guessing.

## 2. Default mode: read-only

The default GitHub posture is read-only. Searching, fetching, reviewing, auditing, comparing, and inspecting files, commits, PRs, issues, branches, CI, and metadata may proceed without a mutation approval.

No write permission should be inferred merely because a connected tool technically allows writes.

## 3. Mutation preflight is mandatory

Before any GitHub mutation, identify and report the exact:

1. repository;
2. target branch/ref;
3. file, PR, issue, branch, release, rule, or other object affected;
4. intended operation;
5. expected scope and impact;
6. current SHA/ref or equivalent target identity when available;
7. reversibility / rollback implications.

Do not mutate an unresolved or guessed target.

## 4. High-risk operations require two-stage approval

The following operations require a fresh explicit approval **after** the preflight has displayed the exact target and impact:

- direct modification of `main`, the default branch, or any protected/release branch;
- deleting files, directories, branches, releases, tags, or other repository objects;
- replacing or broadly overwriting existing content;
- batch writes across multiple repositories;
- merge, auto-merge, branch retargeting, or equivalent integration actions;
- moving refs, rollback, reset, history rewrite, or force operations;
- permission, ruleset, branch-protection, workflow-security, or access-control changes;
- replacement of frozen evidence, canonical assets, release artifacts, benchmark baselines, or authoritative snapshots;
- destructive cleanup or any action with material data-loss risk.

The user's original instruction such as “delete X”, “modify X”, “merge X”, or “update all repos” states intent but **does not count as the post-preflight approval** for a high-risk operation.

Valid second-stage approval must occur after preflight and clearly authorize execution, e.g. “执行”, “确认执行”, “可以”, or an equivalently unambiguous instruction.

## 5. Stale-target protection

If the relevant branch/ref/SHA or target state changes after preflight or approval, stop. Re-read the target, refresh the preflight, and obtain a new approval when the operation remains high risk.

Never apply a destructive write using stale target identity.

## 6. Main/default branch discipline

Prefer a dedicated branch and PR for ordinary development work when practical.

Direct writes to `main` / the default branch are allowed only when:

- the exact direct-write scope was shown in preflight; and
- a fresh post-preflight approval explicitly authorized it.

Approval for one direct write does not authorize unrelated later writes.

## 7. Destructive command restrictions

Force push, history rewrite, `reset --hard`, destructive clean operations, non-fast-forward ref moves, and equivalent actions are prohibited by default.

They may be considered only for an explicit recovery scenario with a dedicated preflight that identifies data-loss risk, recovery source, and rollback/recovery path, followed by explicit approval.

## 8. Frozen, release, evidence, and backup assets

- Frozen/canonical evidence and release assets must not be silently regenerated, replaced, or normalized.
- Backup repositories and backup snapshots are immutable by default.
- A backup may be changed only when the user explicitly identifies that backup as the mutation target after a dedicated preflight.
- Safety-policy maintenance itself is not sufficient reason to alter an immutable backup snapshot.

## 9. Scope containment

Perform only the approved change.

Do not bundle unrelated refactors, formatting changes, dependency upgrades, cleanup, renames, or opportunistic fixes into an approved mutation unless they were included in the preflight scope.

## 10. Verification after writes

After every mutation, perform fresh verification appropriate to the operation before claiming completion.

Examples:

- file create/update: read back the target and verify expected content / SHA;
- deletion: verify the target no longer resolves while unrelated targets remain intact;
- branch/ref operation: re-read the ref and confirm its exact commit;
- merge: verify merged state, resulting commit, and required checks;
- multi-repository update: verify each repository independently.

A tool reporting “success” is not by itself sufficient evidence for a completion claim.

## 11. Failure handling

If any write or verification step fails:

- stop further dependent mutations;
- report exactly what succeeded, failed, or remains unverified;
- do not compensate with additional destructive actions unless separately approved;
- preserve recoverability and current evidence.

## 12. Secret and credential safety

Never commit API keys, tokens, passwords, private credentials, authentication cookies, or other secrets. If secret material is detected, stop the write and surface the issue without reproducing the secret unnecessarily.

## 13. Approval scope and expiry

Approval is scoped to the preflight that immediately preceded it. It expires when:

- repository, branch, target path/object, operation, or material impact changes;
- the target becomes stale;
- new destructive consequences are discovered; or
- execution expands beyond the displayed scope.

A previous approval must never be reused as blanket authorization for future GitHub mutations.
