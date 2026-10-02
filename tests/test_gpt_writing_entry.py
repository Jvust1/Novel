"""Executable content contracts, not proof of prompt obedience or story quality."""
import hashlib
import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'writing_demos/plugin-first-chapter-20261001'
PROMPTS = ROOT / 'docs/prompts/natural-fiction'


def test_original_plugin_chapter_and_acceptance_stay_unchanged():
    raw = (DEMO / 'chapter-001.md').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == 'b6d9e0d26c21658e1be0c9ab30117ca0ce53f7067c941fef8bad969d014c432e'
    state = json.loads((DEMO / 'story_state.json').read_text())
    assert state['revision'] == 0
    assert state['confirmed_canon'] == {'facts': [], 'accepted_chapters': [], 'memory_updates': []}
    for key in ('plan_acceptance', 'chapter_acceptance', 'memory_acceptance'):
        assert state['progress'][key] is None
    for key in ('plan_source', 'draft_source', 'review_source'):
        ref = state['progress'][key]
        assert hashlib.sha256((DEMO / ref['location']).read_bytes()).hexdigest() == ref['sha256']


def test_style_comparison_changes_only_declared_original_slices():
    data = json.loads((DEMO / 'style_revision_examples.json').read_text())
    original = (DEMO / data['source_path']).read_text()
    candidate = (DEMO / data['candidate_path']).read_text()
    assert hashlib.sha256(original.encode()).hexdigest() == data['source_sha256']
    assert hashlib.sha256(candidate.encode()).hexdigest() == data['candidate_sha256']
    rebuilt = original
    for row in data['patches']:
        assert original.count(row['before']) == 1
        assert row['author_accepted'] is None
        for fact in row['protected']:
            assert fact in row['before'] and fact in row['after']
        rebuilt = rebuilt.replace(row['before'], row['after'], 1)
    assert rebuilt == candidate
    assert len(data['patches']) == 3
    assert data['canonical_advanced'] is False
    assert data['human_quality_comparison'] is None


def test_demo_profile_is_explicit_original_genre_candidate():
    data = json.loads((DEMO / 'style_profile.demo.json').read_text())
    assert data['primary_genre'] == '悬疑/推理'
    assert data['reference_books_supplied'] is False
    assert 'not_user_preference' in data['status']
    assert {'陶青', '吕阿棉', '老邓', '韩平', '孟川'} == set(data['voices'])


def test_selected_source_licenses_match_exact_git_blob_pins():
    lock = json.loads((PROMPTS / 'source-lock.json').read_text())
    assert {row['repository'] for row in lock['reused']} == {'blader/humanizer', 'op7418/Humanizer-zh'}
    for row in lock['reused']:
        assert re.fullmatch('[0-9a-f]{40}', row['commit'])
        assert row['stars_observed'] >= 10000
        assert row['license']['spdx'] == 'MIT'
        raw = (ROOT / row['license']['preserved_at']).read_bytes()
        digest = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        assert digest == row['license']['git_blob_sha']
        assert b'Permission is hereby granted' in raw
    rejected = {row['repository']: row for row in lock['evaluated_not_reused']}
    assert rejected['0xtresser/cn-humanizer']['api_license_spdx'] is None
    assert rejected['0xtresser/cn-humanizer']['reuse_status'] == 'Not copied or adapted'


def test_nine_genre_profiles_and_three_stage_contract_are_present():
    genres = (PROMPTS / 'GENRE_PROFILES.md').read_text()
    for name in ['都市 / 日常', '言情 / 关系向', '悬疑 / 推理', '玄幻 / 仙侠', '奇幻', '科幻', '历史 / 架空历史', '武侠', '恐怖 / 惊悚']:
        assert name in genres
    assert len(re.findall(r'^## [1-9]\. ', genres, re.M)) == 9
    assert '主类型' in genres and '辅类型' in genres
    assert '不穷尽子类型' in genres
    assert len(re.findall('原创微例：', genres)) == 9
    before = (PROMPTS / '01-writing-before.md').read_text()
    repair = (PROMPTS / '03-local-repair.md').read_text()
    assert '未提供时不得声称已学得作者文风' in before
    for constraint in ['知识边界', '伏笔', '不确定性', '不全章同义词替换', '未改段落保持原样']:
        assert constraint in repair


@pytest.mark.parametrize('relative', [
    'README.md', 'docs/GPT_WRITING_ENTRY.md',
    'docs/prompts/natural-fiction/README.md', 'docs/prompts/natural-fiction/SOURCES.md',
    'docs/prompts/natural-fiction/01-writing-before.md', 'docs/prompts/natural-fiction/02-editorial-review.md',
    'docs/prompts/natural-fiction/03-local-repair.md',
    'writing_demos/plugin-first-chapter-20261001/style_revision_examples.md',
])
def test_entry_and_prompt_relative_markdown_links_resolve(relative):
    path = ROOT / relative
    text = path.read_text()
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
        if target.startswith(('https://', 'http://', '#', 'mailto:')):
            continue
        assert (path.parent / target.split('#')[0]).resolve().exists(), (relative, target)


def test_blank_template_does_not_fabricate_author_acceptance():
    template = json.loads((ROOT / 'writing_templates/story_state.template.json').read_text())
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('plan_acceptance', 'chapter_acceptance', 'memory_acceptance'):
                    assert item is None
                if key in ('accepted_chapters', 'pending_memory_updates'):
                    assert item == []
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(template)
    assert template['revision'] == 0


def test_vendored_transitions_core_exact_source_identity_and_real_machine():
    from novel_ai._vendor.transitions import Machine, MachineError
    record = json.loads((ROOT / 'third_party/transitions/provenance.json').read_text())
    assert record['observed_stars'] >= 1000
    assert record['license'] == 'MIT'
    for row in record['files']:
        data = (ROOT / row['local_path']).read_bytes()
        assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == row['git_blob_sha']
    machine = Machine(states=['plan', 'draft'], transitions=[['approve', 'plan', 'draft']], initial='plan', auto_transitions=False)
    machine.approve()
    assert machine.state == 'draft'
    with pytest.raises(MachineError):
        machine.approve()


def test_reader_reveal_template_is_blank_and_source_licensed():
    template = json.loads((ROOT / 'writing_templates/reader_reveal_ledger.template.json').read_text())
    assert template['visibility'] == 'private'
    assert template['entries'] == template['pending_updates'] == []
    assert template['entry_template']['status'] == 'candidate'
    assert template['entry_template']['reader_known'] == []
    for key in ('term_id', 'term', 'full_truth', 'accepted_draft_reference', 'memory_confirmation_reference'):
        assert template['entry_template'][key] is None
    record = json.loads((ROOT / 'third_party/chinese-novelist-skill/provenance.json').read_text())
    assert record['stars_observed'] >= 1000
    data = (ROOT / record['license']['preserved_at']).read_bytes()
    assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == record['license']['git_blob_sha']
    assert hashlib.sha256(data).hexdigest() == record['license']['sha256']
    for stage in ('01-writing-before.md', '02-editorial-review.md', '03-local-repair.md'):
        assert 'READER_REVEAL_LEDGER.md' in (PROMPTS / stage).read_text()


def test_style_revision_preserves_only_if_scope_and_texture():
    data = json.loads((DEMO / 'style_revision_examples.json').read_text())
    row = next(row for row in data['patches'] if row['patch_id'] == 'STYLE-01')
    for exact in ('只有绕到卸货坡道，才能斜着看到外侧一截', '粗糙的墙'):
        assert exact in row['before'] and exact in row['after']


def test_published_demo_restore_references_all_resolve_with_matching_bytes():
    state = json.loads((DEMO / 'story_state.json').read_text())
    context_ref = state['candidate_context_source']
    context_path = DEMO / context_ref['location']
    assert context_path.is_file()
    assert hashlib.sha256(context_path.read_bytes()).hexdigest() == context_ref['sha256']
    context = json.loads(context_path.read_text())
    assert context['scene_plan_file'] == 'scene_plan.json'
    assert (DEMO / context['scene_plan_file']).is_file()
    for key in ('plan_source', 'draft_source', 'review_source'):
        ref = state['progress'][key]
        target = DEMO / ref['location']
        assert target.is_file()
        assert hashlib.sha256(target.read_bytes()).hexdigest() == ref['sha256']
