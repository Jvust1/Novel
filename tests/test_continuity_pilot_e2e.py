"""Combined MMR + speaker-span pilot through accepted synthetic memory.

Provider behavior is scripted; this tests information plumbing, not LLM quality.
"""
from __future__ import annotations

import json

import pytest

from novel_ai.context import ContextAssembler
from novel_ai.dialogue_attribution import ATTRIBUTION_VERSION
from novel_ai.engine import NovelEngine
from novel_ai.longform_consistency import character_voice_dna
from novel_ai.memory import apply_extraction
from novel_ai.models import Character, StoryBible
from novel_ai.orchestration import ProviderRouter, ProviderTarget, RouterConfig
from novel_ai.provider import ProviderConfig
from novel_ai.routed_engine import RoutedNovelEngine
from novel_ai.storage import ProjectStore


DRAFT = ('林舟明问：“你怎么还在这里等着，仓库已经封门了？”\n'
         '林舟明问：“你昨天去找守门人时，难道没有看见旧印章吗？”\n'
         '沈青把账本塞回衣袋。')
REVISED = DRAFT.replace('沈青把账本塞回衣袋。', '沈青收好钥匙，向林澄借账本核对。')


class ContinuityPilotProvider:
    def __init__(self, role, calls):
        self.role, self.calls = role, calls

    def chat(self, messages, **kwargs):
        system, prompt = messages[0]['content'], messages[-1]['content']
        if '连续性记录员' in system:
            stage = 'extract'
            assert REVISED in prompt
            response = {
                'chapter_id': '007', 'chapter_title': '核账',
                'summary': '沈青向林澄借账本核对，仓库钥匙仍由沈青保管。',
                'character_updates': [{'name': '沈青', 'knowledge_gained': ['账本由林澄保管']}],
                'timeline_events': [{'description': '向林澄借账本', 'time_hint': '第七天'}],
            }
        elif '章节策划' in system:
            stage = 'plan'
            response = {'chapter_title': '核账', 'scenes': [{
                'scene_no': 1, 'pov': '林舟明', 'objective': '核对账本',
                'opposition': '封门后取证受阻', 'choice': '向林澄借账本',
                'cost': '交出抵押物', 'state_change': '获得临时查阅权',
            }]}
        elif '严苛的网络小说章节编辑' in system:
            stage = 'review'
            assert '仓库钥匙一直由沈青保管' in prompt
            assert '账本已经交给林澄' in prompt
            chapter = prompt.split('【正文】', 1)[1]
            wrong = '沈青把账本塞回衣袋。' in chapter
            response = {'verdict': 'revise' if wrong else 'pass', 'issues': [{
                'category': '账本归属连续性', 'severity': 'high',
                'excerpt': '沈青把账本塞回衣袋。',
                'reason': '历史摘要明确账本已经交给林澄。',
                'suggestion': '保留人物声线，仅把动作改成向林澄借阅。',
            }] if wrong else []}
        elif '局部修订编辑' in system:
            stage = 'repair'
            assert '账本已经交给林澄' in prompt
            assert '账本归属连续性' in prompt
            response = REVISED
        else:
            stage, response = 'draft', DRAFT
        self.calls.append((self.role, stage, prompt))
        return response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)


@pytest.mark.parametrize('routed', [False, True])
def test_recalled_facts_and_correct_speaker_survive_review_repair_and_memory(tmp_path, routed):
    store = ProjectStore(tmp_path)
    summaries = ['仓库钥匙一直由沈青保管。', '账本已经交给林澄。',
                 '村民正在修路。', '雨停后渔船返航。', '集市换了摊位。', '灯会在夜里结束。']
    for i, summary in enumerate(summaries, 1):
        store.save_extraction('P', {'chapter_id': f'{i:03}', 'summary': summary})
    store.save_story_state('P', {'facts': ['林舟不知道仓库密码'], 'timeline': [], 'foreshadowing': [], 'open_threads': []})
    context = ContextAssembler(store, 'P').assemble(recall_query='沈青的仓库钥匙与林澄的账本')
    assert set(context.recall_report['included_chapter_ids']) == {'001', '002'}
    characters = [Character(name='林舟', does_not_know=['仓库密码']), Character(name='林舟明'),
                  Character(name='沈青'), Character(name='林澄')]
    # A short-name baseline must never be compared with a longer-name speaker.
    history = [{'voice_dna': {'林舟': {
        'attribution_version': ATTRIBUTION_VERSION, 'line_count': 12,
        'avg_line_chars': 3, 'question_ratio': 0, 'short_line_ratio': 1,
        'exclamation_ratio': 1, 'ellipsis_ratio': 1,
    }}}]
    calls = []
    writer = ContinuityPilotProvider('writer', calls)
    if routed:
        router = ProviderRouter(RouterConfig(local=ProviderConfig('http://unused', 'unused')))
        router._targets['local'] = ProviderTarget(name='local', provider=writer)
        router._targets['reviewer'] = ProviderTarget(name='reviewer', provider=ContinuityPilotProvider('reviewer', calls))
        engine = RoutedNovelEngine(router)
    else:
        engine = NovelEngine(writer)
    result = engine.run(bible=StoryBible(), outline='重新核对账本', chapter_goal='问明钥匙与账本去向',
                        characters=characters, extra_context=context.prompt_sections(),
                        recent_summaries=context.recent_summaries, historical_voice_dna=history,
                        review=True, auto_repair=True)
    assert [stage for _, stage, _ in calls] == ['plan', 'draft', 'review', 'repair', 'review']
    assert result.final_text == REVISED
    assert set(result.voice_dna_report['current']) == {'林舟明'}
    assert set(result.voice_dna_report['revised']) == {'林舟明'}
    assert result.voice_dna_report['alerts'] == []
    assert result.voice_dna_report['revised_alerts'] == []
    assert not any(i.category == '账本归属连续性' for i in result.review_after_repair.issues)
    assert '林舟不知道仓库密码' in calls[-1][2]

    # Simulate author acceptance only on this original synthetic test fixture.
    accepted_memory = NovelEngine(writer).extract_memory(StoryBible(), characters, '007', result.final_text)
    updated, state = apply_extraction(characters, store.load_story_state('P'), accepted_memory)
    again_characters, again_state = apply_extraction(updated, state, accepted_memory)
    assert again_characters == updated and again_state == state
    assert updated[0].does_not_know == ['仓库密码']
    assert updated[2].knows == ['账本由林澄保管']
    store.write_chapter('P', '007', result.final_text)
    store.write_json('P', 'memory/characters.json', [character.model_dump() for character in updated])
    store.save_story_state('P', state)
    store.save_extraction('P', accepted_memory.model_dump())
    store.save_voice_dna('P', '007', character_voice_dna(result.final_text, [c.name for c in updated]))
    persisted = store.load_voice_dna_history('P')[0]['voice_dna']
    assert set(persisted) == {'林舟明'}
    assert persisted['林舟明']['attribution_version'] == ATTRIBUTION_VERSION
    assert '仓库已经封门了' not in json.dumps(persisted, ensure_ascii=False)
    fresh_store = ProjectStore(tmp_path)
    restored = [Character.model_validate(row) for row in fresh_store.read_json('P', 'memory/characters.json')]
    assert restored == updated
    assert restored[0].does_not_know == ['仓库密码']
    assert restored[2].knows == ['账本由林澄保管']
    next_context = ContextAssembler(store, 'P').assemble(recent_limit=0, recall_query='沈青向林澄借账本核对')
    assert '007' in next_context.recall_report['included_chapter_ids']
    assert '沈青向林澄借账本核对' in next_context.recall_block
