# Current State

## 2026-08-24

Novel has a v0.2 orchestration skeleton on branch dev/multi-model-drive-backend-v0-2.

### Newly completed

- Role-based provider router with local, Colab, V4 and reviewer targets.
- Runtime-only provider configuration through environment variables.
- Google Drive storage adapter for Markdown and JSON artifacts below the Novel root folder.
- Routed writer/reviewer engine that separates draft generation from review.
- Architecture specification for website, backend, model routing and Drive artifact layout.
- Offline routing tests covering preferred providers and missing configuration.
- GitHub Actions run 11 passed: Python compilation and the full pytest suite.

### Latest machine check

On the Windows 1号机, running `ollama pull qwen3:4b` and `ollama run qwen3:4b` returned `Error: could not locate ollama app`. This is an installation/PATH prerequisite, not a model-quality failure. The next local step is to install Ollama, reopen PowerShell, verify `ollama --version`, then pull `qwen3:4b`.

### Existing foundation

- Streamlit local writing workbench.
- OpenAI-compatible model adapter.
- Story Bible / outline / character state input.
- Outline to scene plan to draft to review to local repair.
- Local AI-flavor heuristic scan.
- Style DNA surface and semantic analysis.
- Local project storage and basic CI.

### Current limitations

- The router is not yet wired into the Streamlit UI or a separate HTTP backend.
- Google Drive OAuth/token acquisition is intentionally outside the repository and is not configured by code.
- Chapter acceptance and Drive synchronization are not yet connected to the generation button.
- Post-chapter structured memory extraction is still pending.
- No frozen real-novel A/B benchmark exists.
- docs/HANDOFF.md remains on the prior v0.1 text because the connector returned a branch SHA conflict during update.

### Next sequence

1. Install and verify Ollama on the Windows 1号机.
2. Connect the website session to the provider router.
3. Add an explicit author acceptance gate.
4. Sync accepted draft, review and memory artifacts to Drive.
5. Extract chapter facts, character state, timeline and foreshadowing.
6. Build Canon / Active / Recall context assembly.
7. Run the first fixed multi-genre A/B benchmark.
