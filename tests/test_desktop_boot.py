from pathlib import Path
import sys
import desktop


def test_windowed_standard_streams_are_initialized(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'argv', ['Novel.exe', '--novel-service', '1234', str(tmp_path), str(tmp_path), str(tmp_path/'stop')])
    for key in ('stdout', 'stderr', 'stdin'):
        monkeypatch.setattr(sys, key, None)
    monkeypatch.setenv('NOVEL_BOOT_LOG', str(tmp_path/'boot.log'))
    desktop.prepare_streams()
    try:
        assert sys.stdin.read() == ''
        sys.stdout.write('ready\n'); sys.stdout.flush()
        sys.stderr.write('diagnostic\n'); sys.stderr.flush()
        assert 'ready' in (tmp_path/'boot.log').read_text(encoding='utf-8')
        assert 'diagnostic' in (tmp_path/'boot.log').read_text(encoding='utf-8')
    finally:
        for key in ('stdout', 'stderr', 'stdin'):
            getattr(sys, key).close()
