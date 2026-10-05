#!/usr/bin/env python3
"""Optional private author-change journal. GitHub file access is not Python execution."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from novel_ai.gpt_story_state import artifact
from novel_ai.gpt_story_journal import (JournalCommand, confirmation_binding, journal_fingerprint,
    load_journal, migrate_state, preflight_journal, project_journal, save_journal, transition_journal)


def read_json(path):
    return json.loads(Path(path).read_bytes())


def summary(value):
    p = project_journal(value)
    return {"story_id": value.story_id, "journal_version": p.version, "context_revision": p.context_revision,
            "accepted_chapter_revision": p.story["revision"], "expected_journal_sha256": journal_fingerprint(value),
            "requires_checkpoint": p.requires_checkpoint, "proposal": p.proposal, "amendment": p.amendment,
            "impacts": p.impacts, "progress": p.story["progress"], "readback_receipt": value.readback_receipt,
            "author_authenticated": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    migrate = sub.add_parser("migrate", help="explicit new-envelope migration; old v1 file is preserved")
    migrate.add_argument("source")
    migrate.add_argument("destination")
    migrate.add_argument("--source-id", required=True)
    migrate.add_argument("--source-revision", required=True)
    migrate.add_argument("--confirmation", required=True, help="actual author's migration decision JSON")
    inspect = sub.add_parser("inspect", help="actually read/verify a private saved envelope")
    inspect.add_argument("path")
    inspect.add_argument("--story-id", required=True)
    inspect.add_argument("--sha256")
    inspect.add_argument("--binding", choices=["amendment", "resume", "story"])
    apply = sub.add_parser("apply", help="apply explicit command JSON, append-only save; no automatic acceptance")
    apply.add_argument("path")
    apply.add_argument("command_file")
    preflight = sub.add_parser("preflight", help="actual load plus amendment and required-context checks")
    preflight.add_argument("path")
    preflight.add_argument("--story-id", required=True)
    preflight.add_argument("--sources", required=True)
    preflight.add_argument("--budget-bytes", required=True, type=int)
    preflight.add_argument("--reserve-bytes", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        if args.command == "migrate":
            source_path = Path(args.source).absolute()
            src = artifact(source_path.read_bytes().decode("utf-8"), source_id=args.source_id,
                           location=str(source_path), revision=args.source_revision)
            value = migrate_state(src, read_json(args.confirmation))
            saved = save_journal(args.destination, value)
            output = {**summary(saved["journal"]), "path": saved["path"], "sha256": saved["sha256"],
                      "source_preserved": str(source_path), "readback": "pending; inspect the saved envelope"}
        elif args.command == "inspect":
            value = load_journal(args.path, expected_story_id=args.story_id, expected_sha256=args.sha256)
            output = summary(value)
            output["owned_story"] = project_journal(value).story
            if args.binding:
                output["confirmation_binding_only"] = confirmation_binding(value, args.binding)
        elif args.command == "apply":
            cmd = JournalCommand.model_validate(read_json(args.command_file))
            old = load_journal(args.path, expected_story_id=cmd.story_id)
            old_sha = old.readback_receipt["file_sha256"]
            updated = transition_journal(old, cmd)
            saved = save_journal(args.path, updated, expected_disk_sha256=old_sha)
            output = {**summary(saved["journal"]), "changed": saved["changed"], "sha256": saved["sha256"]}
        else:
            value = load_journal(args.path, expected_story_id=args.story_id)
            output = preflight_journal(value, read_json(args.sources), args.budget_bytes, reserve_bytes=args.reserve_bytes)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 2 if args.command == "preflight" and output["blocked"] else 0
    except (ValueError, TypeError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
