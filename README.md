# 🎮 Halo Night Bot

A Discord bot built for Halo game nights. Manages voice channel teams, tracks player MMR across sessions, runs matchmaking rolls with map images, and provides a full stat leaderboard system using Halo Reach ranks.

---

## Features

- **Team management** — manually build teams, randomise, or balance by MMR using a snake draft
- **MMR tracking** — import session stats from Excel, calculate overall MMR from cumulative leaderboard data
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
pytest>=7.0.0
```

Install with:
```bash
pip install -r requirements.txt
```

### Environment

Create a `.env` file in the project root:
```
DISCORD_BOT_TOKEN=your_token_here
```

Optional: set `LOG_LEVEL` to `DEBUG`, `INFO`, `WARNING`, or `ERROR` (default is `INFO`).

### Running locally

```bash
python bot.py
```

### Deploying to Railway

1. Push to a GitHub repo
2. Connect the repo to [Railway](https://railway.app)
3. Add `DISCORD_BOT_TOKEN` as an environment variable in Railway
4. Railway will auto-deploy on every push to `main`

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
| `/mmr [player]` | Full stats, rank history and session breakdown for a player |
| `/leaderboard` | Full MMR leaderboard grouped by Halo Reach rank |
| `/compare [p1] [p2]` | Side by side stat comparison with winners highlighted |
| `/rivals [p1] [p2]` | Head-to-head session history and overall win tally |
| `/stats` | Top performer in every stat category |
| `/session [session] [player]` | A player's stats from a specific session e.g. `Session 1` |
| `/help` | List all commands available to you |

### Admin Only

| Command | Description |
|---|---|
| `/teams` | Team Builder — stage members (Discord user picker, voice/online/offline lists, or **+All in voice**), pick a channel, **Assign**; **More** for history/recall/clear |
| `/sub [player_out] [player_in]` | Swap two players between active teams |
| `/recall` | Move all voice members back to their mapped lobby channels |
| `/set_lobby` | Map voice channels to lobby destinations for `/recall` |
| `/import_mmr` | Upload a session Excel file to update all player MMR and history |
| `/export` | Download the current MMR data as a timestamped JSON backup |
| `/presets` | View and load saved team lineup presets |
| `/history` | Browse the last 10 team configurations |
| `/matchmaking` | Roll Halo 3 maps, game types and teams — single or two match with veto |
| `/orbital_jump` | Post the Orbital Jump approval roster panel (persistent buttons after bot restarts) |
| `/sync` | Force re-sync slash commands if any are missing |

---

## MMR System

MMR is calculated from the **cumulative Leaderboard sheet** in your Excel file using weighted stats:

| Stat | Weight |
|---|---|
| K/D Ratio | 30% |
| Total Points | 25% |
| Obj Time | 25% |
| Assists | 15% |
| Captures | 5% |

Each stat is normalised 0–100 relative to all players in that import, then weighted and summed. The result is an overall MMR between 0 and 100.

Players with fewer than 3 sessions are marked as **provisional** with an asterisk `*` and their rank is not yet confirmed.

### Excel File

Commit `Collection_of_Stats_across_Halo_Nights.xlsx` to the root of your GitHub repo alongside `bot.py`. Railway will include it in the deployment and the bot reads it from disk.

The bot expects the following sheets:
- **`Leaderboard`** — cumulative stats across all sessions (used for overall MMR)
- **`Session 1`, `Session 2`, ...** — individual session sheets (used for session history and ranks)

Sheets named `Collective` or `Summary` are ignored.

**Updating stats:** Edit your Excel file locally, commit and push to GitHub. Railway redeploys automatically and `/import_mmr` will read the updated file.

**Override with upload:** You can also run `/import_mmr` with a file attached to import from that file directly, bypassing the repo file. Useful for testing before committing.

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
| `recall_channels.json` | Saved lobby channel for `/recall` |
| `presets.json` | Saved team presets |
| `team_history.json` | Last 10 team configurations |
| `orbital_jump.json` | Orbital Jump roster text, emoji, and approved names per server |

These persist across redeployments as long as Railway's volume is attached. Use `/export` regularly to keep a backup.

---

## Development

Code layout:

- `bot.py` — bot instance, most slash commands, team builder UI, stats
- `halo_bot/` — shared constants, JSON storage helpers, pure MMR/rank helpers (`pure.py`), and cogs under `halo_bot/cogs/` (matchmaking, orbital jump)

To add a new command:

1. Add `@bot.tree.command(name="...", description="...")` in `bot.py` (or use an `app_commands.Cog` under `halo_bot/cogs/`) — prefix description with `[Admin]` for admin-only commands
2. Add the `@is_admin()` decorator if admin only
3. For commands on `bot.py`, register `cmd.error(_admin_error)` in `HaloBot.setup_hook` (see the `admin_cmd_names` tuple). Cog commands registered there use the same handler.
4. Push to GitHub — Railway redeploys automatically
5. The `/help` command updates itself automatically — no manual changes needed

Run unit tests (no Discord token required for `halo_bot.pure` tests):

```bash
pip install -r requirements.txt
pytest
```

`pytest.ini` sets `pythonpath` so `halo_bot` imports resolve from the repo root.
