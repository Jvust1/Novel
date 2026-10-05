# Pydantic runtime reuse for finite-vector validation

Novel reuses the installed Pydantic validation engine through a reusable
`TypeAdapter(list[list[FiniteFloat]])` and `validate_python(..., strict=True)`
in `novel_ai/semantic.py`. Pydantic is already a required
dependency (`requirements.txt`: `pydantic>=2.8,<3`). This integration adds no
package, service, remote client, model download, or installation.

This is **runtime reuse of an existing dependency**, not a source port or a
new vendored validation framework. No Pydantic implementation or test file is
copied into this directory. `LICENSE` is the complete, unmodified upstream
Pydantic MIT license. The reviewed sources are linked in `provenance.json`.

## Verified upstream

- Repository: https://github.com/pydantic/pydantic
- Version inspected and executed: `2.13.5`
- Tag: `v2.13.5`
- Exact source commit: `001dea020e0809844e5b17666432c9135a976f46`
- Repository stars observed on 2026-10-01: **28,912**, above the requested 1,000-star threshold
- License: MIT; copyright 2017 to present Pydantic Services Inc. and individual contributors
- Existing transitive validation engine: `pydantic-core==2.46.5`, whose source
  is under `pydantic-core/` at the same commit
- Installed `types.py`, `type_adapter.py`, and `version.py` have Git blob
  hashes identical to the pinned source in both checked Python environments

The observed version is evidence for this review, not a newly imposed
dependency pin. Other versions allowed by Novel's existing requirement were
not executed in this verification.

## What the reused engine guarantees

`FiniteFloat` is upstream's `Annotated[float, AllowInfNan(False)]`.
`TypeAdapter.validate_python(..., strict=True)` invokes Pydantic's validation
engine. Upstream's float validator converts to a Python/float64 value and rejects
NaN and positive or negative infinity when `allow_inf_nan=False`.

Strict finite validation accepts ordinary integer and floating-point values,
including finite NumPy numeric scalars in the tested environments. It rejects
Python `bool`, numeric strings/bytes, non-finite values, and integers too large
for float64. Plain `FiniteFloat` without strict mode also coerces strings and
Python booleans, so it is insufficient for this boundary.

Strict does **not** mean "built-in floats only." Pydantic permits other objects
with numeric conversion protocols. Local probes observed acceptance of
`Decimal`, `Fraction`, `numpy.bool_`, zero-dimensional arrays, and NumPy
complex scalars (the latter with a warning). Novel keeps scalar-shape policy
separate from Pydantic's finite-number validation: `numbers.Real` plus explicit Python-boolean rejection
excludes NumPy booleans, arrays, and complex numbers while preserving tested
NumPy integer/float scalars.

Pydantic does not establish vector dimension, batch cardinality, nonzero norm,
overflow-safe cosine arithmetic, immutable metadata, cache freshness, or
transactional replacement. Those are Novel's responsibilities. Finiteness of
each input does not guarantee naive multiplication or squaring will stay finite.

## Existing Novel contract reviewed

The pre-existing `novel_ai/qdrant_recall.py` already requires an embedding per
input, exact configured dimensions, finite values, JSON-safe metadata, nonempty
document ID/text, and a positive non-boolean integer query limit. Its metadata
JSON round-trip detaches nested data and uses `allow_nan=False`.

Recall reuses that existing metadata helper directly, preserving its JSON
normalization. The vector checks are local contract precedents; they do not
activate a Qdrant client.
Its existing `float(value)` loop is weaker than strict validation: it accepts
numeric strings and booleans and does not catch `OverflowError`. Its JSON
round-trip can normalize tuples and non-string dictionary keys; it does not
promise a lossless arbitrary-Python-object copy. The Qdrant module was inspected
only, with no local or remote Qdrant client created.

## Verification limits

Upstream definitions and relevant tests were read at the pinned commit.
Supplementary local scalar probes ran under Python 3.11.16 / NumPy 2.4.6 and
Python 3.12.14 / NumPy 2.5.3, both with Pydantic 2.13.5 / core 2.46.5. These probes
are not a claim that the full upstream Pydantic suite was run. NumPy-specific
observations come from those probes and the reviewed conversion implementation,
not from claimed upstream NumPy test coverage.

Pydantic-core is an existing installed dependency, not copied here. Its distinct
MIT copyright notice is available in the
[pinned core license](https://github.com/pydantic/pydantic/blob/001dea020e0809844e5b17666432c9135a976f46/pydantic-core/LICENSE);
redistributors of that package must preserve its own license as well.
