# 藍衣全部 B2 集結版 · 產生腳本

由原版 `../../entry-animation/index.html` 內嵌的 `DATA`(座位、場地幾何、場內路徑)重算:

```bash
# 1. 取出原版資料
sed -n '/^const DATA = /p' ../../entry-animation/index.html | sed 's/^const DATA = //; s/;$//' > old.json
# 2. 重排休息區座位、重算路徑與時間
python3 build.py old.json new.json plan.json ../休息區座位_藍衣B2集結版.csv
# 3. 碰撞檢查(兩項都必須是 0,否則 exit 1):行進中穿過已站定者(含同一列)、兩個走路的人互撞(全程)
python3 check.py new.json
# 4. 產生頁面
python3 page.py ../../entry-animation/index.html new.json ../index.html
# 5. 產生 excel(需 10/17 修正版 xlsx 解壓目錄,當版面底稿)
python3 excel.py <解壓目錄> plan.json new.json 休息區座位_藍衣B2集結版_2026-10-18.xlsx
```

## 檔案分工

- **git**：產生腳本，以及座位表 `../休息區座位_藍衣B2集結版.csv`（每人的集結區與休息座位，一人一列）。
  改排法時，PR 上可以逐行看出誰換了座位；模擬時間不寫進這個檔。
- **Google Drive**：excel（`休息區座位_藍衣B2集結版_*.xlsx`）由上面第 5 步產生，只放在 Drive 發放，**不進 git**
  （二進位檔看不出差異，而且它的版面底稿 10/17 修正版 xlsx 不在 repo 裡）。
  更新時在 Drive 對既有檔案用「管理版本 → 上傳新版本」，連結不變。

需要 Python 3、numpy、Pillow。build.py 含避撞迭代與收尾全程碰撞自我檢查(與 check.py 同一套判定,見 `collide.py`),約 1 分鐘;check.py 約 30 秒。
