Integration note: the original #71 scope below is retained; this combined
candidate advances the public pointer on top of #72. See
[integration scope](SETTINGS_CLI_INTEGRATION.md).

# Story-state CLI JSON on redirected Windows streams

This is an independent, narrow follow-up to candidate #70. It does not replace
`governance/current_candidate.json`, advance the cumulative candidate, or change
the GPT + GitHub rules + author-designated private Drive writing route.

## Reproduced defect and smallest change

`scripts/story_state.py:main()` used `ensure_ascii=False` for its success and
error JSON. With redirected ASCII, cp1252 or GBK streams, a Chinese/Arabic/emoji
artifact result could fail during printing. A `create` command could already
have saved its state before reporting an encoding failure. A missing Unicode
filename could also turn the intended JSON error into a traceback.

Only the two CLI JSON serializers now use `ensure_ascii=True`. This produces an
ASCII wire representation, not discarded/replaced characters: `json.loads`
recovers the exact Unicode values. Input UTF-8 bytes, hashes, persisted state,
exit codes for real validation failures, and author-confirmation rules are
unchanged. The caller's stdout/stderr encoding is not forcibly reconfigured.
See the primary [Python JSON documentation](https://docs.python.org/3.12/library/json.html#json.dump).

The tradeoff is visible `\u` escapes when reading raw CLI JSON. Consumers should
parse JSON rather than depend on its literal textual spelling. This change does
not fix arbitrary broken pipes, unsupported stream encodings, other CLI scripts,
Windows power-loss durability, or all native Windows application behavior.

## Synthetic regression coverage

`tests/test_story_state_cli_encoding.py` has 12 parametrized cases: ASCII,
cp1252, GBK and UTF-8, across three scenarios:

1. A Unicode-named artifact with mixed Chinese, Arabic, accented Latin, emoji
   and CRLF: exact text, source metadata, unchanged input bytes and SHA-256.
2. A missing Unicode filename: exit 2, empty stdout, one parseable JSON error,
   no traceback and no file writes.
3. Create, validate and inspect: Unicode story ID/title survives; real disk hash
   matches; create still reports pending readback; no plan, chapter or memory
   acceptance is invented; read-only commands do not rewrite state bytes.

Run with a prepared Python 3.11 or 3.12 environment:

```text
python -m pytest -q tests/test_story_state_cli_encoding.py
python -m pytest -q tests/test_gpt_story_state.py tests/test_initial_preflight_identity.py
```

The tests explicitly set child `PYTHONIOENCODING`; they do not require the user's
console to be UTF-8. The original script fails nine narrow-stream behavior cases;
three UTF-8 cases additionally assert the newly chosen ASCII wire contract, not
pre-existing Unicode data loss in UTF-8 mode.

All data is independently authored synthetic material. No model transport,
private manuscript, paid API, deployment, new application dependency, main merge,
or author-acceptance/schema change is involved. The reserved Bible/flat-outline
CAS and recovery implementation, its tests, and cumulative entry files are not
modified. That in-progress developer's unpublished live diff was unavailable;
this patch stays outside every reserved path named in the handoff.

Validation results belong to the exact candidate PR/CI and local execution
receipts, not to an inferred success from this document. The original retained
fatal Ruff, dependency, compile, integration, entry and full-pytest gates are not
removed, suppressed or weakened. Windows full-suite limitations must be reported
separately from this narrow CLI success.
