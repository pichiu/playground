import json
import subprocess
import sys

import pytest

import check


@pytest.fixture(scope='session')
def built(pipeline):
    return pipeline


def test_check_all_green(built):
    tmp, D = built
    C = check.check_all(D)
    assert C['ok'], json.dumps({k: v for k, v in C.items() if k != 'capacity'}, ensure_ascii=False)[:3000]
    assert C['collisions']['standing'] == 0 == C['collisions']['walking'] and C['nesting']['violations'] == 0
    assert all(0.25 <= v['minGap'] and v['maxGapWithin'] <= 0.55 for v in C['continuity']['gate'].values())
    assert C['seats']['unique'] == 1609 and C['seats']['illegal'] == 0 and C['seats']['orderViolations'] == 0
    assert C['staging']['ok'] and all(v['used'] <= v['capacity'] for v in C['capacity'].values())
    assert D['meta']['checks']['ok'] is True and D['meta']['checks']['nesting'] == C['nesting']


def test_check_cli_exit_code(built):
    tmp, _ = built
    r = subprocess.run([sys.executable, 'check.py', str(tmp / 'data.json')], capture_output=True, text=True, cwd=check.__file__.rsplit('/', 1)[0])
    assert r.returncode == 0, r.stdout + r.stderr
    assert '通過' in r.stdout


def test_check_detects_tampering(built):
    _, D = built
    D = json.loads(json.dumps(D))
    a = next(p for p in D['persons'] if p['lane'] == 'A' and p['laneIdx'] == 0)
    c = next(p for p in D['persons'] if p['lane'] == 'C' and p['laneIdx'] == 0)
    a['exit'], c['exit'] = c['exit'], a['exit']
    C = check.check_all(D)
    assert C['nesting']['violations'] > 0 and C['ok'] is False
