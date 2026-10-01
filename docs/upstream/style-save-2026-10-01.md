# Style Lab fixed save protocol reuse

This integrates Novel's existing fixed recovery pattern from `novel_ai/memory_commit.py` and ProjectStore into three style targets. The implementation directly executes the existing licensed `novel_ai/_vendor/boltons_atomic.py` writer and `storage_guard.project_lock`; it does not introduce a database, framework, package, service or model backend.

- Upstream: https://github.com/mahmoud/boltons
- Existing exact pin: `4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d`
- Existing observation: 6,932 stars on 2026-10-01; not a new live count
- Full unchanged BSD-style three-clause license, source snapshots, retained tests and modifications: [existing provenance](../../third_party/boltons/NOTICE.md)
- Runtime sequence remains exclusive same-directory part creation, write/flush/fsync, atomic publication and supported directory sync
- Existing Pydantic `StyleFingerprint` validates supported values; legacy original data is not destructively round-tripped

The Novel-owned additions are a fixed style intent/receipt, request nonce, exact-byte optimistic checks, coherent loading and UI retry binding. The broader guarantee comes from that bounded caller protocol, not from claiming that a single-file atomic writer provides a general transaction. Existing chapter and memory recovery remain distinct, and mutually pending incompatible intents stop for reconciliation.

Base: PR #63 head `cf360611df034af51d7eeefdffd1e07930234e13`, tree `0d5391faf061aad6529ee2f0d8c09e5023a90410`. This source retains the original licenses and verified upstream snapshots without alteration. No additional upstream-count claim is made.
