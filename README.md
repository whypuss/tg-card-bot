# TG Card Bot - VPS 部署總結

## 部署案例

**平台**: Incudal.com Alpine Linux VPS（256MB RAM）
**架構**: Python + requests + sqlite3（非 aiogram，記憶體不夠）

## 成功部署指令

```bash
# 一次性部署（全新 VPS）
wget -O /tmp/final.sh https://raw.githubusercontent.com/whypuss/tg-card-bot/main/scripts/tg-card-bot-final.sh && bash /tmp/final.sh && cd /root/tg-card-bot && python3 bot.py
```

## 踩坑記錄

### Rust 版（失敗）
- Mac 交叉編譯 → OpenSSL 找不到
- VPS 256MB 編譯 Rust → OOM

### Python aiogram 版（失敗）
- 256MB RAM 運行 aiogram + aiohttp → OOM (Killed)

### Python 輕量版（成功）
- requests + 內建 sqlite3，無 async，内存在 30MB 以内

## Bot 功能

| 指令 | 任何人 | 僅管理員 |
|------|--------|---------|
| /start | ✅ | ✅ |
| 任意文字 | ✅ 列出商品 | ✅ |
| 數字 ID | ✅ 購買發貨 | ✅ |

管理員指令：
- `/admin` - 商品列表
- `/stock` - 庫存
- `/orders` - 訂單
- `/add 名稱 價格 數量` - 添加商品
- `/cancel` - 取消當前操作

## 關鍵參數

| 參數 | 值 |
|------|-----|
| getUpdates timeout | 30s（Long Polling） |
| requests timeout | 35s |
| sleep between loops | 0.2s |
| DB close | 每次操作後顯式 close() |

## 配置文件

```bash
# /root/tg-card-bot/.env
BOT_TOKEN=你的TOKEN
ADMIN_ID=你的TG用戶ID
```

## 目錄結構

```
/root/tg-card-bot/
├── bot.py          # 主程序
├── cards.db       # SQLite 數據庫
├── .env            # 配置
└── bot.log         # 日誌
```
