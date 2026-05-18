import os
import json
import secrets
import string
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

AWAITING_PASSWORD = 1
ADMIN_AWAITING_USER_ID = 2
ADMIN_AWAITING_BALANCE = 3
ADMIN_AWAITING_MESSAGE = 4

DATA_FILE = "data.json"
ADMIN_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))
DATABASE_URL = os.environ.get("DATABASE_URL")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    """Create tables if they don't exist, then migrate data.json if present."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     TEXT PRIMARY KEY,
                    username    TEXT,
                    api_key     TEXT NOT NULL,
                    password    TEXT,
                    balance     DOUBLE PRECISION
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                );
            """)
            cur.execute("""
                INSERT INTO settings (key, value)
                VALUES ('global_message', '')
                ON CONFLICT (key) DO NOTHING;
            """)
        conn.commit()
    logger.info("Database initialised.")
    migrate_json_if_exists()


def migrate_json_if_exists():
    """One-time import of data.json into Postgres, then rename the file."""
    if not os.path.exists(DATA_FILE):
        return
    logger.info("Found data.json — migrating to Postgres...")
    with open(DATA_FILE, "r") as f:
        data = json.load(f)

    with get_conn() as conn:
        with conn.cursor() as cur:
            for uid, u in data.get("users", {}).items():
                cur.execute("""
                    INSERT INTO users (user_id, username, api_key, password, balance)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE
                        SET username = EXCLUDED.username,
                            api_key  = EXCLUDED.api_key,
                            password = EXCLUDED.password,
                            balance  = EXCLUDED.balance;
                """, (uid, u.get("username"), u["api_key"], u.get("password"), u.get("balance")))

            global_msg = data.get("global_message", "")
            cur.execute("""
                INSERT INTO settings (key, value) VALUES ('global_message', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
            """, (global_msg,))
        conn.commit()

    os.rename(DATA_FILE, DATA_FILE + ".migrated")
    logger.info("Migration complete. data.json renamed to data.json.migrated.")


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def generate_api_key() -> str:
    chars = string.ascii_letters + string.digits
    return "QE-" + "".join(secrets.choice(chars) for _ in range(24))


def get_or_create_user(user_id: str, username: str) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row:
                if row["username"] != username:
                    cur.execute("UPDATE users SET username = %s WHERE user_id = %s", (username, user_id))
                    conn.commit()
                return dict(row)
            api_key = generate_api_key()
            cur.execute("""
                INSERT INTO users (user_id, username, api_key, password, balance)
                VALUES (%s, %s, %s, NULL, NULL)
                RETURNING *;
            """, (user_id, username, api_key))
            row = cur.fetchone()
            conn.commit()
            return dict(row)


def get_user(user_id: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def set_user_password(user_id: str, password: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET password = %s WHERE user_id = %s", (password, user_id))
        conn.commit()


def set_user_balance(user_id: str, balance: float):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET balance = %s WHERE user_id = %s", (balance, user_id))
        conn.commit()


def get_all_users() -> list:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users ORDER BY username")
            return [dict(r) for r in cur.fetchall()]


def find_user(query: str) -> dict | None:
    """Find by user_id or @username."""
    query = query.strip()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (query,))
            row = cur.fetchone()
            if row:
                return dict(row)
            lookup = query.lstrip("@").lower()
            cur.execute("SELECT * FROM users WHERE LOWER(username) = %s", (lookup,))
            row = cur.fetchone()
            return dict(row) if row else None


def get_global_message() -> str:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM settings WHERE key = 'global_message'")
            row = cur.fetchone()
            return row["value"] if row else ""


def set_global_message(text: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO settings (key, value) VALUES ('global_message', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
            """, (text,))
        conn.commit()


# ---------------------------------------------------------------------------
# Bot content
# ---------------------------------------------------------------------------

ABOUT_TEXT = """
🏦 *Quantum Edge Arbitrage Fund*

*Type of Business:*
Proprietary High-Frequency Trading Algorithm

*Business Goal:*
Targeting the Stock & Crypto Markets with advanced AI systems.

Quantum Edge Capital is pleased to present an exclusive, invitation-only investment opportunity in our proprietary High-Frequency Arbitrage Fund.

This fund leverages a custom-built algorithm to exploit micro-price inefficiencies between Irish stock listings and corresponding cryptocurrency asset pairings — a niche market inaccessible to retail platforms and most institutional funds.

_Quantum Edge AI — Precision. Speed. Alpha._
"""


def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = get_or_create_user(str(user.id), user.username or user.first_name)
    welcome = f"👋 *Welcome to Quantum Edge AI*\n\nYour unique API Key:\n`{u['api_key']}`\n\n"
    if not u["password"]:
        welcome += "⚠️ *You have not set a password yet.*\nUse /setpassword to create one."
    else:
        welcome += "Use /balance to view your portfolio balance."
    keyboard = [
        [InlineKeyboardButton("💰 Check Balance", callback_data="balance"),
         InlineKeyboardButton("ℹ️ About", callback_data="about")],
        [InlineKeyboardButton("🔑 Set/Change Password", callback_data="setpassword"),
         InlineKeyboardButton("📢 Latest Update", callback_data="update")],
    ]
    await update.message.reply_text(welcome, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard))


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    await msg.reply_text(ABOUT_TEXT, parse_mode="Markdown")


async def setpassword_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    if update.callback_query:
        await update.callback_query.answer()
    await msg.reply_text("🔐 Enter your *new password* (min 6 characters):", parse_mode="Markdown")
    return AWAITING_PASSWORD


async def setpassword_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    if len(password) < 6:
        await update.message.reply_text("❌ Too short. Minimum 6 characters. Try again:")
        return AWAITING_PASSWORD
    set_user_password(str(update.effective_user.id), password)
    await update.message.reply_text("✅ *Password set!* Use /balance to view your portfolio.", parse_mode="Markdown")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


async def balance_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    if update.callback_query:
        await update.callback_query.answer()
    u = get_user(str(update.effective_user.id))
    if not u:
        await msg.reply_text("Please use /start first.")
        return ConversationHandler.END
    if not u["password"]:
        await msg.reply_text("⚠️ You haven't set a password yet. Use /setpassword first.")
        return ConversationHandler.END
    await msg.reply_text("🔒 Enter your password to view your balance:")
    return AWAITING_PASSWORD


async def balance_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(str(update.effective_user.id))
    if update.message.text.strip() != u["password"]:
        await update.message.reply_text("❌ Incorrect password. Access denied.")
        return ConversationHandler.END
    balance = u.get("balance")
    bal_text = f"*${balance:,.2f} USD*" if balance is not None else "_(No balance on record yet)_"
    await update.message.reply_text(
        f"✅ *Access Granted*\n\n"
        f"👤 Account: `{u['api_key']}`\n"
        f"💰 Current Balance: {bal_text}\n\n"
        f"_Quantum Edge AI — Your capital, our algorithm._",
        parse_mode="Markdown")
    return ConversationHandler.END


async def update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    if update.callback_query:
        await update.callback_query.answer()
    message = get_global_message().strip()
    if not message:
        await msg.reply_text("📭 *No update at this time.*\n\nCheck back soon.", parse_mode="Markdown")
    else:
        await msg.reply_text(f"📢 *Latest Update from Quantum Edge:*\n\n{message}", parse_mode="Markdown")


async def admin_setbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"setbalance called by {update.effective_user.id}, ADMIN_ID={ADMIN_ID}")
    if not is_admin(update):
        await update.message.reply_text("⛔ Unauthorized.")
        return ConversationHandler.END
    users = get_all_users()
    if not users:
        await update.message.reply_text("No users registered yet.")
        return ConversationHandler.END
    context.user_data["user_list"] = users
    lines = ["👥 *Select a user to update balance:*\n",
             "Reply with their *number* or *@username*\n"]
    for i, u in enumerate(users, 1):
        bal = f"${u['balance']:,.2f}" if u.get("balance") is not None else "No balance"
        uname = u.get("username") or u["user_id"]
        lines.append(f"{i}. @{uname} — {bal}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    return ADMIN_AWAITING_USER_ID


async def admin_receive_userid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    users = context.user_data.get("user_list", [])
    found = None
    if text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(users):
            found = users[index]
    if not found:
        found = find_user(text)
    if not found:
        await update.message.reply_text(
            "❌ User not found. Try their number from the list or @username.")
        return ConversationHandler.END
    context.user_data["target_uid"] = found["user_id"]
    uname = found.get("username") or found["user_id"]
    bal_str = f"${found['balance']:,.2f}" if found.get("balance") is not None else "None"
    await update.message.reply_text(
        f"✅ Selected: *@{uname}*\nCurrent balance: *{bal_str}*\n\n"
        f"Enter the new balance (e.g. `12500.00`):",
        parse_mode="Markdown")
    return ADMIN_AWAITING_BALANCE


async def admin_receive_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip().replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Enter a number like `12500.00`:", parse_mode="Markdown")
        return ADMIN_AWAITING_BALANCE
    uid = context.user_data["target_uid"]
    set_user_balance(uid, amount)
    u = get_user(uid)
    uname = u.get("username") or uid
    await update.message.reply_text(
        f"✅ Balance updated!\n👤 *@{uname}*\n💰 New Balance: *${amount:,.2f} USD*",
        parse_mode="Markdown")
    return ConversationHandler.END


async def admin_setmessage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Unauthorized.")
        return ConversationHandler.END
    await update.message.reply_text(
        "📝 Enter the *global update message*.\nSend /clear to remove the existing message:",
        parse_mode="Markdown")
    return ADMIN_AWAITING_MESSAGE


async def admin_receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/clear":
        text = ""
    set_global_message(text)
    if text:
        await update.message.reply_text(f"✅ Global message updated:\n\n_{text}_", parse_mode="Markdown")
    else:
        await update.message.reply_text("✅ Global message cleared.")
    return ConversationHandler.END


async def admin_listusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"listusers called by {update.effective_user.id}, ADMIN_ID={ADMIN_ID}")
    if not is_admin(update):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    users = get_all_users()
    if not users:
        await update.message.reply_text("No users yet.")
        return
    lines = ["👥 *Registered Users:*\n"]
    for i, u in enumerate(users, 1):
        bal = f"${u['balance']:,.2f}" if u.get("balance") is not None else "N/A"
        uname = u.get("username") or u["user_id"]
        lines.append(f"{i}. `{u['user_id']}` — @{uname} — {bal}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "about":
        await about(update, context)
    elif query.data == "update":
        await update_cmd(update, context)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    token = os.environ["BOT_TOKEN"]

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set.")

    init_db()

    app = Application.builder().token(token).build()

    escape_fallbacks = [
        CommandHandler("cancel", cancel),
        CommandHandler("start", start),
        CommandHandler("update", update_cmd),
        CommandHandler("about", about),
        CommandHandler("listusers", admin_listusers),
    ]

    balance_conv = ConversationHandler(
        entry_points=[
            CommandHandler("balance", balance_start),
            CallbackQueryHandler(balance_start, pattern="^balance$"),
        ],
        states={AWAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, balance_check)]},
        fallbacks=escape_fallbacks,
    )
    setpw_conv = ConversationHandler(
        entry_points=[
            CommandHandler("setpassword", setpassword_start),
            CallbackQueryHandler(setpassword_start, pattern="^setpassword$"),
        ],
        states={AWAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, setpassword_receive)]},
        fallbacks=escape_fallbacks,
    )
    admin_bal_conv = ConversationHandler(
        entry_points=[CommandHandler("setbalance", admin_setbalance)],
        states={
            ADMIN_AWAITING_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_userid)],
            ADMIN_AWAITING_BALANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_balance)],
        },
        fallbacks=escape_fallbacks,
    )
    admin_msg_conv = ConversationHandler(
        entry_points=[CommandHandler("setmessage", admin_setmessage)],
        states={ADMIN_AWAITING_MESSAGE: [MessageHandler(filters.TEXT, admin_receive_message)]},
        fallbacks=escape_fallbacks,
    )

    # Conversation handlers registered first
    app.add_handler(balance_conv)
    app.add_handler(setpw_conv)
    app.add_handler(admin_bal_conv)
    app.add_handler(admin_msg_conv)

    # Standalone commands after
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("update", update_cmd))
    app.add_handler(CommandHandler("listusers", admin_listusers))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("✅ Quantum Edge AI Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
