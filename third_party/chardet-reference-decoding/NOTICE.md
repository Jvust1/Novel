# chardet reference-decoding integration

Novel uses the official pinned `chardet==7.6.0` package for local encoding candidate ranking in `novel_ai.text_decoding.encoding_candidates`. Its actual `detect_all` pipeline runs when an undecorated file cannot be read as valid UTF-8 text. Novel still requires explicit selection before non-BOM legacy decoding, then strictly decodes and re-encodes every byte. Detector confidence never becomes author approval or proof of intended meaning.

- Repository: https://github.com/chardet/chardet
- Verified 2026-10-01 18:31 UTC: 2,675 stars
- Release: 7.6.0, annotated tag object `a40dc89ac9743ba7242c07a23813766fd23b30c3`
- Exact source commit: `dcf07fb97b082df57cf06125a0f0778e9aaef79d`
- License of this fixed release: 0BSD; complete unchanged `LICENSE` is retained
- LICENSE Git blob `b9dc77f90250bce38ea6b6f3f6585c35af63cb4e`, SHA-256 `0d4cf67e7a26e9957b8948e7dfc0e380e61b427a94b061e618889aba89bb9616`
- Complete unchanged public API source `src/chardet/__init__.py` retained as `upstream_api.py.txt`; Git blob `50bcbdc9624b60c667128dbd2ab0574374bc33ba`, SHA-256 `9174c1f23aa487cde826a1cb3b46e96a2dc1d903adb9fec09f577dda61692a01`
- Both installed Python environments use 7.6.0; their public API source matches this exact upstream blob

The package is a runtime dependency. The retained API file documents provenance; Novel imports the installed detector and does not pretend this one file is the complete algorithm. Compiled wheel details can vary by platform; no whole-wheel reproducibility or dataset audit is claimed. No model API, network detection or remote reference upload is involved.

Calls restrict candidate names to supported codecs, bound the statistical examination to 200,000 bytes, discard malformed/nonfinite candidate records, and verify each proposed codec against the entire original byte stream. A successfully decoded candidate remains a proposal. UTF-8 and recognized BOM handling use Python's strict codecs directly. Source SHA-256, resulting UTF-8 SHA-256, BOM and decision mode are recorded separately from the manuscript.

Investigated but not selected: charset-normalizer 3.5.2 (MIT, 798 stars at this check) did not meet the requested thousand-star source threshold. MarkItDown's current plain-text converter contains an `errors="ignore"` fallback; that default is not adopted. Older chardet releases used another license; this record applies only to the explicitly pinned 7.6.0 source and license above.
