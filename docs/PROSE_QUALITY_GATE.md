# Prose Quality Gate

Novel now runs a layered local quality gate after each draft.

## Core signals, no optional dependencies

- exact sentence repetition
- repeated paragraph openings
- sentence-length variance
- paragraph-length coefficient of variation
- character-bigram diversity
- fallback lexical type/token ratio

## Optional adapters

- OpenCC: normalize Traditional/Simplified Chinese before metrics
- pkuseg → jieba fallback: Chinese tokenization
- LexicalRichness: TTR / RTTR / CTTR
- pycorrector: correction candidates only; never blind auto-edit
- spaCy: capability probe for future structural/entity features
- textstat/proselint/texthero remain auxiliary/reference integrations until Chinese-specific validation passes

## Pipeline

Draft → deterministic quality analysis → model Review → merge findings → local Repair when model or medium/high deterministic issues require revision → re-review.

Metrics are diagnostic signals, not a score to game. Do not randomly alter wording or sentence lengths merely to improve metrics.
