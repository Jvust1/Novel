"""Small MinHash core adapted from datasketch's MIT MinHash implementation.

Copyright (c) 2015 ekzhu; see third_party/datasketch/LICENSE.
Source: ekzhu/datasketch at ee60290e982be00b6f0a6aea8156e2be4d6921e6,
datasketch/minhash.py (permutation/update/jaccard core).

Novel keeps the source algorithm's fixed-size minimum-hash sketch idea while
using salted SHA-1 hashes instead of NumPy permutation arrays. The sketch is
deterministic, serializable, and works directly on already irreversible
shingle hashes, so it never stores source prose.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

DEFAULT_PERMUTATIONS = 64
_EMPTY = (1 << 64) - 1


def _token_hash(token: str, seed: int) -> int:
    payload = f"{seed}:".encode("ascii") + token.encode("utf-8")
    return int.from_bytes(hashlib.sha1(payload).digest()[:8], "big")


def minhash_signature(
    values: Iterable[str], *, num_perm: int = DEFAULT_PERMUTATIONS
) -> tuple[int, ...]:
    """Return a deterministic MinHash signature for a set-like iterable."""
    if type(num_perm) is not int or not 1 <= num_perm <= 256:
        raise ValueError("num_perm must be an integer from 1 to 256")
    minima = [_EMPTY] * num_perm
    seen = False
    for value in values:
        token = str(value)
        seen = True
        for seed in range(num_perm):
            candidate = _token_hash(token, seed)
            if candidate < minima[seed]:
                minima[seed] = candidate
    return tuple(minima) if seen else tuple([_EMPTY] * num_perm)


def minhash_jaccard(
    left: tuple[int, ...], right: tuple[int, ...]
) -> float:
    """Estimate Jaccard similarity from equal-length MinHash signatures."""
    if not left or len(left) != len(right):
        raise ValueError("signatures must have the same nonzero length")
    return round(sum(a == b for a, b in zip(left, right)) / len(left), 6)


def minhash_overlap(
    values: Iterable[str], reference_values: Iterable[str], *, num_perm: int = DEFAULT_PERMUTATIONS
) -> float:
    """Compute approximate Jaccard overlap without retaining either set."""
    return minhash_jaccard(
        minhash_signature(values, num_perm=num_perm),
        minhash_signature(reference_values, num_perm=num_perm),
    )
