"""Optional, read-only MCP tools over Novel's verified GPT story state.

Run with ``python -m novel_ai.mcp_readonly --state PATH --story-id ID`` after
installing ``requirements-mcp.txt``. The state path is fixed at process start;
MCP callers cannot select another file or mutate a story.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_CONTEXT_BYTES = 1_000_000


def normalize_text(value: Any) -> str:
    """Normalize Unicode search text, adapted from Novel Writer English."""
    normalized = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _searchable(value: Any) -> str:
    return " ".join(re.findall(r"[^\W_]+", normalize_text(value), flags=re.UNICODE))


def score_character(character: dict[str, Any], query: str) -> int:
    """Rank canonical character records using the upstream fuzzy-match bands."""
    normalized_query = _searchable(query)
    if not normalized_query:
        return 0
    name = str(character.get("name") or character.get("id") or "")
    normalized_name = _searchable(name)
    haystack = _searchable(
        f"{name} {json.dumps(character, ensure_ascii=False, sort_keys=True)}"
    )
    tokens = normalized_query.split()
    if normalized_name == normalized_query:
        return 1000
    if normalized_name.startswith(normalized_query):
        return 900
    if normalized_query in normalized_name:
        return 800
    if normalized_query in haystack:
        return 700
    if tokens and all(token in haystack for token in tokens):
        return 600 + len(tokens)
    if any(token in normalized_name for token in tokens):
        return 400
    if any(token in haystack for token in tokens):
        return 200
    return 0


def search_characters(characters: list[dict[str, Any]], query: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    """Return ranked canonical character records; the reveal ledger is never searched."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must contain searchable text")
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be an integer from 1 to {MAX_LIMIT}")
    ranked = []
    for character in characters:
        if not isinstance(character, dict):
            continue
        score = score_character(character, query)
        if score:
            ranked.append((score, str(character.get("name") or character.get("id") or ""), character))
    ranked.sort(key=lambda row: (-row[0], normalize_text(row[1])))
    return [{"score": score, "character": character} for score, _, character in ranked[:limit]]


def create_server(state_path: str | Path, story_id: str):
    """Build the optional MCP server; all handlers are read-only."""
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError("Install the optional MCP tools with: pip install -r requirements-mcp.txt") from exc
    from .gpt_story_state import (
        EDITABLE,
        load_state,
        preflight_context,
        preflight_next_chapter_context,
        rebuild_accepted_history,
    )

    fixed_path = Path(state_path).expanduser().absolute()
    if not isinstance(story_id, str) or not story_id.strip():
        raise ValueError("story_id must be nonempty")
    server = FastMCP("Novel read-only library")
    read_only = ToolAnnotations(read_only_hint=True, destructive_hint=False,
                                idempotent_hint=True, open_world_hint=False)

    def read_state(expected_revision: int | None = None, expected_sha256: str | None = None):
        return load_state(fixed_path, expected_story_id=story_id,
                          expected_revision=expected_revision, expected_sha256=expected_sha256)

    @server.tool(annotations=read_only)
    def story_status(expected_revision: int | None = None, expected_sha256: str | None = None) -> dict[str, Any]:
        """Read Novel story identity, workflow phase, accepted chapter IDs and source versions."""
        state = read_state(expected_revision, expected_sha256)
        progress = state.progress
        return {
            "story_id": state.story_id,
            "story_revision": state.revision,
            "title": state.title,
            "phase": progress.phase,
            "chapter_id": progress.chapter_id,
            "plan_revision": progress.plan_revision,
            "draft_revision": progress.draft_revision,
            "accepted_chapters": [row["chapter_id"] for row in state.accepted_chapters],
            "readback_status": state.readback_receipt.get("status"),
            "canon_character_count": len(state.canon.get("characters", [])),
            "author_confirmation_note": "Confirmation records are caller supplied evidence, not human authentication.",
        }

    @server.tool(annotations=read_only)
    def find_characters(query: str, limit: int = DEFAULT_LIMIT,
                        expected_revision: int | None = None,
                        expected_sha256: str | None = None) -> dict[str, Any]:
        """Search canonical characters by name, alias, role, or recorded details."""
        state = read_state(expected_revision, expected_sha256)
        results = search_characters(state.canon.get("characters", []), query, limit)
        return {"story_id": state.story_id, "story_revision": state.revision,
                "query": query, "count": len(results), "results": results,
                "source": "canon.characters"}

    @server.tool(annotations=read_only)
    def accepted_history(recent_limit: int = 8, expected_history_sha256: str | None = None,
                         expected_revision: int | None = None,
                         expected_sha256: str | None = None) -> dict[str, Any]:
        """Rebuild continuity evidence from accepted chapters after verified file readback."""
        state = read_state(expected_revision, expected_sha256)
        return rebuild_accepted_history(
            state, expected_story_id=story_id,
            expected_history_sha256=expected_history_sha256,
            recent_limit=recent_limit,
        )

    @server.tool(annotations=read_only)
    def context_bundle(sources: list[dict[str, Any]], budget_bytes: int,
                       required_sources: list[dict[str, Any]] | None = None,
                       reserve_bytes: int = 0, include_current_draft: bool = False,
                       expected_history_sha256: str | None = None,
                       expected_revision: int | None = None,
                       expected_sha256: str | None = None) -> dict[str, Any]:
        """Build a source-bound UTF-8-budgeted writing context; required material is never dropped."""
        if type(budget_bytes) is not int or budget_bytes <= 0 or budget_bytes > MAX_CONTEXT_BYTES:
            raise ValueError(f"budget_bytes must be an integer no greater than {MAX_CONTEXT_BYTES}")
        state = read_state(expected_revision, expected_sha256)
        common = dict(required_sources=required_sources, reserve_bytes=reserve_bytes,
                      expected_story_id=story_id, include_current_draft=include_current_draft)
        if state.progress.chapter_id and state.progress.phase in EDITABLE:
            return preflight_next_chapter_context(
                state, sources, budget_bytes, expected_history_sha256=expected_history_sha256,
                **common,
            )
        return preflight_context(state, sources, budget_bytes,
                                 required_sources=required_sources,
                                 reserve_bytes=reserve_bytes,
                                 include_current_draft=include_current_draft)

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only MCP tools for one Novel story state file.")
    parser.add_argument("--state", required=True, help="Path to the Novel story-state JSON file")
    parser.add_argument("--story-id", required=True, help="Exact story_id expected in that file")
    args = parser.parse_args()
    create_server(args.state, args.story_id).run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover - exercised as an MCP subprocess
    main()
