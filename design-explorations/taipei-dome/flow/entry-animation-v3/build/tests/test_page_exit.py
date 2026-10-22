"""F 出口帶隊卡（exit.html）頁面測試。"""
import json

from conftest import no_hscroll


def _data(root):
    return json.loads((root / 'data.json').read_text(encoding='utf-8'))


def test_exit_141(open_page, root):
    D = _data(root)
    e = next(e for e in D['exits'] if e['key'] == '141')
    pg, errs, perrs = open_page('exit.html?e=141', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    assert pg.locator('[data-exit]').count() == 7 and pg.locator('[data-row]').count() == len(e['rows'])
    assert pg.locator('[data-seg]').count() == 1 and pg.get_attribute('[data-seg]', 'data-seg') == 'A'
    txt = pg.inner_text('main')
    assert '換 142 出口接 A 路' in txt and '接在 140 出口' in txt
    assert pg.locator('canvas#seatmap').count() == 1 and '2c' not in txt and '藍9' not in txt


def test_exit_142_two_segments(open_page):              # Review Focus 1：142 先供 B 路、再供 A 路，中間有空檔
    pg, errs, perrs = open_page('exit.html?e=142', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    segs = pg.locator('[data-seg]')
    assert segs.count() == 2
    assert segs.nth(0).get_attribute('data-seg') == 'B' and segs.nth(1).get_attribute('data-seg') == 'A'
    txt = pg.inner_text('main')
    assert '本出口改供 A 路' in txt and '空檔' in txt and '換 143 出口接 B 路' in txt and 'A 路到此結束' in txt
    assert not errs and not perrs, (errs, perrs)


def test_exit_145_last_row_has_empty(open_page):
    pg, errs, perrs = open_page('exit.html?e=145', 375, 700)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    rows = pg.locator('[data-row]')
    assert '空' in rows.nth(rows.count() - 1).inner_text()
    assert no_hscroll(pg) and not perrs


def test_exit_pick_button_switches(open_page, root):
    D = _data(root)
    e = next(e for e in D['exits'] if e['key'] == '144')
    pg, errs, perrs = open_page('exit.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    pg.click('[data-exit="144"]')
    assert pg.locator('[data-exit="144"][aria-pressed="true"]').count() == 1
    assert pg.locator('[data-row]').count() == len(e['rows']) and '144 出口' in pg.inner_text('main h1')
    assert '?e=144' in pg.url
    assert not errs and not perrs, (errs, perrs)


def test_seatmap_tip_on_click(open_page, root):
    D = _data(root)
    e = next(e for e in D['exits'] if e['key'] == '141')
    p = next(p for p in D['persons'] if p['id'] == e['order'][0])
    pg, errs, perrs = open_page('exit.html?e=141', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    pt = pg.evaluate(f"window.__seatXY('141', {p['rest']['pai']}, {p['rest']['no']})")
    pg.locator('canvas#seatmap').click(position={'x': pt[0], 'y': pt[1]})
    tip = pg.inner_text('#seat-tip')
    assert f"141 區 {p['rest']['pai']} 排 {p['rest']['no']} 號" in tip and p['id'] in tip and '走 A 路' in tip
    assert not errs and not perrs, (errs, perrs)
