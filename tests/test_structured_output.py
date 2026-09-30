from novel_ai.models import ChapterPlan
from novel_ai.structured_output import InstructorStructuredExtractor, OutlinesStructuredExtractor


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
