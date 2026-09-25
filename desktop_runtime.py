"""Small local-only desktop controller. No installer, elevation, model or broker calls."""
from __future__ import annotations
import argparse
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from urllib.request import build_opener, ProxyHandler

VERSION = '2026.09.25-rc1'


def resource_root() -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


def private_directory(name: str) -> Path:
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share')))
    result = base / (name + 'Desktop')
    result.mkdir(parents=True, exist_ok=True)
    return result


class InstanceLock:
    def __init__(self, root: Path):
        self.stream = (root / '.desktop.lock').open('a+b')
        try:
            if self.stream.seek(0,2)==0:
                self.stream.write(b'0');self.stream.flush()
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise RuntimeError('同一数据目录已有运行实例。请在现有控制窗口打开应用，不要重复启动。') from None
    def close(self):
        self.stream.close()


def wait_http(url: str, process=None, seconds=75):
    opener = build_opener(ProxyHandler({}))
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if process is not None and process.poll() is not None:
            raise RuntimeError('应用服务提前退出；请查看 desktop.log。')
        try:
            with opener.open(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, TimeoutError):
            time.sleep(.2)
    raise RuntimeError('本机服务启动超时，原数据未删除。')


def open_app(url: str):
    if not url.startswith('http://127.0.0.1:'):
        raise ValueError('只允许打开本机应用')
    if os.name == 'nt':
        for key in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'):
            base = os.environ.get(key)
            if not base:
                continue
            exe = Path(base)/'Microsoft/Edge/Application/msedge.exe'
            if exe.is_file():
                subprocess.Popen([str(exe), '--app='+url, '--no-first-run'], close_fds=True)
                return
    if not webbrowser.open(url):
        raise RuntimeError('未找到浏览器。请安装 Edge，或在浏览器中打开控制窗口显示的本机地址。')


def main(adapter):
    parser = argparse.ArgumentParser(description=adapter.NAME+' desktop controller')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--ready-file', type=Path)
    parser.add_argument('--stop-file', type=Path)
    parser.add_argument('--enable-selection-intake', action='store_true')
    parser.add_argument('--restore-backup', type=Path, help='Invest only: restore to a new --data-dir')
    parser.add_argument('--self-test', type=Path, help='Write a headless, temporary-data smoke result')
    args = parser.parse_args()
    home = args.data_dir.resolve() if args.data_dir else private_directory(adapter.NAME)
    if args.restore_backup:
        if not args.data_dir or not hasattr(adapter,'restore') or home.exists():
            raise ValueError('恢复须指定一个不存在的新 --data-dir；仅 Invest 使用此入口')
        if args.restore_backup.stat().st_size>100*1024*1024: raise ValueError('备份超过100MB')
        home.mkdir(parents=True,exist_ok=False)
        adapter.restore(args.restore_backup.read_bytes(),home)
    home.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=home/'desktop.log', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    # Windowed Python does not provide standard streams. Never print credentials.
    for attribute in ('stdout','stderr'):
        if getattr(sys,attribute) is None:
            setattr(sys,attribute,open(home/'desktop.log','a',encoding='utf-8'))
    if args.self_test:
        with tempfile.TemporaryDirectory(prefix=adapter.NAME+'-smoke-') as temp:
            result=adapter.self_test(Path(temp), resource_root())
        args.self_test.parent.mkdir(parents=True,exist_ok=True)
        args.self_test.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return 0 if result.get('ok') else 1
    lock = InstanceLock(home)
    service = None
    try:
        if args.headless:
            service=adapter.start(home, resource_root(), args.enable_selection_intake)
            wait_http(service.health_url)
            if args.ready_file:
                args.ready_file.parent.mkdir(parents=True,exist_ok=True)
                args.ready_file.write_text(json.dumps({'url':service.url,'name':adapter.NAME,'version':VERSION}),encoding='utf-8')
            while not args.stop_file or not args.stop_file.exists():
                time.sleep(.2)
            return 0
        import tkinter as tk
        from tkinter import ttk, messagebox
        root=tk.Tk(); root.title(adapter.NAME+' · 本地桌面版'); root.geometry('690x440')
        root.minsize(600,380)
        box=ttk.Frame(root,padding=24); box.pack(fill='both',expand=True)
        ttk.Label(box,text=adapter.TITLE,font=('Segoe UI',20)).pack(anchor='w')
        ttk.Label(box,text=adapter.DESCRIPTION,wraplength=620,justify='left').pack(anchor='w',pady=12)
        status=tk.StringVar(value='正在启动本机服务…')
        ttk.Label(box,textvariable=status,wraplength=620).pack(anchor='w',pady=10)
        address=tk.StringVar(value='')
        entry=ttk.Entry(box,textvariable=address,state='readonly');entry.pack(fill='x',pady=6)
        intake=tk.BooleanVar(value=args.enable_selection_intake)
        if adapter.NAME=='mygpt':
            ttk.Checkbutton(box,text='允许本次手动选段接收（未核验来源；只在内存中保留）',variable=intake).pack(anchor='w')
        controls=ttk.Frame(box);controls.pack(fill='x',pady=12)
        def on_open():
            try:
                if service: open_app(service.url)
            except Exception as exc: messagebox.showerror('打开失败',str(exc))
        open_button=ttk.Button(controls,text='打开应用',command=on_open,state='disabled');open_button.pack(side='left',padx=4)
        def open_folder():
            if os.name=='nt': os.startfile(str(home))
            else: messagebox.showinfo('数据目录',str(home))
        ttk.Button(controls,text='打开数据与日志目录',command=open_folder).pack(side='left',padx=4)
        def close():
            if not messagebox.askokcancel('关闭本机服务','请先在应用页面保存稿件、笔记或导出备份。未保存的网页编辑不会自动写入。确定退出？'):
                return
            root.destroy()
        ttk.Button(controls,text='退出',command=close).pack(side='right')
        ttk.Label(box,text='数据：'+str(home)+'\n便携包升级不删除此目录。'+adapter.BOUNDARY,wraplength=620,justify='left').pack(anchor='w',pady=16)
        root.protocol('WM_DELETE_WINDOW',close)
        def start():
            nonlocal service
            try:
                service=adapter.start(home, resource_root(), intake.get())
                wait_http(service.health_url)
                address.set(service.url);status.set('服务已就绪；只监听本机。关闭网页不会停止服务。')
                open_button.config(state='normal');on_open()
            except Exception as exc:
                logging.exception('Local application startup failed')
                status.set('启动失败：'+str(exc))
                messagebox.showerror('启动失败',str(exc)+'\n请保留数据目录并查看 desktop.log。')
        # Start after the controller has painted; this is one bounded startup.
        root.after(100,start)
        root.mainloop()
        return 0
    finally:
        if service: service.close()
        lock.close()
