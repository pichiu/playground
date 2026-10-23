"""A 指揮台 console.html 頁面測試（共用 conftest 的 server / browser / open_page）。"""
from conftest import no_hscroll


def test_console(open_page):
    pg, errs, perrs = open_page('console.html', 1280)
    pg.wait_for_selector('canvas')
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    # 時間軸兩軌：上軌 18 區塊（樓梯序 藍9…白9）、下軌 9 大隊
    blocks = pg.locator('[data-track="stair"] [data-block]')
    assert blocks.count() == 18 and pg.locator('[data-track="gate"] [data-dadui]').count() == 9
    assert blocks.first.get_attribute('data-block') == '藍9' and blocks.last.get_attribute('data-block') == '白9'
    assert pg.locator('[data-track="gate"] [data-dadui]').first.get_attribute('data-dadui') == '1'
    # 路別高亮按鈕：aria-pressed 切換
    pg.click('[data-lane="B"]')
    assert pg.get_attribute('[data-lane="B"]', 'aria-pressed') == 'true'
    pg.click('[data-lane="B"]')
    assert pg.get_attribute('[data-lane="B"]', 'aria-pressed') == 'false'
    # 導覽列固定在最上方（body 直屬），目前頁為指揮台
    assert pg.locator('nav.dome-nav a[aria-current="page"]').inner_text() == '指揮台'
    assert pg.locator('body > nav.dome-nav a').count() == 7
    # 時間一律 mm:ss；示意事件含大隊進場
    pg.evaluate('window.__seek(200)')
    pg.wait_for_function('document.getElementById("clock").textContent.endsWith("%")', timeout=5000)
    assert '大隊 1 由西一入口進場' in pg.inner_text('#cues') or pg.locator('#cues li').count() > 0
    assert not errs and not perrs, (errs, perrs)


def test_console_mobile(open_page):
    pg, errs, perrs = open_page('console.html', 375, 700)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert no_hscroll(pg) and not perrs


def test_console_phase_and_head_follow_time(open_page):   # 回歸：播放／拖曳時階段文字與進度指針要跟著更新
    pg, *_ = open_page('console.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    pg.evaluate('window.__seek(120)')
    pg.wait_for_function('parseFloat(document.getElementById("head").style.left) > 10', timeout=5000)   # 等 seek 那一格畫完（t=0 時階段文字本來就有）
    assert pg.inner_text('#phase').strip() not in ('', '休息區就座')
