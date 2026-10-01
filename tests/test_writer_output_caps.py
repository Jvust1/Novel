"""Stage allowances reach actual engine calls; synthetic provider only."""
import json
import pytest
from novel_ai.engine import NovelEngine
from novel_ai.models import StoryBible, ChapterPlan, ChapterReview, StyleFingerprint
from novel_ai.output_policy import OutputPolicy


class Provider:
    def __init__(self): self.calls=[]; self.output='正文完整。'
    def chat(self, messages, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get('response_format'):
            system=messages[0]['content']
            if '连续性记录员' in system:return '{"summary":"本章记忆","chapter_id":"c"}'
            return '{}'
        return self.output


def test_every_stage_has_its_explicit_cap():
    p=Provider(); policy=OutputPolicy(plan_tokens=101,draft_tokens=102,review_tokens=103,repair_tokens=104,style_tokens=105,memory_tokens=106)
    e=NovelEngine(p,output_policy=policy);b=StoryBible();plan=ChapterPlan()
    e.plan(b,'纲','目标',[]);e.draft(b,plan,[],target_chars=9000)
    e.review(b,plan,[],'正文');e.repair('正文',ChapterReview())
    e.enrich_style('参考',StyleFingerprint());e.extract_memory(b,[],'c','正文')
    assert [x['max_tokens'] for x in p.calls]==[101,102,103,104,105,106]


@pytest.mark.parametrize('stage',['draft','repair'])
@pytest.mark.parametrize('output',['', ' \n', None, [], 'x'*81, '\ud800'])
def test_custom_provider_cannot_bypass_engine_output_validation(stage,output):
    p=Provider();p.output=output;e=NovelEngine(p,output_policy=OutputPolicy(max_output_bytes=80))
    with pytest.raises(ValueError):
        if stage=='draft':e.draft(StoryBible(),ChapterPlan(),[])
        else:e.repair('原稿',ChapterReview())


def test_structured_backend_receives_cap_and_cannot_return_unvalidated_model():
    calls=[]
    class Extractor:
        def extract(self,**kwargs):
            calls.append(kwargs)
            return ChapterReview.model_construct(verdict='invented',issues=[])
    e=NovelEngine(Provider(),structured_extractor=Extractor(),output_policy=OutputPolicy(review_tokens=123,max_output_bytes=1000))
    with pytest.raises(ValueError):e.review(StoryBible(),ChapterPlan(),[],'正文')
    assert calls[0]['max_tokens']==123 and calls[0]['max_output_bytes']==1000


def test_structured_backend_cannot_return_oversized_object():
    class Extractor:
        def extract(self,**kwargs):return {'chapter_title':'长'*100}
    e=NovelEngine(Provider(),structured_extractor=Extractor(),output_policy=OutputPolicy(max_output_bytes=50))
    with pytest.raises(ValueError):e.plan(StoryBible(),'纲','目标',[])


@pytest.mark.parametrize('bad',[True,0,-1,2.5])
def test_bad_length_goal_never_reaches_provider(bad):
    p=Provider();e=NovelEngine(p)
    with pytest.raises(ValueError):e.draft(StoryBible(),ChapterPlan(),[],target_chars=bad)
    assert p.calls==[]


def test_runtime_reuse_has_exact_source_license_and_entry_trace():
    import hashlib
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    p=root/'third_party/httpx-output-boundary/provenance.json';data=json.loads(p.read_text())
    assert data['observed_stars']>=1000 and data['source_port'] is False
    assert data['source_commit']=='26d48e0634e6ee9cdc0533996db289ce4b430177'
    assert hashlib.sha256((root/data['license_file']['path']).read_bytes()).hexdigest()==data['license_file']['sha256']
    provider=(root/'novel_ai/provider.py').read_text()
    assert 'client.stream(' in provider and 'response.iter_bytes(' in provider
    assert 'FINAL_OUTPUT_GATES.md' in (root/'docs/GPT_WRITING_ENTRY.md').read_text()
    assert data['comparison_not_adopted']['upstream']=='langchain-ai/langchain'


def test_post_plan_entry_validates_overridden_draft_and_review():
    class CustomEngine(NovelEngine):
        def draft(self,*a,**kw):return 'x'*101
    e=CustomEngine(Provider(),output_policy=OutputPolicy(max_output_bytes=100))
    with pytest.raises(ValueError):e.run_from_plan(bible=StoryBible(),plan=ChapterPlan(),characters=[],review=False)
    class MissingReview(NovelEngine):
        def review(self,*a,**kw):return None
    with pytest.raises(TypeError):NovelEngine(Provider()).run_from_plan(bible=StoryBible(),plan=ChapterPlan(),characters=[],reviewer=MissingReview(Provider()))


def test_configured_hook_response_cannot_escape_output_byte_allowance():
    from novel_ai.engine import apply_external_review_hooks
    class Hook:
        def review_payload(self,**kwargs):return {'issues':[], 'unused':'x'*101}
    with pytest.raises(ValueError):apply_external_review_hooks(ChapterReview(),[Hook()],draft='正文',plan=ChapterPlan(),bible=StoryBible(),characters=[],max_output_bytes=100)
