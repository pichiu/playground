"""C 總譜頁測試（共用 conftest 的 server / browser / open_page）。"""
from conftest import no_hscroll


def test_score(open_page):
    pg, errs, perrs = open_page('score.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    rows = pg.locator('[data-row]')
    assert rows.count() == 54
    assert [rows.nth(i).get_attribute('data-lie') for i in range(7)] == ['1', '2', '3', '4', '5', '6', '7']   # 樓梯序：大隊 1 白三列、藍三列，再大隊 2
    s = pg.inner_text('#summary')
    assert '門前' in s and '最久' in s
    assert '集結' not in pg.inner_text('body') and '2c' not in pg.inner_text('h1')


def test_score_mobile(open_page):
    pg, errs, perrs = open_page('score.html', 375, 700)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert no_hscroll(pg) and not perrs
