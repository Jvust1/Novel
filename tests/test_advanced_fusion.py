from novel_ai.reading import extract_reference_text_with_backend
from novel_ai.semantic import preferred_encoder


def test_plain_text_reader_reports_utf8_backend():
    text, backend = extract_reference_text_with_backend("sample.txt", "第一章\n正文".encode("utf-8"))
    assert "正文" in text
    assert backend == "utf8"


def test_preferred_encoder_has_safe_fallback():
    encoder, backend = preferred_encoder("auto")
    assert backend in {"FlagEmbedding", "text2vec", "char-ngram"}
    if backend == "char-ngram":
        assert encoder is None
