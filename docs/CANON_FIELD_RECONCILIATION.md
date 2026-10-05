# Canon field reconciliation (local only)

The prior workbench loaded `locked_text` from stored Story Bible data but built `StoryBible.locked_facts` from `rules_text`. Distinct stored hard facts could therefore disappear from planning/drafting/review inputs, or be replaced by the world-rule list when saving.

Reuse the separate locked-fact editor and mapping already present in [Novel PR16](https://github.com/Jvust1/Novel/pull/16), exact commit `2b5e23fe3ba238ae6046dad125dd7d09847db13d`:

- The existing world-rule editor edits `world_rules`
- A separate locked-fact editor edits `locked_facts`
- `current_bible()` preserves both lists independently for saving and all existing provider calls
- The already-reconciled project-session cache scopes `locked_text` and preserves unsaved edits when switching books

This adds no model call, dependency or new qualifying upstream source. Existing stored duplicate world-rule/locked-fact values are retained; no data migration, automatic deduplication or deletion occurs.

AppTests use original synthetic facts and a mocked provider. They verify distinct values on load, editing/saving, a fresh app restart, the actual captured plan request, and A→B→A unsaved fact restoration. Engine prompt functions already serialize the full Bible for draft/review/extraction; the corrected input now reaches those same paths. This is wiring verification, not proof that a model obeys Canon.
