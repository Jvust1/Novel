"""Project-scoped UI state; switching books never carries characters across.

Reused from Novel PR #16 @ 2b5e23fe3ba238ae6046dad125dd7d09847db13d.
Adapted fields for current core/MMR; load the target before changing live state.
Unused desktop workflow binding omitted. Provider credentials are not cached.
"""
import copy
import json

from .author_workflow import load_character_source, load_story_bible_source
from .style_commit import load_style_bundle

_CHARACTER_FORM_FIELDS = (
    'new_char_name', 'new_char_identity', 'new_char_desire', 'new_char_goal',
    'new_char_fear', 'new_char_secret', 'new_char_speech', 'new_char_knows',
    'new_char_unknown',
)

_RELEASE_DEFAULTS = {
    'release_stage': 'opening_3', 'release_chapter_order': '',
    'release_title': '', 'release_platform': '番茄小说', 'release_genre': '',
    'release_audience': '', 'release_hook': '', 'release_cadence': '',
    'release_tags': '', 'release_blurb': '', 'release_long_blurb': '',
    'release_checks': '原创性与参考重合人工复核\n人物与时间线连续性人工复核\n当前平台内容规则与格式人工核查',
    'release_scores_text': '',
}
AUTHOR_FIELDS = (
    'hierarchy_markdown', 'hierarchy_editor', 'hierarchy_data', 'hierarchy_selected',
    'hierarchy_previous_node', 'hierarchy_target_id',
    'last_result_meta', 'allow_chapter_overwrite', 'overwrite_chapter_binding', *_RELEASE_DEFAULTS,
)

FIELDS = (
    'title', 'genre', 'tone', 'premise', 'themes_text', 'rules_text', 'locked_text',
    'forbidden_text', 'outline', 'characters', 'characters_source_sha256', 'story_bible_source_sha256', 'style', 'style_profiles',
    'reference_hashes', 'last_result', 'last_overlap', 'last_extraction',
    'style_snapshot', 'style_pending',
    'pending_plan_json', 'pending_plan_meta', 'plan_editor', 'plan_new',
    'chapter_id', 'chapter_goal', 'chapter_notes', 'last_self_similarity',
    'diverse_recall', 'memory_candidate_json', 'last_memory_commit', 'memory_source_bible', 'memory_ui_readback_pending',
    *_CHARACTER_FORM_FIELDS, *AUTHOR_FIELDS,
)


def preserve_project_fields(state):
    """Retain existing project edits when a later gate hides their widgets.

    Assigning under the public user key keeps values through Streamlit's
    stale-widget cleanup. No extra draft cache, file write or acceptance.
    Call before rendering project widgets, including on repeated blocked runs.
    """
    for key in FIELDS:
        if key in state:
            state[key] = state[key]


def _load_project(store, project):
    bible_source = load_story_bible_source(store, project)
    bible = bible_source['bible']
    loaded = {key: bible.get(key, '') for key in ('genre', 'tone', 'premise')}
    loaded['story_bible_source_sha256'] = bible_source['sha256']
    loaded['memory_source_bible'] = copy.deepcopy(bible)
    loaded['title'] = bible.get('title') or project
    for key, field in (
        ('themes_text', 'themes'), ('rules_text', 'world_rules'),
        ('locked_text', 'locked_facts'), ('forbidden_text', 'forbidden_moves'),
    ):
        value = bible.get(field, [])
        loaded[key] = '\n'.join(value) if isinstance(value, list) else str(value)
    loaded['outline'] = store.read_json(project, 'memory/outline.json', {}).get('outline', '')
    character_source = load_character_source(store, project)
    loaded['characters'] = character_source['cards']
    loaded['characters_source_sha256'] = character_source['sha256']
    loaded.update(_style_fields(load_style_bundle(store, project)))
    loaded['style_pending'] = None
    loaded.update(last_result=None, last_overlap=0.0, last_extraction=None,
                  pending_plan_json='', pending_plan_meta={}, plan_new=False,
                  last_self_similarity=[], diverse_recall=False,
                  memory_candidate_json=None, last_memory_commit=None, memory_ui_readback_pending=None)
    hierarchy = store.read_json(project, 'memory/hierarchical_outline.json')
    loaded.update(hierarchy_markdown='', hierarchy_editor=json.dumps(hierarchy, ensure_ascii=False, indent=2) if hierarchy else '',
                  hierarchy_data=hierarchy, last_result_meta={}, allow_chapter_overwrite=False)
    release = store.read_json(project, 'memory/release_workspace.json', {})
    if not isinstance(release, dict):
        raise ValueError("发布工作区必须是 JSON 对象；原文件未改动。")
    for key in _RELEASE_DEFAULTS:
        if key in release and not isinstance(release[key], str):
            raise ValueError(f"发布工作区 {key} 必须是文本；原文件未改动。")
    if release.get('release_stage', 'opening_3') not in ('opening_3', 'retention_20'):
        raise ValueError("发布工作区审阅阶段无效；原文件未改动。")
    loaded.update({key: release.get(key, default) for key, default in _RELEASE_DEFAULTS.items()})
    if not loaded['release_title']:
        loaded['release_title'] = loaded['title']
    if not loaded['release_genre']:
        loaded['release_genre'] = loaded['genre']
    loaded.update({key: '' for key in _CHARACTER_FORM_FIELDS})
    return loaded


def _style_fields(snapshot):
    return {'style_profiles': copy.deepcopy(snapshot['profiles']),
            'style': copy.deepcopy(snapshot['style']),
            'reference_hashes': set(snapshot['signature']['hashes']),
            'style_snapshot': copy.deepcopy(snapshot)}


def switch_project(state, store, project):
    restore_needed = state.get('_project_restore_needed', False)
    if state.get('seeded_project') == project and not restore_needed:
        return
    cache = state.setdefault('_project_drafts', {})
    previous = state.get('seeded_project')
    if previous is not None and not restore_needed:
        cache[previous] = {key: copy.deepcopy(state[key]) for key in FIELDS if key in state}
    # Streamlit may clean up widget keys after a failed run. Keep a complete
    # cached draft first, without replacing it with partial state on retry.
    try:
        if project in cache:
            loaded = copy.deepcopy(cache[project])
            loaded.update(_style_fields(load_style_bundle(store, project)))
        else:
            loaded = _load_project(store, project)
    except Exception:
        state['_project_restore_needed'] = True
        raise
    for key in FIELDS:
        state.pop(key, None)
    state.update(loaded)
    state['_project_drafts'] = cache
    state['seeded_project'] = project
    state['_project_restore_needed'] = False
