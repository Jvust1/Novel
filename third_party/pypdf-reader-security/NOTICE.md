# Existing PDF reader dependency: security-patched pin

- Project: [py-pdf/pypdf](https://github.com/py-pdf/pypdf)
- Current dependency: `pypdf==6.19.0`, [official release](https://github.com/py-pdf/pypdf/releases/tag/6.19.0), published 2026-09-16
- Annotated tag object: `51f9c303af50fa0f55df7640f38e3df0239e8060`
- Exact source commit: `d62cb58d3988b291b0435eddfd118c4f8f6b6a46`
- [PyPI wheel](https://pypi.org/project/pypdf/6.19.0/#files): `pypdf-6.19.0-py3-none-any.whl`; SHA-256 `7e5d6e730e7dae87d560a2cee218b852f6498c8be61966f3cd02ead971e48d14`
- License: BSD-3-Clause as declared by official PyPI metadata; complete unchanged release-wheel license is [LICENSE](LICENSE). GitHub's generic repository metadata returned NOASSERTION; the actual license text and release metadata were inspected rather than treating that label as the license
- Retained license matches source Git blob `ab327d0312875458ba74983867f1b2622b6de39d`, SHA-256 `a97ac230e5f33ef10a5367a850eb01f91f1a0b064e34742c7794d2294557f524`; the downloaded wheel matches the official checksum above
- Observed 2026-10-01 22:42 UTC through GitHub: 10,243 stars, an observation rather than quality evidence

Novel already uses `PdfReader` and `page.extract_text` in `novel_ai/reading.py`. Only the install constraint changes; no pypdf source is vendored, patched or represented as Novel-owned. Its normal distribution retains the upstream license. No new service, credential, model or paid call is introduced. Existing optional parsers remain optional.

Relevant official disclosures include [font Widths, fixed 6.18.1](https://github.com/py-pdf/pypdf/security/advisories/GHSA-g9cg-prrw-2r8q), [ToUnicode follow-up, fixed 6.18.1](https://github.com/py-pdf/pypdf/security/advisories/GHSA-fp3h-c4fm-7vvf) and [XForm extraction, fixed 6.16.1](https://github.com/py-pdf/pypdf/security/advisories/GHSA-763m-79hh-57f2). Pinning 6.19.0 includes these upstream fixes without copying another parser or claiming a comprehensive dependency audit.

Novel-owned regressions generate small synthetic PDF inputs and call the real reader in resource-limited offline subprocesses. Baseline 5.9.0 exhausts the explicit CPU budget on the original sparse-width range input; 6.19.0 returns the complete expected text. This is bounded resource-regression evidence, not proof of sandboxing or universal PDF safety.
