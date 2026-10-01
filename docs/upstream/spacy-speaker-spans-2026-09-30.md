# spaCy speaker-span pilot

## Proven gap and source reuse

Before this change, with registered characters `林舟` and `林舟明`, `林舟明问：“你看清楚了吗？”` was credited to both characters. This polluted per-character Voice DNA and could create false drift findings that enter repair.

Reuse [spaCy](https://github.com/explosion/spaCy)'s MIT-licensed `filter_spans` loop, pinned at `26b4d1dc04a812f426e4bef3e8a1b6f159d6f048`, matching the existing submodule. GitHub API verified **33,931 stars** on 2026-09-30 UTC. Full license/provenance live under `third_party/spacy/`.

## Actual runtime path

`canonical character names → exact name spans → spaCy longest-span filtering → conservative speech-tag attribution → character_voice_dna → voice_drift → ChapterReview → existing repair path`

Both engines, the workbench and accepted-chapter analytics already call `character_voice_dna`, so this changes the existing runtime instead of adding an unused adapter. No external call, model download, NER model or new dependency is introduced.

- Prefer the longest registered name for overlapping spans, independent of character-list order
- Count a quote only when exactly one registered speaker matches its explicit tag; omit ambiguous multi-name tags
- Match explicit speech verbs/adverbs; reject negated/non-speaking tags and obvious addressee prefixes
- Avoid crossing sentence/newline boundaries and comma-separated attribution clauses; adjacent pre-tags keep their own quotes
- Preserve existing numeric Voice DNA dimensions and same-speaker duplicate-line handling
- Add `attribution_version=2` to new per-character metrics

## Baseline compatibility

Legacy or mismatched-version metrics are retained on disk but excluded from new aggregate baselines. They may contain the old overlapping-name attribution error and must not be mixed with new values. New drift review therefore warms up from compatible samples using the existing minimum-line thresholds. No history is deleted or automatically rewritten; accepted original prose can be analyzed again through the normal existing workflow.

## Verification and limits

Run `python -m pytest -q tests/test_dialogue_attribution.py tests/test_longform_consistency.py tests/test_longform_state.py`.

Tests use original synthetic sentences and mocked model responses. They cover positive/negative attribution, overlapping canonical names, mixed baselines and actual engine review consumption. Full suite and remote exact-head outcomes are reported separately when available.

This is conservative lexical attribution, not a semantic speaker resolver. Pronouns, unregistered aliases/names, indirect speech, complex/nested quotations and long ambiguous clauses can be missed. Longest-name filtering only distinguishes registered names. No claim is made about real-model prose quality, blind-review gains or complete character consistency. Frozen story benchmarks and manuscript data are unchanged.
