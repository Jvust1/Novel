# LangChain source adaptation

- Upstream: https://github.com/langchain-ai/langchain
- Commit: `a9780cd3dd73135d21d7130b08711685f2700d51` (matches Novel's existing `vendor/langchain` gitlink)
- Source: https://github.com/langchain-ai/langchain/blob/a9780cd3dd73135d21d7130b08711685f2700d51/libs/core/langchain_core/vectorstores/utils.py
- Symbol: `maximal_marginal_relevance`
- License: MIT; Copyright (c) LangChain, Inc. Full license retained in `LICENSE`
- Star count observed with GitHub API: **147,315**, 2026-09-30 UTC
- Local source: `novel_ai/_vendor/langchain_mmr.py`

Changes: NumPy query/pair cosine calculation is replaced by precomputed relevance scores and a local pair-similarity callback; lists replace arrays; finite-score/range validation is added. The greedy selection order, stable first-maximum tie behavior and relevance/diversity equation are retained. This is an adapted source port, not an unmodified upstream file or a claim that the whole LangChain framework is running. `novel_ai/history_recall.py` supplies bounded character-bigram features from local accepted summaries.

Only the small selected algorithm and required MIT notice are copied. No model, source novel, training data, credential or upstream service is bundled.

## Markdown author-outline parser (2026-10-01)

- Same upstream commit: `a9780cd3dd73135d21d7130b08711685f2700d51`
- Source: https://github.com/langchain-ai/langchain/blob/a9780cd3dd73135d21d7130b08711685f2700d51/libs/text-splitters/langchain_text_splitters/markdown.py
- Source Git blob: `3a518a6bce60625c82b40c0c50f2e14a0826b10e`
- Symbol: `MarkdownHeaderTextSplitter.split_text`, specifically the fenced-code state machine and equal/deeper-header stack pop/push
- Local adapted source: `novel_ai/_vendor/langchain_markdown.py`
- Domain integration: `novel_ai/outline_markdown.py:parse_markdown_outline`
- License: MIT; Copyright (c) LangChain, Inc. The existing complete `LICENSE` applies to both source ports and was rechecked at the exact pin
- Current upstream stars checked with the GitHub repository API on 2026-10-01 UTC: **147,336**

Changes: `Document` and the LangChain runtime are removed. Every heading is retained separately, including empty-body sections and equal-title siblings. Body text keeps its interior whitespace/non-printable characters instead of using the upstream RAG normalization and equal-metadata chunk aggregation. The parser records line numbers and parent indices, accepts ATX headings indented by at most three spaces, and recognizes optional closing hashes. Fence closing is tightened to match the opening character and minimum length, with no trailing non-whitespace; an unclosed fence is rejected. Nonblank text before the root is rejected instead of discarded. The domain wrapper enforces exactly one series root and continuous levels through scene, supplies deterministic position-based IDs, and stores author notes without inventing scene fields.

This is a small, modified source port, not the complete upstream Markdown splitter or a CommonMark implementation. No other screened upstream source was copied. Details and limitations are recorded in `docs/upstream/markdown-outline-2026-10-01.md`.
