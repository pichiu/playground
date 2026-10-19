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


def test_me_waits_for_data_then_applies_typed_id(server, browser):   # review：載入前按「查」要有回饋，載入後套用已輸入的列排
    ctx = browser.new_context(viewport={'width': 375, 'height': 700})
    try:
        pg = ctx.new_page()
        held = []
        pg.route('**/data.json', lambda route: held.append(route))   # 先扣住 data.json
        pg.goto(server + 'me.html', wait_until='domcontentloaded')
        for _ in range(100):
            if held:
                break
            pg.wait_for_timeout(50)
        assert held, 'data.json 沒被要求'
        assert pg.is_visible('#load') and pg.is_disabled('#go')
        pg.fill('#lie', '1')
        pg.fill('#pai', '28')
        pg.press('#pai', 'Enter')
        pg.click('#go', force=True)
        assert pg.locator('[data-step]').count() == 0 and pg.is_visible('#load')
        for r in held:
            r.continue_()
        pg.wait_for_selector('[data-step="到"]', timeout=20000)
        assert pg.is_enabled('#go') and pg.is_hidden('#load')
        assert '140' in pg.inner_text('[data-step="起"]')
    finally:
        ctx.close()


def test_me_feeder_steps_have_distinct_times(open_page, root):   # review：接尾者的「集」與「進」不可同一時刻，否則「集」永遠不會是目前這一步
    import json
    D = json.loads((root / 'data.json').read_text(encoding='utf-8'))
    pid = next(p['id'] for p in D['persons'] if p['assembly'] == 'FEEDER')
    pg, errs, perrs = open_page(f'me.html?id={pid}', 375, 700)
    pg.wait_for_selector('[data-step="到"]', timeout=20000)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert '不集結' in pg.inner_text('[data-step="集"]')
    pg.click('[data-step="集"]')
    pg.wait_for_selector('.step.now[data-step="集"]', timeout=3000)
    pg.click('[data-step="進"]')
    pg.wait_for_selector('.step.now[data-step="進"]', timeout=3000)
    assert not perrs, perrs
