from pathlib import Path
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from desktop_runtime import wait_http

NAME='Novel'
TITLE='Novel · 长篇写作工作台'
DESCRIPTION='设定与人物 → 确认场景计划 → 写作与审校 → 作者批准记忆。支持手工稿件、历史版本与项目备份。'
BOUNDARY='模型需自行配置；不会下载模型或自动发送正文。关闭前请先保存编辑。'

class Service:
    def __init__(self,proc,url,stop,log):
        self.process=proc;self.url=url;self.health_url=url+'/_stcore/health';self.stop=stop;self.log=log
    def close(self):
        self.stop.write_text('stop',encoding='utf-8')
        try:self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.terminate();self.process.wait(timeout=10)
        self.log.close()


def serve(port,home,root,stop):
    os.environ['NOVEL_DATA_DIR']=str(home/'data')
    # A frozen install path is not site-packages; do not misdetect it as Streamlit development.
    os.environ['STREAMLIT_GLOBAL_DEVELOPMENT_MODE']='false'
    from streamlit.web import bootstrap
    from streamlit.runtime import Runtime
    def stop_watcher():
        while not stop.exists():time.sleep(.2)
        for _ in range(100):
            try:
                if Runtime.exists():Runtime.instance().stop();return
            except RuntimeError:pass
            time.sleep(.1)
    threading.Thread(target=stop_watcher,daemon=True).start()
    options={
        'global.developmentMode':False,
        'server.address':'127.0.0.1','server.port':port,'server.headless':True,
        'server.enableCORS':True,'server.enableXsrfProtection':True,'server.fileWatcherType':'none',
        'server.runOnSave':False,'server.maxUploadSize':100,
        'browser.gatherUsageStats':False,'browser.serverAddress':'127.0.0.1',
        'theme.font':'sans-serif',
    }
    bootstrap.load_config_options(options)
    bootstrap.run(str(root/'app.py'),False,[],options)


def start(home,root,intake=False):
    home=Path(home);home.mkdir(parents=True,exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    stop=home/('service-stop-'+uuid.uuid4().hex)
    if getattr(sys,'frozen',False):args=[sys.executable]
    else:args=[sys.executable,str(root/'desktop.py')]
    args+=['--novel-service',str(port),str(home),str(root),str(stop)]
    log=(home/'service.log').open('a',encoding='utf-8')
    proc=subprocess.Popen(args,stdout=log,stderr=log,stdin=subprocess.DEVNULL,
                          cwd=home,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    svc=Service(proc,f'http://127.0.0.1:{port}',stop,log)
    try:wait_http(svc.health_url,proc)
    except Exception as error:
        svc.close()
        detail=(home/'service.log').read_text(encoding='utf-8',errors='replace')[-6000:]
        raise RuntimeError('本机服务未就绪。启动日志：\n'+detail) from error
    return svc


def self_test(home,root):
    from novel_ai.storage import ProjectStore
    store=ProjectStore(home/'data');store.write_chapter('smoke','001','first')
    store.write_chapter('smoke','001','second')
    archive=store.export_project('smoke');store.restore_project(archive,'recovered')
    assert (store.project_dir('recovered')/'chapters/001.md').read_text().strip()=='second'
    svc=start(home,root)
    try:wait_http(svc.health_url,svc.process)
    finally:svc.close()
    assert svc.process.returncode==0
    return {'ok':True,'checks':['packaged Streamlit startup','127.0.0.1 health','atomic manuscript save','history retained','new-project restore','graceful service stop'],'model_calls':0}
