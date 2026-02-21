# 🎮 Discord Voice Manager Bot

A Discord bot for managing voice channels — recall members to lobbies, pick channels, and build teams.

---

## 📁 Project Structure

```
discord-bot/          ← root directory (set this in Render)
├── bot.py            ← main bot file
├── requirements.txt  ← dependencies
├── .env.example      ← token template (copy to .env locally)
├── .gitignore        ← keeps .env out of GitHub
└── README.md
```

---

## 🤖 Commands

| Command | Who | Description |
|---------|-----|-------------|
| `/set_lobby` | Admin | Map each voice channel to a lobby destination |
| `/recall` | Admin | Move ALL voice members to their mapped lobby at once |
| `/joinvc` | Anyone | Dropdown to pick a voice channel to be moved to |
| `/teams` | Admin | Build teams from current voice members, dispatch with one button |

---

## 🚀 Deploying to Render via GitHub

### Step 1 — Create your Discord Bot
1. Go to https://discord.com/developers/applications → **New Application**
2. Go to the **Bot** tab → **Add Bot** → copy the **Token**
3. Enable these **Privileged Gateway Intents**:
   - ✅ Server Members Intent
   - ✅ Message Content Intent
4. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Move Members`, `Send Messages`, `Use Slash Commands`
5. Open the generated URL and invite the bot to your server

### Step 2 — Push to GitHub
```bash
git init
git add .
git commit -m "Initial bot commit"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```
> ⚠️ Make sure `.env` is in `.gitignore` — **never push your token to GitHub**

### Step 3 — Deploy on Render
1. Go to https://render.com → **New** → **Background Worker**
2. Connect your GitHub repo
3. Set these fields:
   - **Root Directory**: `discord-bot` (or `.` if the files are at repo root)
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
4. Go to **Environment** tab and add:
   - Key: `DISCORD_BOT_TOKEN`
   - Value: *(paste your bot token)*
5. Click **Create Background Worker** — Render will build and start your bot!

---

## 💻 Running Locally

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd discord-bot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up your token
cp .env.example .env
# Edit .env and paste your token after DISCORD_BOT_TOKEN=

# 4. Run
python bot.py
```

---

## 📝 Notes

- Lobby mappings are saved to `lobby_map.json` on the server disk. On Render's free tier, the disk resets on redeploy — mappings will need to be reconfigured. Upgrade to a paid plan or use a database (e.g. Render PostgreSQL) for persistence.
- Slash commands may take up to 1 hour to appear globally after the first sync.
