"""總覽頁顯示的規則文字必須與程式的路別對應一致（review 發現 RULES[0] 寫成舊對應；西一入口交叉修正後藍衣分兩種）。"""
import json
import build
import plan


def _fmt(block):
    k = int(block[1:])
    return '/'.join((f'6k{plan.column_of(block, L) - 6 * k:+d}' if plan.column_of(block, L) != 6 * k else '6k').replace('-', '−') for L in 'ABC')


def test_rules_text_matches_lane_mapping():
    assert _fmt('白1') == '6k−5/6k−4/6k−3' and _fmt('藍1') == '6k−2/6k−1/6k' and _fmt('藍2') == '6k/6k−1/6k−2' == _fmt('藍9')
    assert f"白 {_fmt('白1')}" in build.RULES[0] and f"藍1 {_fmt('藍1')}" in build.RULES[0] and f"藍2–9 從死巷反向走回西一入口，{_fmt('藍2')}" in build.RULES[0], build.RULES[0]


def test_data_json_rules_match(root):
    D = json.load(open(root / 'data.json', encoding='utf-8'))
    assert D['meta']['rules'] == build.RULES
