"""Original synthetic history through the actual context/writer entry, no model calls."""
import json
import math
import pytest
from novel_ai.context import ContextAssembler
from novel_ai.engine import NovelEngine
from novel_ai.models import StoryBible
from novel_ai.recall import RecallHit
from novel_ai.recall_backends import LocalSemanticRecall
from novel_ai.semantic_history import select_semantic_history
from novel_ai.storage import ProjectStore


class Encoder:
    def __init__(self):
        self.bad=False
        self.calls=[]
    def encode(self,texts):
        self.calls.append(list(texts))
        if self.bad:return [[float('nan'),1.] for _ in texts]
        return [[float('蓝钥匙' in text),float('火车' in text),0.1] for text in texts]


def seed(store,project,chapters):
    for key,text in chapters:
        store.save_extraction(project,{'chapter_id':key,'chapter_title':key,'summary':text})


def test_actual_writer_five_stages_receive_bounded_semantic_history(tmp_path):
    store=ProjectStore(tmp_path)
    seed(store,'A',[('old-key','蓝钥匙仍藏在旧靴底。'),('old-train','火车第二日才进山。'),('recent','主人公在旧桥等人。')])
    store.save_story_state('A',{'facts':['蓝钥匙尚未交给任何人。'],'open_threads':[],'foreshadowing':[]})
    encoder=Encoder();backend=LocalSemanticRecall(encoder)
    context=ContextAssembler(store,'A',local_semantic_recall=backend,local_semantic_limit=1,recall_char_budget=180).assemble(recent_limit=1,recall_query='寻找蓝钥匙',history_chapter_ids=['old-key','old-train','recent'])
    assert 'old-key' in context.recall_block and '蓝钥匙仍藏在旧靴底' in context.recall_block
    assert 'old-train' not in context.recall_block and len(context.recall_block)<=180
    assert context.recall_report['mode']=='local-semantic'
    assert context.recall_report['included_chapter_ids']==['old-key']
    assert context.recent_summaries[0]['chapter_id']=='recent'
    assert '蓝钥匙尚未交给任何人' in context.canon_block
    class Provider:
        def __init__(self):self.calls=[]
        def chat(self,messages,**kwargs):
            self.calls.append(messages)
            turn=len(self.calls)
            if turn==1:return json.dumps({'chapter_title':'合成测试章','chapter_promise':'决定','tension_curve':'上升','scenes':[{'scene_no':1,'objective':'找钥匙','opposition':'赶不上车','choice':'留在桥头','cost':'错过出发','state_change':'等待证人'}],'must_not_happen':[]},ensure_ascii=False)
            if turn in (3,5):return json.dumps({'verdict':'revise','issues':[]})
            return '他没有去车站，仍在桥头等那个修鞋的人。'
    provider=Provider()
    result=NovelEngine(provider).run(bible=StoryBible(),outline='合成纲',chapter_goal='寻找蓝钥匙',characters=[],review=True,auto_repair=True,extra_context=context.prompt_sections())
    assert result.review_after_repair is not None and len(provider.calls)==5
    assert all('蓝钥匙仍藏在旧靴底' in '\n'.join(m['content'] for m in messages) for messages in provider.calls)
    assert store.load_story_state('A')['facts']==['蓝钥匙尚未交给任何人。']


def test_switch_project_replaces_corpus_and_removal_drops_stale_rows(tmp_path):
    store=ProjectStore(tmp_path);backend=LocalSemanticRecall(Encoder())
    seed(store,'A',[('same-id','蓝钥匙属于第一本书。')])
    seed(store,'B',[('same-id','火车属于第二本书。')])
    a=ContextAssembler(store,'A',local_semantic_recall=backend).assemble(recent_limit=0,recall_query='蓝钥匙',history_chapter_ids=['same-id'])
    b=ContextAssembler(store,'B',local_semantic_recall=backend).assemble(recent_limit=0,recall_query='火车',history_chapter_ids=['same-id'])
    assert a.recall_report['project_scope']!=b.recall_report['project_scope']
    assert '第一本书' not in b.recall_block and '第二本书' in b.recall_block
    assert len(backend.ids)==1
    store.write_json('B','memory/story_state.json',{'facts':[]})
    # A true empty current corpus clears this derived index, never reuses book A.
    selected,report=select_semantic_history(backend,'火车',[],project_scope=b.recall_report['project_scope'])
    assert selected==[] and report['candidate_count']==0 and backend.ids==[]


def test_failed_new_corpus_preserves_backend_but_does_not_return_stale_context(tmp_path):
    store=ProjectStore(tmp_path);encoder=Encoder();backend=LocalSemanticRecall(encoder)
    seed(store,'A',[('c','蓝钥匙原来在旧靴底。')])
    assembler=ContextAssembler(store,'A',local_semantic_recall=backend)
    before=assembler.assemble(recent_limit=0,recall_query='蓝钥匙',history_chapter_ids=['c'])
    old_texts=backend.texts
    store.save_extraction('A',{'chapter_id':'c','summary':'蓝钥匙现在交给了证人。'})
    encoder.bad=True
    with pytest.raises(ValueError):assembler.assemble(recent_limit=0,recall_query='蓝钥匙',history_chapter_ids=['c'])
    assert backend.texts==old_texts
    encoder.bad=False
    after=assembler.assemble(recent_limit=0,recall_query='蓝钥匙',history_chapter_ids=['c'])
    assert before.recall_report['corpus_fingerprint']!=after.recall_report['corpus_fingerprint']
    assert '交给了证人' in after.recall_block and '原来在旧靴底' not in after.recall_block


@pytest.mark.parametrize('kind',['unknown','text','metadata','score','duplicate'])
def test_context_refuses_unknown_or_stale_backend_sources(kind):
    class BadBackend(LocalSemanticRecall):
        def query(self,text,*,limit=5):
            hits=super().query(text,limit=limit)
            original=hits[0]
            if kind=='unknown':return [RecallHit('other',original.score,original.text,original.metadata)]
            if kind=='text':return [RecallHit(original.document_id,original.score,'stale',original.metadata)]
            if kind=='metadata':return [RecallHit(original.document_id,original.score,original.text,{**original.metadata,'project_scope':'other'})]
            if kind=='score':return [RecallHit(original.document_id,float('nan'),original.text,original.metadata)]
            return hits+hits
    with pytest.raises(ValueError):select_semantic_history(BadBackend(Encoder()),'蓝钥匙',[{'chapter_id':'c','summary':'蓝钥匙在旧靴底。'}],project_scope='A',limit=2)


def test_default_mmr_path_unchanged_and_budget_omission_visible(tmp_path):
    store=ProjectStore(tmp_path);seed(store,'A',[('c','蓝钥匙在旧靴底。')])
    default=ContextAssembler(store,'A').assemble(recent_limit=0,recall_query='蓝钥匙',history_chapter_ids=['c'])
    assert default.recall_report.get('mode')!='local-semantic'
    backend=LocalSemanticRecall(Encoder())
    small=ContextAssembler(store,'A',local_semantic_recall=backend,recall_char_budget=10).assemble(recent_limit=0,recall_query='蓝钥匙',history_chapter_ids=['c'])
    assert small.recall_block=='' and small.recall_report['included_chapter_ids']==[]
    assert small.recall_report['selected_sources'][0]['chapter_id']=='c'


def test_conflicting_duplicate_sources_fail_before_encoding():
    encoder=Encoder();backend=LocalSemanticRecall(encoder)
    with pytest.raises(ValueError,match='duplicate'):
        select_semantic_history(backend,'蓝钥匙',[{'chapter_id':'c','summary':'蓝钥匙在靴底。'},{'chapter_id':'c','summary':'蓝钥匙在门后。'}],project_scope='A')
    assert encoder.calls==[]


@pytest.mark.parametrize('options',[{'recall_char_budget':0},{'recall_summary_chars':0},{'recall_token_budget':0}])
def test_disabled_semantic_budget_does_not_encode_or_reuse_old_rows(tmp_path,options):
    store=ProjectStore(tmp_path);seed(store,'A',[('c','蓝钥匙在旧靴底。')])
    encoder=Encoder();backend=LocalSemanticRecall(encoder)
    context=ContextAssembler(store,'A',local_semantic_recall=backend,**options).assemble(recent_limit=0,recall_query='蓝钥匙',history_chapter_ids=['c'])
    assert encoder.calls==[] and backend.ids==[] and context.recall_block==''
    assert context.recall_report['indexed_candidate_count']==0
    assert context.recall_report['included_chapter_ids']==[]


def test_existing_pydantic_reuse_provenance_and_entry_links():
    import hashlib
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    record=json.loads((root/'third_party/pydantic-vector-validation/provenance.json').read_text())
    assert record['observed_stars']>=1000 and record['source_port'] is False
    assert record['source_commit']=='001dea020e0809844e5b17666432c9135a976f46'
    license_file=record['license_file']
    assert hashlib.sha256((root/license_file['local_path']).read_bytes()).hexdigest()==license_file['sha256']
    assert 'TypeAdapter(list[list[FiniteFloat]])' in (root/'novel_ai/semantic.py').read_text()
    assert 'RECALL_INTEGRITY.md' in (root/'docs/GPT_WRITING_ENTRY.md').read_text()
