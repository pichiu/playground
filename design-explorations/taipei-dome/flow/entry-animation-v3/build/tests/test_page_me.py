"""我的路頁（me.html）測試：五步口令卡、找不到時的提示、375px 無橫向捲動。"""
from conftest import no_hscroll


def test_me_card(open_page):
    pg, errs, perrs = open_page('me.html?id=1-28', 375, 700)
    pg.wait_for_selector('[data-step="到"]', timeout=20000)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    assert pg.locator('[data-step]').count() == 5 and '139' in pg.inner_text('[data-step="起"]')
    assert [pg.locator('[data-step]').nth(i).get_attribute('data-step') for i in range(5)] == ['起', '出', '走', '進', '到']
    assert '集結' not in pg.inner_text('#steps') and '白衣' in pg.inner_text('[data-step="走"]')
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
    assert '139' in pg.inner_text('[data-step="起"]')
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
        assert '139' in pg.inner_text('[data-step="起"]')
    finally:
        ctx.close()


def test_me_split_column_person(open_page, root):      # Review Focus 2：一列分坐兩個出口，各自顯示自己的出口
    import json
    D = json.loads((root / 'data.json').read_text(encoding='utf-8'))
    lie = next(l for l in range(1, 55) if len({p['exit'] for p in D['persons'] if p['lie'] == l}) > 1)
    ps = [p for p in D['persons'] if p['lie'] == lie]
    exits = sorted({p['exit'] for p in ps})
    for e in exits:
        p = next(q for q in ps if q['exit'] == e)
        pg, _, perrs = open_page(f"me.html?id={p['id']}", 1280)
        pg.wait_for_selector('[data-step="出"]', timeout=20000)
        assert f"{e} 出口第 {p['exitSeq'] + 1} 位" in pg.inner_text('[data-step="起"]') and not perrs
        other = [x for x in exits if x != e][0]
        assert f"{other} 出口" in pg.inner_text('[data-step="起"]')       # 提醒同一列另一半在別的出口


def test_me_ahead_may_be_other_column(open_page, root):   # 交錯排隊：同一路前一位通常是別列的人
    import json
    D = json.loads((root / 'data.json').read_text(encoding='utf-8'))
    by = {(p['lane'], p['laneIdx']): p for p in D['persons']}
    p = by[('A', 1)]
    ahead = by[('A', 0)]
    pg, _, perrs = open_page(f"me.html?id={p['id']}", 375, 700)
    pg.wait_for_selector('[data-step="走"]', timeout=20000)
    assert ahead['id'] in pg.inner_text('[data-step="走"]') and not perrs
