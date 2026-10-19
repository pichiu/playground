"""講義頁（D，A3 橫式）測試：六格各一張 canvas 都有畫、文字取自資料、手機不橫捲。"""
from conftest import no_hscroll


def test_handout(open_page):
    pg, errs, perrs = open_page('handout.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    assert pg.locator('figure[data-key]').count() == 6
    lens = pg.evaluate("Array.from(document.querySelectorAll('figure[data-key] canvas')).map(c=>c.toDataURL().length)")
    assert len(lens) == 6 and all(l > 5000 for l in lens), lens
    assert '全員到位' in pg.inner_text('figure[data-key="done"]')


def test_handout_mobile(open_page):
    pg, errs, perrs = open_page('handout.html', 375, 700)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert no_hscroll(pg) and not perrs
