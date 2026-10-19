"""總覽頁顯示的規則文字必須與程式的路別對應一致（review 發現 RULES[0] 寫成舊對應）。"""
import json
import build
import plan


def test_rules_text_matches_lane_mapping():
    white = '/'.join(f'6k{plan.LANE_COL["白"][L]:+d}'.replace('+', '−').replace('-', '−') for L in 'ABC')   # 6k−5/6k−4/6k−3
    blue = '/'.join((f'6k{plan.LANE_COL["藍"][L]:+d}' if plan.LANE_COL['藍'][L] else '6k').replace('-', '−') for L in 'ABC')   # 6k−2/6k−1/6k
    assert white == '6k−5/6k−4/6k−3' and blue == '6k−2/6k−1/6k'
    assert f'白 {white}' in build.RULES[0] and f'藍 {blue}' in build.RULES[0], build.RULES[0]


def test_data_json_rules_match(root):
    D = json.load(open(root / 'data.json', encoding='utf-8'))
    assert D['meta']['rules'] == build.RULES
