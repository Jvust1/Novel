# boltons atomic-write source reuse

Novel executes a narrow, modified extraction of `boltons.fileutils.AtomicSaver`,
`atomic_save`, and atomic publication helpers. It is used directly by
`ProjectStore` JSON/manuscript/JSONL writes and the benchmark evidence/scoring
writer. This is source reuse, not installation or vendoring of the whole package.

- Repository: https://github.com/mahmoud/boltons
- Exact commit: `4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d`
- Stars observed 2026-10-01: 6,932
- Copyright: Mahmoud Hashemi, 2013
- License: actual BSD-style three-clause text retained verbatim in [LICENSE](LICENSE)
- GitHub metadata reports `NOASSERTION`; that label is not presented as a detected SPDX identifier
- Exact source, reviewed source tests, line ranges, modifications and SHA-256 hashes: [provenance.json](provenance.json)

The complete pinned source snapshots in `upstream/` are provenance references,
not imported runtime modules. Runtime lives in `novel_ai/_vendor/boltons_atomic.py`.

The modified core preserves the upstream context-manager sequence: exclusive
same-directory part creation → write → flush/fsync/close → atomic publication.
It adds random private part names, UTF-8 text support, cleanup on additional
failure paths, modern os.replace, no-clobber hard-link publication, and supported
POSIX directory fsync. It removes legacy ctypes branches, permission copying,
caller-selected part paths and overwrite_part. The complete upstream API is not
claimed. Only standard-library os/errno are required.

A failure after publication can leave the complete new file visible; error does
not mean rollback. Directory sync may be unsupported. The caller owns confined
paths, cooperating-writer locks and extraction/summary recovery; this core does
not provide identity authentication, remote storage, a filesystem sandbox or
cross-file transactions. Current tests do not prove native Windows behavior or
universal power-loss durability.

The source port's new synthetic tests are separate from the preserved upstream
test snapshot. They cover body/flush/fsync/close/publication failures, private
parts, collisions, no-clobber races, postpublication errors and directory sync.

Alternatives were inspected rather than imported: filelock (978 stars),
portalocker (327) and archived python-atomicwrites (321) did not meet the requested
1,000-star screening threshold on this date. No threshold claim is inferred
from package popularity or download counts.

Verbatim upstream snapshots retain their original CRLF and incidental trailing
whitespace so recorded hashes remain meaningful. Diff whitespace checking is
reported separately for Novel edits; source-preservation tests check these bytes.
