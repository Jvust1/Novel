# Local reference evidence query

`novel_ai.reference_evidence` is an opt-in, local-only query over explicitly
provided TXT, Markdown, or HTML references.  The existing Reference Pack path
keeps its schema and continues to save only derived style/statistical data.
Evidence is generated only when the CLI receives both `--query` and
`--evidence-out`.

```bash
python scripts/build_reference_pack.py reference.txt notes.md \
  --query "夜班 电台" \
  --evidence-out private/reference-evidence.json \
  --top-n 5 --chunk-chars 720 --max-excerpt-chars 360
```

## Contract

- Each source is read through `reading.extract_reference`; TXT/MD decoding and
  invisible-control sanitization are therefore the same as the existing
  Reference Pack path.  HTML uses the already optional local trafilatura →
  Docling → MarkItDown chain and never fetches a URL.
- Paragraphs are split into bounded Unicode-character chunks.  Relevance is a
  deterministic lexical score.  Selection then uses the vendored LangChain
  MMR source port at `vendor/langchain` commit
  `a9780cd3dd73135d21d7130b08711685f2700d51`; the existing MIT
  `third_party/langchain/LICENSE` and `NOTICE.md` remain the provenance.
- A result is an explicit empty `matches` list when no chunk has lexical
  relevance.  Unrelated chunks are not inserted to fill `top_n`.
- `start` and `end` are zero-based, half-open indices in the **sanitized,
  extracted Unicode string**.  They are not HTML DOM positions or raw-byte
  offsets.  Each source and match records the full raw-byte SHA-256 and the
  sanitized extracted-text SHA-256; each match also records its excerpt hash.
- Stable IDs and tie order depend on source filename, source hash, excerpt
  interval, and excerpt hash.  Reordering the explicit input list does not
  change the artifact.
- The JSON artifact contains bounded excerpts and provenance only.  It does
  not contain the source body, does not create a Reference Pack by itself,
  and is not automatically sent to `ContextAssembler`, a model, a writing
  action, an upload, or a permanent index.

## Bounds and failure behavior

| Resource | Bound |
| --- | ---: |
| `top_n` | 1–20 |
| `chunk_chars` | 1–4096 extracted Unicode characters |
| `max_excerpt_chars` | 1–2048 extracted Unicode characters |
| chunks across all sources | 1–10,000 |
| one source | 8 MiB raw bytes |
| all sources | 32 MiB raw bytes |

An empty query, invalid bound, undecodable/corrupt source, unsupported reader,
directory/special-file input, output collision, or existing evidence output
returns an error before an evidence manifest is written.  In query mode, the
CLI stats every source and reads it through a bounded stream before invoking
either extractor or Reference Pack builder; a source that grows past its
limit is rejected without unbounded reads.  Evidence output is written to a
temporary file and published with an exclusive same-directory link, so a
target created by another writer is never overwritten and failed publication
cleans up the temporary file.  In query mode the Reference Pack output uses
the same no-clobber staging path.  Both complete artifacts are staged before
the first publish; if the second publish fails, cleanup removes only the
first file still owned by this invocation and leaves an existing or competing
winner untouched.  This is bounded failure cleanup rather than a cross-file
transaction.  `--query` and `--evidence-out` are an all-or-nothing pair.  With neither flag, normal legacy Reference Pack CLI invocations remain
compatible with the existing Reference Pack schema and writer, and no evidence
file is produced.  Query mode intentionally rejects same-path output pairs and
input or output symlink aliases as a safety tightening; this does not claim
every historical CLI edge behavior is unchanged, and the rejected destructive
alias paths are not restored.


## Streamlit local evidence panel

The seventh 本地证据 tab is a thin session-only entry point over the same
reading.extract_reference and build_reference_evidence functions.  It accepts
explicit TXT/MD uploads and can pass HTML to the existing local reader chain.
It exposes query, top_n, and the bounded excerpt length, then renders source,
chapter, bounded excerpt, sanitized-Unicode offset, score, raw-byte hash, and
extracted-text hash.  The JSON download is explicit.

The panel binds the result to the current project, every uploaded filename and
raw SHA-256, the selected TXT/MD encoding, query, top_n, and excerpt bound.
Changing any binding field, switching projects, or encountering a read/query
failure clears the old result and download.  Uploaded size metadata is checked
before getvalue() when available, then the core 8 MiB per-source and 32 MiB
total bounds remain authoritative.  The panel does not invoke Style DNA
analysis, ContextAssembler, a provider, a model, network access, ProjectStore
writes, Reference Pack writing, or a permanent index.

The real Streamlit AppTest uploader gate uses synthetic TXT/MD bytes and the
actual file_uploader widget serialization.  The optional HTML/trafilatura
acceptance remains a separate no-skip CI probe; TXT/MD UI coverage does not
stand in for that HTML backend check.

### Local Streamlit privacy configuration

The supported local entry in docs/AUTHOR_WORKFLOW.md is
`python -m streamlit run app.py`, started from the repository root. The
project-level `.streamlit/config.toml` sets
`[browser] gatherUsageStats = false`. The Chromium job verifies Streamlit's
effective `browser.gatherUsageStats` option from that file and does not set a
telemetry environment override. Its raw no-external-request assertion stays
unfiltered; no external requests were observed in that browser run with the
repository configuration alone.

This verifies the repository's local entry and this CI browser environment.
Browser extensions, reverse proxies, hosted deployment settings, and other
launch wrappers are outside that check and may make external requests. This
configuration does not promise every deployment environment is network-free.


## Session-only wording check

After a successful evidence query, the panel requires the author to paste a bounded
draft fragment and explicitly select the current evidence matches. Each selected
match is compared with the draft in memory only, using the deterministic normalized
Levenshtein similarity implementation in
novel_ai/rapidfuzz_similarity.py (RapidFuzz/RapidFuzz commit
db6e504539a9c895180b266a06b36a32cb6029ee). The implementation and its
adaptation record remain under the existing MIT license files
third_party/rapidfuzz/LICENSE and third_party/rapidfuzz/provenance.json;
the panel never switches to rapidfuzz.fuzz.ratio.

The check is advisory surface wording similarity. It is not a plagiarism or
originality proof, model judgement, or automatic acceptance signal. The
session binding includes the project, every uploaded filename and raw hash,
query, selected stable IDs, draft text, and the bounds. Changing an upload,
query, encoding, evidence selection, draft, project, or a failed check clears
the previous report and its download. The report and the explicit JSON export
are session-only. The export contains metadata, selected IDs, hashes, offsets,
scores, metric provenance, and parameters; it omits the draft body and bounded
evidence prose.

The checked limits are 2048 Unicode characters for the pasted fragment and 20
selected matches/comparisons. The existing evidence bounds remain 8 MiB per
source, 32 MiB total, and top 20. No provider, model, ContextAssembler,
ProjectStore write, network request, or permanent index is used.

The repository CI includes a test-only Ubuntu Chromium gate under
tests/e2e/. It installs the pinned Playwright 1.62.1 package from the
official npm registry, installs the matching Chromium through Playwright, starts
the real Streamlit server, uploads synthetic TXT/MD bytes, runs MMR, clicks both
download controls, reads the completed files, and checks their JSON bytes against
the visible hashes, offsets, stable IDs, scores, and the current draft binding.
It also checks deterministic repeat downloads, input/selection/project invalidation,
controlled failure, external request absence, and that the project data directory
does not contain the fixture bodies. On success, the two exact synthetic
download bytes and a metadata-only verification summary are retained as a short-lived
CI artifact; no user source, credential, or real data is included. This browser gate
is separate from the optional HTML/trafilatura acceptance path.
