"""Independent adversarial review with original synthetic reference fixtures."""

import codecs
import hashlib
import json

import pytest

from novel_ai import reference_pack
from novel_ai.reading import (
    extract_reference,
    extract_reference_text,
    extract_reference_text_with_backend,
)
from novel_ai.text_decoding import (
    EncodingSelectionRequired,
    TextDecodingError,
    decode_reference_text,
    encoding_candidates,
)


SAMPLE = "  原创测试：雨落在空盒旁。\r\n\r\n她数到三，转身关灯。\t\n  "


def test_valid_utf8_never_needs_detector_and_preserves_whitespace(monkeypatch):
    def unexpected_detection(*args, **kwargs):
        pytest.fail("strict valid UTF-8 must not depend on detector output")

    monkeypatch.setattr("chardet.detect_all", unexpected_detection)
    result = decode_reference_text(SAMPLE.encode("utf-8"))
    assert result.text == SAMPLE
    assert result.decision == "utf8_default"
    assert result.encoding == "utf-8"
    assert extract_reference_text("sample.TXT", SAMPLE.encode()) == SAMPLE
    assert extract_reference_text_with_backend("sample.md", SAMPLE.encode()) == (SAMPLE, "utf8")


@pytest.mark.parametrize(
    ("bom", "encoding"),
    [
        (codecs.BOM_UTF8, "utf-8"),
        (codecs.BOM_UTF16_LE, "utf-16-le"),
        (codecs.BOM_UTF16_BE, "utf-16-be"),
        (codecs.BOM_UTF32_LE, "utf-32-le"),
        (codecs.BOM_UTF32_BE, "utf-32-be"),
    ],
)
def test_bom_decoding_preserves_content_and_proves_original_bytes(bom, encoding, monkeypatch):
    monkeypatch.setattr("chardet.detect_all", lambda *args, **kwargs: pytest.fail("BOM needs no detection"))
    # An interior U+FEFF is content, not another file envelope to remove.
    text = SAMPLE + "\ufeff尾句。"
    raw = bom + text.encode(encoding)
    result = decode_reference_text(raw)
    report = result.report()
    assert result.text == text
    assert result.encoding == encoding
    assert result.had_bom is True
    assert result.decision == "bom"
    assert bom + result.text.encode(result.encoding) == raw
    assert report["source_bytes"] == len(raw)
    assert report["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["decoded_utf8_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert report["round_trip_verified"] is True
    assert "原创测试" not in json.dumps(report, ensure_ascii=False)


@pytest.mark.parametrize(
    ("raw", "explicit"),
    [
        (codecs.BOM_UTF16_LE + SAMPLE.encode("utf-16-le"), "utf-16-be"),
        (codecs.BOM_UTF16_BE + SAMPLE.encode("utf-16-be"), "utf-16-le"),
        (codecs.BOM_UTF32_LE + SAMPLE.encode("utf-32-le"), "utf-32-be"),
        (codecs.BOM_UTF32_BE + SAMPLE.encode("utf-32-be"), "utf-32-le"),
        (codecs.BOM_UTF8 + SAMPLE.encode(), "gb18030"),
    ],
)
def test_explicit_encoding_cannot_override_conflicting_bom(raw, explicit, monkeypatch):
    monkeypatch.setattr("chardet.detect_all", lambda *args, **kwargs: pytest.fail("must not fall back"))
    with pytest.raises(TextDecodingError, match="BOM"):
        decode_reference_text(raw, encoding=explicit)


@pytest.mark.parametrize("encoding", ["utf-16", "utf-32"])
def test_endianness_must_be_explicit_without_bom(encoding):
    with pytest.raises(TextDecodingError):
        decode_reference_text(SAMPLE.encode(encoding + "-le"), encoding=encoding)


@pytest.mark.parametrize("encoding", ["utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be", "gb18030"])
def test_explicit_non_utf8_choice_preserves_the_whole_source(encoding):
    raw = SAMPLE.encode(encoding)
    result = extract_reference("sample.txt", raw, encoding=encoding)
    assert result.text == SAMPLE
    assert result.decoding["decision"] == "explicit"
    assert result.decoding["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result.text.encode(result.decoding["encoding"]) == raw


def test_even_confident_detector_never_authorizes_ambiguous_text(monkeypatch):
    # Both encodings accept these bytes but give different characters.
    raw = b"\xa4\xa4"
    assert raw.decode("big5") != raw.decode("gb18030")
    monkeypatch.setattr(
        "chardet.detect_all",
        lambda *args, **kwargs: [
            {"encoding": "big5", "confidence": 1.0},
            {"encoding": "gb18030", "confidence": 0.999},
        ],
    )
    with pytest.raises(EncodingSelectionRequired) as error:
        decode_reference_text(raw)
    assert {row["encoding"] for row in error.value.candidates} == {"big5", "gb18030"}
    assert decode_reference_text(raw, encoding="big5").text == raw.decode("big5")
    assert decode_reference_text(raw, encoding="gb18030").text == raw.decode("gb18030")


@pytest.mark.parametrize("encoding", ["utf-8", "gb18030"])
def test_invalid_tail_beyond_detector_sample_is_never_accepted(encoding, monkeypatch):
    raw = ("原创长样本。" * 40000).encode(encoding) + b"\x81"
    assert len(raw) > 200000
    monkeypatch.setattr(
        "chardet.detect_all",
        lambda *args, **kwargs: [{"encoding": encoding, "confidence": 1.0}],
    )
    assert encoding_candidates(raw) == []
    with pytest.raises(EncodingSelectionRequired) as error:
        decode_reference_text(raw)
    assert error.value.candidates == []
    with pytest.raises(TextDecodingError):
        decode_reference_text(raw, encoding=encoding)


@pytest.mark.parametrize("encoding", ["utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"])
def test_truncated_bom_file_does_not_trigger_detector_fallback(encoding, monkeypatch):
    boms = {
        "utf-16-le": codecs.BOM_UTF16_LE,
        "utf-16-be": codecs.BOM_UTF16_BE,
        "utf-32-le": codecs.BOM_UTF32_LE,
        "utf-32-be": codecs.BOM_UTF32_BE,
    }
    monkeypatch.setattr("chardet.detect_all", lambda *args, **kwargs: pytest.fail("must not fall back"))
    with pytest.raises(TextDecodingError):
        decode_reference_text(boms[encoding] + SAMPLE.encode(encoding)[:-1])


@pytest.mark.parametrize("control", [0, 1, 8, 11, 14, 31, 127])
def test_binary_controls_cannot_become_a_reference(control):
    with pytest.raises(TextDecodingError):
        decode_reference_text(b"synthetic prose" + bytes([control]), encoding="utf-8")


def test_decodable_big5_alias_does_not_get_false_round_trip_certificate(monkeypatch):
    # Big5 includes two byte sequences for this code point; Python chooses a
    # different one on encoding, so strict decode alone cannot certify bytes.
    raw = b"\xa2\xcc"
    assert raw.decode("big5").encode("big5") != raw
    monkeypatch.setattr(
        "chardet.detect_all", lambda *args, **kwargs: [{"encoding": "big5", "confidence": 1.0}]
    )
    assert encoding_candidates(raw) == []
    with pytest.raises(TextDecodingError):
        decode_reference_text(raw, encoding="big5")


@pytest.mark.parametrize(
    "rows",
    [
        None,
        [None, 1, {}, {"encoding": None, "confidence": 0.8}],
        [{"encoding": "gb18030", "confidence": 10**1000}],
        [{"encoding": "gb18030", "confidence": float("nan")}],
        [{"encoding": "gb18030", "confidence": float("inf")}],
        [{"encoding": "gb18030", "confidence": -0.1}],
        [{"encoding": "gb18030", "confidence": 1.1}],
        [{"encoding": "unsupported_codec", "confidence": 1.0}],
    ],
)
def test_unexpected_advisory_output_still_produces_selection_error(rows, monkeypatch):
    monkeypatch.setattr("chardet.detect_all", lambda *args, **kwargs: rows)
    with pytest.raises(EncodingSelectionRequired) as error:
        decode_reference_text(SAMPLE.encode("gb18030"))
    assert error.value.candidates == []


@pytest.mark.parametrize("error_type", [TypeError, ValueError, OverflowError])
def test_detector_input_errors_cannot_mask_the_selection_requirement(error_type, monkeypatch):
    def broken_detector(*args, **kwargs):
        raise error_type("synthetic detector failure")

    monkeypatch.setattr("chardet.detect_all", broken_detector)
    with pytest.raises(EncodingSelectionRequired) as error:
        decode_reference_text(SAMPLE.encode("gb18030"))
    assert error.value.candidates == []


def test_candidates_are_unique_after_codec_normalization(monkeypatch):
    monkeypatch.setattr(
        "chardet.detect_all",
        lambda *args, **kwargs: [
            {"encoding": "UTF8", "confidence": 0.9},
            {"encoding": "utf-8-sig", "confidence": 0.8},
        ],
    )
    candidates = encoding_candidates(SAMPLE.encode())
    assert len(candidates) == 1
    assert candidates[0]["encoding"] == "utf-8"


@pytest.mark.parametrize("encoding", ["utf-8\x00", "\udcff", "rot13", "", 1])
def test_bad_explicit_codec_names_have_controlled_errors(encoding):
    with pytest.raises(TextDecodingError):
        decode_reference_text(b"synthetic source", encoding=encoding)


@pytest.mark.parametrize("data", ["synthetic source", bytearray(b"source"), None])
def test_reference_requires_original_bytes(data):
    with pytest.raises(TextDecodingError):
        decode_reference_text(data)


def test_invalid_source_never_reaches_style_or_signature_analysis(monkeypatch):
    def must_not_analyze(*args, **kwargs):
        pytest.fail("failed reference decoding reached analysis")

    monkeypatch.setattr(reference_pack, "analyze_style", must_not_analyze)
    monkeypatch.setattr(reference_pack, "build_reference_signature", must_not_analyze)
    with pytest.raises(TextDecodingError):
        reference_pack.build_reference_source("bad.txt", b"partial valid prose\xff", encoding="utf-8")


def test_mixed_legacy_and_explicit_pack_inputs_retain_provenance():
    utf8 = SAMPLE.encode()
    gb = SAMPLE.encode("gb18030")
    pack = reference_pack.build_reference_pack([
        ("original_utf8.txt", utf8, 1.0),
        ("original_gb.txt", gb, 2.0, "gb18030"),
    ])
    first, second = pack.sources
    assert first.char_count == second.char_count
    assert first.signature_hashes == second.signature_hashes
    assert first.decoding["decision"] == "utf8_default"
    assert second.decoding["decision"] == "explicit"
    assert first.decoding["source_sha256"] != second.decoding["source_sha256"]
    assert first.decoding["decoded_utf8_sha256"] == second.decoding["decoded_utf8_sha256"]
    assert "原创测试" not in pack.model_dump_json()
