# 香港護士空缺 nursejob-hk

Netlify-deployable version of the Hong Kong nurse vacancy aggregator.
Stateless pipeline: scrapers write `data/jobs.json`, the site builder
generates `dist/index.html` + `dist/version.json`.

## 架構

- `scraper/` — 5 個來源爬蟲（勞工處 gov、明報 JUMP、CTgoodjobs、公務員事務局 csb、保良局 plk）
- `scraper/run.py` — 全量更新：跑晒 5 個來源，寫入 `data/jobs.json`
  （某來源 `fetched=0` 或出錯時，沿用上一次 committed 嘅 `data/jobs.json` 入面該來源舊資料）
- `site/build.py` — 讀 `data/jobs.json`，輸出 `dist/index.html` + `dist/version.json`，複製 `assets/`
- `netlify/functions/trigger-update.js` — 手動更新按鈕用嘅 endpoint（10 分鐘 rate limit），觸發 Netlify build hook
- `netlify/functions/scheduled-update.js` — 每日 01:00 UTC（= 09:00 HKT）自動觸發 build hook
- `build.sh` — Netlify build command：`pip install → scraper/run.py → site/build.py`

## Setup 步驟

1. **GitHub**：開一個新 repo（例如 `nursejob-hk`），將呢個目錄 push 上去。
   `data/jobs.json` 要一齊 commit（佢係 fallback 用嘅 baseline 資料）。
2. **Netlify Team**：Add site → Import an existing project → 揀 GitHub repo。
   Build settings 會自動讀 `netlify.toml`：
   - Build command: `bash build.sh`
   - Publish directory: `dist`
   - Functions directory: `netlify/functions`
3. **Build hook**：Netlify 後台 Site settings → Build & deploy → Build hooks → Add build hook，
   抄低個 URL。
4. **環境變數**：Site settings → Environment variables → 新增
   `BUILD_HOOK_URL` = 上一步個 build hook URL。
   （trigger-update function 同 scheduled function 都靠佢嚟觸發 rebuild）
5. **（可選）自訂域名**：Domain settings → Add custom domain，
   將 `nursejob.ddns.net` 嘅 DNS 指去 Netlify（CNAME / Netlify DNS），等 SSL 生效。

## 手動「更新職位」按鈕

- 按鈕預設隱藏；管理員喺瀏覽器 console 執行
  `localStorage.setItem('nj_admin','1')` 後再 load 頁就會見到。
- 撳掣 → POST `/.netlify/functions/trigger-update` → polling `/version.json`
  等 `built_at` 變化 → 顯示「✅ 已更新 N 個」→ reload。
- 成功後 60 秒冷卻倒數；function 端另有 10 分鐘 rate limit。

## 本地測試

```bash
bash build.sh        # 實抓 5 個來源，輸出 dist/
open dist/index.html
```
