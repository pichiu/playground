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
    assert P['exits']['139']['used'] == 226 and P['exits']['139']['rows'][0]['pai'] == 12
    assert P['lanes']['A']['segments'][0] == dict(exit='139', fromBlock='藍9', toBlock='藍2', n=226, fromIdx=0, toIdx=225,
                                                fromLabel='藍9', toLabel='藍2（前段）', label='藍9 … 藍2（前段）')
    assert P['blocks'][0]['key'] == '藍9' and P['blocks'][0]['lanes']['A'] == dict(lie=54, n=18, exits=[dict(exit='139', n=18)]) and P['blocks'][0]['lanes']['C']['lie'] == 52
