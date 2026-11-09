"""A 指揮台 console.html 頁面測試（共用 conftest 的 server / browser / open_page）。"""
from conftest import no_hscroll


def test_console(open_page):
    pg, errs, perrs = open_page('console.html', 1280)
    pg.wait_for_selector('canvas')
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    # 時間軸兩軌：上軌 9 大隊下樓梯（白／藍兩路）、下軌 9 大隊進場
    st = pg.locator('[data-track="stair"] [data-dadui]')
    assert st.count() == 9 and pg.locator('[data-track="gate"] [data-dadui]').count() == 9
    assert st.first.get_attribute('data-dadui') == '1'
    # 路別高亮按鈕只有 A、B
    assert pg.locator('[data-lane]').count() == 2 and pg.locator('[data-lane="C"]').count() == 0
    pg.click('[data-lane="B"]')
    assert pg.get_attribute('[data-lane="B"]', 'aria-pressed') == 'true'
    pg.click('[data-lane="B"]')
    assert pg.get_attribute('[data-lane="B"]', 'aria-pressed') == 'false'
    assert pg.locator('nav.dome-nav a[aria-current="page"]').inner_text() == '指揮台'
    assert pg.locator('body > nav.dome-nav a').count() == 8
    pg.evaluate('window.__seek(120)')
    pg.wait_for_function('document.getElementById("clock").textContent.endsWith("%")', timeout=5000)
    assert pg.locator('#cues li').count() > 0
    text = pg.inner_text('body')
    assert not any(w in text for w in ('集結區', '白 2', '白 3', '2c')), text[:300]
    assert '版本 3' in pg.title()
    assert not errs and not perrs, (errs, perrs)


def test_console_mobile(open_page):
    pg, errs, perrs = open_page('console.html', 375, 700)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert no_hscroll(pg) and not perrs


def test_console_draws_six_gate_lanes(open_page):      # 指揮台在 B2 畫出六條西一入口線（北三白、南三藍）
    pg, *_ = open_page('console.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert pg.evaluate('window.__gateLanesDrawn') == 6


def test_console_phase_and_head_follow_time(open_page):   # 回歸：播放／拖曳時階段文字與進度指針要跟著更新
    pg, *_ = open_page('console.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    pg.evaluate('window.__seek(120)')
    pg.wait_for_function('parseFloat(document.getElementById("head").style.left) > 10', timeout=5000)   # 等 seek 那一格畫完（t=0 時階段文字本來就有）
    assert pg.inner_text('#phase').strip() not in ('', '休息區就座')
