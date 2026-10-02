# Settings recovery + CLI output integration

This independent cumulative candidate combines verified #72 with the disjoint
#71 patch. It does not merge main or rewrite either original branch.

- #72 head: `1be2c45105580502077c4a32a4300b28e6f04fc4`.
  Its recorded Python 3.11/3.12 CI run is 36964456200.
- #71 head: `08c33dae4c1b52700e34430ac397465a8f33318f`.
  Its recorded Python 3.11/3.12 CI run is 36963891187.
- The original changed-file sets were compared and have no overlapping path.
- The only Python production change relative to #72 is the two existing JSON
  serializers in `scripts/story_state.py:main()`, with Unicode-safe ASCII escapes.
- Settings, storage, author UI, locks, memory and recovery implementation bytes
  remain exactly #72's published bytes. The current pointer and three public
  entry declarations identify this combined candidate consistently.

See [settings save recovery](SETTINGS_SAVE_RECOVERY.md) and
[CLI regression coverage](WINDOWS_STORY_STATE_CLI.md) for their exact behavior and
limitations. Existing governance records remain historical evidence, not new
test runs. Tests are not declared passing by adding two prior test counts;
the exact combined PR's complete Python 3.11/3.12 CI must run and be inspected.

The intended product remains GPT + GitHub rules + author-designated private
Drive. Private manuscripts, author acceptance, real-model literary performance,
native Windows full-suite support and hardware power-loss durability are not
certified by this integration. No new dependency, model call or acceptance
protocol is introduced. No permissions assertion, Ruff rule or old test is
removed to force a green result.

This integrates the current code-delivery scope, not a claim that every possible
Novel product goal is 100% complete. Source ZIP and rollback receipts must be
bound to the actual final head and observed test outcomes.
