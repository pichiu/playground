import json
import subprocess
import sys


def test_cli_writes_plan(root, tmp_path):
    out = tmp_path / 'plan.json'
    r = subprocess.run([sys.executable, 'plan.py', 'base.json', str(out)], cwd=root / 'build', capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    P = json.loads(out.read_text(encoding='utf-8'))
    assert set(P) == {'blocks', 'lanes', 'exits', 'people'} and len(P['people']) == 1609 and len(P['blocks']) == 18
    assert [len(P['lanes'][L]['segments']) for L in 'ABC'] == [3, 3, 3]
    assert P['exits']['139']['used'] == 199 and P['exits']['139']['rows'][0]['pai'] == 12
    assert P['lanes']['A']['segments'][0] == dict(exit='139', fromBlock='藍9', toBlock='藍3', n=199, fromIdx=0, toIdx=198)
    assert P['blocks'][0]['key'] == '藍9' and P['blocks'][0]['lanes']['A'] == dict(lie=54, exit='139', n=18) and P['blocks'][0]['lanes']['C']['lie'] == 52
