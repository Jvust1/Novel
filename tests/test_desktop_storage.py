import io
import json
import zipfile
from unittest.mock import patch

import pytest

from novel_ai.storage import ProjectStore
from novel_ai.project_session import switch_project, plan_binding


def test_summary_order_and_budget(tmp_path):
    s=ProjectStore(tmp_path)
    for c in ('001','002','003'):
        s.save_extraction('p', {'chapter_id':c, 'summary':c})
    s.save_extraction('p', {'chapter_id':'001','summary':'new'})
    assert [x['chapter_id'] for x in s.all_chapter_summaries('p')] == ['001','002','003']
    assert s.all_chapter_summaries('p')[0]['summary']=='new'
    assert s.recent_chapter_summaries('p',0)==[]
    with pytest.raises(ValueError): s.recent_chapter_summaries('p',-1)


@pytest.mark.parametrize('path',['../secret.json','/tmp/x.json','C:/x.json','memory/../../x','memory\\x.json'])
def test_path_escape_rejected(tmp_path,path):
    with pytest.raises(ValueError): ProjectStore(tmp_path).write_json('p',path,{})


def test_atomic_failure_keeps_previous(tmp_path):
    s=ProjectStore(tmp_path); p=s.write_json('p','memory/state.json',{'n':1})
    with patch('novel_ai.storage.os.replace',side_effect=OSError('simulated')):
        with pytest.raises(OSError): s.write_json('p','memory/state.json',{'n':2})
    assert json.loads(p.read_text()) == {'n':1}


def test_chapter_revisions_and_identical_save(tmp_path):
    s=ProjectStore(tmp_path); s.write_chapter('p','001','first'); s.write_chapter('p','001','second')
    s.write_chapter('p','001','second')
    h=list((s.project_dir('p')/'chapters/history/001').glob('*.md'))
    assert len(h)==1 and h[0].read_text().strip()=='first'


def test_export_restore_new_only(tmp_path):
    s=ProjectStore(tmp_path); s.write_chapter('p','001','first'); s.write_json('p','memory/x.json',{'x':1})
    blob=s.export_project('p'); dest=s.restore_project(blob,'recovered')
    assert (dest/'chapters/001.md').read_text().strip()=='first'
    assert s.read_json('recovered','memory/x.json') == {'x':1}
    with pytest.raises(ValueError): s.restore_project(blob,'p')


@pytest.mark.parametrize('name',['../escape.json','memory/../../bad.json','C:/bad.json','chapters/CON.md','memory/x.json/../other.json'])
def test_restore_checks_all_before_writing(tmp_path,name):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z: z.writestr(name,'{}')
    s=ProjectStore(tmp_path)
    with pytest.raises(ValueError): s.restore_project(out.getvalue(),'bad')
    assert not (tmp_path/'projects/bad').exists()


def test_project_switch_separates_and_recovers_unsaved(tmp_path):
    s=ProjectStore(tmp_path); state={}
    switch_project(state,s,'a'); state['characters']=[{'name':'A'}]; state['premise']='unsaved'
    switch_project(state,s,'b'); assert state['characters']==[] and state['premise']==''
    state['characters']=[{'name':'B'}]
    switch_project(state,s,'a'); assert state['characters']==[{'name':'A'}] and state['premise']=='unsaved'


def test_binding_changes_on_story_input():
    x=plan_binding('p','001',{},[],'o','g')
    assert x != plan_binding('p','002',{},[],'o','g')
    assert x != plan_binding('p','001',{},[{'name':'a'}],'o','g')
