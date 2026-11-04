"""外觀偏好（主題：跟隨系統／淺色／深色；字級：標準／大／特大）：core.js 共用，導覽列的「外觀」按鈕切換，記在 localStorage。"""
import re

import pytest

from conftest import no_hscroll

PAGES = ['index.html', 'console.html', 'me.html?id=1-28', 'score.html', 'captain.html?k=2', 'exit.html']


def _ready(pg):
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)


def _pick(pg, key, value):
    if pg.is_hidden('#dome-prefs-pop'):
        pg.click('.dp-btn')
    pg.click(f'#dome-prefs-pop [data-k="{key}"][data-v="{value}"]')


@pytest.mark.parametrize('path', PAGES)
def test_every_page_has_light_and_dark(open_page, path):
    """每頁都能手動切淺色與深色：背景真的換，文字仍可讀；指揮台、口令卡原本只有深色。"""
    pg, errs, perrs = open_page(path, 1280)
    _ready(pg)
    assert pg.locator('nav.dome-nav .dp-btn').count() == 1
    bg = {}
    for theme in ('light', 'dark'):
        _pick(pg, 'theme', theme)
        assert pg.evaluate('document.documentElement.dataset.theme') == theme
        assert pg.evaluate("getComputedStyle(document.documentElement).colorScheme") == theme
        bg[theme] = pg.evaluate("getComputedStyle(document.body).backgroundColor")
        lum = sum(int(x) for x in re.findall(r'\d+', bg[theme])[:3]) / 3
        assert (lum > 200) if theme == 'light' else (lum < 60), (path, theme, bg[theme])
    assert not errs and not perrs, (errs, perrs)


def test_canvas_recolors_on_switch(open_page):
    """canvas 頁換主題要立刻重讀顏色重畫，不用重新整理。"""
    pg, *_ = open_page('console.html', 1280)
    _ready(pg)
    corner = "(()=>{const d=document.getElementById('cv').getContext('2d').getImageData(4,4,1,1).data;return d[0]})()"
    _pick(pg, 'theme', 'dark')
    pg.wait_for_timeout(100)
    dark = pg.evaluate(corner)
    _pick(pg, 'theme', 'light')
    pg.wait_for_timeout(100)
    assert dark < 60 and pg.evaluate(corner) > 200


def test_font_size_scales_text_and_persists(open_page):
    pg, *_ = open_page('index.html', 1280)
    _ready(pg)
    h1 = lambda: pg.evaluate("parseFloat(getComputedStyle(document.querySelector('h1')).fontSize)")
    body = lambda: pg.evaluate("parseFloat(getComputedStyle(document.body).fontSize)")
    b0 = body()
    _pick(pg, 'fs', '1.3')
    assert pg.evaluate('getComputedStyle(document.documentElement).fontSize') == '20.8px'
    assert abs(body() - b0 * 1.3) < 0.1 and h1() > 0
    _pick(pg, 'theme', 'light')
    pg.goto(pg.url.replace('index.html', 'captain.html'))   # 同一個瀏覽器 context：換頁後偏好還在
    _ready(pg)
    assert pg.evaluate('document.documentElement.dataset.theme') == 'light'
    assert pg.evaluate('getComputedStyle(document.documentElement).fontSize') == '20.8px'
    pg.click('.dp-btn')
    assert pg.locator('#dome-prefs-pop [aria-pressed=true]').all_inner_texts() == ['淺色', '特大']


@pytest.mark.parametrize('path', PAGES)
def test_largest_size_fits_on_phone(open_page, path):
    """特大字級在 375 寬手機上不出現橫向捲動。"""
    pg, *_ = open_page(path, 375, 760)
    pg.evaluate("localStorage.setItem('dome.fs','1.3')")
    pg.reload()
    _ready(pg)
    assert pg.evaluate('getComputedStyle(document.documentElement).fontSize') == '20.8px'
    assert no_hscroll(pg), path


def test_auto_follows_system_and_keyboard(open_page):
    """跟隨系統 = 拿掉 data-theme；面板開啟時焦點進到目前的選項，Esc 關閉並回到按鈕。"""
    pg, *_ = open_page('me.html', 1280)
    _ready(pg)
    _pick(pg, 'theme', 'dark')
    pg.keyboard.press('Escape')
    assert pg.is_hidden('#dome-prefs-pop') and pg.evaluate('document.activeElement.className') == 'dp-btn'
    pg.keyboard.press('Enter')
    assert pg.get_attribute('.dp-btn', 'aria-expanded') == 'true'
    assert pg.evaluate('document.activeElement.textContent') == '深色'
    pg.click('#dome-prefs-pop [data-v=auto]')
    assert pg.evaluate("document.documentElement.hasAttribute('data-theme')") is False
    pg.mouse.click(5, 700)
    assert pg.is_hidden('#dome-prefs-pop')


def test_bad_stored_values_fall_back(open_page):
    pg, *_ = open_page('index.html', 1280)
    pg.evaluate("localStorage.setItem('dome.theme','<b>');localStorage.setItem('dome.fs','9')")
    pg.reload()
    _ready(pg)
    assert pg.evaluate("document.documentElement.hasAttribute('data-theme')") is False
    assert pg.evaluate('document.documentElement.style.fontSize') == ''


def test_handout_stays_paper(open_page):
    """講義是 A3 列印稿：紙張配色、版面以 mm／pt 定死，不顯示「外觀」也不套用偏好。"""
    pg, *_ = open_page('handout.html', 1280)
    pg.evaluate("localStorage.setItem('dome.theme','dark');localStorage.setItem('dome.fs','1.3')")
    pg.reload()
    _ready(pg)
    assert pg.locator('.dp-btn').count() == 0
    assert pg.evaluate("document.documentElement.hasAttribute('data-theme')") is False
    assert pg.evaluate('getComputedStyle(document.documentElement).fontSize') == '16px'


def test_diorama_follows_saved_theme(open_page):
    """3D 模型頁沒有導覽列，但面板跟著其他頁存下的主題（3D 場景本身依設計固定淺色）。"""
    pg, *_ = open_page('index.html', 1280)
    pg.evaluate("localStorage.setItem('dome.theme','dark')")
    pg.goto(pg.url.replace('index.html', 'diorama.html'))
    pg.wait_for_function("document.documentElement.dataset.theme === 'dark'", timeout=20000)
    assert pg.evaluate("getComputedStyle(document.documentElement).colorScheme") == 'dark'


@pytest.mark.parametrize('path', ['console.html', 'score.html'])
def test_switch_during_load_still_recolors_canvas(open_page, path):
    """回歸（PR review）：資料還在讀取時就切主題，載入完成後 canvas 也要用新主題的顏色。"""
    pg, *_ = open_page('index.html', 1280)
    pg.route('**/data.json', lambda r: (pg.wait_for_timeout(1500), r.continue_()))
    pg.goto(pg.url.replace('index.html', path))
    _pick(pg, 'theme', 'light')
    _ready(pg)
    pg.wait_for_timeout(150)
    cv = '#cv' if path == 'console.html' else '#m'
    px = pg.evaluate(f"(()=>{{const c=document.querySelector('{cv}'),x=c.getContext('2d'),d=window.devicePixelRatio||1;return x.getImageData(4*d,4*d,1,1).data[0]}})()")
    assert px > 200, (path, px)


def test_panel_follows_scroll_and_closes_on_tab_out(open_page):
    """回歸（PR review）：面板跟著捲動走；Tab 離開面板就關閉。"""
    pg, *_ = open_page('index.html', 1280)
    _ready(pg)
    pg.click('.dp-btn')
    pg.mouse.wheel(0, 300)
    pg.wait_for_timeout(200)
    btn = pg.evaluate("document.querySelector('.dp-btn').getBoundingClientRect().bottom")
    top = pg.evaluate("document.getElementById('dome-prefs-pop').getBoundingClientRect().top")
    assert abs(top - (btn + 6)) <= 1, (btn, top)
    pg.evaluate('scrollTo(0,0)')
    pg.click('.dp-btn') if pg.is_hidden('#dome-prefs-pop') else None
    pg.focus('#dome-prefs-pop [data-v="1.3"]')
    pg.keyboard.press('Tab')
    assert pg.is_hidden('#dome-prefs-pop') and pg.evaluate('document.activeElement.className') == 'dp-btn'
    pg.keyboard.press('Enter')
    pg.keyboard.press('Shift+Tab')   # 焦點在第一個主題選項以外時，Shift+Tab 先在面板內移動
    pg.focus('#dome-prefs-pop [data-v=auto]')
    pg.keyboard.press('Shift+Tab')
    assert pg.is_hidden('#dome-prefs-pop')


# ---------- 跟隨系統（auto）：交給 prefers-color-scheme ----------
CANVAS = {'console.html': '#cv', 'score.html': '#m', 'captain.html?k=2': '#c', 'me.html?id=1-28': 'canvas'}


def _lum(pg, js):
    return sum(int(x) for x in re.findall(r'\d+', pg.evaluate(js))[:3]) / 3


def _canvas_px(pg, sel):
    return pg.evaluate(f"(()=>{{const c=document.querySelector('{sel}'),d=window.devicePixelRatio||1;"
                       f"return c.getContext('2d').getImageData(3*d,3*d,1,1).data[0]}})()")


@pytest.mark.parametrize('path', PAGES)
def test_auto_follows_system_scheme_live(open_page, path):
    """沒選主題（auto）時跟著系統；系統在頁面開著時切換，頁面與 canvas 都要即時跟著變，不用重新整理。"""
    pg, errs, perrs = open_page(path, 1280)
    pg.emulate_media(color_scheme='light')
    pg.reload()
    _ready(pg)
    assert pg.evaluate("document.documentElement.hasAttribute('data-theme')") is False
    bg = "getComputedStyle(document.body).backgroundColor"
    assert _lum(pg, bg) > 200 and pg.evaluate("getComputedStyle(document.documentElement).colorScheme") == 'light'
    sel = CANVAS.get(path)
    if sel:
        assert _canvas_px(pg, sel) > 200
    pg.emulate_media(color_scheme='dark')      # 系統切深色：matchMedia change → onPrefs
    pg.wait_for_timeout(200)
    assert _lum(pg, bg) < 60 and pg.evaluate("getComputedStyle(document.documentElement).colorScheme") == 'dark'
    if sel:
        assert _canvas_px(pg, sel) < 60, (path, 'canvas 沒跟著系統換色')
    assert not errs and not perrs, (errs, perrs)


@pytest.mark.parametrize('system,manual', [('dark', 'light'), ('light', 'dark')])
def test_manual_choice_beats_system(open_page, system, manual):
    """手動選擇要蓋過相反的系統偏好；改回「跟隨系統」再回到系統的那一邊。"""
    pg, *_ = open_page('captain.html?k=2', 1280)
    pg.emulate_media(color_scheme=system)
    pg.reload()
    _ready(pg)
    bg = "getComputedStyle(document.body).backgroundColor"
    _pick(pg, 'theme', manual)
    pg.wait_for_timeout(100)
    assert (_lum(pg, bg) > 200) == (manual == 'light')
    assert (_canvas_px(pg, '#c') > 200) == (manual == 'light')
    pg.emulate_media(color_scheme=manual)      # 系統再怎麼切，手動選擇都不動
    pg.emulate_media(color_scheme=system)
    pg.wait_for_timeout(100)
    assert (_lum(pg, bg) > 200) == (manual == 'light')
    _pick(pg, 'theme', 'auto')
    pg.wait_for_timeout(100)
    assert (_lum(pg, bg) > 200) == (system == 'light')
    assert (_canvas_px(pg, '#c') > 200) == (system == 'light')


def test_theme_token_blocks_stay_in_sync(root):
    """每個主題各有兩份 token（prefers-color-scheme 與 data-theme），內容必須一模一樣，否則「跟隨系統」與手動選擇顏色不同。"""
    pat = {'dark': (r'@media\(prefers-color-scheme:dark\)\{:root:not\(\[data-theme=light\]\)\{([^}]*)\}\}', r':root\[data-theme=dark\]\{([^}]*)\}'),
           'light': (r'@media\(prefers-color-scheme:light\)\{:root:not\(\[data-theme=dark\]\)\{([^}]*)\}\}', r':root\[data-theme=light\]\{([^}]*)\}')}
    for name in ['index.html', 'console.html', 'me.html', 'score.html', 'captain.html', 'exit.html']:
        s = (root / name).read_text(encoding='utf-8')
        pairs = 0
        for theme, (a, b) in pat.items():
            x, y = re.search(a, s), re.search(b, s)
            assert bool(x) == bool(y), (name, theme, '只有一份')
            if x:
                assert x.group(1) == y.group(1), (name, theme)
                pairs += 1
        assert pairs == 1, (name, '每頁應該正好有一組被覆寫的主題')
