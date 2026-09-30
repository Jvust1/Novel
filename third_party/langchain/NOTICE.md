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
