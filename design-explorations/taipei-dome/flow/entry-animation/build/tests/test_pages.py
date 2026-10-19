"""總覽頁測試（各看法頁各有自己的 test_page_*.py，共用 conftest 的 server / browser / open_page）。"""
from conftest import no_hscroll


def test_index_overview(open_page):
    pg, errs, perrs = open_page('index.html', 1280)
    pg.wait_for_selector('[data-checks] .ok', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    assert pg.locator('nav.dome-nav a').count() == 7 and pg.locator('a[href="seats.csv"]').count() == 1
    assert pg.locator('[data-lane-table] tbody tr').count() == 3 and pg.locator('[data-stair-order] [data-block]').count() == 18
    assert pg.locator('[data-checks].ok').count() == 1 and pg.locator('[data-exit-usage] [data-exit]').count() == 7


def test_index_mobile_no_hscroll(open_page):
    pg, errs, perrs = open_page('index.html', 375, 700)
    pg.wait_for_selector('[data-checks] .ok', timeout=20000)
    assert no_hscroll(pg) and not perrs


def test_fetch_failure_banner(open_page):   # Review Focus 5：資料讀不到要有提示橫幅
    pg, *_ = open_page('index.html?data=missing.json', 1280)
    pg.wait_for_selector('#dome-err', timeout=20000)
    assert 'http.server' in pg.inner_text('#dome-err')
