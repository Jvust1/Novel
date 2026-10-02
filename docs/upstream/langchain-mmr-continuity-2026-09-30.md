# LangChain MMR continuity pilot

## Why this integration

Novel already pins LangChain and lists many optional recall adapters. The actual workbench's ContextAssembler still used the oldest summaries until its character cap, and its review/repair prompts did not receive assembled historical evidence. This bounded source port closes that runtime gap rather than adding another backend declaration.

Upstream: [LangChain](https://github.com/langchain-ai/langchain), **147,315 stars**, MIT, observed 2026-09-30 UTC. Adapted [MMR function at the exact pin](https://github.com/langchain-ai/langchain/blob/a9780cd3dd73135d21d7130b08711685f2700d51/libs/core/langchain_core/vectorstores/utils.py). The complete license and adaptation record are in `third_party/langchain/`.

## Runtime path

1. In the workbench's writing tab, enable **多样化历史召回（实验）** (default off), then supply the chapter goal
2. Both planning/confirmation and one-step generation pass this goal to `ContextAssembler.assemble(recall_query=...)`
3. Accepted older summaries are scored with local Chinese character-bigram cosine. Keep the top 64 candidates in a bounded heap, then reuse the adapted MMR loop to rank at most eight rows for relevance plus diversity
4. Canon/Active are unchanged. The whole recalled block, including labels, must fit the existing character budget and optional token budget; incomplete rows are omitted
5. Plan, draft, review, local repair and re-review receive the selected context. The routed engine uses its writer for draft/repair and reviewer for both review passes
6. Long summaries use a complete query-relevant sentence marked with omission ellipses; rank exactly that excerpt. Overlong single sentences are omitted rather than cut into potentially misleading facts
7. The pure Python `WritingContext.recall_report` records selected chapter IDs, relevance, hashes, source offsets and actual included IDs/length; it contains no source text or raw query

No provider is called for retrieval. No upstream package/model/database initialization or paid call is added by retrieval. Enabling ordinary AI drafting uses the author's configured provider. The role-routed auto-repair path now makes one additional reviewer call for re-review, matching the normal engine; this may consume provider tokens. The existing one-repair limit and author acceptance boundaries remain.

## Reproduction

`python -m pytest -q tests/test_history_recall.py tests/test_app.py`

`python -m compileall app.py novel_ai && python -m pytest -q`

The synthetic provider-mocked pilot covers continuity-evidence propagation, writer/reviewer roles, diversity, no-match handling, zero/small budgets, default-off UI and confirmed-plan flow. It is not a real model evaluation. Local Python and exact remote commit/CI outcomes are recorded in the draft PR; no main merge or deployment is included.

## Limits

- Lexical matching is not semantic reasoning, contradiction detection, or proof of quality
- Query and each summary are scored only through their first 2,000 characters; complete-sentence excerpts obey the existing summary-length cap; long indivisible sentences can be omitted
- MMR prioritizes less-redundant rows; it does not guarantee every selected row is unique
- Summaries can be wrong and never grant characters new knowledge. Canon, character cards and human review remain authoritative
- The existing chronological path remains unchanged when no recall query is supplied. Historical-review prompt propagation is a deliberate consistency fix whenever extra context is supplied
- No frozen benchmark cases, user manuscripts, reference books, or first-real outputs are added or altered
