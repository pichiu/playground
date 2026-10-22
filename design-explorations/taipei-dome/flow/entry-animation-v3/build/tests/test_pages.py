"""總覽頁測試（各看法頁各有自己的 test_page_*.py，共用 conftest 的 server / browser / open_page）。"""
from conftest import no_hscroll


def test_index_overview(open_page):
    pg, errs, perrs = open_page('index.html', 1280)
    pg.wait_for_selector('[data-checks] .ok', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    assert pg.locator('nav.dome-nav a').count() == 7 and pg.locator('a[href="seats.csv"]').count() == 1
    assert pg.locator('[data-lane-table] tbody tr').count() == 2
    assert pg.locator('[data-lane-table] tbody tr').first.locator('td').count() == 6     # 路名 + 4 段 + 合計
    assert pg.locator('[data-stair-order] [data-dadui]').count() == 9
    assert pg.locator('[data-exit-usage] [data-exit]').count() == 7
    assert pg.locator('[data-checks].ok').count() == 1
    assert pg.locator('a[href="../entry-animation/index.html"]').count() == 1
    assert '2c' not in pg.title() and '版本 3' in pg.title()
    body = pg.inner_text('body')
    assert '139→140' in pg.inner_text('[data-stair-order]') and '遞補' not in body and '死巷' not in body and '門前' in body


def test_index_mobile_no_hscroll(open_page):          # Review Focus 5
    pg, errs, perrs = open_page('index.html', 375, 700)
    pg.wait_for_selector('[data-checks] .ok', timeout=20000)
    assert no_hscroll(pg) and not perrs
    assert pg.evaluate("[...document.querySelectorAll('[data-stair-order] *')].filter(e=>e.scrollWidth>e.clientWidth+1).length") == 0


def test_fetch_failure_banner(open_page):   # 資料讀不到要有提示橫幅
    pg, *_ = open_page('index.html?data=missing.json', 1280)
    pg.wait_for_selector('#dome-err', timeout=20000)
    assert 'http.server' in pg.inner_text('#dome-err')


def test_data_param_is_not_injected(open_page):   # 錯誤橫幅不得把 ?data= 當 HTML
    payload = '%3Cimg%20src%3Dx%20onerror%3D%22window.__pwned%3D1%22%3E'
    pg, errs, perrs = open_page(f'index.html?data={payload}', 1280)
    pg.wait_for_selector('#dome-err', timeout=20000)
    assert pg.evaluate('window.__pwned') is None
    assert pg.locator('#dome-err img').count() == 0


def test_data_param_rejects_absolute_url(open_page):
    pg, *_ = open_page('index.html?data=https://example.com/x.json', 1280)
    pg.wait_for_selector('#dome-err', timeout=20000)
    assert '相對路徑' in pg.inner_text('#dome-err')


def test_core_names(open_page):
    pg, *_ = open_page('index.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert pg.evaluate('Object.keys(Dome.LANE_NAME)') == ['A', 'B']
    assert pg.evaluate('Object.keys(Dome.ZONE_NAME)') == ['DOOR'] and pg.evaluate('Dome.ZONE_NAME.DOOR') == '門前集合（B2）'
    assert pg.get_attribute('nav.dome-nav', 'aria-label') == '進場動線版本 3 各頁'


def test_index_lane_table_shows_to(open_page):         # spec §6.1：每段寫從哪裡起、到哪裡、人數
    pg, *_ = open_page('index.html', 1280)
    pg.wait_for_selector('[data-checks] .ok', timeout=20000)
    cells = pg.locator('[data-lane-table] tbody td .seg')
    assert cells.count() == 8 and all('到 大隊' in cells.nth(i).inner_text() for i in range(8))
