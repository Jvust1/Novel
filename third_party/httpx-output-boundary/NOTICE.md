# HTTPX output-boundary runtime reuse

Novel calls the existing required HTTPX dependency's streaming-response API in its actual OpenAI-compatible writer transport. This is runtime API reuse, not a source-code port, new dependency, or adoption of another workflow framework.

- Upstream: https://github.com/encode/httpx
- Observed 2026-10-01: 15,524 stars
- Verified installed version: 0.28.1
- Exact tag commit: `26d48e0634e6ee9cdc0533996db289ce4b430177`
- Full unmodified BSD-3-Clause license: `LICENSE.md` beside this file; copyright Encode OSS Ltd
- Source inspected: `httpx/_client.py` (`Client.stream`, lines 828 onward), `httpx/_models.py` (`HTTPStatusError` behavior, `iter_raw`, `iter_bytes`), and `httpx/__version__.py`
- Installed source bytes in Linux Python 3.11 and 3.12 match that commit. SHA-256/Git blob identities are recorded in `provenance.json`

The existing buffered `post()` call is replaced with scoped streaming, so the adapter can stop consuming a response when its explicit allowance is exceeded. The context manager owns closure, including failures and compatibility retry. Requests explicitly select identity content encoding and reject compressed responses before iteration; the checked limit bounds accepted body bytes, not every transport/process allocation. The output cap, positive unsupported-response-format classification, completion-shape validation, and stage policy are Novel integration rules, not claimed to come from HTTPX. See the actual provider implementation and offline MockTransport tests for exact transport limits. A client output allowance is not a model context-window proof or billing guarantee.

## A concrete alternative inspected and not copied

LangChain's pinned `libs/core/langchain_core/utils/json.py` at `a9780cd3dd73135d21d7130b08711685f2700d51` (147,345 stars observed on the same date, MIT) defaults to `parse_partial_json`. It can synthesize closing braces/quotes and remove trailing characters until parsing succeeds. That useful recovery policy conflicts with this boundary's requirement to reject truncated and ambiguous reviews. It was not copied or counted as another adoption; the existing licensed LangChain MMR and Markdown header ports remain intact.

The JSON boundary instead uses Python's existing `json.JSONDecoder.raw_decode`, duplicate-key hook, finite serialization and UTF-8 validation, followed by existing Pydantic model validation. Novel's confined storage already uses the finite/UTF-8 serialization contract. This does not invent a new parser framework or claim CPython/Pydantic source was newly ported.

Optional Instructor, Outlines, Guidance and LiteLLM integrations remain explicit opt-ins. Their schema/limit compatibility tests use stubs, not installed SDKs or live providers; no paid call or new framework is enabled by these changes. Preserve that distinction in acceptance reports.
