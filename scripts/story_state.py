#!/usr/bin/env python3
"""Optional offline JSON checks; a GitHub plugin alone does not run this script."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# Supports both `python scripts/story_state.py` and module execution.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pydantic import ValidationError
from novel_ai.gpt_story_state import (
    Command, StateError, artifact, create_state, load_state, preflight_context,
    preflight_next_chapter_context, rebuild_accepted_history, save_state,
    state_fingerprint, transition, validate_state,
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("create", help="create a private blank story JSON")
    new.add_argument("path")
    new.add_argument("--story-id", required=True)
    new.add_argument("--title", default="")
    new.add_argument("--template")
    check = sub.add_parser("validate", help="schema and version checks, not author authentication")
    check.add_argument("path")
    apply = sub.add_parser("apply", help="apply an explicit command JSON and save atomically")
    apply.add_argument("path")
    apply.add_argument("command_file")
    inspect = sub.add_parser("inspect", help="actually read and verify a saved state")
    inspect.add_argument("path")
    inspect.add_argument("--story-id", required=True)
    inspect.add_argument("--revision", type=int)
    inspect.add_argument("--sha256")
    context = sub.add_parser("preflight", help="check complete required context against UTF-8 byte budget")
    context.add_argument("path")
    context.add_argument("--sources", required=True)
    context.add_argument("--required")
    context.add_argument("--budget-bytes", type=int, required=True)
    context.add_argument("--reserve-bytes", type=int, default=0)
    history = sub.add_parser("accepted-history", help="reread saved state and rebuild continuity only from accepted versions")
    history.add_argument("path")
    history.add_argument("--story-id", required=True)
    history.add_argument("--revision", type=int)
    history.add_argument("--sha256")
    history.add_argument("--expected-history-sha256")
    history.add_argument("--recent-limit", type=int, default=8)
    next_context = sub.add_parser("next-preflight", help="reread accepted archive and prepare the real next-chapter context")
    next_context.add_argument("path")
    next_context.add_argument("--story-id", required=True)
    next_context.add_argument("--revision", type=int)
    next_context.add_argument("--sha256")
    next_context.add_argument("--sources", required=True)
    next_context.add_argument("--required")
    next_context.add_argument("--budget-bytes", type=int, required=True)
    next_context.add_argument("--reserve-bytes", type=int, default=0)
    next_context.add_argument("--expected-history-sha256")
    next_context.add_argument("--history-source-limit", type=int, default=4)
    src = sub.add_parser("artifact", help="read explicit UTF-8 file, hash its actual bytes, emit artifact JSON")
    src.add_argument("path")
    src.add_argument("--source-id", required=True)
    src.add_argument("--revision", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = save_state(args.path, create_state(args.story_id, args.title,
                                template=read_json(args.template) if args.template else None))
            output = {"story_id": result.state.story_id, "revision": result.state.revision,
                      "phase": result.state.progress.phase, "path": result.path, "sha256": result.sha256,
                      "readback": "pending; run inspect to actually verify",
                      "expected_state_sha256": state_fingerprint(result.state)}
        elif args.command == "validate":
            state = validate_state(Path(args.path).read_bytes())
            output = {"valid": True, "story_id": state.story_id, "revision": state.revision,
                      "phase": state.progress.phase, "author_authenticated": False,
                      "expected_state_sha256": state_fingerprint(state)}
        elif args.command == "apply":
            command = Command.model_validate(read_json(args.command_file))
            raw = Path(args.path).read_bytes()
            old = load_state(args.path, expected_story_id=command.story_id,
                             expected_sha256=hashlib.sha256(raw).hexdigest())
            updated = transition(old, command)
            # An exact retry must not rewrite timestamps/bytes on disk.
            if updated.model_dump() == old.model_dump():
                output = {"changed": False, "story_id": old.story_id, "revision": old.revision,
                          "phase": old.progress.phase, "sha256": hashlib.sha256(raw).hexdigest(),
                          "expected_state_sha256": state_fingerprint(old)}
            else:
                saved = save_state(args.path, updated, expected_disk_revision=old.revision,
                                   expected_disk_sha256=hashlib.sha256(raw).hexdigest())
                output = {"changed": True, "story_id": saved.state.story_id, "revision": saved.state.revision,
                          "phase": saved.state.progress.phase, "memory_update_id": saved.state.progress.memory_update_id,
                          "path": saved.path, "sha256": saved.sha256, "readback": "pending",
                          "expected_state_sha256": state_fingerprint(saved.state)}
        elif args.command == "inspect":
            state = load_state(args.path, expected_story_id=args.story_id,
                               expected_revision=args.revision, expected_sha256=args.sha256)
            output = {"state": state.model_dump(mode="json"), "expected_state_sha256": state_fingerprint(state)}
        elif args.command == "preflight":
            output = preflight_context(validate_state(Path(args.path).read_bytes()), read_json(args.sources),
                                       args.budget_bytes, reserve_bytes=args.reserve_bytes,
                                       required_sources=read_json(args.required) if args.required else None)
        elif args.command in {"accepted-history", "next-preflight"}:
            raw = Path(args.path).read_bytes()
            state = load_state(args.path, expected_story_id=args.story_id, expected_revision=args.revision,
                               expected_sha256=args.sha256 or hashlib.sha256(raw).hexdigest())
            if args.command == "accepted-history":
                output = rebuild_accepted_history(
                    state, expected_story_id=args.story_id,
                    expected_history_sha256=args.expected_history_sha256, recent_limit=args.recent_limit,
                )
            else:
                output = preflight_next_chapter_context(
                    state, read_json(args.sources), args.budget_bytes,
                    required_sources=read_json(args.required) if args.required else None,
                    reserve_bytes=args.reserve_bytes, expected_story_id=args.story_id,
                    expected_history_sha256=args.expected_history_sha256,
                    history_source_limit=args.history_source_limit,
                )
        else:
            path = Path(args.path).absolute()
            # No universal-newline translation: SHA-256 covers the actual UTF-8 file bytes.
            value = artifact(path.read_bytes().decode("utf-8"), source_id=args.source_id,
                             location=str(path), revision=args.revision)
            output = value.model_dump(mode="json")
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 2 if args.command in {"preflight", "next-preflight"} and output["blocked"] else 0
    except (OSError, ValueError, TypeError, ValidationError, StateError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
