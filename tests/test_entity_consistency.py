from dataclasses import dataclass

from novel_ai.entity_consistency import SpacyEntityExtractor, SpacyEntityReviewHook


@dataclass
class Character:
    name: str


class Ent:
    def __init__(self, text, label, start=0, end=1):
        self.text = text
        self.label_ = label
        self.start_char = start
        self.end_char = end


class Doc:
    def __init__(self, ents):
        self.ents = ents


class NLP:
    def __call__(self, _text):
        return Doc([
            Ent("林默", "PERSON"),
            Ent("阿默", "PERSON"),
            Ent("赵乾", "PERSON"),
            Ent("上海", "GPE"),
        ])


def test_spacy_entity_hook_flags_only_unknown_people():
    hook = SpacyEntityReviewHook(
        SpacyEntityExtractor(NLP()),
        aliases={"阿默": "林默"},
    )
    payload = hook.review_payload(
        draft="正文",
        plan=None,
        bible=None,
        characters=[Character("林默")],
    )
    assert [item["excerpt"] for item in payload["issues"]] == ["赵乾"]


def test_extractor_preserves_entity_offsets_and_labels():
    rows = SpacyEntityExtractor(lambda _text: Doc([Ent("林默", "PERSON", 3, 5)])).extract("xxx林默")
    assert rows[0].text == "林默"
    assert rows[0].label == "PERSON"
    assert rows[0].start_char == 3
    assert rows[0].end_char == 5
