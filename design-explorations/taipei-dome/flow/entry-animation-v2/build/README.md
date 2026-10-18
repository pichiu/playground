# 藍衣全部 B2 集結版 · 產生腳本

由原版 `../../entry-animation/index.html` 內嵌的 `DATA`(座位、場地幾何、場內路徑)重算:

```bash
# 1. 取出原版資料
sed -n '/^const DATA = /p' ../../entry-animation/index.html | sed 's/^const DATA = //; s/;$//' > old.json
# 2. 重排休息區座位、重算路徑與時間
python3 build.py old.json new.json plan.json
# 3. 檢查「行進中穿過已站定者」人數(應為 0)
python3 check.py new.json
# 4. 產生頁面
python3 page.py ../../entry-animation/index.html new.json ../index.html
# 5. 產生 excel(需 10/17 修正版 xlsx 解壓目錄)
python3 excel.py <解壓目錄> plan.json new.json 休息區座位_藍衣B2集結版_2026-10-18.xlsx
```

需要 Python 3、numpy、Pillow。
