# Guidance structured-output integration — 2026-09-30

Upstream: `guidance-ai/guidance`  
Revision inspected: `21b1d90dfbebff4b141df70c714c8af15aa5f4af`  
License: MIT

Novel now exposes Guidance through the same `StructuredExtractor` contract used by Instructor and Outlines.

The adapter uses Guidance JSON generation with a Pydantic schema and captured output. Guidance remains optional; Novel core behavior is unchanged unless the extractor is explicitly selected.

Intended evaluation: run the same frozen ChapterPlan / ChapterReview / MemoryExtraction cases through Instructor, Outlines and Guidance and compare schema success, latency, cost and downstream review quality.
