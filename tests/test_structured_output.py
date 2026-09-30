from novel_ai.models import ChapterPlan
from novel_ai.structured_output import FallbackStructuredExtractor, GuidanceStructuredExtractor, InstructorStructuredExtractor, OutlinesStructuredExtractor


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        model = kwargs["response_model"]
        return model(chapter_title="第七章", chapter_promise="兑现旧案线索")


class FakeClient:
    def __init__(self):
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions()


def test_instructor_structured_extractor_returns_validated_model():
    client = FakeClient()
    extractor = InstructorStructuredExtractor(client)
    result = extractor.extract(
        response_model=ChapterPlan,
        messages=[{"role": "user", "content": "规划章节"}],
        temperature=0.2,
    )
    assert result.chapter_title == "第七章"
    call = client.chat.completions.calls[0]
    assert call["response_model"] is ChapterPlan
    assert call["temperature"] == 0.2


def test_outlines_structured_extractor_accepts_json_string():
    class Model:
        def __call__(self, prompt, output_type, **kwargs):
            assert output_type is ChapterPlan
            assert "规划章节" in prompt
            return '{"chapter_title":"第八章","chapter_promise":"推进主线"}'

    extractor = OutlinesStructuredExtractor(Model())
    result = extractor.extract(
        response_model=ChapterPlan,
        messages=[{"role": "user", "content": "规划章节"}],
        temperature=0.3,
    )
    assert result.chapter_title == "第八章"



def test_guidance_structured_extractor_uses_pydantic_schema_and_captured_json():
    calls = []

    class Model:
        def __init__(self):
            self.values = {}

        def __iadd__(self, value):
            if isinstance(value, dict) and value.get("_fake_guidance_json"):
                self.values[value["name"]] = '{"chapter_title":"第九章","chapter_promise":"约束推进"}'
            return self

        def __getitem__(self, key):
            return self.values[key]

    def fake_json_factory(**kwargs):
        calls.append(kwargs)
        return {"_fake_guidance_json": True, **kwargs}

    extractor = GuidanceStructuredExtractor(Model(), json_factory=fake_json_factory)
    result = extractor.extract(
        response_model=ChapterPlan,
        messages=[{"role": "user", "content": "生成严格结构化章节计划"}],
        temperature=0.15,
    )
    assert result.chapter_title == "第九章"
    assert calls[0]["schema"] is ChapterPlan
    assert calls[0]["temperature"] == 0.15



def test_structured_fallback_chain_uses_next_backend_after_failure():
    class Broken:
        name = "broken"

        def extract(self, **_kwargs):
            raise RuntimeError("boom")

    class Working:
        name = "working"

        def extract(self, *, response_model, **_kwargs):
            return response_model(
                chapter_title="第十章",
                chapter_promise="备用后端接管",
            )

    extractor = FallbackStructuredExtractor([Broken(), Working()])
    result = extractor.extract(
        response_model=ChapterPlan,
        messages=[{"role": "user", "content": "计划"}],
        temperature=0.2,
    )
    assert result.chapter_title == "第十章"


def test_structured_fallback_chain_reports_all_failed_backend_names():
    class Broken:
        def __init__(self, name):
            self.name = name

        def extract(self, **_kwargs):
            raise ValueError("bad")

    extractor = FallbackStructuredExtractor([Broken("guidance"), Broken("outlines")])
    import pytest
    with pytest.raises(RuntimeError, match="guidance.*outlines"):
        extractor.extract(
            response_model=ChapterPlan,
            messages=[{"role": "user", "content": "计划"}],
            temperature=0.2,
        )
