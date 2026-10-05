from __future__ import annotations

from typing import Any


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

    def count(self, text: str) -> int:
        if self.encoding is not None:
            return len(self.encoding.encode(text or ""))
        return int((len(text or "") + self.fallback_chars_per_token - 1) // self.fallback_chars_per_token)

    def clip(self, text: str, max_tokens: int) -> str:
        value = str(text or "").strip()
        if max_tokens <= 0 or self.count(value) <= max_tokens:
            return value
        if self.encoding is not None:
            ids = self.encoding.encode(value)[:max_tokens]
            return self.encoding.decode(ids).rstrip() + "……"
        approx_chars = max(1, int(max_tokens * self.fallback_chars_per_token))
        return value[:approx_chars].rstrip() + "……"
