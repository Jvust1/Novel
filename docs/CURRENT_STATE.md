# Current State

## 2026-08-24

Novel has a v0.2 orchestration skeleton on branch dev/multi-model-drive-backend-v0-2.

### Newly completed

- Role-based provider router with local, Colab, V4 and reviewer targets.
- Runtime-only provider configuration through environment variables.
- Google Drive storage adapter for Markdown and JSON artifacts below the Novel root folder.
- Architecture specification for website, backend, model routing and Drive artifact layout.
- Offline routing tests covering preferred providers and missing configuration.

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
- CI for this branch is not yet verified.

### Next sequence

1. Connect the website session to the provider router.
2. Add an explicit author acceptance gate.
3. Sync accepted draft, review and memory artifacts to Drive.
4. Extract chapter facts, character state, timeline and foreshadowing.
5. Build Canon / Active / Recall context assembly.
6. Run the first fixed multi-genre A/B benchmark.
