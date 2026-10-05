# Novel read-only MCP adapter

The optional adapter exposes verified story state to an MCP client without adding
write tools.

## Install

```bash
python -m pip install -r requirements-mcp.txt
```

## Start

```bash
python -m novel_ai.mcp_readonly --state /absolute/path/story.json --story-id story-A
```

The state path and story ID are fixed when the server starts. Each tool rereads
the state through Novel's existing readback and source guards.

## Tools

- `story_status`: phase, revision, current chapter, accepted chapter IDs.
- `find_characters`: ranked lookup over `canon.characters`; it never searches
  the full-truth reader reveal ledger.
- `accepted_history`: rebuilds continuity evidence from verified accepted
  chapters.
- `context_bundle`: applies Novel's UTF-8 byte budget and required-source
  rules. For an active chapter it includes accepted-history preflight and
  excludes the current draft by default.

All tools are annotated read-only and idempotent. MCP output is evidence for the
host; it is never author approval and cannot mutate Canon or manuscript files.
