# spaCy span-filter source port

- Upstream: https://github.com/explosion/spaCy
- Exact commit: `26b4d1dc04a812f426e4bef3e8a1b6f159d6f048` (existing Novel `vendor/spacy` gitlink)
- Source: https://github.com/explosion/spaCy/blob/26b4d1dc04a812f426e4bef3e8a1b6f159d6f048/spacy/util.py
- Symbol: `filter_spans`
- License: MIT. Full original copyright/license retained in `LICENSE`
- GitHub API star count: **33,931**, verified 2026-09-30 UTC
- Local port: `novel_ai/_vendor/spacy_spans.py`

Changes are limited to annotations accepting lightweight character-offset objects and explanatory documentation. The longest-first, stable-first-overlap selection loop is retained. Novel's original `dialogue_attribution.py` uses the resulting non-overlapping canonical name spans to avoid attributing a longer character name's dialogue to its prefix.

No spaCy package, trained pipeline, corpus or model download is required. This is a source-level algorithm reuse, not neural entity recognition and not a claim that spaCy's full NLP pipeline is running.
