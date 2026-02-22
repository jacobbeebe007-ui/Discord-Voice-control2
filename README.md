# 🎮 Discord Voice Control Bot

A Discord bot for managing voice channels during Halo gaming sessions — recall players to lobbies, build teams manually, randomise them, or generate MMR-balanced teams using UNSC rankings derived from your real session stats.

---

## Commands

| Command | Who | Description |
|---|---|---|
| `/teams` | Admin | Open the Team Builder panel |
| `/set_lobby` | Admin | Map voice channels to a lobby destination |
| `/recall` | Admin | Move all voice members to their mapped lobbies |
| `/import_mmr` | Admin | Import player stats from your session Excel file |
| `/leaderboard` | Everyone | View the full UNSC MMR leaderboard |
| `/mmr [player]` | Everyone | Look up a player's MMR, rank, and rating history |
| `/presets` | Admin | View and load saved team presets |
| `/history` | Admin | View past team configurations |

---

## /teams — Team Builder

The main control panel. All features are buttons inside this panel.

### Manual Teams
1. Pick members from dropdown 1️⃣
2. Pick their destination channel from dropdown 2️⃣
3. Click ➕ **Assign to Team**
4. Repeat for each team
5. Click 🚀 **Send Teams** to move everyone

> Players can only be on one team. Reassigning moves them automatically.

### 🎲 Randomise Teams
1. Click 🎲 **Randomise Teams**
2. Pick 2 or more voice channels
3. Click 🎲 **Randomise!** — all players in voice are shuffled evenly and moved instantly

### ⚖️ Balanced Teams (MMR)
1. Click ⚖️ **Balanced Teams**
2. Pick 2 or more voice channels
3. Click ⚖️ **Generate Balanced Teams** — players are distributed using a snake draft based on MMR so teams are as even as possible

### 💾 Save Preset
Saves the current team layout with a name and optional note (e.g. *"6v6 Competitive — sweaty lineup"*). Load presets any time with `/presets`.

### Other Buttons

| Button | What it does |
|---|---|
| 📋 Show Teams | Display current assignments with MMR |
| 🗑️ Clear Teams | Wipe all team assignments |
| 🔁 Recall All to Lobby | Pull everyone back to their mapped lobby |

Team configurations are automatically saved to history whenever you use 🚀 Send Teams, 🎲 Randomise, or ⚖️ Balanced Teams.

---

## /set_lobby — Lobby Mapper

1. Pick one or more **source** channels (recalled FROM) using dropdown 1️⃣
2. Pick the **destination** lobby channel (recalled TO) using dropdown 2️⃣
3. Click 💾 **Save Mapping**

Run `/set_lobby` multiple times to set different channels pointing to different lobbies. Mappings persist across restarts.

---

## /import_mmr — Importing Stats

Upload your Excel file directly in Discord. The bot supports two formats:

**Multi-session file** (recommended) — your `Collection_of_Stats_across_Halo_Nights.xlsx` style with one sheet per session (e.g. Session 1, Session 2...). The bot reads every session sheet, calculates MMR for each independently, and stores the full history per player.

**Leaderboard file** — a single sheet with cumulative stats. Used as a fallback if no session sheets are found.

### Expected Columns (per session sheet)
| Column | Used for |
|---|---|
| Player Name | Player identifier |
| K/D Ratio | 30% of MMR |
| Total Points | 25% of MMR |
| Time in Obj (sec) | 25% of MMR |
| Total Assists | 15% of MMR |
| Captures | 5% of MMR |

MMR is normalised 0–100 within each session so every session is fairly weighted regardless of overall score inflation.

---

## UNSC Rank System

MMR maps to UNSC military ranks:

| MMR | Rank |
|---|---|
| 95–100 | ⭐ Spartan |
| 88–94 | 🔱 Inheritor |
| 80–87 | 💠 Reclaimer |
| 72–79 | 🔷 Forerunner |
| 63–71 | 🟣 Legendary |
| 54–62 | 🟤 Mythic |
| 45–53 | ⬛ Onyx |
| 36–44 | 💎 Diamond |
| 27–35 | 🩶 Platinum |
| 18–26 | 🥇 Gold |
| 10–17 | 🩵 Silver |
| 0–9 | 🟫 Bronze |

---

## /mmr [player] — Player Lookup

Shows a player's current MMR, UNSC rank, leaderboard position, all stats, and their full session-by-session rating history with trend arrows (▲ improved / ▼ dropped / ─ same).

Example:
```
Jacob ⭐ Spartan
MMR: 100.0 | Rank: #1
K/D: 2.24 | Points: 381 | Obj Time: 1057s | Assists: 446 | Captures: 2

📈 Rating History
> ⭐ Session 1: 89.0 MMR (Reclaimer)
> 💠 Session 2: 80.3 MMR (Reclaimer) ▼
> ⭐ Session 3: 97.7 MMR (Inheritor) ▲
> 🔷 Session 4: 79.6 MMR (Reclaimer) ▼
> 🟣 Session 5: 71.5 MMR (Legendary) ▼
```

---

## /presets — Saved Team Presets

View and reload any saved team configuration. Each preset stores:
- The team name
- An optional note
- Which players were assigned to which channel

---

## /history — Team History

The bot automatically saves the last 10 team configurations whenever teams are dispatched or generated. Use `/history` to view or recall any past setup.

---

## Deployment (Railway via GitHub)

### 1. Create your Discord bot
1. Go to https://discord.com/developers/applications → **New Application**
2. Go to **Bot** tab → **Add Bot** → copy the **Token**
3. Enable under **Privileged Gateway Intents**:
   - ✅ Server Members Intent
   - ✅ Message Content Intent
4. Go to **OAuth2 → Redirects** → add `https://localhost` → Save
5. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Move Members`, `Send Messages`, `Use Slash Commands`
6. Open the generated URL and invite the bot to your server

### 2. Push to GitHub
Make sure these files are in your repo:
```
bot.py
requirements.txt
.env.example
.gitignore
README.md
```
> ⚠️ Never commit `.env` — your token must stay out of GitHub

### 3. Deploy on Railway
1. Go to https://railway.app → sign up with GitHub
2. **New Project** → **Deploy from GitHub repo** → select your repo
3. Go to **Variables** tab → add:
   - `DISCORD_BOT_TOKEN` = your bot token
4. Railway auto-detects Python and runs `pip install -r requirements.txt`
5. Set **Start Command** to `python bot.py` under Settings if not auto-detected

Railway's free tier includes $5 credit/month which resets monthly — more than enough for this bot.

---

## Running Locally

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env and paste your token after DISCORD_BOT_TOKEN=
python bot.py
```

---

## Data Storage

| File | Contents | Persists |
|---|---|---|
| `lobby_map.json` | Voice channel → lobby mappings | ✅ Disk |
| `mmr_data.json` | Player MMR, stats, session history | ✅ Disk |
| `presets.json` | Saved team presets with notes | ✅ Disk |
| `team_history.json` | Last 10 team configurations | ✅ Disk |
| Team assignments | Active team session | ❌ Memory only |

> Note: Railway persists files between deploys. If you ever redeploy from scratch, re-upload your stats file with `/import_mmr` to restore MMR data.
