# Qdrant recall adapter candidate

This branch adds a bounded, opt-in Qdrant adapter behind Novel's existing `RecallBackend` contract. It directly serves long-form consistency by making character/world/canon memory searchable without replacing `ContextAssembler` or changing the default path.

## Upstream

- Repository: https://github.com/qdrant/qdrant-client
- Version: v1.19.1
- Commit: `cf747f4b6fa71ba35dfb467931f3fa65f2cdf263`
- License: Apache-2.0
- Source used in this run: GitHub. No matching qdrant-client source bundle was found in Drive `Github`.

## Boundaries

- Default remains off; existing in-memory recall remains the baseline.
- Embedding selection stays outside the adapter.
- The provided factory is local-only and rejects URL-like locations.
- Upserts fail closed on invalid IDs/text, non-finite or wrong-size vectors, or non-JSON-safe metadata.
- Query results must carry Novel's payload schema before becoming `RecallHit`.
- Raw reference novels are not automatically persisted; use this for authorized derived/canon/world/character state.
- No generation prompt, Style DNA logic, or originality gate is changed.

## Evaluation gate

Keep this as an A/B candidate until frozen chapter evaluation measures continuity/recall quality, latency, memory growth, and false-recall behavior. Better retrieval alone is insufficient if it increases continuity errors or retrieves reference-work wording.
