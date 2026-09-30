# Structured Workflow Upstream Fusion — 2026-09-30

本批继续吸收千星级开源项目，但只搬对 Novel 长篇工程有直接收益的能力。

## Upstreams

| Project | License | Inspected revision | Novel integration |
|---|---|---|---|
| 567-labs/instructor | MIT | e12f8b49203b0c1f253d27c1e709d0a09b9fc5a8 | schema-first ChapterPlan / ChapterReview / MemoryExtraction |
| langchain-ai/langgraph | MIT | 07b33185eab893be2ed031eedae52f09314bf77c | compiled graph adapter as optional external review hook |
| pydantic/pydantic-ai | MIT | 75f0400d39d89149763a0852cfd6011e95fe977c | typed Agent adapter as optional external review hook |

## Design

- Instructor is the primary addition: NovelEngine can accept a `structured_extractor` and use Pydantic schemas directly for planning, review and memory extraction.
- If no structured extractor is configured, the old OpenAI-compatible JSON path stays unchanged.
- LangGraph and PydanticAI remain opt-in second-pass editorial systems through Novel's existing review-hook contract.
- None of these frameworks becomes a default dependency.
- No upstream repository is copied wholesale; the integration is kept at stable capability boundaries to reduce lock-in and upgrade cost.

## Expected value

1. Fewer malformed JSON failures during long runs.
2. Stronger schema guarantees for chapter plans and memory deltas.
3. A durable workflow path for multi-stage editorial review.
4. Typed agent review without coupling the core drafting engine to one agent framework.
