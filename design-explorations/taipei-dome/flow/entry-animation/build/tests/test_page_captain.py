"""E 口令卡 captain.html 的頁面測試（共用 conftest 的 server / browser / open_page）。"""
from conftest import no_hscroll


def test_captain_feeder_cohort(open_page):   # 白4 以後：白衣不集結，顯示「白衣接尾中」
    pg, errs, perrs = open_page('captain.html?k=5', 375, 700)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    assert pg.locator('[data-cue]').count() >= 6 and '白衣接尾中' in pg.inner_text('body')
    assert pg.locator('[data-lie]').count() == 6 and no_hscroll(pg)


def test_captain_staged_cohort(open_page):   # 白1–白3 隊頭站定就起步（邊到邊走），所以是「白衣最後一位到」；藍衣早已站定是「藍衣到齊」；有西一入口交接
    pg, errs, perrs = open_page('captain.html?k=2', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    body = pg.inner_text('body')
    assert '白衣最後一位到' in body and '邊到邊走' in body and '藍衣到齊' in body and '西一入口交接' in body
    assert not perrs


def test_captain_first_cohort_no_handover(open_page):   # 大隊 1 沒有前一大隊，不該有「西一入口交接」；口令依時間排序
    pg, errs, perrs = open_page('captain.html?k=1', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    body = pg.inner_text('body')
    assert '西一入口交接' not in body and '白衣最後一位到' in body
    ts = pg.locator('[data-cue]').evaluate_all('els => els.map(e => +e.dataset.t)')
    assert len(ts) >= 6 and ts == sorted(ts)
    assert pg.locator('nav.dome-nav a[aria-current=page]').inner_text() == '口令卡'


def test_captain_gate_order_follows_data(open_page):   # review：西一入口六路順序要由資料算，藍2–9 的 A 路在最南；六列卡片依 白 A·B·C、藍 A·B·C 排
    pg, errs, perrs = open_page('captain.html?k=1', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert '白 A·B·C、藍 A·B·C' in pg.inner_text('#sum') and not perrs
    assert pg.locator('[data-lie]').evaluate_all('els => els.map(e => +e.dataset.lie)') == [1, 2, 3, 4, 5, 6]
    pg, errs, perrs = open_page('captain.html?k=4', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert '白 A·B·C、藍 C·B·A' in pg.inner_text('#sum') and 'A 路在最南' in pg.inner_text('#sum') and not perrs
    assert pg.locator('[data-lie]').evaluate_all('els => els.map(e => +e.dataset.lie)') == [19, 20, 21, 24, 23, 22]
    assert pg.locator('[data-lie="24"]').inner_text().find('A 路') >= 0


def test_captain_speed_and_labels(open_page):   # 速度預設 ×6、可切換；標籤開關預設關，開了會重畫；手機版時間軸不被擠扁
    pg, errs, perrs = open_page('captain.html?k=1', 375, 700)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    assert pg.locator('#speed button[aria-pressed=true]').inner_text() == '×6'
    pg.click('#speed button[data-s="12"]')
    assert pg.locator('#speed button[aria-pressed=true]').inner_text() == '×12'
    assert pg.get_attribute('#lbl', 'aria-pressed') == 'false'
    pg.click('#lbl')
    assert pg.get_attribute('#lbl', 'aria-pressed') == 'true'
    assert pg.evaluate("document.getElementById('tl').getBoundingClientRect().width") > 150 and no_hscroll(pg)
