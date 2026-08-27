# Artifact Sync Policy

This policy defines required synchronization behavior between a local/Work/Codex workspace, GitHub, and the project Google Drive vault.

## Meaning of “sync all artifacts”

`同步所有成果` / `更新所有成果` means: reconcile all known artifacts and publish only missing or materially changed content. It does **not** mean re-upload every file or recreate every commit.

## Required preflight

Before any write:

1. Inventory workspace/local artifacts.
2. Read the current GitHub target branch/tree.
3. Read the relevant Drive project folders.
4. Classify every candidate as one of:
   - `NEW`
   - `CHANGED`
   - `SKIP_IDENTICAL`
   - `HISTORICAL_DUPLICATE_PRESERVED`
   - `CONFLICT_NEEDS_REVIEW`
5. Only then perform writes.

Starting uploads before this classification is a policy violation.

## GitHub rules

- Binary files: compare exact bytes/content hash; identical => `SKIP_IDENTICAL`.
- Text files: keep raw blob identity for provenance, but for duplicate suppression normalize CRLF/CR to LF and ignore a final trailing-newline-only difference. Normalized-identical text must not create a commit merely for formatting.
- Materially changed content => update and mark `CHANGED`.
- Batch related changes into the minimum practical number of commits. One-file-per-commit bulk publishing is prohibited unless each file is genuinely an independent logical change.

## Google Drive rules

1. Compare target folder, filename, size, and SHA-256.
2. If identical content already exists in the correct folder, reuse the existing Drive ID and mark `SKIP_IDENTICAL`.
3. If the same logical artifact has changed bytes, update the existing Drive object in place when safe and supported.
4. Create a new Drive object only for a genuinely new artifact or an intentionally distinct immutable snapshot/run.
5. Same-name copies are not a default versioning mechanism.

## Historical evidence exception

Do not deduplicate away artifacts whose filenames or metadata represent distinct experimental history, including `r1/r2/r3`, different run IDs/timestamps, frozen evidence, first-real results, replays, calibration attempts, and pre/post-freeze snapshots. Even if payload hashes match, retain them as `HISTORICAL_DUPLICATE_PRESERVED` when separate identity matters for auditability. Never delete them automatically.

## Aggregate archives

An archive such as `all-project-artifacts-YYYYMMDD.zip` is a checkpoint convenience, not permission to duplicate all constituent artifacts. Reconcile constituents first, include a path/name + size + SHA-256 manifest where practical, compare the aggregate archive itself against Drive, and skip uploading an identical archive.

## Conflict handling

Use `CONFLICT_NEEDS_REVIEW` instead of guessing when GitHub and workspace changed the same logical file independently, two Drive objects conflict, a frozen artifact appears to be replaced, or provenance cannot be established. Do not silently choose the newest timestamp as truth.

## Required report

Every synchronization must report:

```text
NEW: <count>
CHANGED: <count>
SKIP_IDENTICAL: <count>
HISTORICAL_DUPLICATE_PRESERVED: <count>
CONFLICT_NEEDS_REVIEW: <count>
GitHub commits created: <count>
Drive files created: <count>
Drive files updated in place: <count>
```

Identify destructive actions separately; if none were needed, say so.

## Idempotency acceptance criterion

Given unchanged workspace, GitHub, and Drive inputs, a second consecutive run must create **zero GitHub commits and zero new Drive objects**, while preserving intentional historical evidence unchanged.
