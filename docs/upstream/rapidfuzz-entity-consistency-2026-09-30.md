# RapidFuzz entity alias consistency — 2026-09-30

Upstream: `rapidfuzz/RapidFuzz`  
Revision inspected: `db6e504539a9c895180b266a06b36a32cb6029ee`  
License: MIT

Novel already listed RapidFuzz as an optional fuzzy-matching dependency. This change promotes it to a real adapter:

- caller-supplied observed character/place/term mentions are compared with canonical names and aliases;
- exact aliases are accepted;
- high-scoring near-matches are emitted as possible typo/name-drift alerts;
- optional alerts are fused into `build_longform_health().guard_context`.

Entity extraction remains a separate concern; this module does not guess entities from arbitrary prose by itself.
