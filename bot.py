#!/usr/bin/env python3
"""
TG Card Bot - Light Version
用于 256MB RAM Alpine VPS，使用 requests + sqlite3（無 async）
"""
import os, time, random, sqlite3, re
import requests

# ============ 配置 ============
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = "/root/tg-card-bot/cards.db"
ADMIN_ONLY = os.getenv("ADMIN_ONLY", "false").lower() == "true"

# ============ 工具函數 ============
def db_exec(sql, args=()):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(sql, args)
    conn.commit()
    conn.close()

def db_query(sql, args=(), one=True):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows[0] if one and rows else rows

def init_db():
    db_exec("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            card TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    db_exec("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER,
            pid INTEGER,
            card TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

def send_msg(chat_id, text, parse_mode=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[send_msg error] {e}")

def escape_md(text):
    return re.sub(r'([_*\[\]()`#\+\-\=\|\{\}<>~])', r'\\\1', str(text))

# ============ 管理員狀態（進程內記憶）===========
admin_state = {}  # uid -> step

# ============ 處理更新 ============
def process_update(update):
    if "message" not in update:
        return
    msg = update["message"]
    text = msg.get("text", "").strip()
    chat_id = msg["chat"]["id"]
    uid = msg["from"]["id"]

    # === /start ===
    if text == "/start":
        send_msg(chat_id,
            "🦀 *TG Card Bot* 已就緒\n\n"
            "直接發數字 ID 購買\n"
            "或發任意文字查看商品列表\n\n"
            "管理員指令：\n"
            "/admin - 商品列表\n"
            "/stock - 庫存\n"
            "/orders - 訂單\n"
            "/add - 添加商品（逐步）", parse_mode="Markdown")
        return

    # === 任意文字 → 列表或購買 ===
    if text == "/cancel":
        admin_state.pop(uid, None)
        send_msg(chat_id, "✅ 已取消")
        return

    if text == "/admin":
        if uid != ADMIN_ID:
            return
        rows = db_query("SELECT id, name, price, stock FROM products", one=False)
        if not rows:
            send_msg(chat_id, "📦 無商品")
        else:
            lines = "\n".join([f"{r[0]}. {r[1]} (¥{r[2]}) x{r[3]}" for r in rows])
            send_msg(chat_id, f"📦 商品列表：\n\n{lines}")
        return

    if text == "/stock":
        if uid != ADMIN_ID:
            return
        rows = db_query("SELECT id, name, stock FROM products", one=False)
        if not rows:
            send_msg(chat_id, "📦 無商品")
        else:
            lines = "\n".join([f"{r[0]}. {r[1]} 剩 {r[2]}" for r in rows])
            send_msg(chat_id, f"📦 庫存：\n\n{lines}")
        return

    if text == "/orders":
        if uid != ADMIN_ID:
            return
        rows = db_query(
            "SELECT o.id, o.uid, p.name, o.card, o.created_at FROM orders o "
            "LEFT JOIN products p ON o.pid = p.id ORDER BY o.id DESC LIMIT 20",
            one=False
        )
        if not rows:
            send_msg(chat_id, "📋 無訂單")
        else:
            lines = "\n".join([f"#{r[0]} uid:{r[1]} {r[2] or '?'} -> {r[3][:20] or '無卡密'} {r[4]}" for r in rows])
            send_msg(chat_id, f"📋 訂單：\n\n{lines}")
        return

    # === /add 逐步添加 ===
    if text.startswith("/add") and uid == ADMIN_ID:
        name = text[4:].strip()
        if not name:
            send_msg(chat_id, "📦 用法：/add 商品名稱\n\n例：/add 會員月卡")
            return
        admin_state[uid] = {"step": "price", "name": name}
        send_msg(chat_id, f"📦 {name}\n\n請輸入價格（USDT 數字）：")
        return

    # === 管理員逐步輸入流程 ===
    if uid == ADMIN_ID and uid in admin_state:
        step = admin_state[uid]
        if step["step"] == "price":
            try:
                price = float(text)
                admin_state[uid] = {"step": "stock", "name": step["name"], "price": price}
                send_msg(chat_id, f"💰 價格 ¥{price}\n\n請輸入庫存數量：")
            except:
                send_msg(chat_id, "❌ 請輸入數字")
            return

        elif step["step"] == "stock":
            try:
                stock = int(text)
                admin_state[uid] = {
                    "step": "card",
                    "name": step["name"],
                    "price": step["price"],
                    "stock": stock
                }
                send_msg(chat_id, f"📊 庫存 {stock}\n\n請粘貼卡密（每行一組）：")
            except:
                send_msg(chat_id, "❌ 請輸入整數")
            return

        elif step["step"] == "card":
            cards = text.strip()
            if not cards:
                send_msg(chat_id, "❌ 卡密不能為空")
                return
            db_exec(
                "INSERT INTO products (name, price, stock, card) VALUES (?,?,?,?)",
                (step["name"], step["price"], step["stock"], cards)
            )
            card_count = len([c for c in cards.split("\n") if c.strip()])
            del admin_state[uid]
            send_msg(chat_id,
                f"✅ 添加成功！\n\n"
                f"📦 {step['name']}\n"
                f"💰 ¥{step['price']}\n"
                f"📊 {step['stock']} 張 / {card_count} 組卡密")
            return

    # === 普通用戶：數字 ID → 購買 ===
    if text.isdigit():
        pid = int(text)
        row = db_query("SELECT id, name, price, stock, card FROM products WHERE id=? AND stock>0", (pid,))
        if not row:
            send_msg(chat_id, "❌ 商品不存在或已售罄")
            return
        _, name, price, stock, cards = row
        card_list = [c.strip() for c in cards.split("\n") if c.strip()]
        if not card_list:
            send_msg(chat_id, "❌ 卡密已耗盡，請聯繫管理員")
            return
        card = random.choice(card_list)
        new_cards = "\n".join(card_list)
        db_exec("UPDATE products SET stock=stock-1, card=? WHERE id=?", (new_cards, pid))
        db_exec("INSERT INTO orders (uid, pid, card) VALUES (?,?,?)", (uid, pid, card))
        send_msg(chat_id,
            f"🎉 *購買成功！*\n\n"
            f"📦 {name}\n"
            f"💰 ¥{price}\n\n"
            f"🔑 卡密：\n`{card}`", parse_mode="Markdown")
        return

    # === 普通用戶：任意文字 → 商品列表 ===
    if not ADMIN_ONLY or uid == ADMIN_ID:
        rows = db_query("SELECT id, name, price, stock FROM products WHERE stock>0", one=False)
        if not rows:
            send_msg(chat_id, "📦 暫無商品")
        else:
            lines = "\n".join([f"{r[0]}. {r[1]} (¥{r[2]}) 剩{r[3]}" for r in rows])
            send_msg(chat_id, f"📦 可購商品：\n\n{lines}")

# ============ 主循環 ============
def main():
    init_db()
    print("🤖 TG Card Bot Light 啟動")
    offset = None
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            params = {"timeout": 30, "allowed_updates": "message"}
            if offset:
                params["offset"] = offset
            resp = requests.get(url, params=params, timeout=35)
            updates = resp.json()
            if updates.get("ok") and updates.get("result"):
                for u in updates["result"]:
                    offset = u["update_id"] + 1
                    try:
                        process_update(u)
                    except Exception as e:
                        print(f"[process error] {e}")
            time.sleep(0.2)
        except requests.exceptions.ReadTimeout:
            continue
        except Exception as e:
            print(f"[loop error] {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
