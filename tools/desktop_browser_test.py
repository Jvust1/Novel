"""Browser tests against the actual packaged EXE on a Windows runner, no real providers."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from playwright.sync_api import sync_playwright, expect

exe=Path(sys.argv[1]);out=Path(sys.argv[2]);name=os.environ['DESKTOP_APP'];checks=[];errors=[]

def record(name):checks.append(name)

def start(home,tag):
    ready=home/(tag+'-ready.json');stop=home/(tag+'-stop')
    proc=subprocess.Popen([str(exe),'--headless','--data-dir',str(home/'user'),
                           '--ready-file',str(ready),'--stop-file',str(stop)],cwd=home)
    end=time.monotonic()+100
    while not ready.exists():
        if proc.poll() is not None:raise RuntimeError('Packaged service exited before readiness')
        if time.monotonic()>end:proc.terminate();raise TimeoutError('Packaged service not ready')
        time.sleep(.2)
    return proc,stop,json.loads(ready.read_text())['url']

def stop_process(proc,stop):
    stop.write_text('stop');proc.wait(timeout=45);assert proc.returncode==0

with tempfile.TemporaryDirectory(prefix=name+'-browser-') as tmp, sync_playwright() as pw:
    home=Path(tmp);proc,stop,url=start(home,'first');browser=None
    try:
        try:
            browser=pw.chromium.launch(channel='msedge',headless=True);engine='Microsoft Edge'
        except Exception:
            browser=pw.chromium.launch(headless=True);engine='Chromium fallback'
        page=browser.new_page(viewport={'width':1400,'height':960})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('dialog',lambda dialog:dialog.accept())
        page.goto(url,wait_until='domcontentloaded')
        if name=='Invest':
            page.locator('#load-demo').click();expect(page.locator('#demo-notice')).to_be_visible(timeout=20000);record('demo_load')
            page.locator('#tab-backtest').click()
            page.locator('#backtest-form [name=cost_model_acknowledged]').check()
            page.locator('#backtest-form button[type=submit]').click()
            expect(page.locator('#backtest-results')).to_be_visible(timeout=20000);record('cost_acknowledged_backtest')
            page.locator('#tab-paper').click();page.locator('#account-name').fill('CI native demo')
            page.locator('#account-form button[type=submit]').click()
            expect(page.locator('#account-select')).not_to_have_value('');record('paper_account_save')
            with page.expect_download() as item:page.locator('#private-backup').click()
            item.value.save_as(home/'backup.zip');assert (home/'backup.zip').stat().st_size>100;record('private_backup_download')
            page.screenshot(path=str(out/'invest.png'),full_page=True)
        elif name=='mygpt':
            expect(page.locator('#message')).to_contain_text('本机工作台已就绪',timeout=20000);record('study_state_load')
            page.locator('#title').fill('Native smoke');page.locator('#source').fill('定义：两个相同的 x 相加，得到 2x。')
            page.locator('#mode').select_option('review');page.locator('#prepare').click()
            expect(page.locator('#prompt')).to_contain_text('USER_SUPPLIED_UNVERIFIED');record('source_bound_prompt')
            page.locator('#note').fill('Explicitly saved native smoke note');page.locator('#save-note').click()
            expect(page.locator('#message')).to_contain_text('已保存');record('native_notes_save')
            page.locator('#minutes').fill('1');page.locator('#reset').click();page.locator('#start').click();page.wait_for_timeout(1500);page.locator('#pause').click()
            assert page.locator('#timer').inner_text() not in ('01:00','25:00');record('focus_timer_pause')
            assert page.locator('#teach').is_disabled();record('local_model_default_off')
            page.screenshot(path=str(out/'mygpt.png'),full_page=True)
        else:
            expect(page.get_by_role('heading',name='Novel · AI 网络小说写作助手')).to_be_visible(timeout=50000)
            assert page.locator('[data-testid=stException]').count()==0;record('packaged_streamlit_render')
            page.get_by_label('书名',exact=True).fill('Native smoke novel')
            page.get_by_role('button',name='保存故事设定到本地',exact=True).click()
            expect(page.get_by_text('已原子保存到本地项目目录。',exact=True)).to_be_visible();record('story_save')
            page.get_by_role('tab',name='🗂️ 稿件与备份').click()
            page.get_by_label('手工编辑正文',exact=True).fill('这是本机Windows测试稿件，不是用户的私人作品。')
            page.get_by_role('button',name='保存稿件并保留上一版',exact=True).click()
            expect(page.get_by_text('已保存：001.md',exact=False)).to_be_visible();record('manual_manuscript_save')
            page.get_by_role('button',name='生成完整项目备份',exact=True).click()
            with page.expect_download() as item:page.get_by_role('button',name='下载项目 ZIP 备份',exact=True).click()
            item.value.save_as(home/'novel-backup.zip');record('project_backup_download')
            page.get_by_label('当前项目',exact=True).fill('DifferentBook');page.get_by_label('当前项目',exact=True).press('Enter')
            page.get_by_role('tab',name='📚 故事与大纲').click()
            expect(page.get_by_label('书名',exact=True)).to_have_value('DifferentBook');record('project_isolation')
            page.screenshot(path=str(out/'novel.png'),full_page=True)
        page.close();stop_process(proc,stop);record('graceful_exit')
        proc,stop,url=start(home,'second')
        page=browser.new_page();page.goto(url,wait_until='domcontentloaded')
        if name=='Invest':
            page.locator('#tab-paper').click()
            expect(page.locator('#account-select')).to_contain_text('CI native demo',timeout=20000)
        elif name=='mygpt':
            expect(page.locator('#notes')).to_contain_text('Native smoke',timeout=20000)
        else:
            expect(page.get_by_label('书名',exact=True)).to_have_value('Native smoke novel',timeout=50000)
            assert page.locator('[data-testid=stException]').count()==0
        record('native_restart_persistence')
        assert not errors,errors
        record('no_browser_javascript_errors')
        (out/'browser.json').write_text(json.dumps({'ok':True,'os':sys.platform,'browser':engine,'packaged_exe':exe.name,'checks':checks,'javascript_errors':errors,'real_provider_calls':0},ensure_ascii=False,indent=2),encoding='utf-8')
    except BaseException:
        if browser:
            try:page.screenshot(path=str(out/'failure.png'),full_page=True)
            except Exception:pass
        # Only test fixture data is copied; no real user workspace was opened.
        for p in (home/'user').glob('*.log'):
            (out/p.name).write_bytes(p.read_bytes())
        raise
    finally:
        if browser:browser.close()
        if proc.poll() is None:stop_process(proc,stop)
