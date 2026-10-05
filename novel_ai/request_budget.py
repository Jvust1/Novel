"""One explicit, in-process ledger for bounded OpenAI-compatible wire attempts.

No truncation, guessed tokenizer, estimated dollars or automatic reset. Admission
reserves the entire requested output cap before dispatch, including retries. An
error does not refund a request that may already have reached the server.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass
from typing import Any

from ._vendor.pydantic_ai_usage import RunUsage, UsageLimitExceeded, UsageLimits
from .output_policy import positive_int


class RequestBudgetExceeded(UsageLimitExceeded):
    """Refusal before a wire attempt; exception messages contain no story text."""


@dataclass(frozen=True)
class RequestBudgetLimits:
    max_requests: int = 8
    max_request_bytes: int = 512 * 1024
    max_total_request_bytes: int = 2 * 1024 * 1024
    max_reserved_output_tokens: int = 96 * 1024

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            positive_int(value, name=name)


def bounded_request_bytes(payload: dict[str, Any], *, max_bytes: int) -> bytes:
    """Serialize the exact JSON sent to the server, never clipping fields.

    Chunked encoding bounds the accepted body, not an adversarial Python object
    graph/process memory. A single already-built string may still allocate a
    JSON encoder chunk. Only ordinary trusted local callers are supported.
    """
    positive_int(max_bytes, name="max_bytes")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a nonempty list")
    for message in messages:
        if (not isinstance(message, dict) or set(message) != {"role", "content"}
                or message["role"] not in {"system", "user", "assistant"}
                or not isinstance(message["content"], str)):
            raise ValueError("only explicit text chat messages are supported")
    body = bytearray()
    try:
        encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        for part in encoder.iterencode(payload):
            encoded = part.encode("utf-8")
            if len(body) + len(encoded) > max_bytes:
                raise RequestBudgetExceeded("request JSON exceeds the per-request byte allowance")
            body.extend(encoded)
    except RequestBudgetExceeded:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise ValueError("request JSON contains unsupported values") from None
    return bytes(body)


class RequestBudget:
    """Share one instance across every provider used by one writing session.

    The ledger is process-local, thread-coordinated and monotone. It is neither
    an author approval nor a durable billing/security boundary. Creating another
    ledger explicitly starts another allowance; snapshots cannot restore one.
    """

    def __init__(self, limits: RequestBudgetLimits | None = None):
        if limits is not None and type(limits) is not RequestBudgetLimits:
            raise TypeError("limits must be RequestBudgetLimits")
        self._limits = limits or RequestBudgetLimits()
        self._guard = UsageLimits(request_limit=self._limits.max_requests,
                                  output_tokens_limit=self._limits.max_reserved_output_tokens)
        self._pid = os.getpid()
        self._lock = threading.Lock()
        self._attempts: list[dict[str, Any]] = []
        self._request_bytes = 0
        self._reserved_tokens = 0
        self._closed = False

    def __copy__(self):
        raise TypeError("live request budgets cannot be copied; share the same instance")

    def __deepcopy__(self, memo):
        raise TypeError("live request budgets cannot be copied; share the same instance")

    def __reduce_ex__(self, protocol):
        raise TypeError("live request budgets cannot be serialized or restored")

    def _assert_process(self) -> None:
        # Check before acquiring an inherited lock, which may be held by a
        # thread absent in the child. A fork cannot clone an allowance.
        if os.getpid() != self._pid:
            raise RequestBudgetExceeded("request budget belongs to another process")

    @property
    def limits(self) -> RequestBudgetLimits:
        self._assert_process()
        return self._limits

    def close(self) -> None:
        """Stop further requests without changing any previous reservations."""
        self._assert_process()
        with self._lock:
            self._closed = True

    def admit(self, body: bytes, *, max_tokens: int) -> int:
        """Atomically reserve a complete request immediately before dispatch."""
        if type(body) is not bytes or not body:
            raise TypeError("body must be nonempty serialized bytes")
        positive_int(max_tokens, name="max_tokens")
        size = len(body)
        self._assert_process()
        with self._lock:
            if self._closed:
                raise RequestBudgetExceeded("request budget is closed")
            if size > self._limits.max_request_bytes:
                raise RequestBudgetExceeded("request JSON exceeds the per-request byte allowance")
            if self._request_bytes + size > self._limits.max_total_request_bytes:
                raise RequestBudgetExceeded("request would exceed the total request-byte allowance")
            try:
                self._guard.check_before_request(RunUsage(requests=len(self._attempts)))
                self._guard.check_tokens(RunUsage(output_tokens=self._reserved_tokens + max_tokens))
            except UsageLimitExceeded as exc:
                raise RequestBudgetExceeded(str(exc)) from None
            attempt = len(self._attempts) + 1
            self._attempts.append({"attempt": attempt, "request_sha256": hashlib.sha256(body).hexdigest(),
                                   "request_bytes": size, "reserved_output_tokens": max_tokens,
                                   "status": "admitted"})
            self._request_bytes += size
            self._reserved_tokens += max_tokens
            return attempt

    def finish(self, attempt: int, *, succeeded: bool) -> None:
        """Record outcome; no retry/refund and no provider data in the ledger."""
        if type(attempt) is not int or type(succeeded) is not bool:
            raise TypeError("invalid attempt outcome")
        self._assert_process()
        with self._lock:
            if not 1 <= attempt <= len(self._attempts):
                raise ValueError("unknown attempt")
            row = self._attempts[attempt - 1]
            if row["status"] != "admitted":
                raise ValueError("attempt outcome was already recorded")
            row["status"] = "succeeded" if succeeded else "failed"

    def snapshot(self) -> dict[str, Any]:
        self._assert_process()
        with self._lock:
            return {"schema": "novel-request-budget-v1", "limits": asdict(self._limits),
                    "requests_reserved": len(self._attempts), "request_bytes_reserved": self._request_bytes,
                    "output_tokens_reserved": self._reserved_tokens, "closed": self._closed,
                    "attempts": [dict(row) for row in self._attempts],
                    "actual_tokens": None, "actual_cost": None,
                    "scope": "in-process OpenAI-compatible HTTP attempts; reservations are not billed usage"}
