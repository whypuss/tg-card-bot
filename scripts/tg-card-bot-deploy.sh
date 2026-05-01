#!/bin/bash
set -e
echo "========== TG Card Bot 一鍵部署 =========="

# 1. 創建目錄
echo "[1/5] 創建目錄..."
mkdir -p /root/tg-card-bot

# 2. 安裝依賴
echo "[2/5] 安裝 Python + requests..."
apk add --no-cache python3 py3-pip > /dev/null 2>&1
pip3 install requests --break-system-packages --quiet 2>/dev/null

# 3. 寫入 bot.py
echo "[3/5] 寫入 bot.py..."
cat > /root/tg-card-bot/bot.py << 'PYEOF'
#!/usr/bin/env python3
import os, time, random, sqlite3, re, requests

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = "/root/tg-card-bot/cards.db"

def db_exec(sql, args=()):
    conn = sqlite3.connect(DB_PATH); conn.execute(sql, args); conn.commit(); conn.close()

def db_query(sql, args=(), one=True):
    conn = sqlite3.connect(DB_PATH); cur = conn.execute(sql, args); rows = cur.fetchall(); cur.close(); conn.close()
    return rows[0] if one and rows else rows

def init_db():
    db_exec("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, price REAL NOT NULL, stock INTEGER NOT NULL DEFAULT 0, card TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT (datetime('now')))")
    db_exec("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, pid INTEGER, card TEXT, created_at TEXT DEFAULT (datetime('now')))")

def send_msg(chat_id, text, parse_mode=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode: payload["parse_mode"] = parse_mode
    try: requests.post(url, json=payload, timeout=10)
    except: pass

admin_state = {}

def process_update(update):
    if "message" not in update: return
    msg = update["message"]; text = msg.get("text","").strip(); chat_id = msg["chat"]["id"]; uid = msg["from"]["id"]

    if text == "/start":
        send_msg(chat_id, "🦀 TG Card Bot 已就緒\n\n直接發數字 ID 購買\n或發任意文字查看商品列表\n\n/admin - 商品\n/stock - 庫存\n/orders - 訂單\n/add 名稱 - 添加商品")
        return

    if text == "/cancel":
        admin_state.pop(uid, None)
        send_msg(chat_id, "✅ 已取消")
        return

    if text == "/admin" and uid == ADMIN_ID:
        rows = db_query("SELECT id, name, price, stock FROM products", one=False)
        send_msg(chat_id, "📦 無商品" if not rows else "📦 商品列表：\n\n" + "\n".join([f"{r[0]}. {r[1]} (¥{r[2]}) x{r[3]}" for r in rows]))
        return

    if text == "/stock" and uid == ADMIN_ID:
        rows = db_query("SELECT id, name, stock FROM products", one=False)
        send_msg(chat_id, "📦 無商品" if not rows else "📦 庫存：\n\n" + "\n".join([f"{r[0]}. {r[1]} 剩 {r[2]}" for r in rows]))
        return

    if text == "/orders" and uid == ADMIN_ID:
        rows = db_query("SELECT o.id, o.uid, p.name, o.card, o.created_at FROM orders o LEFT JOIN products p ON o.pid = p.id ORDER BY o.id DESC LIMIT 20", one=False)
        send_msg(chat_id, "📋 無訂單" if not rows else "📋 訂單：\n\n" + "\n".join([f"#{r[0]} uid:{r[1]} {r[2] or '?'} -> {r[3][:20] or '無'} {r[4]}" for r in rows]))
        return

    if text.startswith("/add ") and uid == ADMIN_ID:
        name = text[4:].strip()
        if not name: send_msg(chat_id, "用法：/add 商品名稱"); return
        admin_state[uid] = {"step": "price", "name": name}
        send_msg(chat_id, f"📦 {name}\n\n請輸入價格（數字）：")
        return

    if uid == ADMIN_ID and uid in admin_state:
        step = admin_state[uid]
        if step["step"] == "price":
            try: price = float(text); admin_state[uid] = {"step": "stock", "name": step["name"], "price": price}; send_msg(chat_id, f"💰 ¥{price}\n\n請輸入庫存：")
            except: send_msg(chat_id, "❌ 請輸入數字")
            return
        if step["step"] == "stock":
            try: stock = int(text); admin_state[uid] = {"step": "card", "name": step["name"], "price": step["price"], "stock": stock}; send_msg(chat_id, f"📊 {stock}\n\n請粘貼卡密（每行一組）：")
            except: send_msg(chat_id, "❌ 請輸入整數")
            return
        if step["step"] == "card":
            cards = text.strip()
            if not cards: send_msg(chat_id, "❌ 卡密不能為空"); return
            db_exec("INSERT INTO products (name, price, stock, card) VALUES (?,?,?,?)", (step["name"], step["price"], step["stock"], cards))
            send_msg(chat_id, f"✅ 添加成功！\n\n📦 {step['name']}\n💰 ¥{step['price']}\n📊 {step['stock']} 張")
            del admin_state[uid]
            return

    if text.isdigit():
        pid = int(text); row = db_query("SELECT id, name, price, stock, card FROM products WHERE id=? AND stock>0", (pid,))
        if not row: send_msg(chat_id, "❌ 商品不存在或已售罄"); return
        _, name, price, stock, cards = row
        card_list = [c.strip() for c in cards.split("\n") if c.strip()]
        if not card_list: send_msg(chat_id, "❌ 卡密已耗盡"); return
        card = random.choice(card_list)
        db_exec("UPDATE products SET stock=stock-1, card=? WHERE id=?", ("\n".join(card_list), pid))
        db_exec("INSERT INTO orders (uid, pid, card) VALUES (?,?,?)", (uid, pid, card))
        send_msg(chat_id, f"🎉 購買成功！\n\n📦 {name}\n💰 ¥{price}\n\n🔑 卡密：\n{card}")
        return

    rows = db_query("SELECT id, name, price, stock FROM products WHERE stock>0", one=False)
    send_msg(chat_id, "📦 暫無商品" if not rows else "📦 可購商品：\n\n" + "\n".join([f"{r[0]}. {r[1]} (¥{r[2]})" for r in rows]))

def main():
    init_db()
    print("🤖 TG Card Bot Light 啟動")
    offset = None
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            params = {"timeout": 30, "allowed_updates": "message"}
            if offset: params["offset"] = offset
            resp = requests.get(url, params=params, timeout=35)
            updates = resp.json()
            if updates.get("ok") and updates.get("result"):
                for u in updates["result"]:
                    offset = u["update_id"] + 1
                    try: process_update(u)
                    except Exception as e: print(f"[err] {e}")
            time.sleep(0.2)
        except: time.sleep(5)

if __name__ == "__main__": main()
PYEOF

# 4. 寫入 .env
echo "[4/5] 寫入配置文件..."
cat > /root/tg-card-bot/.env << 'ENVEOF'
BOT_TOKEN=YOUR_BOT_TOKEN_HERE
ADMIN_ID=0
ENVEOF

# 5. 啟動
echo "[5/5] 完成！"
echo ""
echo "=========================================="
echo "下一步："
echo ""
echo "1. 配置："
echo "   nano /root/tg-card-bot/.env"
echo ""
echo "2. 運行："
echo "   cd /root/tg-card-bot"
echo "   nohup python3 bot.py > bot.log 2>&1 &"
echo ""
echo "3. 查看日誌："
echo "   tail -f /root/tg-card-bot/bot.log"
echo ""
echo "4. 添加商品（管理員）："
echo "   /add 會員月卡"
echo "   15"
echo "   10"
echo "   card001"
echo "      card002"
echo "=========================================="
