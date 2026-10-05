"""Offline accepted-source review export; no model, acceptance or public upload."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from novel_ai.accepted_export import (
    build_accepted_review_bundle,
    save_accepted_review_bundle,
)
from novel_ai.accepted_writing import restore_journal_source, restore_source
from novel_ai.output_policy import strict_json_object
from novel_ai.release_pack import MarketProfile
from novel_ai.storage import ProjectStore
from novel_ai.storage_guard import reject_links

MAX_METADATA_BYTES = 1024 * 1024


def main(argv=None):
    parser = argparse.ArgumentParser(description='Package exact author-accepted 3/20 chapters for private review.')
    parser.add_argument('source', type=Path)
    parser.add_argument('metadata', type=Path, help='Explicit release-copy JSON with profile, title, hook and blurb')
    parser.add_argument('--source-kind', choices=['v1', 'journal'], default='v1')
    parser.add_argument('--story-id', required=True)
    parser.add_argument('--revision', type=int, required=True)
    parser.add_argument('--sha256', required=True, help='Actual currently read source-file SHA-256')
    parser.add_argument('--context-revision', type=int)
    parser.add_argument('--journal-sha256')
    parser.add_argument('--chapter-id', action='append', required=True)
    parser.add_argument('--stage', choices=['opening_3', 'retention_20'], required=True)
    parser.add_argument('--out-root', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.source_kind == 'journal':
            if args.context_revision is None or args.journal_sha256 is None:
                parser.error('journal requires --context-revision and --journal-sha256')
            source = restore_journal_source(args.source, expected_story_id=args.story_id,
                expected_revision=args.revision, expected_context_revision=args.context_revision,
                expected_journal_sha256=args.journal_sha256, expected_file_sha256=args.sha256)
        else:
            if args.context_revision is not None or args.journal_sha256 is not None:
                parser.error('journal identities cannot be silently applied to a v1 source')
            source = restore_source(args.source, expected_story_id=args.story_id,
                                     expected_revision=args.revision, expected_sha256=args.sha256)
        reject_links(args.metadata.absolute())
        with args.metadata.open('rb') as stream:
            raw = stream.read(MAX_METADATA_BYTES + 1)
        metadata = strict_json_object(raw.decode('utf-8'), max_bytes=MAX_METADATA_BYTES)
        allowed = {'profile', 'title', 'one_line_hook', 'short_blurb', 'long_blurb', 'tags',
                   'content_warnings', 'manual_checks'}
        if set(metadata) - allowed or not {'profile','title','one_line_hook','short_blurb'} <= set(metadata):
            raise ValueError('unsupported or missing release metadata fields')
        profile = metadata.pop('profile')
        if type(profile) is not dict or set(profile) - set(MarketProfile.model_fields):
            raise ValueError('unsupported profile fields')
        bundle = build_accepted_review_bundle(source, chapter_ids=args.chapter_id, stage=args.stage,
            profile=MarketProfile.model_validate(profile, strict=True), **metadata)
        target = save_accepted_review_bundle(ProjectStore(args.out_root), args.story_id, bundle)
        report = bundle.report()
        print(json.dumps({'artifact_path': str(target), 'bundle_sha256': report['bundle_sha256'],
            'story_id': report['source']['story_id'],
            'chapter_ids': [row['chapter_id'] for row in report['source']['chapters']],
            'human_review_status': report['human_review_status'], 'publishability_verdict': None}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        # Do not copy Pydantic's potentially private input values into CLI logs.
        parser.error('accepted export refused (' + type(exc).__name__ +
                     '); verify source identity, accepted selection, release metadata and destination')


if __name__ == '__main__':
    raise SystemExit(main())
