import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]   # entry-animation-v3/
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


# ---------- 頁面測試共用（http.server + Playwright） ----------
_CHROMES = ['/opt/pw-browsers/chromium', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome']   # 預裝的 Chromium（新版環境是前者）
CHROME = next((c for c in _CHROMES if Path(c).exists()), _CHROMES[0])


@pytest.fixture(scope='session')
def server(root):
    import socket
    import subprocess
    import time
    import urllib.request
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    proc = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1'], cwd=root,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}/'
    for _ in range(50):
        try:
            urllib.request.urlopen(base + 'core.js', timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    yield base
    proc.terminate()


@pytest.fixture(scope='session')
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        yield b
        b.close()


@pytest.fixture
def open_page(server, browser):
    """open_page(path, width, height=800) -> (page, console_errors, page_errors)。沙箱沒有外網，Google Fonts 載不到不算錯。"""
    contexts = []

    def _open(path, width, height=800):
        ctx = browser.new_context(viewport={'width': width, 'height': height})
        contexts.append(ctx)
        pg = ctx.new_page()
        errs, perrs = [], []
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'fonts.g' not in m.location.get('url', '') else None)
        pg.on('pageerror', lambda e: perrs.append(str(e)))
        pg.goto(server + path, wait_until='load')
        return pg, errs, perrs
    yield _open
    for ctx in contexts:
        ctx.close()


def no_hscroll(pg):
    return pg.evaluate('document.documentElement.scrollWidth') <= pg.viewport_size['width']
