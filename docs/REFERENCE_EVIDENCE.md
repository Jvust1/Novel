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
transaction.  `--query` and `--evidence-out` are an all-or-nothing pair.  With
neither flag, the legacy Reference Pack CLI behavior is retained and no
evidence file is produced.
