# Export fault injection after staging handles close

This independent follow-up retains the exact integrated #73 production source.
It changes two existing tests in `tests/test_accepted_export_review.py` only:
root redirection before publication, and replacement of a staged temporary file.

The old fixtures renamed objects from an `os.fsync` callback while the staging
file was still open. Native Windows rejects these setup operations with
WinError 5/32 before the intended security boundary is tested. The revised
fixtures use a context manager around the actual `NamedTemporaryFile`: after
the real handle closes and before publication, they perform the same redirection
or replacement. Every original safety assertion and expected ValueError is
retained; two assertions additionally verify that the staging handle is closed.
No test is skipped, no production exception is swallowed, and the real fsync,
readback, cleanup-failure and other attack checks remain unchanged.

Observed local candidate validation:
- Native Windows Python 3.11: 63 passed in this test file.
- Native Windows Python 3.12: 63 passed in this test file.
- Same two-case transaction: original 2 failed (exit 1), modified 2 passed
  (exit 0), actual rollback restores original bytes and 2 failed (exit 1).
- Composite retained CLI/native-fixture patch reconstructs both files exactly.

These are test-file checks, not full native-Windows certification. The retained
#73 Windows full gate hit its 1800-second limit after partial progress and
reported the existing POSIX 0600 assertion failure as well. No assertion was
removed to hide it. Full exact-head Linux CI is a separate publication gate;
its outcome must be read from the new run rather than inherited or summed.

The public writing entry remains #73 until a separately reviewed cumulative
promotion. This follow-up does not merge main, change production storage or
author confirmation, introduce dependencies, call models or publish manuscripts.
