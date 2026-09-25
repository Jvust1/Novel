from pathlib import Path
import multiprocessing
import sys

if __name__ == '__main__':
    multiprocessing.freeze_support()
    if '--novel-service' in sys.argv:
        from desktop_adapter import serve
        _,port,home,root,stop=sys.argv[1:]
        serve(int(port),Path(home),Path(root),Path(stop))
    else:
        from desktop_runtime import main
        import desktop_adapter
        try:
            raise SystemExit(main(desktop_adapter))
        except Exception as error:
            if '--headless' in sys.argv or '--self-test' in sys.argv:raise
            from tkinter import messagebox
            messagebox.showerror('本机应用无法启动',str(error)+'\n未删除任何已有数据。')
            raise SystemExit(1)
