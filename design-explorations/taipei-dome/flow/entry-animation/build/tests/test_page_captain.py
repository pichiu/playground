"""E 口令卡 captain.html 的頁面測試（共用 conftest 的 server / browser / open_page）。"""
from conftest import no_hscroll


def test_captain_feeder_cohort(open_page):   # 白4 以後：白衣不集結，顯示「白衣接尾中」
    pg, errs, perrs = open_page('captain.html?k=5', 375, 700)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    assert pg.locator('[data-cue]').count() >= 6 and '白衣接尾中' in pg.inner_text('body')
    assert pg.locator('[data-lie]').count() == 6 and no_hscroll(pg)


def test_captain_staged_cohort(open_page):   # 白1–白3：白衣、藍衣各有「到齊」，且有西一入口交接
    pg, errs, perrs = open_page('captain.html?k=2', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert '白衣到齊' in pg.inner_text('body') and '藍衣到齊' in pg.inner_text('body') and '西一入口交接' in pg.inner_text('body')
    assert not perrs


def test_captain_first_cohort_no_handover(open_page):   # 大隊 1 沒有前一大隊，不該有「西一入口交接」；口令依時間排序
    pg, errs, perrs = open_page('captain.html?k=1', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    body = pg.inner_text('body')
    assert '西一入口交接' not in body and '白衣到齊' in body
    ts = pg.locator('[data-cue]').evaluate_all('els => els.map(e => +e.dataset.t)')
    assert len(ts) >= 6 and ts == sorted(ts)
    assert pg.locator('nav.dome-nav a[aria-current=page]').inner_text() == '口令卡'
