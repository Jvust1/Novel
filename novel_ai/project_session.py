"""Project-scoped UI state; switching books never carries characters across."""
import copy
import hashlib
import json

FIELDS = ('title','genre','tone','premise','themes_text','rules_text','locked_text','forbidden_text',
          'outline','characters','style','style_profiles','reference_hashes','last_result','last_overlap',
          'last_extraction','pending_plan_json','pending_plan_meta','plan_editor','plan_new',
          'chapter_id','chapter_goal','chapter_notes','result_binding','memory_candidate','manual_manuscript',
          'manual_chapter','manuscript_loaded')


def switch_project(state, store, project):
    if state.get('seeded_project') == project:
        return
    cache = state.setdefault('_project_drafts', {})
    previous = state.get('seeded_project')
    if previous:
        cache[previous] = {k: copy.deepcopy(state[k]) for k in FIELDS if k in state}
    for k in FIELDS:
        state.pop(k, None)
    if project in cache:
        state.update(copy.deepcopy(cache[project]))
    else:
        bible = store.read_json(project, 'memory/story_bible.json', {})
        state.update({k: bible.get(k, '') for k in ('genre','tone','premise')})
        state['title'] = bible.get('title') or project
        for k, field in [('themes_text','themes'),('rules_text','world_rules'),('locked_text','locked_facts'),('forbidden_text','forbidden_moves')]:
            value = bible.get(field, [])
            state[k] = '\n'.join(value) if isinstance(value, list) else str(value)
        state['outline'] = store.read_json(project, 'memory/outline.json', {}).get('outline', '')
        state['characters'] = store.read_json(project, 'memory/characters.json', [])
        state['style_profiles'] = store.read_json(project, 'styles/style_profiles.json', [])
        state['style'] = store.read_json(project, 'styles/style_dna.json')
        state['reference_hashes'] = set(store.read_json(project,'styles/reference_signature.json',{}).get('hashes',[]))
        state.update(last_result=None, last_overlap=0.0, last_extraction=None, pending_plan_json='',
                     pending_plan_meta={}, plan_new=False, memory_candidate=None)
    state['seeded_project'] = project


def plan_binding(project, chapter, bible, characters, outline, goal):
    value = [project, chapter, bible, characters, outline, goal]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()
