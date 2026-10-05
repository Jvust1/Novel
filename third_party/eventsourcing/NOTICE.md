# Event replay kernel: source and modifications

Novel directly calls a small adapted source extraction from
[pyeventsourcing/eventsourcing](https://github.com/pyeventsourcing/eventsourcing/blob/575d42c10a821828639b90178ed56703abe9c9f1/examples/aggregate7/immutablemodel.py).
This is executable code reuse, not a claim that the full framework is installed.

- Upstream commit: `575d42c10a821828639b90178ed56703abe9c9f1`, branch observed: `9.5`
- Upstream package version at that commit: `9.5.5`
- GitHub stars observed on 2026-10-01: **1,687**
- License: **BSD-3-Clause**, copyright (c) 2025 John Bywater
- Preserved verbatim license: [LICENSE](LICENSE)
- Machine-readable pins, excerpt ranges, and byte hashes: [provenance.json](provenance.json)

## What is reused

The runtime module is [eventsourcing_example.py](../../novel_ai/_vendor/eventsourcing_example.py).
Its immutable Pydantic base, event/aggregate envelopes, and ordered projection
closure derive from upstream `examples/aggregate7/immutablemodel.py` lines 17–31
and 49–64. The complete original **64-line** file is preserved without changes
as [upstream_immutablemodel.py](upstream_immutablemodel.py); it is a reference,
not an imported runtime module.

The identity and exact-next-version checks derive from
[`CanMutateAggregate.mutate`](https://github.com/pyeventsourcing/eventsourcing/blob/575d42c10a821828639b90178ed56703abe9c9f1/eventsourcing/domain.py#L288-L329),
particularly lines 310–317. The full enclosing method is preserved verbatim
in [upstream_mutate_excerpt.py.txt](upstream_mutate_excerpt.py.txt). The upstream
exception declarations at lines 1789–1802 are preserved separately in
[upstream_errors_excerpt.py.txt](upstream_errors_excerpt.py.txt).

## Explicit modifications

1. Removed the optional Snapshot class and its imports of the full framework,
   dynamic topic lookup, and timestamp factory. Novel supplies explicit typed
   payloads and timestamps. No dynamic module import is driven by story data.
2. Replaced UUID IDs with non-empty strings to match Novel's stable story IDs.
3. Added Pydantic strict mode and non-negative aggregate / positive event version
   bounds. Timestamps remain datetime values as upstream.
4. Moved the upstream mutable aggregate's identity and next-version checks into
   the immutable projection loop. A new stream must begin at version 1; a seeded
   stream must continue at exactly aggregate.version + 1. Events are never sorted.
5. Made the errors ValueError subclasses. Added explicit checks that each event
   has been validated and that each mutator returns a non-None Aggregate whose
   ID and version match the event. The example's implicit unknown-event return
   cannot silently erase a projection.
6. Tightened the mutator type annotation to its two actual arguments. Retained
   upstream function, event, and aggregate names to keep the reuse inspectable.

## Dependency and scope

Only the standard library and Novel's existing Pydantic >=2.8,<3 are needed.
No eventsourcing package, ORJSON, database, queue, service, network connection,
credentials, or model API is added.

Pydantic frozen models are shallow: nested dictionaries and lists still need
detached copies and schema validation at the application boundary. This kernel
does not supply deep immutability, authorship authentication, idempotency,
append-only storage enforcement, conflict resolution, durable transactions, or
proof against a party replacing an entire untrusted file. Novel owns those
domain rules and must test them separately.

The original upstream example's Snapshot uses a full-framework topic registry;
that mechanism was deliberately excluded. The upstream repository reconstruction
and class-version upcasting code were inspected but are not copied or enabled.
Future schema migration must be explicit and must not rewrite historical evidence.

## Tests inspected, not copied

- [aggregate7 application test](https://github.com/pyeventsourcing/eventsourcing/blob/575d42c10a821828639b90178ed56703abe9c9f1/examples/aggregate7/test_application.py):
  three recorded events, snapshot at version 3, and continued projection after it
- [aggregate guard tests](https://github.com/pyeventsourcing/eventsourcing/blob/575d42c10a821828639b90178ed56703abe9c9f1/tests/domain_tests/test_aggregate.py#L897-L921):
  wrong originator version and wrong originator ID must raise

The upstream tests were read for behavior; no upstream test suite was downloaded
or run as part of the source-selection research.

## Alternative evaluated

[SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy/tree/36e47d3a281869defb7c31f4ea0c9309e2f4494c)
had **12,192** stars and an MIT license on 2026-10-01. Its actual
`examples/versioned_history/history_meta.py` stores old row values in a history
table during before_flush and can enable optimistic concurrency via
use_mapper_versioning. The corresponding test checks a second stale session
raises StaleDataError. This is meaningful version-history reuse, but would add
an ORM/database model to Novel's optional JSON/Drive workflow. It is **not copied,
installed, or used**. Source pins and decision are retained in provenance.json.
