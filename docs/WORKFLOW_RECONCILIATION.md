# Existing workflow reconciliation (local pilot)

This slice reuses two existing Novel fixes to make the licensed MMR/speaker integrations safer in the author workflow. It is not counted as another ≥10,000-star upstream project and does not merge or replace either source PR.

## Exact sources

- [PR13](https://github.com/Jvust1/Novel/pull/13), commit `766efe52b19b6b1c20491f66f1902851516cebe7`: in-place update/deduplication of an existing chapter summary, plus nonpositive recent-summary limit handling. Only these methods are ported; newer storage/long-form methods are retained
- [PR16](https://github.com/Jvust1/Novel/pull/16), commit `2b5e23fe3ba238ae6046dad125dd7d09847db13d`: `novel_ai/project_session.py` project-state caching/restoration. Adapt the field list to current core/MMR, omit unused desktop workflow bindings, and prepare target data before replacing current fields

## Concrete failures

Editing chapter001 after chapters001–006 previously produced order002,003,004,005,006,001. A two-chapter Active window then treated001 as recent and pushed true later history into Recall. The port preserves the original slot, removes same-ID duplicates and appends genuinely new chapters. It does not infer or repair the ordering of already-corrupted history.

Switching projects previously retained characters and pending plans from the previous book. The reused session cache now switches Bible/outline/characters/style/reference signatures/result/plan/goal/notes/recall settings together, including the unsubmitted new-character form. Returning to the previous project restores unsaved session work. Switching itself does not save chapter or character files. Provider credentials/settings remain outside the project cache.

A failed target-project read also needs care: Streamlit can remove keys for widgets not rendered during the failed run. Cache the prior draft before loading, avoid replacing active fields until loading succeeds, and restore the saved widget fields on the next valid selection. Tests reproduce a corrupt target JSON followed by returning to the prior project without losing its unsaved chapter goal. Empty project names, which the existing store maps to `novel`, also retain their drafts rather than being mistaken for an uninitialized project.

## Validation

`python -m pytest -q tests/test_project_session.py tests/test_app.py tests/test_context.py tests/test_memory.py`

`python -m compileall app.py novel_ai && python -m pytest -q`

Test coverage includes A→B→A, nested cache independence, no credential caching, unchanged on-disk project data during switching, failed-load recovery, old-summary edits, duplicate rows, recent/older recall membership and zero/negative recent limits. Source code and source branches remain separate from this local combined pilot.

## Limits

Unsaved drafts are retained only in the current server session; this is not a disk autosave or crash-recovery feature. The existing store is still non-transactional and project folder naming remains unchanged. Already-reordered historical summaries require explicit reconciliation because arbitrary chapter labels do not establish chronology. Not-yet-imported Style Lab/reference inputs and standalone review-input widgets remain session-wide; saved style profiles and reference signatures are project-scoped. The original workflow-reconciliation snapshot left the separate `locked_text` mapping unchanged; the later [Canon field slice](CANON_FIELD_RECONCILIATION.md) corrects that pre-existing UI behavior. No model call, new dependency, schema migration, real-story quality result or remote PR publication is included.
