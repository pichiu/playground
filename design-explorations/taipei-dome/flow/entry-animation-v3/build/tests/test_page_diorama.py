"""3D 模型頁（diorama.html）：由 build/diorama.src.html 以 python3 -I build/inline.py 產生，讀同一份 data.json。
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


def _pip(xs, ys, poly):
    """向量化 ray casting：點 (xs, ys) 是否在多邊形 poly 內。"""
    import numpy as np
    inside = np.zeros(xs.shape, bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i - 1]
        x2, y2 = poly[i]
        c = (y2 > ys) != (y1 > ys)
        with np.errstate(divide='ignore', invalid='ignore'):
            xi = (x1 - x2) * (ys - y2) / (y1 - y2) + x2
        inside ^= c & (xs < xi)
    return inside


def _solid_hits(solids, xs, ys):
    """落在任何實體平面外框內（扣掉洞）的點數，依實體種類分開數。圓（中央平台各級）用半徑判斷。"""
    import numpy as np
    out = {}
    for s in solids:
        if s['r'] is not None:
            hit = np.hypot(xs, ys) <= s['r']
        else:
            poly = s['poly']
            bx0, by0 = min(p[0] for p in poly), min(p[1] for p in poly)
            bx1, by1 = max(p[0] for p in poly), max(p[1] for p in poly)
            box = (xs >= bx0) & (xs <= bx1) & (ys >= by0) & (ys <= by1)
            hit = np.zeros(xs.shape, bool)
            if box.any():
                h = _pip(xs[box], ys[box], poly)
                for hole in s['holes']:
                    h &= ~_pip(xs[box], ys[box], hole)
                hit[box] = h
        out[s['kind']] = out.get(s['kind'], 0) + int(hit.sum())
    return out


def test_diorama_stage_solids_clear(open_page, three_cdn):
    """舞台、伸展台、中央平台、紅色方塊、LED 牆／立柱／側螢幕的平面外框：1,609 人全部 path（每 0.02 細分）、
    data.others 3,679 人、場內位置與休息區座位都不能落在裡面。南側下段階梯（omega，資料讓人走上最多 3 階）是例外，只列出。"""
    import json
    import numpy as np
    pg, errs, perrs = open_page('diorama.html', 1280, 800)
    _ready(pg)
    solids = pg.evaluate('__dome.debug.solids()')
    kinds = {s['kind'] for s in solids}
    assert {'landing', 'main', 'omega', 'omegaN', 'upper', 'ramp', 'runway', 'ring', 'pad', 'led'} <= kinds, kinds
    D = json.loads((ROOT / 'data.json').read_text(encoding='utf-8'))
    xs, ys = [], []
    for p in D['persons']:
        a = np.array([q[:2] for q in p['path']], float)
        seg = np.diff(a, axis=0)
        n = np.maximum(1, np.ceil(np.hypot(seg[:, 0], seg[:, 1]) / 0.02)).astype(int)
        k = np.repeat(np.arange(len(seg)), n)                          # 每個細分點屬於哪一段
        f = (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)) / n[k]   # 段內的比例 0, 1/n, …
        xs.append(a[k, 0] + seg[k, 0] * f)
        ys.append(a[k, 1] + seg[k, 1] * f)
        xs.append(a[-1:, 0])
        ys.append(a[-1:, 1])
    px, py = np.concatenate(xs), np.concatenate(ys)
    paths = _solid_hits(solids, px, py)
    ox = np.array([o['X'] for o in D['others']] + [s['X'] for s in D['restSeats']] + [p['field']['X'] for p in D['persons']])
    oy = np.array([o['Y'] for o in D['others']] + [s['Y'] for s in D['restSeats']] + [p['field']['Y'] for p in D['persons']])
    others = _solid_hits(solids, ox, oy)
    print('path points', len(px), 'hits', paths, '| others+seats', len(ox), 'hits', others)
    assert all(v == 0 for k, v in paths.items() if k != 'omega'), paths
    assert all(v == 0 for v in others.values()), others
    assert not errs and not perrs, (errs, perrs)


def test_diorama_led_wall_fades(open_page, three_cdn):
    """主 LED 牆：總覽不透明；章節 3–6 的特寫與跟隨淡化；鏡頭在牆東側且牆擋住路線時淡化。draw call ≤ 60。"""
    pg, errs, perrs = open_page('diorama.html', 1280, 800)
    _ready(pg)
    settle = '() => { const l = __dome.debug.led(); return l.opacity === l.target && !__dome.debug.flight(); }'
    pg.evaluate('__dome.debug.pause(); __dome.debug.view("home")')
    pg.wait_for_function(settle, timeout=120000, polling=500)
    home = pg.evaluate('__dome.debug.led()')
    assert home['target'] == 1 and home['opacity'] == 1, home
    for k in range(7):
        pg.evaluate(f'__dome.debug.chapter({k})')
        pg.wait_for_function(settle, timeout=120000, polling=500)
        led = pg.evaluate('__dome.debug.led()')
        if 2 <= k <= 5:                      # 章節 3–6
            assert led['target'] < 0.5 and led['opacity'] == led['target'], (k, led)
    # 從東側高處往西看（接近企劃 3D 圖的角度）：牆擋住牆後的門前隊伍與 B2 走廊 → 淡化
    pg.evaluate('__dome.seek(45); __dome.debug.setCam([8.6, 9.0, 0.02], [-3.7, -0.4, 0.02])')
    pg.wait_for_function(settle, timeout=120000, polling=500)
    east = pg.evaluate('__dome.debug.led()')
    assert east['occ'] > 0 and east['target'] < 0.5, east
    # 跟隨一列 → 淡化
    pg.evaluate('__dome.debug.search("列 14")')
    pg.wait_for_function(settle, timeout=120000, polling=500)
    assert pg.evaluate('__dome.debug.led()')['target'] < 0.5
    assert pg.evaluate('__dome.debug.info().calls') <= 60
    assert not errs and not perrs, (errs, perrs)
