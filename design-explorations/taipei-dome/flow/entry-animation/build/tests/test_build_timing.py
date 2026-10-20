import csv
import json
import subprocess
import sys

COLUMNS = ['位置編碼', '衣色', '大隊', '演繹列', '演繹位置', '休息區', '休息排', '座號', '出口', '出口帶隊序',
           '樓梯路', '樓梯序號', '欄內順序', '集結區', '西一入口路', '西一入口序號']


def test_build_no_avoid(root, tmp_path):
    b = root / 'build'
    subprocess.run([sys.executable, 'plan.py', 'base.json', str(tmp_path / 'plan.json')], cwd=b, check=True)
    r = subprocess.run([sys.executable, 'build.py', 'base.json', str(tmp_path / 'plan.json'), str(tmp_path / 'data.json'),
                        str(tmp_path / 'seats.csv'), '--no-avoid'], cwd=b, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-3000:]
    D = json.loads((tmp_path / 'data.json').read_text(encoding='utf-8'))
    P = {p['id']: p for p in D['persons']}
    assert len(P) == 1609 and abs(min(p['t']['leave'] for p in P.values()) - 6.73) < 1e-6
    for p in P.values():
        t = p['t']
        assert t['leave'] <= t['assembly'] <= t['enter'] <= t['gate'] <= t['arrive'], p['id']
        assert p['path'][0][:2] == [p['rest']['X'], p['rest']['Y']] and p['path'][-1][2] == t['arrive']
        assert all(b[2] >= a[2] for a, b in zip(p['path'], p['path'][1:])), p['id']
    for j in range(6):                                   # 同大隊內 0.4 不斷拍；大隊交界六路對齊，可有 ≤ 4 秒的對齊空檔
        ps = sorted((p for p in P.values() if p['gateLane'] == j), key=lambda p: p['gateIdx'])
        for a, b in zip(ps, ps[1:]):
            gap = b['t']['gate'] - a['t']['gate']
            if a['dadui'] == b['dadui']:
                assert abs(gap - 0.4) < 1e-6, (a['id'], b['id'], gap)
            else:
                assert 0.4 - 1e-6 <= gap <= 5.0, (a["id"], b["id"], gap)
    w4 = [p for p in P.values() if p['dadui'] >= 4 and p['costume'] == '白']
    assert all(p['t']['assembly'] == p['t']['enter'] for p in w4)
    staged = [p for p in P.values() if p['assembly'] != 'FEEDER']
    assert all(p['t']['enter'] >= p['t']['assembly'] + 0.6 - 1e-6 for p in staged)
    assert all('stairPlan' in p['t'] for p in staged) and all('stairPlan' not in p['t'] for p in w4)
    assert set(D) >= {'meta', 'phases', 'nodes', 'map', 'restSeats', 'exits', 'lanes', 'groups', 'files', 'persons', 'others', 'stairSlots', 'zones'}
    assert len(D['exits']) == 7 and len(D['groups']) == 18 and len(D['files']) == 54 and D['meta']['population'] == 1609
    assert sum(1 for s in D['restSeats'] if s['who']) == 1609 and D['meta']['tEnd'] == max(p['t']['arrive'] for p in P.values())
    assert [k['key'] for k in D['phases']] == ['seated', 'descend', 'enter']
    assert all(a['t1'] == b['t0'] for a, b in zip(D['phases'], D['phases'][1:]))
    # 兩個時鐘重疊：大隊 1 不等全部集結完就出發，樓梯在白3 與白4 之間不留大空檔
    assert D['meta']['tGateStart'] < max(p['t']['assembly'] for p in staged)
    G = {g['key']: g for g in D['groups']}
    assert G['白4']['tStairFirst'] - G['白3']['tStairLast'] < 10
    for L in 'ABC':                                      # 每一路：接尾者過樓梯口仍在最後一位集結者之後
        last = max(p['t']['stairPlan'] for p in staged if p['lane'] == L)
        assert min(p['t']['enter'] for p in w4 if p['lane'] == L) >= last + 0.4 - 1e-6, L
    rows = list(csv.DictReader(open(tmp_path / 'seats.csv', encoding='utf-8')))
    assert len(rows) == 1609 and list(rows[0]) == COLUMNS
    assert rows[0]['位置編碼'] == '1-1' and rows[0]['出口'] == '140'
