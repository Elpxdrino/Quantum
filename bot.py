import os
import json
import secrets
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)

# ── State machine stages ──
AWAITING_PASSWORD = 1
ADMIN_AWAITING_USER_ID = 2
ADMIN_AWAITING_BALANCE = 3
ADMIN_AWAITING_MESSAGE = 4

# ── Data file paths ──
DATA_FILE = "data.json"

# ── Admin config ──
ADMIN_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


# ════════════════════════════════════════════
#  Data helpers
# ════════════════════════════════════════════

def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "global_message": ""}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def generate_api_key() -> str:
    chars = string.ascii_letters + string.digits
    return "QE-" + "".join(secrets.choice(chars) for _ in range(24))


def get_or_create_user(data: dict, user_id: str, username: str) -> dict:
    if user_id not in data["users"]:
        data["users"][user_id] = {
            "username": username,
            "api_key": generate_api_key(),
            "password": None,
            "balance": None,
        }
    return data["users"][user_id]


# ════════════════════════════════════════════
#  /start
# ════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    data = load_data()
    u = get_or_create_user(data, uid, user.username or user.first_name)
    save_data(data)

    api_key = u["api_key"]
    has_password = bool(u["password"])

    welcome = (
        f"👋 *Welcome to Quantum Edge AI*\n\n"
        f"Your unique API Key:\n`{api_key}`\n\n"
    )

    if not has_password:
        welcome += (
            "⚠️ *You have not set a password yet.*\n"
            "Use /setpassword to create one. "
            "You'll need it every time you check your balance."
        )
    else:
        welcome += "Use /balance to view your portfolio balance."

    keyboard = [
        [InlineKeyboardButton("💰 Check Balance", callback_data="balance"),
         InlineKeyboardButton("ℹ️ About", callback_data="about")],
        [InlineKeyboardButton("🔑 Set/Change Password", callback_data="setpassword"),
         InlineKeyboardButton("📢 Latest Update", callback_data="update")],
    ]
    await update.message.reply_text(
        welcome,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ════════════════════════════════════════════
#  About
# ════════════════════════════════════════════

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

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    await msg.reply_text(ABOUT_TEXT, parse_mode="Markdown")


# ════════════════════════════════════════════
#  /setpassword  (conversation)
# ════════════════════════════════════════════

async def setpassword_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    if update.callback_query:
        await update.callback_query.answer()
    await msg.reply_text(
        "🔐 Please enter your *new password* (min 6 characters):",
        parse_mode="Markdown",
    )
    return AWAITING_PASSWORD


async def setpassword_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    if len(password) < 6:
        await update.message.reply_text("❌ Password too short. Minimum 6 characters. Try again:")
        return AWAITING_PASSWORD

    uid = str(update.effective_user.id)
    data = load_data()
    data["users"][uid]["password"] = password
    save_data(data)

    await update.message.reply_text(
        "✅ *Password set successfully!*\n\nUse /balance to view your portfolio.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


# ════════════════════════════════════════════
#  /balance  (conversation)
# ════════════════════════════════════════════

async def balance_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    if update.callback_query:
        await update.callback_query.answer()

    uid = str(update.effective_user.id)
    data = load_data()
    u = data["users"].get(uid)

    if not u:
        await msg.reply_text("Please use /start first.")
        return ConversationHandler.END

    if not u["password"]:
        await msg.reply_text(
            "⚠️ You haven't set a password yet. Use /setpassword first."
        )
        return ConversationHandler.END

    await msg.reply_text("🔒 Enter your password to view your balance:")
    return AWAITING_PASSWORD


async def balance_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load_data()
    u = data["users"].get(uid)

    entered = update.message.text.strip()

    if entered != u["password"]:
        await update.message.reply_text("❌ Incorrect password. Access denied.")
        return ConversationHandler.END

    balance = u.get("balance")
    if balance is None:
        bal_text = "_(No balance on record yet)_"
    else:
        bal_text = f"*${balance:,.2f} USD*"

    api_key = u["api_key"]
    await update.message.reply_text(
        f"✅ *Access Granted*\n\n"
        f"👤 Account: `{api_key}`\n"
        f"💰 Current Balance: {bal_text}\n\n"
        f"_Quantum Edge AI — Your capital, our algorithm._",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ════════════════════════════════════════════
#  /update  — global message
# ════════════════════════════════════════════

async def update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    if update.callback_query:
        await update.callback_query.answer()

    data = load_data()
    message = data.get("global_message", "").strip()

    if not message:
        await msg.reply_text(
            "📭 *No update at this time.*\n\nCheck back soon.",
            parse_mode="Markdown",
        )
    else:
        await msg.reply_text(
            f"📢 *Latest Update from Quantum Edge:*\n\n{message}",
            parse_mode="Markdown",
        )


# ════════════════════════════════════════════
#  Admin commands
# ════════════════════════════════════════════

def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID


async def admin_setbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Unauthorized.")
        return ConversationHandler.END

    await update.message.reply_text(
        "👤 Enter the *Telegram User ID* of the user whose balance you want to set:",
        parse_mode="Markdown",
    )
    return ADMIN_AWAITING_USER_ID


async def admin_receive_userid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text.strip()
    data = load_data()

    if uid not in data["users"]:
        await update.message.reply_text(
            f"❌ User `{uid}` not found. Make sure they have started the bot.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    context.user_data["target_uid"] = uid
    uname = data["users"][uid].get("username", uid)
    await update.message.reply_text(
        f"✅ Found user: *{uname}*\n\nEnter the new balance (numbers only, e.g. `12500.00`):",
        parse_mode="Markdown",
    )
    return ADMIN_AWAITING_BALANCE


async def admin_receive_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip().replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Please enter a number.")
        return ADMIN_AWAITING_BALANCE

    uid = context.user_data["target_uid"]
    data = load_data()
    data["users"][uid]["balance"] = amount
    save_data(data)

    uname = data["users"][uid].get("username", uid)
    await update.message.reply_text(
        f"✅ Balance updated!\n👤 User: *{uname}*\n💰 New Balance: *${amount:,.2f} USD*",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def admin_setmessage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Unauthorized.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📝 Enter the *global update message* (send /clear to remove existing message):",
        parse_mode="Markdown",
    )
    return ADMIN_AWAITING_MESSAGE


async def admin_receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "/clear":
        text = ""

    data = load_data()
    data["global_message"] = text
    save_data(data)

    if text:
        await update.message.reply_text(f"✅ Global message updated:\n\n_{text}_", parse_mode="Markdown")
    else:
        await update.message.reply_text("✅ Global message cleared.")

    return ConversationHandler.END


async def admin_listusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    data = load_data()
    users = data["users"]
    if not users:
        await update.message.reply_text("No users yet.")
        return

    lines = ["👥 *Registered Users:*\n"]
    for uid, u in users.items():
        bal = f"${u['balance']:,.2f}" if u.get("balance") is not None else "N/A"
        lines.append(f"• `{uid}` — @{u.get('username','?')} — {bal}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ════════════════════════════════════════════
#  Callback router
# ════════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_cb = query.data

    if data_cb == "about":
        await about(update, context)
    elif data_cb == "update":
        await update_cmd(update, context)


# ════════════════════════════════════════════
#  App entry point
# ════════════════════════════════════════════

def main():
    token = os.environ["BOT_TOKEN"]
    app = Application.builder().token(token).build()

    # Password / balance conversation (user)
    balance_conv = ConversationHandler(
        entry_points=[
            CommandHandler("balance", balance_start),
            CallbackQueryHandler(balance_start, pattern="^balance$"),
        ],
        states={AWAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, balance_check)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Set-password conversation (user)
    setpw_conv = ConversationHandler(
        entry_points=[
            CommandHandler("setpassword", setpassword_start),
            CallbackQueryHandler(setpassword_start, pattern="^setpassword$"),
        ],
        states={AWAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, setpassword_receive)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Admin set-balance conversation
    admin_bal_conv = ConversationHandler(
        entry_points=[CommandHandler("setbalance", admin_setbalance)],
        states={
            ADMIN_AWAITING_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_userid)],
            ADMIN_AWAITING_BALANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_balance)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Admin set-message conversation
    admin_msg_conv = ConversationHandler(
        entry_points=[CommandHandler("setmessage", admin_setmessage)],
        states={ADMIN_AWAITING_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_message)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("update", update_cmd))
    app.add_handler(CommandHandler("listusers", admin_listusers))
    app.add_handler(balance_conv)
    app.add_handler(setpw_conv)
    app.add_handler(admin_bal_conv)
    app.add_handler(admin_msg_conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("✅ Quantum Edge AI Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
