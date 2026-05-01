#!/usr/bin/env python3
"""
TG Card Bot - Inline Buttons + Manual Confirmation
256MB RAM Alpine VPS，requests + sqlite3
"""
import os, sys, time, random, sqlite3, re, json
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = "/root/tg-card-bot/cards.db"

# stdout flush for nohup
print = lambda *a, **kw: (print(*a, **kw), sys.stdout.flush())

# ============ DB ============
def db_exec(sql, args=()):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute(sql, args)
    conn.commit()
    conn.close()

def db_query(sql, args=(), one=True):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cur = conn.execute(sql, args)
    rows = cur.fetchall()
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
            pay_addr TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    db_exec("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER,
            uname TEXT DEFAULT '',
            pid INTEGER,
            pname TEXT,
            price REAL,
            card TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

# ============ API ============
def api(method, data=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        r = requests.post(url, json=data, timeout=10)
        return r.json()
    except Exception as e:
        print(f"[api error] {e}")
        return None

def send_msg(chat_id, text, reply_markup=None, parse_mode=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    if parse_mode:
        payload["parse_mode"] = parse_mode
    result = api("sendMessage", payload)
    if result and not result.get("ok"):
        print(f"[send_msg failed] {result}")
    return result

def edit_msg(chat_id, msg_id, text, reply_markup=None, parse_mode=None):
    payload = {"chat_id": chat_id, "message_id": msg_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    if parse_mode:
        payload["parse_mode"] = parse_mode
    result = api("editMessageText", payload)
    return result

def answer_cb(query_id, text=None, show_alert=False):
    payload = {"callback_query_id": query_id}
    if text:
        payload["text"] = text
    if show_alert:
        payload["show_alert"] = True
    api("answerCallbackQuery", payload)

# ============ Keyboards ============
def main_menu_kb():
    return {"inline_keyboard": [
        [{"text": "🛒 所有商品", "callback_data": "list_all"}],
        [{"text": "📋 我的訂單", "callback_data": "my_orders"}],
    ]}

def product_list_kb(rows):
    keyboard = []
    for r in rows:
        keyboard.append([{"text": f"🛒 {r[1]} - ¥{r[2]}", "callback_data": f"p_{r[0]}"}])
    keyboard.append([{"text": "◀️ 返回主頁", "callback_data": "home"}])
    return {"inline_keyboard": keyboard}

def product_kb(pid, name, price, stock):
    if stock > 0:
        kb = [[{"text": "💰 立即購買", "callback_data": f"buy_{pid}"}]]
    else:
        kb = [[{"text": "❌ 缺貨", "callback_data": "list_all"}]]
    kb.append([{"text": "◀️ 返回", "callback_data": "list_all"}])
    return {"inline_keyboard": kb}

def confirm_kb(pid, order_id):
    return {"inline_keyboard": [
        [{"text": "✅ 我已付款", "callback_data": f"paid_{order_id}"}],
        [{"text": "❌ 取消", "callback_data": f"cancel_{order_id}"}],
        [{"text": "◀️ 返回", "callback_data": "list_all"}],
    ]}

# ============ Handlers ============
def handle_message(msg):
    text = msg.get("text", "").strip()
    chat_id = msg["chat"]["id"]
    uid = msg["from"]["id"]

    if text == "/start":
        send_msg(chat_id,
            "🦀 *TG Card Store*\n\n"
            "歡迎來到卡密商城\n"
            "點擊下方按鈕開始購物",
            reply_markup=main_menu_kb(),
            parse_mode="Markdown")
        return

    if text == "/admin" and uid == ADMIN_ID:
        rows = db_query("SELECT id, name, price, stock FROM products", one=False)
        if not rows:
            send_msg(chat_id, "📦 無商品")
        else:
            txt = "📦 商品列表：\n\n" + "\n".join([f"{r[0]}. {r[1]} (¥{r[2]}) x{r[3]}" for r in rows])
            send_msg(chat_id, txt)
        return

    if text == "/stock" and uid == ADMIN_ID:
        rows = db_query("SELECT id, name, stock FROM products", one=False)
        if not rows:
            send_msg(chat_id, "📦 無商品")
        else:
            txt = "📦 庫存：\n\n" + "\n".join([f"{r[0]}. {r[1]} 剩 {r[2]}" for r in rows])
            send_msg(chat_id, txt)
        return

    if text == "/orders" and uid == ADMIN_ID:
        rows = db_query(
            "SELECT id, uid, uname, pname, price, status, created_at FROM orders ORDER BY id DESC LIMIT 20",
            one=False
        )
        if not rows:
            send_msg(chat_id, "📋 無訂單")
        else:
            em = {"pending": "⏳", "paid": "✅", "shipped": "📦", "cancelled": "❌", "rejected": "🚫"}
            txt = "📋 訂單：\n\n" + "\n".join([
                f"#{r[0]} {em.get(r[5],'')} {r[3] or '?'} ¥{r[4]} uid:{r[1]} @{r[2]} {r[6]}"
                for r in rows
            ])
            send_msg(chat_id, txt)
        return

    if text.startswith("/add ") and uid == ADMIN_ID:
        name_prod = text[4:].strip()
        if not name_prod:
            send_msg(chat_id, "📦 用法：/add 商品名稱\n例：/add 會員月卡")
            return
        db_exec("INSERT INTO products (name, price, stock, card, pay_addr) VALUES (?,?,?,?,?)",
                 (name_prod, 0, 0, "[待設置]", ""))
        pid = db_query("SELECT last_insert_rowid()")[0]
        send_msg(chat_id,
            f"✅ 創建商品 #{pid}：{name_prod}\n\n"
            f"請繼續設置：\n\n"
            f"`/setprice {pid} 15`\n"
            f"`/setstock {pid} 10`\n"
            f"`/setaddr {pid} TRC20地址`\n"
            f"然後回复卡密內容（每行一組）", parse_mode="Markdown")
        return

    if text.startswith("/setprice ") and uid == ADMIN_ID:
        parts = text[10:].strip().split()
        if len(parts) < 2:
            send_msg(chat_id, "用法：/setprice ID 價格"); return
        pid, price = int(parts[0]), float(parts[1])
        db_exec("UPDATE products SET price=? WHERE id=?", (price, pid))
        send_msg(chat_id, f"✅ #{pid} 價格設為 ¥{price}")
        return

    if text.startswith("/setstock ") and uid == ADMIN_ID:
        parts = text[9:].strip().split()
        if len(parts) < 2:
            send_msg(chat_id, "用法：/setstock ID 數量"); return
        pid, stock = int(parts[0]), int(parts[1])
        db_exec("UPDATE products SET stock=? WHERE id=?", (stock, pid))
        send_msg(chat_id, f"✅ #{pid} 庫存設為 {stock}")
        return

    if text.startswith("/setaddr ") and uid == ADMIN_ID:
        parts = text[8:].strip().split(maxsplit=1)
        if len(parts) < 2:
            send_msg(chat_id, "用法：/setaddr ID TRC20地址"); return
        pid, addr = int(parts[0]), parts[1]
        db_exec("UPDATE products SET pay_addr=? WHERE id=?", (addr, pid))
        send_msg(chat_id, f"✅ #{pid} 收款地址：\n`{addr}`", parse_mode="Markdown")
        return

    # 管理員回复卡密（粘貼內容）
    if uid == ADMIN_ID:
        pending = db_query("SELECT id FROM products WHERE card='[待設置]' ORDER BY id DESC LIMIT 1")
        if pending:
            pid = pending[0]
            db_exec("UPDATE products SET card=? WHERE id=?", (text.strip(), pid))
            send_msg(chat_id, f"✅ #{pid} 卡密已保存")
            return

    if text == "/cancel":
        send_msg(chat_id, "✅ 已取消", reply_markup=main_menu_kb())
        return

    # Default: 商品列表
    rows = db_query("SELECT id, name, price, stock FROM products WHERE price > 0", one=False)
    if not rows:
        send_msg(chat_id, "📦 暫無商品", reply_markup=main_menu_kb())
    else:
        send_msg(chat_id, "🛒 商品列表：", reply_markup=product_list_kb(rows))

def handle_callback(cb):
    data = cb.get("data", "")
    query_id = cb["id"]
    uid = cb["from"]["id"]
    chat_id = cb["message"]["chat"]["id"]
    msg_id = cb["message"]["message_id"]

    if data == "home" or data == "list_all":
        rows = db_query("SELECT id, name, price, stock FROM products WHERE price > 0", one=False)
        if not rows:
            edit_msg(chat_id, msg_id, "📦 暫無商品", reply_markup=main_menu_kb())
        else:
            edit_msg(chat_id, msg_id, "🛒 商品列表：", reply_markup=product_list_kb(rows))
        answer_cb(query_id)
        return

    if data.startswith("p_"):
        pid = int(data[2:])
        row = db_query("SELECT name, price, stock, pay_addr FROM products WHERE id=?", (pid,))
        if not row:
            answer_cb(query_id, "❌ 商品不存在", True); return
        name, price, stock, pay_addr = row
        txt = (f"📦 *{name}*\n\n"
               f"💰 價格：¥{price}\n"
               f"📊 庫存：{stock}")
        edit_msg(chat_id, msg_id, txt,
                 reply_markup=product_kb(pid, name, price, stock),
                 parse_mode="Markdown")
        answer_cb(query_id)
        return

    if data.startswith("buy_"):
        pid = int(data[4:])
        row = db_query("SELECT name, price, stock, pay_addr, card FROM products WHERE id=? AND stock > 0", (pid,))
        if not row:
            answer_cb(query_id, "❌ 庫存不足", True); return
        name, price, stock, pay_addr, card = row

        # 檢查重複訂單
        pending = db_query("SELECT id FROM orders WHERE uid=? AND pid=? AND status='pending'", (uid, pid))
        if pending:
            answer_cb(query_id, "⏳ 你有未完成的訂單，請先完成", True); return

        db_exec("INSERT INTO orders (uid, pid, pname, price, status) VALUES (?,?,?,?,'pending')",
                (uid, pid, name, price))
        order_id = db_query("SELECT last_insert_rowid()")[0]

        if pay_addr and pay_addr != "":
            txt = (f"🛒 *訂單 #{order_id}*\n\n"
                   f"📦 {name}\n"
                   f"💰 ¥{price}\n\n"
                   f"請轉帳至：\n"
                   f"`{pay_addr}`\n\n"
                   f"轉帳後點擊「✅ 我已付款」")
        else:
            txt = (f"🛒 *訂單 #{order_id}*\n\n"
                   f"📦 {name}\n"
                   f"💰 ¥{price}\n\n"
                   f"⚠️  未設置收款地址，請聯繫管理員")

        edit_msg(chat_id, msg_id, txt,
                 reply_markup=confirm_kb(pid, order_id),
                 parse_mode="Markdown")
        answer_cb(query_id)
        return

    if data.startswith("paid_"):
        order_id = int(data[5:])
        row = db_query("SELECT uid, pname, status FROM orders WHERE id=?", (order_id,))
        if not row or row[2] not in ("pending",):
            answer_cb(query_id, "❌ 訂單無效或已處理", True); return
        db_exec("UPDATE orders SET status='paid' WHERE id=?", (order_id,))
        edit_msg(chat_id, msg_id,
            f"✅ 付款通知已發送！\n\n📦 {row[1]}\n\n管理員對帳後自動發貨，請稍候。",
            reply_markup={"inline_keyboard": [[{"text": "◀️ 返回", "callback_data": "list_all"}]]})
        answer_cb(query_id, "已通知管理員")

        # 通知管理員
        send_msg(ADMIN_ID,
            f"🔔 新付款通知 #order{order_id}\n\n"
            f"📦 {row[1]}\n"
            f"👤 uid：{row[0]}\n\n"
            f"/ship {order_id}  發貨\n"
            f"/reject {order_id} 拒絕")
        return

    if data.startswith("cancel_"):
        order_id = int(data[7:])
        db_exec("UPDATE orders SET status='cancelled' WHERE id=?", (order_id,))
        edit_msg(chat_id, msg_id, "❌ 訂單已取消",
                 reply_markup={"inline_keyboard": [[{"text": "◀️ 返回", "callback_data": "list_all"}]]})
        answer_cb(query_id)
        return

    if data == "my_orders":
        rows = db_query("SELECT id, pname, price, status, created_at FROM orders WHERE uid=? ORDER BY id DESC", (uid,), one=False)
        if not rows:
            answer_cb(query_id, "📋 暫無訂單", True); return
        em = {"pending": "⏳待付款", "paid": "✅待發貨", "shipped": "📦已發貨", "cancelled": "❌已取消", "rejected": "🚫已拒絕"}
        txt = "📋 你的訂單：\n\n" + "\n".join([f"#{r[0]} {em.get(r[3],r[3])} {r[1] or '?'} ¥{r[2]}" for r in rows])
        answer_cb(query_id, txt, True)
        return

    # === 管理員發貨 ===
    if data.startswith("ship_") and uid == ADMIN_ID:
        order_id = int(data[5:])
        row = db_query("SELECT uid, pid, pname, status FROM orders WHERE id=?", (order_id,))
        if not row or row[3] not in ("pending", "paid"):
            answer_cb(query_id, "❌ 無效訂單"); return
        prod = db_query("SELECT card, stock FROM products WHERE id=?", (row[1],))
        if not prod or not prod[0].strip() or prod[0] == "[待設置]":
            answer_cb(query_id, "❌ 卡密未設置"); return
        card = random.choice([c.strip() for c in prod[0].split("\n") if c.strip()])
        new_cards = "\n".join([c.strip() for c in prod[0].split("\n") if c.strip() and c.strip() != card])
        db_exec("UPDATE products SET card=?, stock=stock-1 WHERE id=?", (new_cards, row[1]))
        db_exec("UPDATE orders SET status='shipped', card=? WHERE id=?", (card, order_id))
        send_msg(row[0],
            f"📦 *發貨了！*\n\n📦 {row[2]}\n\n🔑 卡密：\n`{card}`",
            parse_mode="Markdown")
        edit_msg(chat_id, msg_id, f"✅ #{order_id} 已發貨", reply_markup={"inline_keyboard": [[{"text": "◀️ 返回", "callback_data": "list_all"}]]})
        answer_cb(query_id)
        return

    if data.startswith("reject_") and uid == ADMIN_ID:
        order_id = int(data[7:])
        db_exec("UPDATE orders SET status='rejected' WHERE id=?", (order_id,))
        row = db_query("SELECT uid, pname FROM orders WHERE id=?", (order_id,))
        if row:
            send_msg(row[0], f"❌ 訂單 #{order_id} {row[1]} 已拒絕，款項將退還。")
        edit_msg(chat_id, msg_id, f"❌ #{order_id} 已拒絕", reply_markup={"inline_keyboard": [[{"text": "◀️ 返回", "callback_data": "list_all"}]]})
        answer_cb(query_id)
        return

    answer_cb(query_id)

# ============ Main Loop ============
def main():
    init_db()
    print(f"🤖 Bot 啟動，ADMIN={ADMIN_ID}")
    offset = None
    while True:
        try:
            params = {"timeout": 30, "allowed_updates": json.dumps(["message", "callback_query"])}
            if offset:
                params["offset"] = offset
            resp = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params=params, timeout=35
            )
            data = resp.json()
            if not data.get("ok"):
                print(f"[api error] {data}")
                time.sleep(5); continue
            updates = data.get("result", [])
            if updates:
                print(f"[收到 {len(updates)} 個更新]")
            for u in updates:
                offset = u["update_id"] + 1
                try:
                    if "callback_query" in u:
                        handle_callback(u["callback_query"])
                    elif "message" in u:
                        handle_message(u["message"])
                except Exception as e:
                    import traceback
                    print(f"[handler error] {e}\n{traceback.format_exc()}")
            time.sleep(0.3)
        except requests.exceptions.ReadTimeout:
            continue
        except Exception as e:
            import traceback
            print(f"[loop error] {e}\n{traceback.format_exc()}")
            time.sleep(5)

if __name__ == "__main__":
    main()
