"""Strict reference-text decoding with local, advisory chardet candidates."""
from __future__ import annotations

import codecs
import hashlib
import math
import re
from dataclasses import dataclass

ENCODINGS = frozenset({"ascii", "utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be",
                       "utf-32", "utf-32-le", "utf-32-be", "gb18030", "gbk", "gb2312",
                       "big5", "cp1252"})
_BOMS = ((codecs.BOM_UTF32_LE, "utf-32-le"), (codecs.BOM_UTF32_BE, "utf-32-be"),
         (codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF16_LE, "utf-16-le"),
         (codecs.BOM_UTF16_BE, "utf-16-be"))
_CONTROLS = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")


class TextDecodingError(ValueError):
    """No partial text may proceed to analysis or originality checking."""


class EncodingSelectionRequired(TextDecodingError):
    def __init__(self, candidates: list[dict]):
        self.candidates = candidates
        names = "、".join(row["encoding"] for row in candidates)
        suffix = f"候选：{names}。" if names else "没有可靠的可逆候选。"
        super().__init__("无法按 UTF-8 或 BOM 完整读取；请核对原文件并明确选择编码。" + suffix)


def _encoding(value: str) -> str:
    if type(value) is not str:
        raise TextDecodingError("编码必须是明确的受支持名称")
    try:
        name = codecs.lookup(value).name
    except (LookupError, ValueError) as exc:
        raise TextDecodingError("不支持所选文本编码") from exc
    if name not in ENCODINGS:
        raise TextDecodingError("不支持所选文本编码")
    return name


def _decode(data: bytes, encoding: str) -> tuple[str, str, bool]:
    bom, inferred = next(((b, name) for b, name in _BOMS if data.startswith(b)), (b"", None))
    if bom:
        family = "utf-16" if inferred.startswith("utf-16") else "utf-32" if inferred.startswith("utf-32") else "utf-8-sig"
        if encoding not in {inferred, family}:
            raise TextDecodingError("所选编码与文件 BOM 冲突，未进行分析")
        codec = inferred
        payload = data[len(bom):]
    else:
        if encoding in {"utf-16", "utf-32"}:
            raise TextDecodingError("无 BOM 时必须明确指定 UTF-16/32 的字节顺序")
        codec = "utf-8" if encoding == "utf-8-sig" else encoding
        payload = data
    try:
        text = payload.decode(codec, errors="strict")
        restored = bom + text.encode(codec, errors="strict")
    except UnicodeError as exc:
        raise TextDecodingError("原件包含无法按所选编码完整转换的字节，未进行分析") from exc
    if restored != data:
        raise TextDecodingError("文本无法按原编码逐字节还原，未进行分析")
    if _CONTROLS.search(text):
        raise TextDecodingError("文本含 NUL 或异常控制字符，请核对编码或文件类型")
    return text, codec, bool(bom)


def encoding_candidates(data: bytes) -> list[dict]:
    """Rank supported reversible candidates; scores never authorize decoding."""
    from chardet import detect_all

    try:
        ranked = detect_all(data, compat_names=False, prefer_superset=False,
                            include_encodings=sorted(ENCODINGS - {"utf-16", "utf-32", "utf-8-sig"}),
                            no_match_encoding="utf-8", max_bytes=200000)
    except (TypeError, ValueError, OverflowError):
        return []
    if not isinstance(ranked, list):
        return []
    candidates, seen = [], set()
    for row in ranked:
        try:
            codec = _encoding(row["encoding"])
            score = float(row["confidence"])
            if not math.isfinite(score) or not 0 <= score <= 1 or codec in seen:
                continue
            text, effective, _ = _decode(data, codec)
        except (TextDecodingError, KeyError, TypeError, ValueError, OverflowError):
            continue
        if effective in seen:
            continue
        seen.add(effective)
        candidates.append({"encoding": effective, "confidence": score, "char_count": len(text)})
        if len(candidates) == 5:
            break
    return candidates


@dataclass(frozen=True)
class DecodedText:
    text: str
    encoding: str
    had_bom: bool
    decision: str
    source_bytes: int
    source_sha256: str

    def report(self) -> dict:
        return {"encoding": self.encoding, "had_bom": self.had_bom, "decision": self.decision,
                "source_bytes": self.source_bytes, "source_sha256": self.source_sha256,
                "decoded_utf8_sha256": hashlib.sha256(self.text.encode("utf-8")).hexdigest(),
                "round_trip_verified": True}


def decode_reference_text(data: bytes, *, encoding: str | None = None) -> DecodedText:
    if type(data) is not bytes:
        raise TextDecodingError("参考原件必须是 bytes")
    inferred = next((name for bom, name in _BOMS if data.startswith(bom)), None)
    if encoding is not None:
        codec, decision = _encoding(encoding), "explicit"
    elif inferred is not None:
        codec, decision = inferred, "bom"
    else:
        codec, decision = "utf-8", "utf8_default"
    try:
        text, effective, had_bom = _decode(data, codec)
    except TextDecodingError:
        # A detected BOM or an explicit choice must not fall back to another
        # codec when invalid. Preserve the source and require reconciliation.
        if encoding is not None or inferred is not None:
            raise
        raise EncodingSelectionRequired(encoding_candidates(data)) from None
    return DecodedText(text, effective, had_bom, decision, len(data), hashlib.sha256(data).hexdigest())
