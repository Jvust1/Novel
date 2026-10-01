from novel_ai.token_budget import TokenCounter


class FakeEncoding:
    def encode(self, text):
        return list(text)

    def decode(self, ids):
        return "".join(ids)


def test_token_counter_uses_real_encoding_when_injected():
    counter = TokenCounter(FakeEncoding())
    assert counter.count("abcd") == 4
    assert counter.clip("abcdef", 3) == "abc……"


def test_token_counter_has_dependency_free_fallback():
    counter = TokenCounter(None, fallback_chars_per_token=2)
    assert counter.count("abcd") == 2
    assert counter.clip("abcdef", 2) == "abcd……"

import pytest
from novel_ai.token_budget import ModelBudgetExceeded, ModelCallBudget


def test_message_counter_includes_full_normalized_payload_without_clipping():
    counter = TokenCounter(FakeEncoding())
    messages = [{"role": "system", "content": "A"}, {"role": "user", "content": "中文"}]
    assert counter.count_messages(messages) == len('[{"content":"A","role":"system"},{"content":"中文","role":"user"}]')


def test_model_call_budget_reserves_failed_attempt_allowance_and_shrinks_next_grant():
    counter = TokenCounter(FakeEncoding())
    budget = ModelCallBudget(token_counter=counter, max_input_tokens=1000,
                             total_output_tokens=15, max_attempts=2)
    messages = [{"role": "user", "content": "x"}]
    assert budget.claim(messages, 10) == 10
    assert budget.claim(messages, 10) == 5
    assert budget.snapshot()["reserved_output_tokens"] == 15
    with pytest.raises(ModelBudgetExceeded, match="attempt count|exhausted"):
        budget.claim(messages, 10)


def test_model_call_budget_rejects_full_input_without_trimming_or_attempt_reservation():
    counter = TokenCounter(FakeEncoding())
    messages = [{"role": "user", "content": "required canon sentinel"}]
    exact = counter.count_messages(messages)
    budget = ModelCallBudget(token_counter=counter, max_input_tokens=exact - 1,
                             total_output_tokens=10, max_attempts=2)
    with pytest.raises(ModelBudgetExceeded, match="required context was not clipped"):
        budget.claim(messages, 10)
    assert budget.attempts == 0
    assert budget.reserved_output_tokens == 0
    assert budget.last_input_tokens == exact


def test_hard_gate_tiktoken_fallback_defaults_to_one_character_per_token():
    counter = TokenCounter.from_tiktoken()
    assert counter.fallback_chars_per_token == 1.0


def test_model_call_budget_accumulates_repeated_input_and_blocks_before_next_attempt():
    counter = TokenCounter(FakeEncoding())
    messages = [{"role": "user", "content": "same required context"}]
    exact = counter.count_messages(messages)
    budget = ModelCallBudget(
        token_counter=counter,
        max_input_tokens=exact,
        total_input_tokens=exact * 2 - 1,
        total_output_tokens=100,
        max_attempts=3,
    )
    assert budget.claim(messages, 10) == 10
    with pytest.raises(ModelBudgetExceeded, match="cumulative model input-token allowance"):
        budget.claim(messages, 10)
    snap = budget.snapshot()
    assert snap["attempts"] == 1
    assert snap["consumed_input_tokens"] == exact
    assert snap["remaining_input_tokens"] == exact - 1
    assert snap["reserved_output_tokens"] == 10
