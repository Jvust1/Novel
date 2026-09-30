from novel_ai.entity_alias import RapidFuzzEntityMatcher
from novel_ai.longform_consistency import build_longform_health


class FakeProcess:
    @staticmethod
    def extractOne(query, choices, *, scorer, score_cutoff):
        scored = [(choice, scorer(query, choice), idx) for idx, choice in enumerate(choices)]
        scored.sort(key=lambda row: row[1], reverse=True)
        best = scored[0]
        return best if best[1] >= score_cutoff else None


def fake_scorer(left, right):
    if left == "林舟":
        return 100.0 if right == "林舟" else 20.0
    if left == "林州" and right == "林舟":
        return 95.0
    return 10.0


def test_rapidfuzz_entity_matcher_flags_near_name_drift_only():
    matcher = RapidFuzzEntityMatcher(process_module=FakeProcess, scorer=fake_scorer)
    alerts = matcher.find_drift(
        ["林舟", "林州", "完全不同"],
        {"林舟": ["小舟"], "周岚": []},
        threshold=80,
    )
    assert len(alerts) == 1
    assert alerts[0].observed == "林州"
    assert alerts[0].canonical == "林舟"
    assert alerts[0].score == 95.0


class StubMatcher:
    def find_drift(self, observed_entities, canonical_aliases, *, threshold=86.0):
        assert observed_entities == ["林州"]
        assert canonical_aliases == {"林舟": ["小舟"]}
        return [
            type(
                "Alert",
                (),
                {
                    "to_dict": lambda self: {
                        "observed": "林州",
                        "canonical": "林舟",
                        "score": 95.0,
                        "matched_alias": "林舟",
                    }
                },
            )()
        ]


def test_longform_health_includes_entity_alias_guard_when_enabled():
    report = build_longform_health(
        current_text="正文",
        character_names=[],
        voice_history=[],
        current_story_dna={},
        story_dna_history=[],
        story_state={},
        chapter_order=["001"],
        observed_entities=["林州"],
        canonical_aliases={"林舟": ["小舟"]},
        entity_matcher=StubMatcher(),
    )
    assert report["entity_alias_drift"][0]["canonical"] == "林舟"
    assert "实体别名" in report["guard_context"]
