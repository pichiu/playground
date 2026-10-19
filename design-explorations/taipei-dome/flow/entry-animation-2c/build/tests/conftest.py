import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]   # entry-animation-2c/
sys.path.insert(0, str(ROOT / 'build'))        # import plan / routes / check


@pytest.fixture(scope='session')
def root():
    return ROOT


@pytest.fixture(scope='session')
def base():
    return json.loads((ROOT / 'build' / 'base.json').read_text(encoding='utf-8'))


@pytest.fixture(scope='session')
def pipeline(root, tmp_path_factory):
    """跑一次完整管線（plan → build 含避撞），整個 session 共用：回傳 (tmp_dir, data)。"""
    import subprocess
    tmp = tmp_path_factory.mktemp('pipeline')
    b = ROOT / 'build'
    subprocess.run([sys.executable, 'plan.py', 'base.json', str(tmp / 'plan.json')], cwd=b, check=True)
    r = subprocess.run([sys.executable, 'build.py', 'base.json', str(tmp / 'plan.json'), str(tmp / 'data.json'), str(tmp / 'seats.csv')],
                       cwd=b, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-3000:]
    return tmp, json.loads((tmp / 'data.json').read_text(encoding='utf-8'))
