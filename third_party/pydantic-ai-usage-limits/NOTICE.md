# PydanticAI usage-limit source port

Upstream: https://github.com/pydantic/pydantic-ai
Exact commit: `675d9f52b38e4dffe0c248451b5fb44595f7308c`
Original path: `pydantic_ai_slim/pydantic_ai/usage.py`
License: MIT. Copyright Pydantic Services Inc. 2024 to present.
The complete original LICENSE and byte-exact source are preserved alongside this notice. Git blob IDs and SHA-256 are in provenance.json.

## Precisely what is reused

`novel_ai/_vendor/pydantic_ai_usage.py` retains the original request-limit comparison and output-token-limit comparison with their error messages. They execute during every RequestBudget.admit before owned HTTP dispatch. This is a small selective source port, not a full PydanticAI integration.

## Changes

- Drop unused model pricing, token extraction, tools, telemetry, serialization, warnings and helper dependencies
- Use frozen minimal RunUsage/UsageLimits records and a local ValueError subclass
- Novel supplies the monotonically reserved maximum output-token allowance, not provider-reported actual token usage
- Novel adds strict positive limit validation, exact complete request-body bytes, atomic cooperating-thread admission, failure outcomes and a shared writing-session entry outside the upstream port
- No output reservation is refunded after dispatch, including transport errors or the first unsupported-format request

No PydanticAI SDK, model client, credential or service is installed. The complete preserved source is a provenance reference, not imported code. No price, tokenizer, billing guarantee or automatic author acceptance is claimed.
