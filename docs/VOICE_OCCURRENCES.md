# Occurrence-correct character Voice DNA

This independent candidate starts from `main` commit
`e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96`. The public entry remains
`governance/current_candidate.json`; this document is not a merge receipt.

## GPT plugin reading is the primary path

The live [GPT entry](GPT_WRITING_ENTRY.md) now carries these rules into
[02 review](prompts/natural-fiction/02-editorial-review.md) and
[03 local repair](prompts/natural-fiction/03-local-repair.md): cite each quote by
chapter, draft revision, paragraph and occurrence; preserve intentional repeats;
apply a patch only to its approved occurrence; review the changed draft afresh.

With GitHub file access alone, GPT performs text review and labels it as not
having run Voice DNA. Reading this repository does not execute Python or spaCy,
register an MCP server, or require the author to install an application. Numeric
v3 diagnostics below are only for an actual executor or a genuinely obtained,
source-bound report. They are not prerequisites for the plugin writing workflow.

## Reproduced defects

- Two separate occurrences of `林舟问：“你来吗？”` were reduced to one
  dialogue sample because attribution deduplicated by text as well as source
  span. This changed sample counts and statistical weights, and suppressed the
  existing two-current-line minimum for voice-drift review.
- `林舟说：“走吧。”` recorded no final `吧`: particle counting looked at the
  sentence's punctuation rather than its last lexical character.

## Bounded correction

Keep each unambiguous quote occurrence in source order. Multiple matching tags
for the same quote still coalesce by its exact source span. Repeated character
names in the input do not duplicate samples, and ambiguous speakers, addressees,
negated speech and overlapping names keep their existing conservative handling.

For final-particle counts only, ignore trailing whitespace and sentence-final
punctuation (`。！？!?…．.`). Preserve the actual quote for every length and
punctuation ratio. A backward suffix scan avoids regex backtracking on long
punctuation runs. A particle inside a sentence or before a comma is not treated
as sentence-final. The recognized particle vocabulary is unchanged.

New measurements use `attribution_version=3`. Existing aggregation excludes v2,
unversioned and other incompatible cached measurements without deleting them or
relabeling their values. Direct callers of `voice_drift` must still supply a
compatible baseline; production callers obtain it through the shared aggregator.
An existing accepted-history rebuild recalculates the metrics from the exact
accepted draft bytes, preserving accepted-source fingerprints and author records.
Pending memory proposals containing old derived metrics may fail the existing
exact after-image check; regenerate and explicitly confirm the new proposal
rather than reusing an old confirmation.

## Reuse and dependency decision

Reuse the existing MIT spaCy `filter_spans` source port at
[`26b4d1dc04a812f426e4bef3e8a1b6f159d6f048`](https://github.com/explosion/spaCy/blob/26b4d1dc04a812f426e4bef3e8a1b6f159d6f048/spacy/util.py#L1361-L1381).
The original source and full license were reread through GitHub on 2026-10-04.
The retained `third_party/spacy/LICENSE` blob equals upstream
`6cb7810c6ee4ca32c79e68b9f39fbbce2183243a`; the port and license are unchanged.

The project's existing RapidFuzz and semantic-encoder options solve approximate
text matching, not exact source-occurrence identity. They are not enabled for
this correction. No framework, model, service or runtime dependency is added.

## Verification and boundaries

Run the focused regression with:

`python -m pytest -q tests/test_voice_occurrences_review.py`

The regression exercises direct attribution, metrics, compatible baseline
aggregation, all three shared writing entries, repair/re-review, and an actual
saved/read-back accepted archive. Inputs and provider responses are original
synthetic fixtures; no live model call or private manuscript is used.

The five existing PR54 response snapshots include derived voice metrics. Their
original frozen hashes and source fixtures are retained: the compatibility test
first checks exact v3 measurements and real UTF-8 accounting, then projects only
those known derived fields back to v2 for the original hash assertion. In that
fixture the corrected history JSON is exactly 30 bytes longer. No source
fingerprint, selection decision, blocked result or other response field is
normalized away. Revision-zero snapshots remain byte-identical.

The entry/prompt content contracts and source-link checks are tested separately
from Python execution. Actual connected GitHub file reads are reported with their
exact commit and blob identities on the PR; they prove retrieval, not that an
independent GPT session will obey the prompts or produce better fiction.

Results and remote CI receipts belong to the candidate record and its draft PR.
The normal minimum-sample thresholds and advisory review behavior are retained.
This does not make lexical attribution a semantic speaker resolver, establish
whole-book quality, or accept any manuscript on the author's behalf.
