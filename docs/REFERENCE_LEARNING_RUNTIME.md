# Reference Learning Runtime

## Book-to-Skill

`novel_ai.book_skill_adapter.convert_documents_to_skill()` runs the pinned
`vendor/book-to-skill` code against local files. Initialize submodules first:

```bash
git submodule update --init --recursive
```

The adapter sets `BOOK_TO_SKILL_SCOPE=project`, so generated skills remain
project-local instead of becoming an uncontrolled global dependency.

## Similarity protection

Novel's default reference protection uses only non-reversible 18-character
shingle hashes already produced by Style Lab / Reference Pack.

Optional runtime-only layers may compare temporary passages or derived Story
DNA event sequences. Those inputs are not persisted by the similarity module.

Similarity findings are safeguards against overly close reuse, not a target
metric for stylistic optimization.
