# Style-quality upstream pins — 2026-09-30

These upstream projects are pinned as Git submodules for writing-quality analysis and Chinese NLP support.

| Path | Upstream | Pinned commit | License | Novel purpose |
|---|---|---|---|---|
| `vendor/lexicalrichness` | `LSYS/LexicalRichness` | `69e6b8f381d6b86ec826911c3f0bb2fb298aac25` | MIT | lexical diversity / repetition diagnostics |
| `vendor/textstat` | `textstat/textstat` | `e398f27543389283e847fc29568b049623c0e243` | MIT | readability / sentence complexity |
| `vendor/proselint` | `amperser/proselint` | `dbed789caae662d06c7c8a5a13dd31f1acd36f5c` | BSD-3-Clause | prose-lint heuristics; English-oriented |
| `vendor/pkuseg-python` | `lancopku/pkuseg-python` | `071d57c7df9ac0680edda7034b47787d7c6f9184` | MIT | Chinese segmentation for style metrics |

Goal: improve originality, variation, readability, and natural prose quality. These components are not integrated to defeat or target a particular AI-detection service.
