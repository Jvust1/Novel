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
