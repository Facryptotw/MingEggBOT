# ⚡ MingEggBOT — 台股處置監控機器人

Discord Bot，自動監控台股處置股動態，每日生成精美圖卡推送至指定頻道。

## 功能

| 模組 | 說明 |
|------|------|
| 🚨 **處置倒數** | 即將被處置的股票，顯示倒數天數 |
| 🔓 **越關越大尾** | 即將出關的股票，含處置前/中漲跌幅比較 |
| 🔒 **還能噴嗎** | 目前正在處置中的股票一覽 |

## 快速開始

### 1. 安裝依賴

```bash
pip install -r requirements.txt
```

### 2. 設定環境變數

複製 `.env.example` 為 `.env`，填入你的設定：

```bash
cp .env.example .env
```

```env
DISCORD_TOKEN=你的Discord Bot Token
DISCORD_CHANNEL_ID=推送頻道ID
SCHEDULE_TIME=19:30
```

### 3. 啟動

```bash
python main.py
```

## 指令

| 指令 | 說明 |
|------|------|
| `/disposition` | 手動觸發處置股監控報告 |

## 排程

Bot 每日於 `SCHEDULE_TIME` 設定的時間（預設 19:30）自動推送報告至指定頻道，週末不推送。

## 資料來源

- [臺灣證券交易所 (TWSE)](https://www.twse.com.tw/)
- [證券櫃檯買賣中心 (TPEX)](https://www.tpex.org.tw/)

## 專案結構

```
MingEggBOT/
├── main.py              # 入口 & Bot 設定
├── config.py            # 環境變數 & 常數
├── services/
│   └── twse.py          # TWSE/TPEX 資料抓取
├── utils/
│   └── image_gen.py     # 圖卡生成器 (Pillow)
├── cogs/
│   └── disposition.py   # Discord 指令 & 排程
├── requirements.txt
├── .env.example
└── .gitignore
```

## 免責聲明

本工具僅供參考，不構成任何投資建議。投資有風險，請自行判斷。
