# spaCy entity-consistency integration — 2026-09-30

Upstream: `explosion/spaCy`  
Revision inspected: `c2dabfce56ad2991685ec85783cd59637a5d7b8f`  
License: MIT

Novel now uses spaCy through an optional, model-explicit adapter:

- extracts PERSON/PER entities from generated prose;
- compares them with Novel's current character names and explicit alias map;
- emits review issues for unknown people;
- never mutates canon automatically;
- never downloads a spaCy model automatically.

This adapter can be inserted into Novel's existing external review-hook chain after local precision testing on Chinese chapters.
