from pathlib import Path
import importlib.util
import sys
import pytest

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('desktop_runtime_tests',root/'desktop_runtime.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)


def test_single_instance_lock(tmp_path):
    lock=runtime.InstanceLock(tmp_path)
    try:
        with pytest.raises(RuntimeError): runtime.InstanceLock(tmp_path)
    finally: lock.close()
    second=runtime.InstanceLock(tmp_path);second.close()


def test_browser_rejects_remote_url():
    with pytest.raises(ValueError): runtime.open_app('https://external.invalid/')
