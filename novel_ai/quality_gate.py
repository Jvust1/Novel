from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
from typing import Mapping

_CJK = re.compile(r"[\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff]")
_LATIN_WORD = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")
_LOCATED = re.compile(r"(?:第\\s*\\d+\\s*(?:段|行|章|节)|line\\s*\\d+|paragraph\\s*\\d+|“[^”]{8,}”|\\\"[^\\\"]{8,}\\\")", re.IGNORECASE)
_HASH = re.compile(r"(?:chapter_hash|chapter sha256|章节哈希)\\s*[:=：]\\s*([a-fA-F0-9]{64})", re.IGNORECASE)


def content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prose_units(text: str) -> int:
    """Chinese-friendly length: CJK characters plus Latin/number tokens."""
    return len(_CJK.findall(text)) + len(_LATIN_WORD.findall(text))


def _norm(text: str) -> str:
    return re.sub(r"\\s+", "", text).strip().lower()


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\\n\\s*\\n", text) if p.strip()]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[。！？!?])\\s*", text) if s.strip()]


@dataclass(frozen=True)
class CriticCheck:
    status: str
    units: int
    located_findings: int
    has_matching_chapter_hash: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def check_critic(critic_text: str, chapter_text: str, *, min_units: int = 180, min_located_findings: int = 2) -> CriticCheck:
    units = prose_units(critic_text)
    located = len(_LOCATED.findall(critic_text))
    expected = content_sha256(chapter_text)
    hashes = [m.group(1).lower() for m in _HASH.finditer(critic_text)]
    hash_ok = expected.lower() in hashes
    reasons: list[str] = []
    if units < min_units:
        reasons.append(f"critic_too_short:{units}<{min_units}")
    if located < min_located_findings:
        reasons.append(f"located_findings:{located}<{min_located_findings}")
    if not hash_ok:
        reasons.append("missing_or_stale_chapter_hash")
    return CriticCheck("PASS" if not reasons else "FAIL", units, located, hash_ok, tuple(reasons))


def duplicate_paragraphs(chapters: Mapping[str, str], *, min_units: int = 60) -> list[dict]:
    seen: dict[str, list[str]] = {}
    sample: dict[str, str] = {}
    for chapter, text in chapters.items():
        for paragraph in _paragraphs(text):
            if prose_units(paragraph) < min_units:
                continue
            key = _norm(paragraph)
            if not key:
                continue
            seen.setdefault(key, []).append(chapter)
            sample.setdefault(key, paragraph[:120])
    return [{"chapters": names, "sample": sample[key]} for key, names in seen.items() if len(set(names)) >= 2]


def repeated_sentences(chapters: Mapping[str, str], *, min_units: int = 18, min_chapters: int = 3) -> list[dict]:
    locations: dict[str, set[str]] = {}
    sample: dict[str, str] = {}
    for chapter, text in chapters.items():
        for sentence in _sentences(text):
            if prose_units(sentence) < min_units:
                continue
            key = _norm(sentence)
            locations.setdefault(key, set()).add(chapter)
            sample.setdefault(key, sentence[:120])
    return [{"chapters": sorted(names), "sample": sample[key]} for key, names in locations.items() if len(names) >= min_chapters]


def build_manifest(chapters: Mapping[str, str]) -> dict:
    items = [{"chapter": c, "sha256": content_sha256(t), "units": prose_units(t)} for c, t in sorted(chapters.items())]
    canonical = "\\n".join(f"{x['chapter']}\\t{x['sha256']}\\t{x['units']}" for x in items)
    return {"schema_version": 1, "chapter_count": len(items), "chapters": items, "manifest_sha256": content_sha256(canonical)}


def run_quality_gate(chapters: Mapping[str, str], critics: Mapping[str, str] | None = None, *, min_chapter_units: int = 800) -> dict:
    critics = critics or {}
    rows: list[dict] = []
    blocking: list[dict] = []
    for chapter, text in sorted(chapters.items()):
        units = prose_units(text)
        row = {"chapter": chapter, "units": units, "sha256": content_sha256(text), "status": "PASS" if units >= min_chapter_units else "FAIL"}
        if units < min_chapter_units:
            row["reason"] = f"chapter_too_short:{units}<{min_chapter_units}"
            blocking.append({"type": "chapter_floor", **row})
        if chapter in critics:
            critic = check_critic(critics[chapter], text)
            row["critic"] = critic.to_dict()
            if critic.status != "PASS":
                blocking.append({"type": "critic_evidence", "chapter": chapter, **critic.to_dict()})
        rows.append(row)
    duplicates = duplicate_paragraphs(chapters)
    refrains = repeated_sentences(chapters)
    if duplicates:
        blocking.append({"type": "duplicate_paragraphs", "findings": duplicates})
    return {
        "status": "PASS" if not blocking else "FAIL",
        "manifest": build_manifest(chapters),
        "chapters": rows,
        "blocking": blocking,
        "advisory": {"cross_chapter_repeated_sentences": refrains, "note": "Repeated sentences are advisory because deliberate callbacks may be valid."},
        "method": {"origin": "Novel-native Chinese adaptation of Open-Write deterministic completion/critic gates", "principle": "actual bytes on disk outrank model self-report"},
    }
