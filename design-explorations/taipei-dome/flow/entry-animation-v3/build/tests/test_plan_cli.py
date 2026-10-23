import json
import subprocess
import sys


def test_cli_writes_plan(root, tmp_path):
    out = tmp_path / 'plan.json'
    r = subprocess.run([sys.executable, 'plan.py', 'base.json', str(out)], cwd=root / 'build', capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert '1609 人' in r.stdout
    P = json.loads(out.read_text(encoding='utf-8'))
    assert set(P) == {'groups', 'lanes', 'exits', 'people'} and len(P['people']) == 1609 and len(P['groups']) == 18
    assert [g['key'] for g in P['groups'][:3]] == ['白1', '藍1', '白2']
    assert P['groups'][0]['columns'] == [1, 2, 3] and P['groups'][0]['lane'] == 'A' and P['groups'][0]['exits'] == [dict(exit='139', n=87)]
    s = P['lanes']['A']['segments'][0]
    assert (s['exit'], s['fromIdx'], s['toIdx'], s['n']) == ('139', 0, 225, 226) and s['from']['dadui'] == 1 and s['to']['dadui'] == 3
    assert P['exits']['139']['used'] == 226 and P['exits']['139']['rows'][0]['pai'] == 12
