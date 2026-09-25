"""Windowed entry point; service children also receive usable standard streams."""
from pathlib import Path
import os
import sys


def prepare_streams():
    """PyInstaller windowed apps set stdio to None even for redirected children."""
    if '--novel-service' in sys.argv and len(sys.argv) == 6:
        home = Path(sys.argv[3])
    elif '--data-dir' in sys.argv:
        home = Path(sys.argv[sys.argv.index('--data-dir') + 1])
    else:
        home = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'.local/share'))) / 'NovelDesktop'
    home.mkdir(parents=True, exist_ok=True)
    log = Path(os.environ.get('NOVEL_BOOT_LOG', str(home/'boot.log')))
    log.parent.mkdir(parents=True, exist_ok=True)
    for name in ('stdout', 'stderr'):
        if getattr(sys, name) is None:
            setattr(sys, name, log.open('a', encoding='utf-8', buffering=1))
    if sys.stdin is None:
        sys.stdin = open(os.devnull, 'r', encoding='utf-8')


def entry():
    prepare_streams()
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        if '--novel-service' in sys.argv:
            from desktop_adapter import serve
            _, port, home, root, stop = sys.argv[1:]
            serve(int(port), Path(home), Path(root), Path(stop))
            return 0
        from desktop_runtime import main
        import desktop_adapter
        return main(desktop_adapter)
    except Exception as error:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        if not any(flag in sys.argv for flag in ('--headless', '--self-test', '--novel-service')):
            from tkinter import messagebox
            messagebox.showerror('本机应用无法启动', str(error)+'\n未删除任何已有数据。请查看 boot.log。')
        return 1


if __name__ == '__main__':
    raise SystemExit(entry())
