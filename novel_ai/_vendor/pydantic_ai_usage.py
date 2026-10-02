"""Small MIT-licensed PydanticAI usage-limit port used by the request budget.

Derived from pydantic/pydantic-ai@675d9f52b38e4dffe0c248451b5fb44595f7308c,
pydantic_ai_slim/pydantic_ai/usage.py. Copyright Pydantic Services Inc.
See third_party/pydantic-ai-usage-limits for original source, license and changes.
Only the request and output-token checks are retained; values are deliberately
supplied by Novel's reservation ledger, not presented as billed usage.
"""
from dataclasses import dataclass


class UsageLimitExceeded(ValueError):
    """A request cannot be admitted under the configured limits."""


@dataclass(frozen=True)
class RunUsage:
    requests: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, kw_only=True)
class UsageLimits:
    request_limit: int | None = 50
    output_tokens_limit: int | None = None

    def check_before_request(self, usage: RunUsage) -> None:
        request_limit = self.request_limit
        if request_limit is not None and usage.requests >= request_limit:
            raise UsageLimitExceeded(f'The next request would exceed the request_limit of {request_limit}')

    def check_tokens(self, usage: RunUsage) -> None:
        output_tokens = usage.output_tokens
        if self.output_tokens_limit is not None and output_tokens > self.output_tokens_limit:
            raise UsageLimitExceeded(
                f'Exceeded the output_tokens_limit of {self.output_tokens_limit} ({output_tokens=})'
            )
