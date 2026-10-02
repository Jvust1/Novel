# Combined continuity pilot

This local integration combines the licensed [LangChain MMR port](langchain-mmr-continuity-2026-09-30.md) and [spaCy speaker-span port](spacy-speaker-spans-2026-09-30.md). It adds no third upstream dependency.

## What is actually exercised

Original synthetic historical summaries carry separate key-holder and ledger-holder facts. Goal-based local recall selects both; normal and role-routed engines receive the evidence during planning, drafting, review, one repair and re-review. Overlapping names remain distinct in current/revised Voice DNA. A scripted reviewer finds the intentional ledger contradiction and a scripted repair fixes only that part.

Tests then simulate author acceptance of that synthetic fixture, extract/apply memory, preserve an unrelated character's unknown knowledge, save/reload character cards and metric-only Voice DNA, and recall the accepted chapter for the next generation context. No real author acceptance or model judgement is inferred from the scripted fixture.

## Workflow gaps closed

- The memory-writeback button previously persisted story state/summary but only updated character cards in session memory. An AppTest reproduced missing knowledge on disk/restart. The button now saves the same updated cards to characters.json
- Confirmed-plan re-review previously ran only model/prose checks. A changed speaker could pass despite strong Voice DNA drift. Revised voice extraction/checks now run and enter ChapterReview
- Confirmed-plan reference overlap was only a visual warning, bypassing the review/repair contract. Initial and revised similarity findings now merge consistently with the engines
- Post-repair Story DNA/behavior findings are also remerged, preserving the existing one-repair cap
- An empty revised voice-alert list now suppresses stale draft warnings instead of falling back to them

## Reproduction

`python -m pytest -q tests/test_continuity_pilot_e2e.py tests/test_app.py`

`python -m compileall app.py novel_ai && python -m pytest -q`

The separate MMR branch and spaCy branch remain independently testable. This combined branch is local review material until publication is separately permitted. Remote CI is not substituted by local tests.

## Boundaries

This is same-project, provider-mocked engineering verification, not prose-quality, semantic-reasoning, general project-switch or crash-transaction acceptance. The existing multi-file store remains non-transactional. Frozen story inputs, original evaluation evidence, dependencies and CI workflow are unchanged. No manuscript/reference text, model or credential is copied. Source sentence fixtures are original synthetic examples.
