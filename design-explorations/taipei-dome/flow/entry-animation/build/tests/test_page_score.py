"""C 總譜頁測試（共用 conftest 的 server / browser / open_page）。"""
from conftest import no_hscroll


def test_score(open_page):
    pg, errs, perrs = open_page('score.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    assert pg.locator('[data-row]').count() == 54 and pg.get_attribute('[data-row] >> nth=0', 'data-lie') == '54'   # 樓梯序第一列：藍9 的 A 路＝列 54
    assert '最長等待' in pg.inner_text('#summary')


def test_score_mobile(open_page):
    pg, errs, perrs = open_page('score.html', 375, 700)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert no_hscroll(pg) and not perrs
