# Trafilatura local HTML adapter provenance

- Upstream: https://github.com/adbar/trafilatura
- Current check: 2026-10-05 UTC; 6,914 GitHub stars; default branch `master`.
- Tested release: `v2.3.0`, upstream commit `6c1977a00b4e82ebb7e6fad1192467adaf24d430`.
- License: Apache-2.0 (`LICENSE` at the tested release). The `v1.8.0` release notes record the license change to Apache-2.0; versions before `v1.8.0` are outside this adapter's constraint.
- Constraint: `trafilatura>=1.8.0,<3`. The optional reference extra does not enter the default installation.
- Runtime boundary: for uploaded `.html`/`.htm` bytes only, call `trafilatura.extract(..., url=None, favor_precision=True, include_comments=False, include_tables=False, output_format="txt")`. Novel does not call `fetch_url`/`fetch_response`, open a URL, download a model, or copy upstream source.
- Fallback: missing package, extraction exception, empty output, malformed or empty HTML all retain the existing Docling/MarkItDown dependency error contract. TXT/MD, DOCX and PDF readers keep their existing paths and sanitizer/OpenCC normalization.
- Notice: the tested upstream root has `LICENSE` and no `NOTICE` file. No upstream source is vendored; this file records the repository, version, commit, license and adapter boundary.
- Validation fixture: `tests/fixtures/reference.html`, consumed through the actual `extract_reference` upload-byte path. CI has a separate Ubuntu/Python 3.12 install probe for the optional package and the same fixture.
