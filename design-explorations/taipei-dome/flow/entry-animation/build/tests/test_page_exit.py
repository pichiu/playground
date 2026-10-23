"""F 出口帶隊卡（exit.html）頁面測試。"""
from conftest import no_hscroll


def test_exit_141(open_page):
    pg, errs, perrs = open_page('exit.html?e=141', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    assert pg.locator('[data-exit]').count() == 7 and pg.locator('[data-row]').count() == 12
    assert '藍9' in pg.inner_text('[data-row] >> nth=0') and pg.locator('[data-handover]').count() >= 1
    assert pg.locator('canvas#seatmap').count() == 1


def test_exit_143_last_row_has_empty(open_page):                # 保留不坐之後只剩 143 有空席（6 席）
    pg, errs, perrs = open_page('exit.html?e=143', 375, 700)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    rows = pg.locator('[data-row]')
    assert '空' in rows.nth(rows.count() - 1).inner_text()
    assert no_hscroll(pg) and not perrs


def test_exit_141_handover_text_and_switch(open_page):
    """141 先供 B 路（藍9…藍1 前段）再供 A 路（白9 後段）：要有「換 142 接 B 路」、「本出口改供 A 路」、「A 路到此結束」。"""
    pg, errs, perrs = open_page('exit.html?e=141', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    txt = pg.inner_text('main')
    assert '藍1（前段） 最後一位' in txt and '換 142' in txt and '接 B 路' in txt and '藍1（後段） 起' in txt
    assert '改供 A 路' in txt and '白9（後段） 起' in txt
    assert 'A 路到此結束' in txt
    assert not errs and not perrs, (errs, perrs)


def test_exit_pick_button_switches(open_page):
    pg, errs, perrs = open_page('exit.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    pg.click('[data-exit="144"]')
    assert pg.locator('[data-exit="144"][aria-pressed="true"]').count() == 1
    assert pg.locator('[data-row]').count() == 8 and '144 出口' in pg.inner_text('main h1')
    assert '?e=144' in pg.url
    assert not errs and not perrs, (errs, perrs)


def test_seatmap_tip_on_click(open_page):
    pg, errs, perrs = open_page('exit.html?e=141', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    # 透過頁面暴露的座標查詢點到 141 區 12 排 4 號（53-1，本出口第 1 位）
    pt = pg.evaluate("window.__seatXY('141', 12, 4)")
    pg.locator('canvas#seatmap').click(position={'x': pt[0], 'y': pt[1]})
    tip = pg.inner_text('#seat-tip')
    assert '141 區 12 排 4 號' in tip and '53-1' in tip and '大隊 9藍' in tip and '走 B 路' in tip
    assert not errs and not perrs, (errs, perrs)
