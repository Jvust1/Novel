from pathlib import Path
import asyncio
import os
import socket
import subprocess
import sys
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


async def serve_until_stopped(server,stop):
    await server.start()
    try:
        while not stop.exists():await asyncio.sleep(.1)
    finally:
        # Stop the HTTP server as well as the runtime; Runtime.stop alone leaves
        # the Starlette/Uvicorn listener alive in current Streamlit releases.
        server.stop()
        await server.stopped


def serve(port,home,root,stop):
    os.environ['NOVEL_DATA_DIR']=str(home/'data')
    os.environ['STREAMLIT_GLOBAL_DEVELOPMENT_MODE']='false'
    from streamlit.web import bootstrap
    from streamlit.web.server import Server
    options={
        'global.developmentMode':False,
        'server.address':'127.0.0.1','server.port':port,'server.headless':True,
        'server.enableCORS':True,'server.enableXsrfProtection':True,'server.fileWatcherType':'none',
        'server.runOnSave':False,'server.maxUploadSize':100,
        'browser.gatherUsageStats':False,'browser.serverAddress':'127.0.0.1',
        'theme.font':'sans-serif',
    }
    bootstrap.load_config_options(options)
    script=str(root/'app.py')
    sys.path.insert(0,str(root));sys.argv=[script]
    bootstrap.prepare_streamlit_environment(script)
    asyncio.run(serve_until_stopped(Server(script,False),stop))


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
    assert svc.process.returncode==0,(home/'service.log').read_text(encoding='utf-8',errors='replace')[-6000:]
    return {'ok':True,'checks':['packaged Streamlit startup','127.0.0.1 health','atomic manuscript save','history retained','new-project restore','graceful service stop'],'model_calls':0}
