# 🎮 Discord Voice Manager Bot

A bot for moving voice channel members, picking channels, and managing teams.

---

## Commands

| Command | Who | What it does |
|---------|-----|--------------|
| `/set_lobby` | Admin | Interactively map each voice channel to a lobby channel |
| `/recall` | Admin | Move ALL members in every voice channel to their mapped lobby |
| `/joinvc` | Anyone | Dropdown to pick a voice channel to be moved to |
| `/teams` | Admin | Build teams from current voice members, then send them to channels with one button |

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Create a Discord Application
1. Go to https://discord.com/developers/applications
2. Create a new application → go to **Bot** tab → click **Add Bot**
3. Copy the **Token**
4. Under **Privileged Gateway Intents**, enable:
   - **Server Members Intent**
   - **Voice States** (on by default)
   - **Message Content Intent**
5. Under **OAuth2 → URL Generator**, select scopes: `bot`, `applications.commands`
6. Bot permissions: `Move Members`, `Send Messages`, `Use Slash Commands`
7. Use the generated URL to invite the bot to your server

### 3. Run the bot
```bash
export DISCORD_BOT_TOKEN="your-token-here"
python bot.py
```
Or on Windows:
```cmd
set DISCORD_BOT_TOKEN=your-token-here
python bot.py
```

---

## How to Use

### Setting up lobbies (`/set_lobby`)
Run this once as admin. A dropdown appears — pick a voice channel, then pick which lobby it should drain into when `/recall` is used. Repeat for each channel. Settings are saved to `lobby_map.json`.

### Recalling everyone (`/recall`)
Moves ALL members from every mapped voice channel into their assigned lobby at once. Great for ending a game and pulling everyone back together.

### Joining a voice channel (`/joinvc`)
Any member can run this. A dropdown shows all voice channels with current member counts. Selecting one moves the member there (they must already be in a voice channel for the bot to move them).

### Building teams (`/teams`)
1. Run `/teams` — a panel appears showing all members currently in voice
2. Select members from the first dropdown
3. Select their destination channel from the second dropdown
4. Repeat to build more teams
5. Use **📋 Show Teams** to review
6. Press **🚀 Send Teams to Channels** to move everyone at once
