"""3D 模型頁（diorama.html）：由 pichiu/workshop 的 diorama.src.html 以 inline.py --pages 產生，讀同一份 data.json。
需要 WebGL（SwiftShader）與 cdn.jsdelivr.net 的 three.js；SwiftShader 每幀約 1 秒，所以等待時間放寬。"""
import re
from conftest import no_hscroll

READY = 'window.__dome && window.__dome.ready === true || !!window.__domeError'


def _ready(pg):
    pg.wait_for_function(READY, timeout=240000, polling=500)
    assert pg.evaluate('window.__domeError || null') is None


def test_diorama_loads_shared_data(open_page):
    pg, errs, perrs = open_page('diorama.html', 1280, 800)
    _ready(pg)
    assert not errs and not perrs, (errs, perrs)
    # 和其他頁同一份 data.json，位置照 core.js 的 Dome.pos
    r = pg.evaluate('''async () => { const S = await Dome.load(); const P = S.P, out = [];
        for (const t of [10, 40, 60, S.T_END - 1]) { __dome.seek(t);
          for (let i = 0; i < P.length; i += 97) { const a = __dome.worldXZ(i), b = Dome.pos(P[i], t);
            out.push(Math.hypot(a[0] - b[0], a[1] - b[1])); } }
        return { n: P.length, max: Math.max(...out), k: out.length }; }''')
    assert r['n'] == 1609 and r['k'] > 60 and r['max'] < 1e-4, r
    link = pg.locator('#pages-link')
    assert link.is_visible() and link.get_attribute('href') == 'index.html'
    body = pg.inner_text('body')
    assert not re.search(r'\d{1,2}:\d\d', body) and '分鐘' not in body


def test_diorama_mobile_no_hscroll(open_page):
    pg, errs, perrs = open_page('diorama.html', 390, 844)
    _ready(pg)
    assert no_hscroll(pg) and not errs and not perrs, (errs, perrs)


def test_nav_links_to_diorama(open_page):
    pg, *_ = open_page('index.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert pg.locator('nav.dome-nav a[href="diorama.html"]').inner_text() == '3D 模型'
