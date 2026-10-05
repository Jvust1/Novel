# Microsoft GraphRAG corpus integration — 2026-09-30

Upstream: `microsoft/graphrag`  
Revision: `769542fbf1d8e5b4c6a8677fefc34621c87894c5`  
License: MIT

Novel keeps story state and Story Graph authoritative. The integration exports one deterministic UTF-8 text corpus from graph nodes, relationships and chapter summaries. GraphRAG remains an external optional index/query runtime; it does not own or mutate Novel canon.

This makes long-range graph retrieval testable without coupling Novel's internal memory format to one GraphRAG release.
