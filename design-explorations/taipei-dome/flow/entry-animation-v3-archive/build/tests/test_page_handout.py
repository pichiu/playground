"""講義頁（D，A3 橫式）測試：六格各一張 canvas 都有畫、文字取自資料、手機不橫捲。"""
import json

from conftest import no_hscroll


def test_handout(open_page, root):
    D = json.loads((root / 'data.json').read_text(encoding='utf-8'))
    pg, errs, perrs = open_page('handout.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    figs = pg.locator('figure[data-key]')
    assert figs.count() == 6
    assert [figs.nth(i).get_attribute('data-key') for i in range(6)] == ['seated', 'form', 'gate', 'swapA', 'swapB', 'done']
    lens = pg.evaluate("Array.from(document.querySelectorAll('figure[data-key] canvas')).map(c=>c.toDataURL().length)")
    assert len(lens) == 6 and all(l > 5000 for l in lens), lens
    assert '139' in pg.inner_text('figure[data-key="swapA"]') and '140' in pg.inner_text('figure[data-key="swapA"]')
    assert '144' in pg.inner_text('figure[data-key="swapB"]') and '145' in pg.inner_text('figure[data-key="swapB"]')
    assert '全員到位' in pg.inner_text('figure[data-key="done"]')
    body = pg.inner_text('body')
    assert not any(w in body for w in ('白2', '白 2', '2c', '遞補', '死巷'))


def test_handout_mobile(open_page):
    pg, errs, perrs = open_page('handout.html', 375, 700)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert no_hscroll(pg) and not perrs


def test_handout_moments_in_time_order(open_page):
    pg, *_ = open_page('handout.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    ts = pg.evaluate("[...document.querySelectorAll('figure[data-key]')].map(e=>+e.dataset.t)")
    assert ts == sorted(ts), ts


def test_handout_survives_fewer_segments(open_page, root):   # final review：座位改了、段數變了，講義不能壞
    D = json.loads((root / 'data.json').read_text(encoding='utf-8'))
    for L, keep in (('A', ['139', '140']), ('B', ['142', '145'])):
        D['lanes'][L]['segments'] = [s for s in D['lanes'][L]['segments'] if s['exit'] in keep]
    tmp = root / 'tmp-handout-test.json'
    tmp.write_text(json.dumps(D, ensure_ascii=False), encoding='utf-8')
    try:
        pg, errs, perrs = open_page('handout.html?data=tmp-handout-test.json', 1280)
        pg.wait_for_function('window.__dome_ready === true', timeout=20000)
        assert not perrs, perrs
        assert '139→140' in pg.inner_text('figure[data-key="swapA"]') and '142→145' in pg.inner_text('figure[data-key="swapB"]')
    finally:
        tmp.unlink()


def test_handout_single_segment_and_go_time(open_page, root):   # review：只有一段時不能寫假換口；出發時刻用門前起步
    D = json.loads((root / 'data.json').read_text(encoding='utf-8'))
    go = min(p['t']['enter'] for p in D['persons'])
    pg, *_ = open_page('handout.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert abs(float(pg.get_attribute('figure[data-key="gate"]', 'data-t')) - go) < 1e-6
    D['lanes']['A']['segments'] = D['lanes']['A']['segments'][:1]
    tmp = root / 'tmp-handout-test2.json'
    tmp.write_text(json.dumps(D, ensure_ascii=False), encoding='utf-8')
    try:
        pg, errs, perrs = open_page('handout.html?data=tmp-handout-test2.json', 1280)
        pg.wait_for_function('window.__dome_ready === true', timeout=20000)
        t = pg.inner_text('figure[data-key="swapA"]')
        assert '139→139' not in t and '不換口' in t and not perrs
    finally:
        tmp.unlink()
