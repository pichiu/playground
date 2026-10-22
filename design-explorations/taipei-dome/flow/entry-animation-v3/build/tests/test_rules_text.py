"""總覽頁顯示的規則文字必須與程式一致。"""
import json
import build


def test_rules_text_words():
    text = '\n'.join(build.RULES)
    assert all(w in text for w in ('白衣', '藍衣', '坐滿', '142', '139 → 140 → 141 → 142', '142 → 143 → 144 → 145'))
    assert not any(w in text for w in ('集結區', '遞補', '死巷', 'C 路'))


def test_data_json_rules_match(root):
    D = json.load(open(root / 'data.json', encoding='utf-8'))
    assert D['meta']['rules'] == build.RULES
