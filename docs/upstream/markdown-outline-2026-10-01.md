# Markdown author-outline import — 2026-10-01

## Outcome and scope

Novel already had a tree builder that reconstructed hierarchy from accepted chapter plans. It did not turn the author's existing free-text outline into that hierarchy. This local slice adds `parse_markdown_outline(text: str, *, title: str, premise: str = '') -> HierarchicalOutline`, using an attributed source port of LangChain's heading stack and fence handling. It provides the input side of outline → chapter plan, without calling a model or inventing missing scene fields.

This parser is a callable module. Its separate workbench, chapter-plan, review and release-bundle integration must be verified by the enclosing author-workflow change; parser tests alone do not establish that UI path or any story-quality improvement.

## Actual source reuse

- Upstream: [LangChain](https://github.com/langchain-ai/langchain), **147,336 stars**, checked through the GitHub repository API on 2026-10-01 UTC
- Exact existing vendor pin: `a9780cd3dd73135d21d7130b08711685f2700d51`
- [Source file](https://github.com/langchain-ai/langchain/blob/a9780cd3dd73135d21d7130b08711685f2700d51/libs/text-splitters/langchain_text_splitters/markdown.py): `MarkdownHeaderTextSplitter.split_text`
- Source blob: `3a518a6bce60625c82b40c0c50f2e14a0826b10e`
- [MIT license at the same pin](https://github.com/langchain-ai/langchain/blob/a9780cd3dd73135d21d7130b08711685f2700d51/LICENSE), Copyright (c) LangChain, Inc.; full license retained in `third_party/langchain/LICENSE`
- Local adapted source: `novel_ai/_vendor/langchain_markdown.py`; local domain wrapper: `novel_ai/outline_markdown.py`
- Machine-readable pin and evidence: `third_party/langchain/markdown-outline-provenance.json`

The source-level reuse is the upstream's explicit code-fence state and nested header stack, including popping every equal/deeper header before pushing the next one. It is not merely a dependency declaration or unused adapter. The wrapper immediately uses its parent relationships and body sections to build `OutlineNode` objects.

Important adaptations:

1. Replace LangChain `Document` objects with small local section records; no LangChain runtime installation
2. Retain each heading, including heading-only and duplicate-title nodes, rather than aggregate chunks with equal metadata
3. Preserve body text and interior indentation, blank lines, tabs, trailing spaces and non-printable characters; normalize line endings to LF and trim outer blank lines only
4. Tighten fence closing to the same character and at least the opening run length, with whitespace-only trailing content; reject an unclosed fence
5. Add parent indices and source line numbers, strict domain hierarchy validation, and stable position-based IDs
6. Reject a nonblank preamble instead of discarding it; store notes as both `promise` and `metadata['author_notes']`, while leaving conflict/outcome empty

## Accepted author syntax and limits

- `#` = series, `##` = volume, `###` = arc, `####` = chapter, `#####` = scene
- Every heading requires a nonempty title. Exactly one series root is required. Child headings must follow the next hierarchy level; returning to an ancestor/sibling level is allowed
- ATX headings and backtick/tilde code fences may be indented by zero to three spaces. Tabs/spaces may separate heading markers and titles. Optional trailing closing hashes are accepted
- Fenced content belongs to the current node's author notes. Hash-prefixed lines inside it never become nodes
- Unsupported Markdown such as Setext headings, bullet outlines and indented code remains author-note text. This is not a full CommonMark/HTML parser and does not infer chapter structure from prose
- All semantic levels may have empty notes and no children. Later planning must ask the author to complete the required scene fields rather than pretend they were extracted
- `title` names the project; the root retains its Markdown heading. A blank project title falls back to the root heading. `premise` is explicitly supplied and is not inferred from notes
- IDs include hierarchy positions and titles. Identical input is deterministic, and equal-title siblings have different IDs. Inserting/reordering/renaming nodes can change IDs; subsequent chapter bindings need revalidation
- The module is local and deterministic. It makes no provider/network calls and writes no files

## Source-screened alternatives

Started from Novel's existing registry/vendor pins. Five mature implementations were inspected at their specific code paths below. This was a targeted source screen, not a full audit of every repository. Star counts are live GitHub API observations from 2026-10-01 UTC, not quality scores.

| Candidate | Stars | License checked at pin | Inspected implementation and decision |
| --- | ---: | --- | --- |
| LangChain | 147,336 | MIT | `MarkdownHeaderTextSplitter.split_text` at `a9780cd3dd73135d21d7130b08711685f2700d51`: selected. Its fence and header-stack code fits the missing author-outline import; lossy RAG aggregation/normalization is deliberately excluded |
| LlamaIndex | 52,377 | MIT, Copyright Jerry Liu | [`MarkdownNodeParser.get_nodes_from_node`](https://github.com/run-llama/llama_index/blob/7e2c60a78ec27e8d146dfdd596778aea83c041d5/llama-index-core/llama_index/core/node_parser/file/markdown.py) at `7e2c60a78ec27e8d146dfdd596778aea83c041d5`: close alternative, already retains individual sections. Its inspected fence implementation only toggles on triple backticks and metadata joins titles into a path; additional adaptation is still needed for tilde fences and positional identity. No benefit from installing its Node/Callback stack here |
| NetworkX | 17,301 | BSD-3-Clause in actual LICENSE.txt; GitHub metadata reports NOASSERTION | [`topological_generations`](https://github.com/networkx/networkx/blob/92f497e2eb8192d1ce9205595f512294e4a9b696/networkx/algorithms/dag.py) at `92f497e2eb8192d1ce9205595f512294e4a9b696`: a valid candidate for future plot prerequisite DAG ordering/cycle checks. The current author outline is an ordered tree, so adding a DAG now does not supply the missing input/review path |
| MarkItDown | 187,807 | MIT, Copyright Microsoft | [`DocxConverter.convert`](https://github.com/microsoft/markitdown/blob/b8f79c57ebc0044be41323d89b2a45d3fda8460e/packages/markitdown/src/markitdown/converters/_docx_converter.py) at `b8f79c57ebc0044be41323d89b2a45d3fda8460e`: useful future DOCX→Markdown author-outline ingestion. It routes through Mammoth, preprocessing and HTML conversion, so copying the short adapter alone would not deliver the actual conversion capability. Too wide for an already-pasted Markdown outline |
| DeepEval | 18,527 | Apache-2.0 | [`DAGMetric`](https://github.com/confident-ai/deepeval/blob/b13093cf9c9b5468dbe7d00529e8f20e14300d55/deepeval/metrics/dag/dag.py) at `b13093cf9c9b5468dbe7d00529e8f20e14300d55`: mature evaluation workflow, but its constructor initializes judge models and measure executes model-backed DAG evaluation. That does not fit this slice's explicit offline human market-score record and no-new-paid-calls scope |

Two directly novel-oriented registry projects were also checked at metadata/license level, not deeply source-reviewed: `yangkevin2/doc-story-generation` had **160 stars** (MIT) and `facebookresearch/doc-storygen-v2` had **93 stars** (its LICENSE states Apache-2.0, while GitHub metadata reports NOASSERTION). They do not meet the requested 10,000-star threshold for this adoption. They remain possible research references, not qualifying mature code reuse in this slice.

No source from the alternatives was copied. No new model, service, raw manuscript or paid call was used.

## Verification

`/tmp/novel-venv311/bin/python -m pytest -q tests/test_outline_markdown.py tests/test_outline.py`: **37 passed** on 2026-10-01. `compileall` also passed for the new parser and wrapper.

Coverage includes body preservation; hierarchical sibling/ancestor traversal; equal-title and heading-only node identity; deterministic IDs; backtick/tilde fences and matching lengths; inline backticks; LF/CRLF input; source lines; no fabricated conflict/outcome; and fail-closed handling of nonblank preamble, missing/duplicate roots, skipped levels, empty headings, unsupported heading depth and unclosed fences. Tests use synthetic text only. Bare `pytest` was not on the default PATH, so the existing Novel Python 3.11 environment was used. The enclosing workflow owns aggregate verification.
