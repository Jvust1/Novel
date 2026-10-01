from __future__ import annotations

import json
from typing import Any


class ModelBudgetExceeded(ValueError):
    """A model attempt would exceed the configured input/cumulative allowance."""


class TokenCounter:
    """Optional tiktoken counter with deterministic char fallback."""

    def __init__(self, encoding: Any | None = None, *, fallback_chars_per_token: float = 2.0) -> None:
        if fallback_chars_per_token <= 0:
            raise ValueError("fallback_chars_per_token must be positive")
        self.encoding = encoding
        self.fallback_chars_per_token = float(fallback_chars_per_token)

    @classmethod
    def from_tiktoken(cls, encoding_name: str = "o200k_base") -> "TokenCounter":
        try:
            import tiktoken
        except ImportError:
            return cls()
        return cls(tiktoken.get_encoding(encoding_name))

    @property
    def mode(self) -> str:
        return "tokenizer" if self.encoding is not None else "deterministic-fallback"

    def count(self, text: str) -> int:
        if self.encoding is not None:
            return len(self.encoding.encode(text or ""))
        return int((len(text or "") + self.fallback_chars_per_token - 1) // self.fallback_chars_per_token)

    def count_messages(self, messages: list[dict[str, str]]) -> int:
        """Count the complete normalized message payload without trimming it.

        This is deterministic and includes role/name/content framing. Even with a
        real tokenizer it is a configured-tokenizer count of Novel's canonical
        message JSON, not a claim about a provider's proprietary chat template.
        """
        if not isinstance(messages, list) or any(not isinstance(item, dict) for item in messages):
            raise TypeError("messages must be a list of dictionaries")
        normalized: list[dict[str, str]] = []
        for item in messages:
            row: dict[str, str] = {}
            for key, value in item.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise TypeError("message keys and values must be strings")
                row[key] = value
            normalized.append(row)
        payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return self.count(payload)

    def clip(self, text: str, max_tokens: int) -> str:
        value = str(text or "").strip()
        if max_tokens <= 0 or self.count(value) <= max_tokens:
            return value
        if self.encoding is not None:
            ids = self.encoding.encode(value)[:max_tokens]
            return self.encoding.decode(ids).rstrip() + "……"
        approx_chars = max(1, int(max_tokens * self.fallback_chars_per_token))
        return value[:approx_chars].rstrip() + "……"


class ModelCallBudget:
    """Conservative allowance shared by every attempt of one model stage.

    Output tokens are *reserved* before each remote/backend attempt and never
    refunded, because an exception does not prove the provider generated zero
    tokens. This bounds retries/fallbacks even when usage metadata is absent.
    Input is checked in full before each attempt and is never silently clipped.
    """

    def __init__(self, *, token_counter: TokenCounter, max_input_tokens: int,
                 total_output_tokens: int, max_attempts: int) -> None:
        if not isinstance(token_counter, TokenCounter):
            raise TypeError("token_counter must be TokenCounter")
        for name, value in {
            "max_input_tokens": max_input_tokens,
            "total_output_tokens": total_output_tokens,
            "max_attempts": max_attempts,
        }.items():
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        self.token_counter = token_counter
        self.max_input_tokens = max_input_tokens
        self.total_output_tokens = total_output_tokens
        self.max_attempts = max_attempts
        self.attempts = 0
        self.reserved_output_tokens = 0
        self.last_input_tokens: int | None = None
        self.max_observed_input_tokens = 0

    @property
    def remaining_output_tokens(self) -> int:
        return self.total_output_tokens - self.reserved_output_tokens

    @property
    def remaining_attempts(self) -> int:
        return self.max_attempts - self.attempts

    def claim(self, messages: list[dict[str, str]], requested_output_tokens: int) -> int:
        if type(requested_output_tokens) is not int or requested_output_tokens <= 0:
            raise ValueError("requested_output_tokens must be a positive integer")
        input_tokens = self.token_counter.count_messages(messages)
        self.last_input_tokens = input_tokens
        self.max_observed_input_tokens = max(self.max_observed_input_tokens, input_tokens)
        if input_tokens > self.max_input_tokens:
            raise ModelBudgetExceeded("model input exceeds its token allowance; required context was not clipped")
        if self.attempts >= self.max_attempts:
            raise ModelBudgetExceeded("model attempt count exceeds the cumulative stage allowance")
        grant = min(requested_output_tokens, self.remaining_output_tokens)
        if grant <= 0:
            raise ModelBudgetExceeded("cumulative model output-token allowance is exhausted")
        self.attempts += 1
        self.reserved_output_tokens += grant
        return grant

    def snapshot(self) -> dict[str, int | str | None]:
        return {
            "counter_mode": self.token_counter.mode,
            "max_input_tokens": self.max_input_tokens,
            "last_input_tokens": self.last_input_tokens,
            "max_observed_input_tokens": self.max_observed_input_tokens,
            "max_attempts": self.max_attempts,
            "attempts": self.attempts,
            "total_output_tokens": self.total_output_tokens,
            "reserved_output_tokens": self.reserved_output_tokens,
            "remaining_output_tokens": self.remaining_output_tokens,
        }
