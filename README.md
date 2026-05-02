# Quantum Edge AI — Telegram Bot

A private investment portal bot for Quantum Edge Arbitrage Fund.

---

## Features

| Feature | Description |
|---|---|
| Auto API Key | Every new user gets a unique `QE-XXXXXXXX` API key on first `/start` |
| Password Protection | Users set their own password; required every time to view balance |
| Admin Balance Control | Admin sets each user's balance via Telegram commands |
| Global Updates | Admin broadcasts a message to anyone who checks `/update` |
| About Page | Full fund description and business profile |

---

## Commands

### User Commands
| Command | What it does |
|---|---|
| `/start` | Register, see your API key, main menu |
| `/about` | View Quantum Edge fund description |
| `/setpassword` | Create or change your balance password |
| `/balance` | Enter password → see your balance |
| `/update` | See latest message from Quantum Edge team |
| `/cancel` | Cancel any in-progress action |

### Admin-Only Commands
| Command | What it does |
|---|---|
| `/setbalance` | Set balance for any user (prompts for user ID then amount) |
| `/setmessage` | Set the global update message (send `/clear` to remove it) |
| `/listusers` | List all registered users and their balances |

---

## Setup Instructions

### Step 1 — Create your bot on Telegram
1. Open Telegram and message **@BotFather**
2. Send `/newbot`
3. Name it: `Quantum Edge AI`
4. Username: something like `quantumedgeai_bot`
5. Copy the **Bot Token** you receive

### Step 2 — Get your Telegram Admin ID
1. Message **@userinfobot** on Telegram
2. It will show your numeric Telegram User ID (e.g. `123456789`)

### Step 3 — Deploy on Render

1. Push all these files to a **GitHub repository**
2. Go to [render.com](https://render.com) and sign in
3. Click **New → Background Worker**
4. Connect your GitHub repo
5. Render will auto-detect `render.yaml`
6. Set the following **Environment Variables** in Render:

| Variable | Value |
|---|---|
| `BOT_TOKEN` | Your token from BotFather |
| `ADMIN_TELEGRAM_ID` | Your numeric Telegram ID |
| `ADMIN_PASSWORD` | (optional, reserved for future use) |

7. Make sure the **Disk** is attached (defined in `render.yaml`) so `data.json` persists between deploys
8. Click **Deploy**

### Step 4 — Test it
- Open Telegram, find your bot by username
- Send `/start` — you'll get your API key
- Use `/setpassword` to create a password
- As admin, use `/setbalance` to add a balance for any user
- Users can then check `/balance` with their password

---

## Data Storage

User data is stored in `data.json` in the project directory. The Render disk mount ensures this file survives redeployments.

Structure:
```json
{
  "users": {
    "123456789": {
      "username": "john",
      "api_key": "QE-AbCdEfGhIjKlMnOpQrStUv",
      "password": "mypassword",
      "balance": 25000.00
    }
  },
  "global_message": "Fund update: Returns are up 12% this quarter."
}
```

---

## Admin Workflow

**To add a user's balance:**
1. Wait for user to `/start` the bot (they register automatically)
2. Run `/listusers` to find their Telegram ID
3. Run `/setbalance` → enter their ID → enter amount

**To post an update:**
- `/setmessage` → type your update text
- To clear: `/setmessage` → send `/clear`

---

*Quantum Edge AI — Precision. Speed. Alpha.*
