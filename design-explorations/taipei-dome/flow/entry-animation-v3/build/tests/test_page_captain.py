"""E 口令卡 captain.html 的頁面測試（共用 conftest 的 server / browser / open_page）。"""
import json

from conftest import no_hscroll

CUES = ['白衣第一位離座', '藍衣第一位離座', '白衣最後一位離座', '藍衣最後一位離座', '第一位過西一入口', '最後一位過西一入口', '全隊到位']


def test_captain_seven_cues(open_page, root):
    D = json.loads((root / 'data.json').read_text(encoding='utf-8'))
    pg, errs, perrs = open_page('captain.html?k=1', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    cues = pg.locator('[data-cue]')
    assert cues.count() == 7
    assert sorted(cues.nth(i).locator('.h').inner_text() for i in range(7)) == sorted(CUES)
    ts = cues.evaluate_all('els => els.map(e => +e.dataset.t)')
    assert ts == sorted(ts)
    ps = [p for p in D['persons'] if p['dadui'] == 1]
    want = {'白衣第一位離座': min(p['t']['leave'] for p in ps if p['costume'] == '白'),
            '最後一位過西一入口': max(p['t']['gate'] for p in ps), '全隊到位': max(p['t']['arrive'] for p in ps)}
    got = dict(zip(cues.evaluate_all("els => els.map(e => e.querySelector('.h').textContent)"), ts))
    assert all(abs(got[k] - v) < 1e-6 for k, v in want.items())
    body = pg.inner_text('body')
    assert not any(w in body for w in ('集結區', '集結等待', '2c', 'C 路'))
    assert pg.locator('[data-lie]').evaluate_all('els => els.map(e => +e.dataset.lie)') == [1, 2, 3, 4, 5, 6]
    assert pg.locator('nav.dome-nav a[aria-current=page]').inner_text() == '口令卡'


def test_captain_split_dadui(open_page, root):          # Review Focus 2：換口的大隊要寫出兩個出口
    D = json.loads((root / 'data.json').read_text(encoding='utf-8'))
    g = next(g for g in D['groups'] if len(g['exits']) > 1)
    pg, _, perrs = open_page(f"captain.html?k={g['dadui']}", 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    text = pg.inner_text('#sum')
    assert all(e['exit'] in text for e in g['exits']) and '兩個出口' in text and not perrs
    lie = next(l for l in g['columns'] if len({p['exit'] for p in D['persons'] if p['lie'] == l}) > 1)
    card = pg.inner_text(f'[data-lie="{lie}"]')
    assert all(e['exit'] in card for e in g['exits'])


def test_captain_mobile(open_page):
    pg, errs, perrs = open_page('captain.html?k=5', 375, 700)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    assert pg.locator('[data-lie]').count() == 6 and no_hscroll(pg)


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
