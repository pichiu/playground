"""3D 模型頁（diorama.html）：由 pichiu/workshop 的 diorama.src.html 以 inline.py --pages 產生，讀同一份 data.json。
需要 WebGL（SwiftShader）與 cdn.jsdelivr.net 的 three.js；SwiftShader 每幀約 1 秒，所以等待時間放寬。"""
import functools
import re
import urllib.request
import pytest
from conftest import ROOT, no_hscroll

READY = 'window.__dome && window.__dome.ready === true || !!window.__domeError'


@functools.lru_cache(maxsize=None)
def _three_unreachable():
    """three.module.js 的網址（diorama.html importmap 裡那一個）連不到時回傳原因，連得到回傳 None。整個 session 只探一次。"""
    m = re.search(r'"three":\s*"(https://cdn\.jsdelivr\.net/[^"]+/three\.module\.js)"', (ROOT / 'diorama.html').read_text(encoding='utf-8'))
    if not m:
        return 'diorama.html 的 importmap 找不到 three.module.js 網址'
    try:
        with urllib.request.urlopen(urllib.request.Request(m.group(1), method='HEAD'), timeout=5) as r:
            return None if r.status == 200 else f'{m.group(1)} 回應 HTTP {r.status}'
    except Exception as e:
        return f'{m.group(1)} 連不到（{type(e).__name__}: {e}）'


@pytest.fixture
def three_cdn():
    """需要 cdn.jsdelivr.net 上的 three.js 的測試：CDN 連不到就 skip（說明原因），而不是等 240 秒後失敗。"""
    why = _three_unreachable()
    if why:
        pytest.skip('3D 模型頁需要 cdn.jsdelivr.net 的 three.js：' + why)


def _ready(pg):
    pg.wait_for_function(READY, timeout=240000, polling=500)
    assert pg.evaluate('window.__domeError || null') is None


def test_diorama_loads_shared_data(open_page, three_cdn):
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
    # 品牌卡裡的「其他頁面」選單鈕（見 test_diorama_pages_menu）
    assert pg.locator('#pages-btn').is_visible()
    body = pg.inner_text('body')
    assert not re.search(r'\d{1,2}:\d\d', body) and '分鐘' not in body


def test_diorama_mobile_no_hscroll(open_page, three_cdn):
    pg, errs, perrs = open_page('diorama.html', 390, 844)
    _ready(pg)
    assert no_hscroll(pg) and not errs and not perrs, (errs, perrs)


def test_nav_links_to_diorama(open_page):
    pg, *_ = open_page('index.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert pg.locator('nav.dome-nav a[href="diorama.html"]').inner_text() == '3D 模型'


def test_diorama_pages_menu(open_page, three_cdn):
    """品牌卡的「其他頁面」選單：列出版本 3 的 8 頁（和 core.js 的 Dome.NAV 相同）、目前頁打勾不是連結、鍵盤可操作、總覽連結可用。"""
    pg, errs, perrs = open_page('diorama.html', 1280, 800)
    _ready(pg)
    if pg.locator('#help').is_visible():      # 第一次進來會先顯示說明
        pg.click('#help-go')
    btn = pg.get_by_role('button', name='其他頁面')
    assert btn.is_visible() and btn.get_attribute('aria-expanded') == 'false'
    box = btn.bounding_box()
    assert box['width'] >= 44 and box['height'] >= 44, box
    menu = pg.locator('#pages-menu')
    assert menu.is_hidden()
    btn.focus()
    pg.keyboard.press('Enter')
    assert menu.is_visible() and btn.get_attribute('aria-expanded') == 'true'
    items = pg.evaluate("""() => [...document.querySelectorAll('#pages-list li')].map(li => {
        const a = li.querySelector('a'), c = li.querySelector('[aria-current]');
        return { href: a ? a.getAttribute('href') : null, text: (a || c).textContent.trim(), cur: c ? c.getAttribute('aria-current') : null }; })""")
    nav = pg.evaluate('Dome.NAV')                # core.js 匯出的頁面清單，選單直接用它
    assert len(items) == 8 == len(nav), items
    assert [i['text'].replace('（目前頁面）', '') for i in items] == [n[1] for n in nav]
    cur = [i for i in items if i['cur']]
    assert len(cur) == 1 and cur[0]['cur'] == 'page' and cur[0]['href'] is None and cur[0]['text'].startswith('3D 模型'), cur
    assert pg.locator('#pages-list [aria-current="page"] svg.ck path').count() == 1      # 打勾
    assert [i['href'] for i in items if i['href']] == [n[0] for n in nav if n[0] != 'diorama.html']
    # 鍵盤：Enter 開啟後焦點在第一項，↓ 下一項，Esc 關閉並回到按鈕
    assert pg.evaluate('document.activeElement.textContent.trim()') == '總覽'
    pg.keyboard.press('ArrowDown')
    assert pg.evaluate('document.activeElement.textContent.trim()') == '指揮台'
    pg.keyboard.press('Escape')
    assert menu.is_hidden() and pg.evaluate("document.activeElement.id") == 'pages-btn'
    # 總覽連結可用
    btn.click()
    with pg.expect_navigation(url='**/index.html', timeout=60000):
        pg.locator('#pages-list a[href="index.html"]').click()
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert pg.locator('nav.dome-nav a[aria-current="page"]').inner_text() == '總覽'
    assert not errs and not perrs, (errs, perrs)
