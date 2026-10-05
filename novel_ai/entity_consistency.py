"""Optional spaCy entity extraction and character-consistency review.

Upstream: explosion/spaCy @
c2dabfce56ad2991685ec85783cd59637a5d7b8f (MIT).

Novel owns canon and character identity. spaCy is used only to extract
candidate person entities from generated prose; it does not mutate canon.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class EntityMention:
    text: str
    label: str
    start_char: int
    end_char: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SpacyEntityExtractor:
    """Wrap a configured spaCy Language object behind a stable Novel boundary."""

    def __init__(self, nlp: Any) -> None:
        if not callable(nlp):
            raise TypeError("spaCy pipeline must be callable")
        self._nlp = nlp

    def extract(self, text: str) -> list[EntityMention]:
        doc = self._nlp(text)
        entities = getattr(doc, "ents", None)
        if entities is None:
            raise TypeError("spaCy doc must expose ents")
        rows: list[EntityMention] = []
        for ent in entities:
            value = str(getattr(ent, "text", "")).strip()
            label = str(getattr(ent, "label_", "")).strip()
            if not value or not label:
                continue
            rows.append(
                EntityMention(
                    text=value,
                    label=label,
                    start_char=int(getattr(ent, "start_char", 0)),
                    end_char=int(getattr(ent, "end_char", 0)),
                )
            )
        return rows


def _character_names(characters: Sequence[Any]) -> set[str]:
    names: set[str] = set()
    for item in characters:
        if isinstance(item, Mapping):
            value = item.get("name")
        else:
            value = getattr(item, "name", None)
        if value:
            names.add(str(value).strip())
    return {name for name in names if name}


class SpacyEntityReviewHook:
    """Flag unknown PERSON/PER entities without changing Novel canon."""

    name = "spacy-entity-review"

    def __init__(
        self,
        extractor: SpacyEntityExtractor,
        *,
        person_labels: Iterable[str] = ("PERSON", "PER"),
        aliases: Mapping[str, str] | None = None,
    ) -> None:
        self._extractor = extractor
        self._person_labels = {str(item) for item in person_labels}
        self._aliases = {str(k): str(v) for k, v in dict(aliases or {}).items()}

    def review_payload(
        self,
        *,
        draft: str,
        plan: Any,
        bible: Any,
        characters: list[Any],
    ) -> dict[str, Any]:
        known = _character_names(characters)
        known.update(self._aliases.keys())
        unknown: list[str] = []
        seen: set[str] = set()
        for entity in self._extractor.extract(draft):
            if entity.label not in self._person_labels:
                continue
            canonical = self._aliases.get(entity.text, entity.text)
            if canonical in known or entity.text in known:
                continue
            if entity.text not in seen:
                seen.add(entity.text)
                unknown.append(entity.text)

        issues = [
            {
                "category": "人物实体一致性",
                "severity": "medium",
                "excerpt": name,
                "reason": f"正文出现未登记 PERSON 实体“{name}”。",
                "suggestion": "核对是否为新角色、别名或 NER 误报；确认后再写入角色/别名表。",
            }
            for name in unknown
        ]
        return {"issues": issues}


def create_spacy_entity_review_hook(
    model_name_or_path: str,
    *,
    aliases: Mapping[str, str] | None = None,
    person_labels: Iterable[str] = ("PERSON", "PER"),
    **load_kwargs: Any,
) -> SpacyEntityReviewHook:
    """Load an explicitly named local/installed spaCy pipeline.

    This factory never downloads a model.
    """
    if not str(model_name_or_path).strip():
        raise ValueError("model_name_or_path cannot be empty")
    try:
        import spacy
    except ImportError as exc:
        raise RuntimeError(
            "spaCy is optional; install requirements-extras/nlp.txt before enabling entity review"
        ) from exc
    nlp = spacy.load(model_name_or_path, **load_kwargs)
    return SpacyEntityReviewHook(
        SpacyEntityExtractor(nlp),
        aliases=aliases,
        person_labels=person_labels,
    )
