"""我的路頁（me.html）測試：六步口令卡、找不到時的提示、375px 無橫向捲動。"""
from conftest import no_hscroll


def test_me_card(open_page):
    pg, errs, perrs = open_page('me.html?id=1-28', 375, 700)
    pg.wait_for_selector('[data-step="到"]', timeout=20000)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    assert pg.locator('[data-step]').count() == 6 and '140' in pg.inner_text('[data-step="起"]')
    assert no_hscroll(pg)


def test_me_invalid_input(open_page):   # Review Focus 4
    for q in ['55-1', '1-99', '１-２８', '-', '']:
        pg, errs, perrs = open_page(f'me.html?id={q}', 375, 700)
        pg.wait_for_selector('#notfound', state='visible', timeout=20000)
        assert not perrs, (q, perrs)


def test_me_form_fullwidth(open_page):   # 手動輸入全形數字也要查得到
    pg, errs, perrs = open_page('me.html', 375, 700)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    pg.fill('#lie', '１')
    pg.fill('#pai', '２８')
    pg.click('form button')
    pg.wait_for_selector('[data-step="到"]', timeout=20000)
    assert not perrs, perrs
    assert '140' in pg.inner_text('[data-step="起"]')
    assert pg.locator('#notfound').is_hidden()
