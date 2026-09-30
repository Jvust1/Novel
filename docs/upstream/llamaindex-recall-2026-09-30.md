# LlamaIndex recall integration — 2026-09-30

Upstream: `run-llama/llama_index`  
Revision: `7e2c60a78ec27e8d146dfdd596778aea83c041d5`  
License: MIT

Novel now exposes LlamaIndex through the same `RecallBackend` contract as local semantic recall, Mem0 and Qdrant. The adapter rebuilds a VectorStoreIndex from Novel-owned RecallDocument values, retrieves through `as_retriever(similarity_top_k=...)`, and maps results back to RecallHit.

LlamaIndex remains optional and is not the default recall path until frozen A/B evaluation justifies it.
