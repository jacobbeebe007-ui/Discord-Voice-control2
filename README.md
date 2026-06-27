# 🎮 Halo Night Bot

A Discord bot built for Halo game nights. Manages voice channel teams, tracks player MMR across sessions, runs matchmaking rolls with map images, and provides a full stat leaderboard system using Halo Reach ranks.

---

## Features

- **Team management** — manually build teams, randomise, or balance by MMR using a snake draft
- **MMR tracking** — import session stats from Excel, update uncapped player ratings with session performance and placement bonuses
- **Halo Reach rank system** — 22 ranks from Recruit to Inheritor with custom server emojis
- **Matchmaking roller** — roll Halo 3 maps, game types and teams with a veto system
- **Stat commands** — leaderboard, player lookup, session breakdown, head-to-head rivals, compare, top stats

---

## Setup

### Requirements

- Python 3.10+
- A Discord bot token ([discord.com/developers](https://discord.com/developers/applications))
- The following packages:

```
discord.py==2.3.2
python-dotenv==1.0.0
audioop-lts==0.2.1
openpyxl==3.1.2
```

Install with:
```bash
pip install -r requirements.txt
```

### Environment

Create a `.env` file in the project root:
```
DISCORD_BOT_TOKEN=your_token_here
GOOGLE_SHEET_XLSX_URL=https://docs.google.com/spreadsheets/d/1O4Ez5uVnxbFDLooKfwPPxQHyFKq-SnX_s1CklwRP-Ik/export?format=xlsx
STATS_REFRESH_INTERVAL_MINUTES=10
```

### Running locally

```bash
python bot.py
```

### Deploying to Railway

1. Push to a GitHub repo
2. Connect the repo to [Railway](https://railway.app)
3. Add `DISCORD_BOT_TOKEN` as an environment variable in Railway
4. Optionally add `GOOGLE_SHEET_XLSX_URL` and `STATS_REFRESH_INTERVAL_MINUTES` to override the default stats source and refresh interval
5. Railway will auto-deploy on every push to `main`

---

## Bot Permissions

The bot requires the following permissions in your Discord server:

- Move Members
- Send Messages
- Embed Links
- Read Message History
- Use Application Commands

Enable the following **Privileged Gateway Intents** in the Discord Developer Portal:
- Server Members Intent
- Message Content Intent

---

## Custom Emojis

The bot uses custom server emojis for the 22 Halo Reach ranks. Upload the following emojis to your server with **exact names**:

| Emoji Name | Rank |
|---|---|
| `000_Recruit` | Recruit |
| `001_Private` | Private |
| `002_Corporal` | Corporal |
| `003_Sergeant` | Sergeant |
| `004_Warrant_Officer` | Warrant Officer |
| `005_Captain` | Captain |
| `006_Major` | Major |
| `007_Lt_Colonel` | Lt. Colonel |
| `008_Commander` | Commander |
| `009_Colonel` | Colonel |
| `010_Brigadier` | Brigadier |
| `011_General` | General |
| `012_Field_Marshall` | Field Marshall |
| `013_Hero` | Hero |
| `014_Legend` | Legend |
| `015_Mythic` | Mythic |
| `016_Noble` | Noble |
| `017_Eclipse` | Eclipse |
| `018_Nova` | Nova |
| `019_Forerunner` | Forerunner |
| `020_Reclaimer` | Reclaimer |
| `021_Inheritor` | Inheritor |

---

## Commands

### Everyone

| Command | Description |
|---|---|
| `/rank` | Check your own current rank, MMR and stats |
| `/mmr_hub` | Button hub for leaderboard, player MMR lookup, compare, rivals, sessions, stats and podium |
| `/matchmaking` | Roll Halo 3 maps, game types and teams — single or two match with veto |
| `/explainmmr` | Explain how MMR, placements, session deltas and ranks work |
| `/help` | List all commands available to you |

### Admin Only

| Command | Description |
|---|---|
| `/teammanager` | Team Manager — manual setup, auto teams, send teams, recall lobby, presets/history, and match setup |
| `/sub [player_out] [player_in]` | Swap two players between active teams |
| `/recall` | Move all voice members back to their mapped lobby channels |
| `/set_lobby` | Map voice channels to lobby destinations for `/recall` |
| `/import_mmr` | Manually refresh MMR from Google Sheets, the repo workbook, or an uploaded backup |
| `/export` | Download the current MMR data as a timestamped JSON backup |
| `/presets` | View and load saved team lineup presets |
| `/history` | Browse the last 10 team configurations |
| `/sync` | Force re-sync slash commands if any are missing |

---

## MMR System

MMR is an uncapped persistent rating. New players start at **1000 MMR** and can keep climbing above the highest rank threshold.

Existing old-scale MMR is migrated with:

```
new_mmr = 1000 + old_mmr * 19
```

That means an old `100` becomes about `2900`, leaving room to keep gaining MMR.

Each new session calculates a performance score from weighted stats:

| Stat | Weight |
|---|---|
| K/D Ratio | 30% |
| Total Points | 25% |
| Obj Time | 25% |
| Assists | 15% |
| Captures | 5% |

Each stat is normalised 0–100 relative to players in that session. If session placement columns from `1st` to `8th` exist, they add a small placement component:

| Placing | Points |
|---|---:|
| 1st | 9 |
| 2nd | 7 |
| 3rd | 5 |
| 4th | 3 |
| 5th-8th | 1 |

```
performance_score = 85% stat_score + 15% placement_score
```

The bot compares the player's performance score to the expected score for their current MMR versus the lobby average. Each session can change MMR by up to **+500** or **-500**.

Players with fewer than 3 sessions are marked as **provisional** with an asterisk `*` and their rank is not yet confirmed.

The rank thresholds now use the 1000+ scale:

| Rank | MMR |
|---|---:|
| Recruit | 1000+ |
| Private | 1100+ |
| Corporal | 1200+ |
| Sergeant | 1290+ |
| Warrant Officer | 1380+ |
| Captain | 1470+ |
| Major | 1560+ |
| Lt. Colonel | 1650+ |
| Commander | 1740+ |
| Colonel | 1830+ |
| Brigadier | 1920+ |
| General | 2010+ |
| Field Marshall | 2100+ |
| Hero | 2190+ |
| Legend | 2280+ |
| Mythic | 2370+ |
| Noble | 2460+ |
| Eclipse | 2550+ |
| Nova | 2640+ |
| Forerunner | 2730+ |
| Reclaimer | 2820+ |
| Inheritor | 2910+ |

Inheritor is the highest rank name, not a maximum MMR.

### Stats Source

The bot refreshes stats automatically every 10 minutes by default. It tries sources in this order:

1. Google Sheet XLSX export from `GOOGLE_SHEET_XLSX_URL`
2. `Collection_of_Stats_across_Halo_Nights.xlsx` committed to the GitHub repo root alongside `bot.py`
3. A Discord `.xlsx` upload when an admin runs `/import_mmr file:<attachment>`

The bot expects the following sheets:
- **`Leaderboard`** — cumulative stats across all sessions (used for player totals and old-score migration)
- **`Session 1`, `Session 2`, ...** — individual session sheets (used for session history and ranks)

Sheets named `Collective` or `Summary` are ignored.

**Updating stats:** Update the Google Sheet first. If the Sheet cannot be fetched, the bot falls back to the committed workbook from GitHub on the next scheduled refresh or `/import_mmr`.

**Manual backup:** Run `/import_mmr` with a `.xlsx` file attached only when both the Google Sheet and repo workbook are unavailable.

---

## Matchmaking

`/matchmaking` supports **Halo 3** maps and game types.

**Single Match mode:**
- Choose number of teams (2–8)
- Choose map pool (standard only or all DLC)
- Rolls one map + game type, posts publicly with map image

**Two Matches mode:**
- Same setup, rolls two matches simultaneously
- Posts both as embeds with map images
- Veto system: each match has a Map veto and a Game Type veto button
- Each veto rerolls that slot once — buttons disable after use
- Lock In confirms the final matches

**Maps included:**

Standard: Construct, Epitaph, Guardian, High Ground, Isolation, Last Resort, Narrows, Sandtrap, Snowbound, The Pit, Valhalla

DLC: Foundry, Rat's Nest, Standoff, Avalanche, Blackout, Ghost Town, Assembly, Citadel, Heretic, Longshore, Orbital, Sandbox

**Game Types:** Slayer, Team Slayer, Capture the Flag, Oddball, King of the Hill, VIP, Territories, Assault, Infection

---

## Data Persistence

All data is saved to JSON files in the bot's working directory:

| File | Contents |
|---|---|
| `mmr_data.json` | All player MMR, stats and session history |
| `lobby_map.json` | Voice channel → lobby mappings |
| `presets.json` | Saved team presets |
| `team_history.json` | Last 10 team configurations |

These persist across redeployments as long as Railway's volume is attached. Use `/export` regularly to keep a backup.

---

## Development

To add a new command:

1. Add `@bot.tree.command(name="...", description="...")` — prefix description with `[Admin]` for admin-only commands
2. Add the `@is_admin()` decorator if admin only
3. Add the error handler to the `@<command>.error` block at the bottom
4. Push to GitHub — Railway redeploys automatically
5. The `/help` command updates itself automatically — no manual changes needed
