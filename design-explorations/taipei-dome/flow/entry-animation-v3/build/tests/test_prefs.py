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
