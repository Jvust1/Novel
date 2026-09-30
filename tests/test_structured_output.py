from novel_ai.models import ChapterPlan
from novel_ai.structured_output import InstructorStructuredExtractor


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
