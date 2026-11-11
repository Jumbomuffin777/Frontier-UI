---
name: generative-ui-widgets
description: "Use when 回答旅遊/地圖問題：產出照片卡＋即時地圖＋真實路線 widget。"
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [widgets, travel, map, generative-ui, desktop]
    category: productivity
    related_skills: [hermes-desktop-plugins, tui-widgets]
---

# Generative UI Widgets (Frontier-UI 移植版 v2)

用公開免金鑰服務產生 ChatGPT 風格生成式 UI，嵌入 Hermes 聊天（`::preview{file="..."}`）。
移植自 Frontier-UI (MIT, Jumbomuffin777/Frontier-UI)：地圖＝MapLibre GL + OpenFreeMap 向量瓦片、
路線＝OSRM 公開路由、照片＝Wikipedia/Commons/SearXNG、定位＝Wiki 座標→Nominatim→Photon。
已移植 block（對照上游 21 種）：text、images、map(多路線 day-tabs＋GPX)、places、timeline、
budget、calculator、weather、stock、table、compare、steps、callout、hero、quote、stats、
status、links、email、ics、sources、followups。

## When to Use
用戶問旅遊規劃、地點推薦、步行/騎行/自駕路線、地圖視覺化，或要求「像 Frontier-UI 那樣回答」時。

## Procedure

1. 寫出 spec JSON（v2 格式，blocks 數組；上游 examples/ 可參考）：
   ```json
   {
     "title": "兩日遊", "hint": "新北市",
     "blocks": [
       {"type": "hero", "md": "..."},
       {"type": "map", "mode": "car", "hint": "新北市",
        "stops": [{"name": "猴硐貓街", "page": "猴硐貓村", "day": "Day 1", "rating": 4.5, "tags": ["貓村"]}],
        "routes": [{"label": "Day 1", "mode": "car"}, {"label": "Day 2", "mode": "foot"}]},
       {"type": "timeline", "items": [{"time": "09:00", "title": "...", "place": "猴硐貓街", "day": "Day 1"}]},
       {"type": "budget", "items": [{"label": "門票", "min": 0, "max": 200, "value": 90}]},
       {"type": "calculator", "formula": "p*r*i/(1-(1+i)**-n)", "vars": {"p": ["本金", 5000000]}},
       {"type": "weather", "place": "瑞芳區"},
       {"type": "stock", "symbols": [{"sym": "2330.TW"}, {"sym": "BTC-USD"}]},
       {"type": "table", "headers": ["站點", "門票"], "rows": [["猴硐", "免費"]]},
       {"type": "email", "to": "...", "subject": "...", "body": "..."},
       {"type": "ics", "title": "...", "start": "20261121T0900", "end": "20261121T1100", "place": "猴硐"}
     ],
     "sources": [{"title": "維基百科", "url": "https://..."}],
     "followups": ["改成兩天一夜"]
   }
   ```
   規則：stops 的 day 值必須等於對應 routes[i].label（day-tabs 連動）；timeline 的 place 必須與
   stop 名完全相同（點行→閃 pin）；place 的 page=維基條目名（geocode 最穩來源，地名歧義時必給，
   如「猴硐貓街」→ page「猴硐貓村」）；hint=城市（Nominatim countrycodes 判斷用）。
2. 執行管線：`python3 scripts/build_widget.py spec.json out.html`
   （geocode→OSRM→weather/stock→照片→渲染；印出每 leg 距離/時間＋定位備註，直接拿来寫文字時間表）
3. 驗證渲染（見 Verification），再用 `::preview{file="out.html 絕對路徑"}` 交付。
4. 同時給文字摘要（距離/時間/站數/花費），widget 只是視覺層。
5. 用戶按 widget 按鈕後 `data-hermes-send` 原文以用戶訊息送達，按內容分派：
   「用預覽瀏覽器開啟這個網頁：<url>」→ desktop_preview(open)+read 確認；
   「輸出成 GPX/ICS 檔案…」→ 依訊息內座標寫 .gpx/.ics，MEDIA: 交付；
   「發 Gmail 草稿…」→ 輸出 mailto 連結或請用戶確認內容。
   followups 按鈕文字要寫成當下可直接執行重排的指令。

## Valves
- mode = foot|bike|car（OSRM routed-foot/bike/car）。多日行程用 routes 數組，每 route 一個 mode。
- 地圖樣式 `tiles.openfreemap.org/styles/liberty`；乾淨底圖改 positron。
- 照片優先序：wiki summary → 本地 SearXNG（見 memory，192.168.100.212:4000，spec 加 "searxng": "http://..."）→ Commons。
- stock=Yahoo Finance chart API（1D/1M/1Y SVG）；weather=open-meteo。

## Pitfalls
- **地名歧義**：Nominatim 會命中同名遠地（猴硐→嘉義、國父紀念館→舊金山）。帶 page（維基條目）
  給座標最穩；腳本有 consensus 修正（全站中位數 clustering，離群的自動改選候選），但 spec 給對
  page 才是正解。geocode 失敗訊息會提示加 page 或 lat/lon。
- **沙箱死連結**：`::preview` iframe 只有 `sandbox="allow-scripts"`——`<a href>`、window.open、
  blob 下載、剪貼簿全部靜默失靈，只有 data-hermes-send 通。模板內所有可點元素一律發 prompt。
- **JS 大括號**：絕不用 f-string 生成 HTML/JS；一律 templates/widget.html `__TOKEN__` 替換。
- **交付前 node --check**：腳本內建抽取 inline script 檢查，沒過別交付。
- **改源頭不改產物**：文字錯誤改 spec.json 重跑管線，別手改 HTML。
- **簡繁檢查**：所有產出字串必須繁體台灣用語；維基/OSM 來源常混簡體（猫→貓），交付前掃一輪。
- **公版端點公平使用**：OSRM/Nominatim 限流；一次 widget 查一輪，結果存 scratch。
- **widget 尺寸**：外層 `.wrap` 固定 760px；顏色只用 theme vars，不設 body 背景。
- **vision_analyze 可能 404**：渲染驗證走 DOM/網路，不看截圖。
- **tab/timeline 連動**：stops.day==route.label、timeline.place==stop.name，大小寫空格都要一致；
  對不上的话 day-tabs 篩選會漏行（腳本會 note）。

## Verification
瀏覽器開 file:// 後用 js() 確認：
- `!!document.querySelector('#map canvas')` → true；`.pin` 數 == 站數
- 初始態：可見 pin/tl 行數 == 第一日站數/行數（day-tabs 初始篩選生效）
- 切 tab → pin 數變化；點 timeline 行 → `.pin.hi` == 1
- budget `.tot b`、calculator `.res b` 有計算值；stock `svg.on` 每檔 1 個
- 照片 naturalWidth>0；`performance.getEntriesByType('resource')` 有 openfreemap 與 wikimedia

## 上游同步
本 skill 的源頭是 `/root/opencode-stuffs/Frontier-UI/hermes-port/`（純附加目錄，
不改上游任何檔案；sync.sh 同步到這裡）。上游更新：git pull 後 diff src/，port 端只動 hermes-port/。
