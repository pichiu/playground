"""C 總譜頁測試（共用 conftest 的 server / browser / open_page）。"""
from conftest import no_hscroll


def test_score(open_page):
    pg, errs, perrs = open_page('score.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs, (errs, perrs)
    rows = pg.locator('[data-row]')
    assert rows.count() == 54
    assert [rows.nth(i).get_attribute('data-lie') for i in range(7)] == ['1', '2', '3', '4', '5', '6', '7']   # 樓梯序：大隊 1 白三列、藍三列，再大隊 2
    s = pg.inner_text('#summary')
    assert '門前' in s and '最久' in s
    assert '集結' not in pg.inner_text('body') and '2c' not in pg.inner_text('h1')


def test_score_mobile(open_page):
    pg, errs, perrs = open_page('score.html', 375, 700)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert no_hscroll(pg) and not perrs


def test_score_row_labels_do_not_overlap_group_labels(open_page):   # 分坐兩出口的列標籤較長，不可蓋到左側大隊標籤
    pg, *_ = open_page('score.html', 1280)
    pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    hit = pg.evaluate("""(()=>{const g=[...document.querySelectorAll('#labels .grp')].map(e=>e.getBoundingClientRect());
      return [...document.querySelectorAll('[data-row]')].filter(e=>{const r=e.getBoundingClientRect();
        const rg=document.createRange();rg.selectNodeContents(e);const left=rg.getBoundingClientRect().left;
        return g.some(b=>b.top<r.bottom&&b.bottom>r.top&&left<b.right-1);}).length;})()""")
    assert hit == 0
