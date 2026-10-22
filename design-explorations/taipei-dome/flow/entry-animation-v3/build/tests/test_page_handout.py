"""講義頁（D，A3 橫式）測試：六格各一張 canvas 都有畫、文字取自資料、手機不橫捲。"""
import json

from conftest import no_hscroll


def _fmt(v):
    return f'{int(v // 60):02d}:{int(v % 60):02d}'


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
    assert _fmt(D['meta']['tGateStart']) in pg.inner_text('figure[data-key="gate"]')
    assert '139' in pg.inner_text('figure[data-key="swapA"]') and '140' in pg.inner_text('figure[data-key="swapA"]')
    assert '144' in pg.inner_text('figure[data-key="swapB"]') and '145' in pg.inner_text('figure[data-key="swapB"]')
    assert '全員到位' in pg.inner_text('figure[data-key="done"]')
    body = pg.inner_text('body')
    assert not any(w in body for w in ('集結區', '白2', '白 2', '2c'))


def test_handout_mobile(open_page):
    pg, errs, perrs = open_page('handout.html', 375, 700)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert no_hscroll(pg) and not perrs


def test_handout_moments_in_time_order(open_page):
    pg, *_ = open_page('handout.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    ts = pg.evaluate("[...document.querySelectorAll('figure[data-key] time')].map(e=>e.textContent)")
    assert ts == sorted(ts), ts
