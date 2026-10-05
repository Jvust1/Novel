# Sentence Transformers recall integration — 2026-10-01

Upstream: `huggingface/sentence-transformers`  
Revision inspected: `4a3b5cd6ec718e421f57e824a41ed3fd99595df6`  
License: Apache-2.0

Novel already supported Sentence Transformers as an embedding encoder. This fusion adds a direct `RecallBackend` factory. It defaults to `local_files_only=True`, preserves Novel `RecallDocument` IDs/text/metadata, and can A/B against lexical, FAISS and Qdrant backends.
